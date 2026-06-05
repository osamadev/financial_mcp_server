import hmac
import json
import logging
import re
import time
from typing import Any, Optional

import httpx
import jwt  # type: ignore[reportMissingImports]
from mcp.server.auth.provider import AccessToken, TokenVerifier  # type: ignore[reportMissingImports]

logger = logging.getLogger(__name__)


class StaticTokenVerifier(TokenVerifier):
    """Simple bearer-token verifier for streamable HTTP deployments."""

    def __init__(self, token: str, client_id: str = "financial-mcp-client") -> None:
        self._token = token
        self._client_id = client_id

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if not token:
            return None
        if not hmac.compare_digest(token, self._token):
            return None
        return AccessToken(
            token=token,
            client_id=self._client_id,
            scopes=["mcp.tools", "mcp.resources"],
        )


class OidcJwtVerifier(TokenVerifier):
    """Validates external OIDC access tokens using issuer, audience, and JWKS."""

    def __init__(
        self,
        issuer_url: str,
        audience: str,
        issuer_urls: list[str] | None = None,
        required_scopes: list[str] | None = None,
        jwks_url: str | None = None,
        http_timeout_seconds: int = 10,
        jwks_cache_ttl_seconds: int = 300,
    ) -> None:
        self.issuer_url = self._normalize_issuer(issuer_url)
        configured_issuers = [self.issuer_url]
        for issuer in issuer_urls or []:
            normalized = self._normalize_issuer(issuer)
            if normalized not in configured_issuers:
                configured_issuers.append(normalized)
        for alias in self._derive_issuer_aliases(self.issuer_url):
            if alias not in configured_issuers:
                configured_issuers.append(alias)
        self.issuer_urls = configured_issuers
        self.audiences = [a.strip() for a in audience.split(",") if a.strip()]
        if not self.audiences:
            raise ValueError("At least one OAuth audience is required.")
        self.required_scopes = required_scopes or []
        self.jwks_url = jwks_url
        self.http_timeout_seconds = http_timeout_seconds
        self.jwks_cache_ttl_seconds = jwks_cache_ttl_seconds

        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_expires_at = 0.0

    @staticmethod
    def _normalize_issuer(issuer: str) -> str:
        return issuer.strip().rstrip("/")

    @staticmethod
    def _derive_issuer_aliases(issuer: str) -> list[str]:
        # Entra tokens can use either login.microsoftonline.com/.../v2.0 or
        # sts.windows.net/<tenant-id>/ for equivalent tenants.
        match = re.match(
            r"^https://login\.microsoftonline\.com/([^/]+)/v2\.0$", issuer.strip().rstrip("/"), re.IGNORECASE
        )
        if not match:
            return []
        tenant_id = match.group(1)
        return [f"https://sts.windows.net/{tenant_id}"]

    @staticmethod
    def _scope_matches(required_scope: str, token_scope: str) -> bool:
        if required_scope == token_scope:
            return True
        if "://" in required_scope:
            short_required = required_scope.rsplit("/", 1)[-1]
            return token_scope == short_required
        return token_scope.endswith(f"/{required_scope}")

    def _expand_scopes_for_middleware(self, scopes: list[str]) -> list[str]:
        expanded = list(scopes)
        for scope in scopes:
            if "://" in scope:
                continue
            for audience in self.audiences:
                if not audience.startswith("api://"):
                    continue
                full_scope = f"{audience.rstrip('/')}/{scope}"
                if full_scope not in expanded:
                    expanded.append(full_scope)
        for required_scope in self.required_scopes:
            if any(self._scope_matches(required_scope, scope) for scope in expanded):
                if required_scope not in expanded:
                    expanded.append(required_scope)
        return expanded

    async def _fetch_openid_configuration(self) -> dict[str, Any]:
        url = f"{self.issuer_url}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=self.http_timeout_seconds) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def _fetch_jwks(self) -> dict[str, Any]:
        if self.jwks_url:
            jwks_endpoint = self.jwks_url
        else:
            metadata = await self._fetch_openid_configuration()
            jwks_endpoint = metadata.get("jwks_uri")
            if not jwks_endpoint:
                raise ValueError("OIDC metadata missing jwks_uri.")

        async with httpx.AsyncClient(timeout=self.http_timeout_seconds) as client:
            response = await client.get(jwks_endpoint)
            response.raise_for_status()
            return response.json()

    async def _get_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._jwks_cache and now < self._jwks_expires_at:
            return self._jwks_cache

        jwks = await self._fetch_jwks()
        self._jwks_cache = jwks
        self._jwks_expires_at = now + self.jwks_cache_ttl_seconds
        return jwks

    @staticmethod
    def _extract_scopes(payload: dict[str, Any]) -> list[str]:
        scopes: list[str] = []
        if isinstance(payload.get("scope"), str):
            scopes.extend([s for s in payload["scope"].split() if s])
        if isinstance(payload.get("scp"), str):
            scopes.extend([s for s in payload["scp"].split() if s and s not in scopes])
        if isinstance(payload.get("roles"), list):
            for role in payload["roles"]:
                if isinstance(role, str) and role not in scopes:
                    scopes.append(role)
        return scopes

    @staticmethod
    def _select_jwk(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
        keys = jwks.get("keys", [])
        if not isinstance(keys, list) or not keys:
            return None
        if kid:
            for key in keys:
                if isinstance(key, dict) and key.get("kid") == kid:
                    return key
        return keys[0] if isinstance(keys[0], dict) else None

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if not token:
            return None

        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")
            alg = unverified_header.get("alg", "RS256")

            jwks = await self._get_jwks()
            jwk = self._select_jwk(jwks, kid)
            if not jwk:
                logger.warning("No matching JWK found for token.")
                return None

            allowed_algs = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
            if alg not in allowed_algs:
                logger.warning("Unsupported JWT algorithm: %s", alg)
                return None

            if alg.startswith("ES"):
                public_key = jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk))
            else:
                public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))

            payload = jwt.decode(
                token,
                public_key,
                algorithms=[alg],
                audience=self.audiences if len(self.audiences) > 1 else self.audiences[0],
                options={"verify_signature": True, "verify_exp": True, "verify_iss": False},
            )

            token_issuer = self._normalize_issuer(str(payload.get("iss", "")))
            if token_issuer not in self.issuer_urls:
                logger.warning(
                    "Token issuer is not allowed. token_iss=%s allowed=%s",
                    token_issuer,
                    self.issuer_urls,
                )
                return None

            scopes = self._extract_scopes(payload)
            for required_scope in self.required_scopes:
                if not any(self._scope_matches(required_scope, scope) for scope in scopes):
                    logger.warning(
                        "Token missing required scope. required=%s token_scopes=%s",
                        required_scope,
                        scopes,
                    )
                    return None

            client_id = (
                payload.get("azp")
                or payload.get("client_id")
                or payload.get("appid")
                or payload.get("sub")
                or "oauth-client"
            )
            return AccessToken(
                token=token,
                client_id=str(client_id),
                scopes=self._expand_scopes_for_middleware(scopes),
                expires_at=payload.get("exp"),
                resource=self.audiences[0],
            )
        except Exception as exc:
            logger.warning(f"OIDC token verification failed: {exc}")
            return None

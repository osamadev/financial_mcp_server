import hmac
import json
import logging
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
            scopes=["mcp:tools", "mcp:resources"],
        )


class OidcJwtVerifier(TokenVerifier):
    """Validates external OIDC access tokens using issuer, audience, and JWKS."""

    def __init__(
        self,
        issuer_url: str,
        audience: str,
        required_scopes: list[str] | None = None,
        jwks_url: str | None = None,
        http_timeout_seconds: int = 10,
        jwks_cache_ttl_seconds: int = 300,
    ) -> None:
        self.issuer_url = issuer_url.rstrip("/")
        self.audiences = [a.strip() for a in audience.split(",") if a.strip()]
        if not self.audiences:
            raise ValueError("At least one OAuth audience is required.")
        self.required_scopes = required_scopes or []
        self.jwks_url = jwks_url
        self.http_timeout_seconds = http_timeout_seconds
        self.jwks_cache_ttl_seconds = jwks_cache_ttl_seconds

        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_expires_at = 0.0

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
                issuer=self.issuer_url,
                options={"verify_signature": True, "verify_exp": True},
            )

            scopes = self._extract_scopes(payload)
            if self.required_scopes and not set(self.required_scopes).issubset(set(scopes)):
                logger.warning("Token missing required scopes.")
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
                scopes=scopes,
                expires_at=payload.get("exp"),
                resource=self.audiences[0],
            )
        except Exception as exc:
            logger.warning(f"OIDC token verification failed: {exc}")
            return None

import hmac
from typing import Optional

from mcp.server.auth.provider import AccessToken, TokenVerifier  # type: ignore[reportMissingImports]


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

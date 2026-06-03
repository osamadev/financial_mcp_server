import asyncio
import json
import time
import unittest

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from services.security import OidcJwtVerifier, StaticTokenVerifier


class AuthSecurityTests(unittest.TestCase):
    def test_static_token_verifier(self):
        verifier = StaticTokenVerifier("static-secret")
        valid = asyncio.run(verifier.verify_token("static-secret"))
        invalid = asyncio.run(verifier.verify_token("wrong"))
        self.assertIsNotNone(valid)
        self.assertIsNone(invalid)

    def test_oidc_verifier_accepts_valid_jwt(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
        jwk["kid"] = "test-key"

        token = jwt.encode(
            {
                "iss": "https://issuer.example.com",
                "aud": "api://financial-mcp",
                "exp": int(time.time()) + 300,
                "iat": int(time.time()) - 1,
                "scope": "mcp:tools mcp:resources",
                "sub": "user-123",
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

        verifier = OidcJwtVerifier(
            issuer_url="https://issuer.example.com",
            audience="api://financial-mcp",
            required_scopes=["mcp:tools"],
            jwks_url="https://issuer.example.com/jwks",
        )

        async def fake_fetch_jwks():
            return {"keys": [jwk]}

        verifier._fetch_jwks = fake_fetch_jwks  # type: ignore[method-assign]

        access_token = asyncio.run(verifier.verify_token(token))
        self.assertIsNotNone(access_token)
        self.assertEqual(access_token.client_id, "user-123")
        self.assertIn("mcp:tools", access_token.scopes)

    def test_oidc_verifier_rejects_missing_required_scope(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
        jwk["kid"] = "test-key"

        token = jwt.encode(
            {
                "iss": "https://issuer.example.com",
                "aud": "api://financial-mcp",
                "exp": int(time.time()) + 300,
                "iat": int(time.time()) - 1,
                "scope": "profile email",
                "sub": "user-123",
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

        verifier = OidcJwtVerifier(
            issuer_url="https://issuer.example.com",
            audience="api://financial-mcp",
            required_scopes=["mcp:tools"],
            jwks_url="https://issuer.example.com/jwks",
        )

        async def fake_fetch_jwks():
            return {"keys": [jwk]}

        verifier._fetch_jwks = fake_fetch_jwks  # type: ignore[method-assign]

        access_token = asyncio.run(verifier.verify_token(token))
        self.assertIsNone(access_token)

    def test_oidc_verifier_accepts_any_configured_audience(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
        jwk["kid"] = "test-key"

        token = jwt.encode(
            {
                "iss": "https://issuer.example.com",
                "aud": "client-guid",
                "exp": int(time.time()) + 300,
                "iat": int(time.time()) - 1,
                "scope": "mcp:tools",
                "sub": "user-456",
            },
            private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

        verifier = OidcJwtVerifier(
            issuer_url="https://issuer.example.com",
            audience="api://financial-mcp,client-guid",
            required_scopes=["mcp:tools"],
            jwks_url="https://issuer.example.com/jwks",
        )

        async def fake_fetch_jwks():
            return {"keys": [jwk]}

        verifier._fetch_jwks = fake_fetch_jwks  # type: ignore[method-assign]

        access_token = asyncio.run(verifier.verify_token(token))
        self.assertIsNotNone(access_token)


if __name__ == "__main__":
    unittest.main()

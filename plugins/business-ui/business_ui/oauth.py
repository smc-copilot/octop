"""Generic OAuth2/OIDC authorization-code + PKCE helpers. Not Casdoor-specific."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

OAUTH_PENDING_TTL = 600


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def new_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def new_state() -> str:
    return secrets.token_urlsafe(32)


def parse_discovery(body: dict[str, Any]) -> dict[str, str]:
    authorize = str(body.get("authorization_endpoint") or "")
    token = str(body.get("token_endpoint") or "")
    revoke = str(body.get("revocation_endpoint") or "")
    if not authorize.startswith("https://") or not token.startswith("https://"):
        raise ValueError("discovery missing authorization_endpoint or token_endpoint")
    out = {"authorize_url": authorize, "token_url": token}
    if revoke.startswith("https://"):
        out["revoke_url"] = revoke
    return out


def build_authorization_url(
    authorize_url: str,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scopes: str,
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": scopes or "openid profile",
        }
    )
    sep = "&" if "?" in authorize_url else "?"
    return f"{authorize_url}{sep}{query}"

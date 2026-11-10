"""Non-redirecting HTTPS client pinned to an approved connection."""

from __future__ import annotations

import json
import ssl
from collections.abc import Mapping
from typing import Any

import httpx

from .security import (
    OUTBOUND_MAX_BYTES,
    OUTBOUND_TIMEOUT_SECONDS,
    UnsafeUrl,
    origin_of,
    resolve_and_authorize,
    validate_https_url_syntax,
)

PROTOCOL = "business-ui.v1"


class AdapterError(Exception):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _headers(token: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {token}",
        "accept": "application/json",
        "content-type": "application/json",
    }


def build_client(*, tls_ca_pem: str | None) -> httpx.Client:
    verify: bool | ssl.SSLContext = True
    if tls_ca_pem:
        verify = ssl.create_default_context(cadata=tls_ca_pem)
    return httpx.Client(
        verify=verify,
        follow_redirects=False,
        timeout=OUTBOUND_TIMEOUT_SECONDS,
        trust_env=False,
        max_redirects=0,
    )


def authorize_url(
    url: str,
    *,
    base_url: str,
    extra_origins: list[str],
    private_exceptions: tuple[Any, ...],
) -> str:
    validate_https_url_syntax(url)
    allowed = {origin_of(base_url), *(origin_of(item) for item in extra_origins)}
    if origin_of(url) not in allowed:
        raise UnsafeUrl("url origin is not on the approved registry")
    resolve_and_authorize(url, private_exceptions=private_exceptions)
    return url


def request_json(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    token: str,
    body: Mapping[str, Any] | None = None,
    base_url: str,
    extra_origins: list[str],
    private_exceptions: tuple[Any, ...],
) -> tuple[int, dict[str, Any] | None, str]:
    authorize_url(
        url,
        base_url=base_url,
        extra_origins=extra_origins,
        private_exceptions=private_exceptions,
    )
    try:
        response = client.request(
            method,
            url,
            headers=_headers(token),
            content=None if body is None else json.dumps(body).encode("utf-8"),
        )
    except httpx.TimeoutException as exc:
        raise AdapterError("timeout", "adapter request timed out", status=504) from exc
    except httpx.ConnectError as exc:
        raise AdapterError("tls_or_connect", "tls or connect failed", status=502) from exc
    except httpx.HTTPError as exc:
        raise AdapterError("upstream", "adapter request failed", status=502) from exc
    if 300 <= response.status_code < 400:
        raise AdapterError("redirect", "redirects are not followed", status=502)
    raw = response.content[: OUTBOUND_MAX_BYTES + 1]
    if len(raw) > OUTBOUND_MAX_BYTES:
        raise AdapterError("too_large", "adapter response too large", status=502)
    text = raw.decode("utf-8", errors="replace")
    parsed: dict[str, Any] | None
    try:
        loaded = json.loads(text) if text else None
        parsed = loaded if isinstance(loaded, dict) else None
    except ValueError:
        parsed = None
    return response.status_code, parsed, text


def handshake_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/v1/handshake"


def classify_unsupported(status: int, body: dict[str, Any] | None, text: str) -> str:
    if body is None:
        snippet = text[:80].replace("\n", " ")
        if "<html" in text.lower() or "<!doctype" in text.lower():
            return "ordinary_website_html"
        if "login" in text.lower():
            return "login_page_not_protocol"
        return f"non_json_http_{status}:{snippet}"
    if body.get("protocol") != PROTOCOL:
        return "incompatible_protocol"
    return "malformed_capability"


def evaluate_handshake(body: dict[str, Any] | None) -> tuple[bool, str | None, list[str]]:
    if not isinstance(body, dict):
        return False, "malformed_capability", []
    if body.get("protocol") != PROTOCOL:
        return False, "incompatible_protocol", []
    if body.get("kind") != "business-ui-adapter":
        return False, "unsupported_service_kind", []
    features = body.get("features")
    if not isinstance(features, dict):
        return False, "malformed_capability", []
    required = ("form_registry", "tickets", "receipts", "interactions")
    missing = [name for name in required if features.get(name) is not True]
    if missing:
        return False, "missing_features:" + ",".join(missing), missing
    for key in ("ticket_path", "redeem_path", "interaction_path", "resolve_path"):
        if not isinstance(body.get(key), str) or not body[key].startswith("/"):
            return False, f"missing_endpoint:{key}", missing
    return True, None, []

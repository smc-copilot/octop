from __future__ import annotations

import socket
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "business-ui"
sys.path.insert(0, str(_PLUGIN_ROOT))

from business_ui.outbound import (  # noqa: E402
    AdapterError,
    authorize_url,
    classify_unsupported,
    evaluate_handshake,
    request_json,
)
from business_ui.security import (  # noqa: E402
    UnsafeUrl,
    parse_exception_list,
    resolve_and_authorize,
    validate_https_url_syntax,
)


def test_rejects_non_https_and_embedded_secrets() -> None:
    with pytest.raises(UnsafeUrl):
        validate_https_url_syntax("http://example.com/v1")
    with pytest.raises(UnsafeUrl):
        validate_https_url_syntax("https://user:pass@example.com/v1")
    with pytest.raises(UnsafeUrl):
        validate_https_url_syntax("https://example.com/v1#frag")


def test_hard_denies_metadata_even_with_allowlist() -> None:
    exceptions = parse_exception_list(["169.254.169.254/32", "169.254.0.0/16"])
    with pytest.raises(UnsafeUrl):
        resolve_and_authorize("https://169.254.169.254/", private_exceptions=exceptions)


def test_loopback_requires_explicit_exception() -> None:
    with pytest.raises(UnsafeUrl):
        resolve_and_authorize("https://127.0.0.1/", private_exceptions=())
    ips = resolve_and_authorize(
        "https://127.0.0.1/",
        private_exceptions=parse_exception_list(["127.0.0.1/32"]),
    )
    assert "127.0.0.1" in ips


def test_html_login_pages_are_unsupported_not_success() -> None:
    reason = classify_unsupported(200, None, "<!doctype html><html>login</html>")
    assert "html" in reason or "login" in reason
    ok, why, _ = evaluate_handshake({"protocol": "something-else", "kind": "website"})
    assert ok is False
    assert why == "incompatible_protocol"


def test_dns_rebinding_to_metadata_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: int, *args: object, **kwargs: object) -> list[tuple]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port))]

    monkeypatch.setattr("business_ui.security.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrl):
        resolve_and_authorize("https://evil.example/", private_exceptions=())


def test_unapproved_origin_is_rejected() -> None:
    exceptions = parse_exception_list(["127.0.0.1/32"])
    with pytest.raises(UnsafeUrl):
        authorize_url(
            "https://127.0.0.1:9/v1/handshake",
            base_url="https://127.0.0.1:8443",
            extra_origins=[],
            private_exceptions=exceptions,
        )


def test_redirect_is_not_followed() -> None:
    client = MagicMock()
    response = MagicMock()
    response.status_code = 302
    response.content = b""
    client.request.return_value = response
    with pytest.raises(AdapterError) as exc:
        request_json(
            client,
            "POST",
            "https://127.0.0.1/v1/handshake",
            token="t",
            body={},
            base_url="https://127.0.0.1",
            extra_origins=[],
            private_exceptions=parse_exception_list(["127.0.0.1/32"]),
        )
    assert exc.value.code == "redirect"

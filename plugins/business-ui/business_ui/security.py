"""HTTPS URL and SSRF policy for adapter/business origins."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Always blocked, even if an admin lists them as private exceptions.
_HARD_DENY_NETWORKS = (
    ipaddress.ip_network("169.254.169.254/32"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fd00:ec2::254/128"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)

_METADATA_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
    }
)

_MAX_URL_LEN = 2048
OUTBOUND_TIMEOUT_SECONDS = 8.0
OUTBOUND_MAX_BYTES = 256_000


class UnsafeUrl(ValueError):
    """URL rejected by policy."""


def _parse_https(url: str) -> tuple[object, str]:
    if not isinstance(url, str) or not url or len(url) > _MAX_URL_LEN:
        raise UnsafeUrl("invalid url")
    if url != url.strip():
        raise UnsafeUrl("invalid url")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UnsafeUrl("only https is allowed")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrl("url credentials are forbidden")
    if parsed.fragment:
        raise UnsafeUrl("url fragments are forbidden")
    host = parsed.hostname
    if not host:
        raise UnsafeUrl("missing hostname")
    normalized = host.lower().rstrip(".")
    if normalized in _METADATA_HOSTS:
        raise UnsafeUrl("metadata hosts are forbidden")
    return parsed, normalized


def parse_allow_entry(raw: str) -> ipaddress._BaseNetwork | str:
    text = (raw or "").strip().lower().rstrip(".")
    if not text:
        raise UnsafeUrl("empty allow entry")
    if "/" in text:
        try:
            return ipaddress.ip_network(text, strict=False)
        except ValueError as exc:
            raise UnsafeUrl("invalid cidr") from exc
    try:
        return ipaddress.ip_network(ipaddress.ip_address(text).exploded, strict=False)
    except ValueError:
        if text in _METADATA_HOSTS:
            raise UnsafeUrl("metadata hosts are forbidden") from None
        return text


def _hard_denied(addr: ipaddress._BaseAddress) -> bool:
    return any(addr in net for net in _HARD_DENY_NETWORKS)


def _needs_exception(addr: ipaddress._BaseAddress) -> bool:
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _allowed_by_exceptions(
    addr: ipaddress._BaseAddress,
    host: str,
    exceptions: tuple[ipaddress._BaseNetwork | str, ...],
) -> bool:
    for item in exceptions:
        if isinstance(item, str):
            if host == item:
                return True
        elif addr in item:
            return True
    return False


def validate_https_url_syntax(url: str) -> str:
    parsed, host = _parse_https(url)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        addr = ipaddress.ip_address(host)
        if _hard_denied(addr):
            raise UnsafeUrl("address is forbidden")
    return url.split("#", 1)[0]


def origin_of(url: str) -> str:
    parsed, host = _parse_https(url)
    port = parsed.port or 443
    return f"https://{host}:{port}" if parsed.port else f"https://{host}"


def same_origin(url: str, base: str) -> bool:
    return origin_of(url) == origin_of(base)


def resolve_and_authorize(
    url: str,
    *,
    private_exceptions: tuple[ipaddress._BaseNetwork | str, ...],
) -> list[str]:
    """Resolve DNS and enforce SSRF policy. Returns resolved IP strings."""
    validate_https_url_syntax(url)
    parsed, host = _parse_https(url)
    port = parsed.port or 443
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrl(f"cannot resolve {host}") from exc
    if not infos:
        raise UnsafeUrl(f"cannot resolve {host}")
    ips: list[str] = []
    for info in infos:
        ip_str = info[4][0]
        addr = ipaddress.ip_address(ip_str)
        if _hard_denied(addr):
            raise UnsafeUrl("resolved address is forbidden")
        if _needs_exception(addr) and not _allowed_by_exceptions(addr, host, private_exceptions):
            raise UnsafeUrl("private or local address is not on the allowlist")
        ips.append(ip_str)
    return ips


def parse_exception_list(raw: list[str] | None) -> tuple[ipaddress._BaseNetwork | str, ...]:
    if not raw:
        return ()
    return tuple(parse_allow_entry(item) for item in raw)

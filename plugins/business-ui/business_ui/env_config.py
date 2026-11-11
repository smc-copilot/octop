"""Parse BUSINESS_UI_* process env into a public connection spec.

Secrets are never taken from environment values. Host ``~/.octop/env`` is
copied into agent shells and MCP stdio (except ``OCTOP_*``), so this module
rejects inline passwords/tokens/client secrets and requires absolute secret
files instead.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .security import (
    UnsafeUrl,
    parse_exception_list,
    resolve_and_authorize,
    validate_https_url_syntax,
)

_PREFIX = "BUSINESS_UI_"
_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]{0,63}$")
_SPLIT = re.compile(r"[\s,]+")
_INLINE_FORBIDDEN_EXACT = frozenset(
    {
        "BUSINESS_UI_SERVICE_SECRET",
        "BUSINESS_UI_SECRET",
        "BUSINESS_UI_OAUTH_CLIENT_SECRET",
        "BUSINESS_UI_PASSWORD",
        "BUSINESS_UI_PAT",
        "BUSINESS_UI_ACCESS_TOKEN",
        "BUSINESS_UI_USER_TOKEN",
        "BUSINESS_UI_REFRESH_TOKEN",
    }
)
_INLINE_FORBIDDEN_SUFFIXES = ("_SECRET", "_PASSWORD", "_TOKEN", "_PAT", "_CREDENTIAL")
_MAX_SECRET_BYTES = 32_000
_ISSUER_RE = re.compile(r"^https://[A-Za-z0-9._:-]+(/[A-Za-z0-9._/-]*)?$")


class EnvConfigError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class EnvConnectionSpec:
    connection_id: str
    display_name: str
    base_url: str
    auth_method: str
    user_auth_method: str
    instance_issuer: str
    operator_user_id: int
    extra_origins: tuple[str, ...]
    private_allow: tuple[str, ...]
    oauth_discovery_url: str | None
    oauth_authorize_url: str | None
    oauth_token_url: str | None
    oauth_revoke_url: str | None
    oauth_client_id: str | None
    oauth_scopes: str | None
    service_secret_file: str
    oauth_client_secret_file: str | None
    tls_ca_file: str | None
    enabled: bool


def _get(env: Mapping[str, str], key: str) -> str:
    return str(env.get(key) or "").strip()


def _split_list(raw: str) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part for part in _SPLIT.split(raw) if part)


def _truthy(raw: str) -> bool:
    return raw.lower() not in {"", "0", "false", "no", "off"}


def _require_abs_file(path_str: str | None, key: str) -> str | None:
    if not path_str:
        return None
    if not Path(path_str).is_absolute():
        raise EnvConfigError("SECRET_REF_INVALID", f"{key} must be an absolute file path")
    return path_str


def reject_inline_secrets(env: Mapping[str, str]) -> None:
    for key, value in env.items():
        if not key.startswith(_PREFIX) or not str(value or "").strip():
            continue
        if key.endswith("_FILE"):
            continue
        if key in _INLINE_FORBIDDEN_EXACT or key.endswith(_INLINE_FORBIDDEN_SUFFIXES):
            raise EnvConfigError(
                "ENV_SECRET_INLINE",
                "BUSINESS_UI_* must not hold passwords, PATs, user tokens, or client/service "
                "secrets; use *_FILE references (host env is visible to shells/MCP)",
            )


def read_protected_file(path_str: str, *, kind: str, allow_world_read: bool = False) -> str:
    if not path_str.strip():
        raise EnvConfigError("SECRET_REF_MISSING", f"{kind} file path is required")
    path = Path(path_str.strip())
    if not path.is_absolute():
        raise EnvConfigError("SECRET_REF_INVALID", f"{kind} must be an absolute file path")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise EnvConfigError("SECRET_REF_MISSING", f"{kind} file not found") from exc
    if not resolved.is_file():
        raise EnvConfigError("SECRET_REF_INVALID", f"{kind} is not a regular file")
    if os.name == "posix":
        mode = resolved.stat().st_mode
        if mode & 0o002:
            raise EnvConfigError("SECRET_REF_INSECURE", f"{kind} must not be world-writable")
        if not allow_world_read and mode & 0o004:
            raise EnvConfigError(
                "SECRET_REF_INSECURE", f"{kind} must not be world-readable (use 0600 or 0640)"
            )
    data = resolved.read_bytes()
    if len(data) > _MAX_SECRET_BYTES:
        raise EnvConfigError("SECRET_REF_INVALID", f"{kind} file is too large")
    try:
        text = data.decode("utf-8").strip("\r\n")
    except UnicodeDecodeError as exc:
        raise EnvConfigError("SECRET_REF_INVALID", f"{kind} file is not UTF-8") from exc
    if not text:
        raise EnvConfigError("SECRET_REF_EMPTY", f"{kind} file is empty")
    return text


def file_sha256(path_str: str) -> str:
    payload = Path(path_str).read_bytes()
    return hashlib.sha256(payload).hexdigest()


def public_fingerprint(fields: Mapping[str, Any]) -> str:
    blob = json.dumps(
        {
            "connection_id": str(fields.get("connection_id") or ""),
            "base_url": str(fields.get("base_url") or "").rstrip("/"),
            "auth_method": str(fields.get("auth_method") or ""),
            "user_auth_method": str(fields.get("user_auth_method") or ""),
            "instance_issuer": str(fields.get("instance_issuer") or "").rstrip("/"),
            "oauth_client_id": str(fields.get("oauth_client_id") or ""),
            "oauth_discovery_url": str(fields.get("oauth_discovery_url") or ""),
            "oauth_authorize_url": str(fields.get("oauth_authorize_url") or ""),
            "oauth_token_url": str(fields.get("oauth_token_url") or ""),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def parse_env_spec(env: Mapping[str, str] | None = None) -> EnvConnectionSpec | None:
    source = env if env is not None else os.environ
    reject_inline_secrets(source)
    base_url = _get(source, "BUSINESS_UI_BASE_URL")
    if not base_url:
        return None
    connection_id = _get(source, "BUSINESS_UI_CONNECTION_ID") or "default"
    if not _ID_RE.match(connection_id):
        raise EnvConfigError("ENV_INVALID", "BUSINESS_UI_CONNECTION_ID is not a stable identifier")
    display_name = _get(source, "BUSINESS_UI_DISPLAY_NAME") or connection_id
    auth_method = _get(source, "BUSINESS_UI_AUTH_METHOD") or "api_token"
    if auth_method not in {"api_token", "authorization_code"}:
        raise EnvConfigError(
            "ENV_INVALID", "BUSINESS_UI_AUTH_METHOD must be api_token or authorization_code"
        )
    user_auth = _get(source, "BUSINESS_UI_USER_AUTH_METHOD") or "oauth2"
    if user_auth not in {"oauth2", "native_login", "personal_access_token"}:
        raise EnvConfigError(
            "ENV_INVALID",
            "BUSINESS_UI_USER_AUTH_METHOD must be oauth2, native_login, or personal_access_token",
        )
    issuer = _get(source, "BUSINESS_UI_INSTANCE_ISSUER").rstrip("/")
    if not issuer or not _ISSUER_RE.match(issuer) or " " in issuer:
        raise EnvConfigError(
            "ENV_INVALID",
            "BUSINESS_UI_INSTANCE_ISSUER must be this Octop https origin (unique per instance)",
        )
    operator_raw = _get(source, "BUSINESS_UI_OPERATOR_USER_ID")
    if not operator_raw.isdigit() or int(operator_raw) <= 0:
        raise EnvConfigError(
            "ENV_INVALID",
            "BUSINESS_UI_OPERATOR_USER_ID must be the positive local admin user_id that owns Host credentials",
        )
    secret_file = _get(source, "BUSINESS_UI_SERVICE_SECRET_FILE")
    if not secret_file:
        raise EnvConfigError(
            "SECRET_REF_MISSING",
            "BUSINESS_UI_SERVICE_SECRET_FILE is required; service authentication is never skipped",
        )
    if not Path(secret_file).is_absolute():
        raise EnvConfigError(
            "SECRET_REF_INVALID", "BUSINESS_UI_SERVICE_SECRET_FILE must be absolute"
        )
    oauth_client_id = _get(source, "BUSINESS_UI_OAUTH_CLIENT_ID") or None
    discovery = _get(source, "BUSINESS_UI_OAUTH_DISCOVERY_URL") or None
    authorize = _get(source, "BUSINESS_UI_OAUTH_AUTHORIZE_URL") or None
    token_url = _get(source, "BUSINESS_UI_OAUTH_TOKEN_URL") or None
    if user_auth == "oauth2" and (
        not oauth_client_id or not (discovery or (authorize and token_url))
    ):
        raise EnvConfigError(
            "OAUTH_UNCONFIGURED",
            "oauth2 requires BUSINESS_UI_OAUTH_CLIENT_ID and discovery or authorize+token URLs",
        )
    extra = _split_list(_get(source, "BUSINESS_UI_EXTRA_ORIGINS"))
    private_allow = _split_list(_get(source, "BUSINESS_UI_PRIVATE_ALLOW"))
    spec = EnvConnectionSpec(
        connection_id=connection_id,
        display_name=display_name[:80],
        base_url=base_url.rstrip("/"),
        auth_method=auth_method,
        user_auth_method=user_auth,
        instance_issuer=issuer,
        operator_user_id=int(operator_raw),
        extra_origins=extra,
        private_allow=private_allow,
        oauth_discovery_url=discovery,
        oauth_authorize_url=authorize,
        oauth_token_url=token_url,
        oauth_revoke_url=_get(source, "BUSINESS_UI_OAUTH_REVOKE_URL") or None,
        oauth_client_id=oauth_client_id,
        oauth_scopes=_get(source, "BUSINESS_UI_OAUTH_SCOPES") or "openid profile",
        service_secret_file=secret_file,
        oauth_client_secret_file=_require_abs_file(
            _get(source, "BUSINESS_UI_OAUTH_CLIENT_SECRET_FILE") or None,
            "BUSINESS_UI_OAUTH_CLIENT_SECRET_FILE",
        ),
        tls_ca_file=_require_abs_file(
            _get(source, "BUSINESS_UI_TLS_CA_FILE") or None, "BUSINESS_UI_TLS_CA_FILE"
        ),
        enabled=_truthy(_get(source, "BUSINESS_UI_ENABLED") or "1"),
    )
    validate_spec_urls(spec)
    return spec


def validate_spec_urls(spec: EnvConnectionSpec) -> None:
    try:
        validate_https_url_syntax(spec.base_url)
        exceptions = parse_exception_list(list(spec.private_allow))
        resolve_and_authorize(spec.base_url, private_exceptions=exceptions)
        issuer_url = (
            spec.instance_issuer
            if spec.instance_issuer.count("/") > 2
            else spec.instance_issuer + "/"
        )
        validate_https_url_syntax(issuer_url)
        for extra in spec.extra_origins:
            validate_https_url_syntax(extra)
            resolve_and_authorize(extra, private_exceptions=exceptions)
        for url in (
            spec.oauth_discovery_url,
            spec.oauth_authorize_url,
            spec.oauth_token_url,
            spec.oauth_revoke_url,
        ):
            if url:
                validate_https_url_syntax(url)
                resolve_and_authorize(url, private_exceptions=exceptions)
    except UnsafeUrl as exc:
        raise EnvConfigError("UNSAFE_URL", str(exc)) from exc


def load_secret_bundle(spec: EnvConnectionSpec) -> dict[str, str]:
    secret = read_protected_file(spec.service_secret_file, kind="service secret")
    bundle: dict[str, str] = {
        "auth_method": spec.auth_method,
        "secret": secret,
        "single_use": "true" if spec.auth_method == "authorization_code" else "",
        "oauth_client_id": spec.oauth_client_id or "",
    }
    if spec.oauth_client_secret_file:
        bundle["oauth_client_secret"] = read_protected_file(
            spec.oauth_client_secret_file, kind="oauth client secret"
        )
    if spec.tls_ca_file:
        bundle["tls_ca_pem"] = read_protected_file(
            spec.tls_ca_file, kind="tls ca", allow_world_read=True
        )
    return bundle


def secret_material_hash(spec: EnvConnectionSpec) -> str:
    parts = [file_sha256(spec.service_secret_file)]
    if spec.oauth_client_secret_file:
        parts.append(file_sha256(spec.oauth_client_secret_file))
    if spec.tls_ca_file:
        parts.append(file_sha256(spec.tls_ca_file))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()

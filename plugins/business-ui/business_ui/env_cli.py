"""Non-chat handshake check from process env + secret files. No Host required."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import PROTOCOL
from .env_config import EnvConfigError, load_secret_bundle, parse_env_spec
from .outbound import (
    AdapterError,
    build_client,
    classify_unsupported,
    evaluate_handshake,
    handshake_url,
    request_json,
)
from .security import parse_exception_list


def run_healthcheck(env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        spec = parse_env_spec(env)
    except EnvConfigError as exc:
        return {"ok": False, "error": exc.code, "detail": exc.message, "stages": []}
    if spec is None:
        return {
            "ok": False,
            "error": "ENV_INACTIVE",
            "detail": "BUSINESS_UI_BASE_URL is unset; nothing to test",
            "stages": [],
        }
    stages: list[dict[str, Any]] = []
    try:
        bundle = load_secret_bundle(spec)
    except EnvConfigError as exc:
        return {"ok": False, "error": exc.code, "detail": exc.message, "stages": stages}
    token = bundle.get("secret") or ""
    if not token:
        return {
            "ok": False,
            "error": "SECRET_REQUIRED",
            "detail": "service secret file produced no token; authentication is not skipped",
            "stages": stages,
        }
    exceptions = parse_exception_list(list(spec.private_allow))
    client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
    try:
        status, body, text = request_json(
            client,
            "POST",
            handshake_url(spec.base_url),
            token=token,
            body={
                "protocol": PROTOCOL,
                "destructive": False,
                "instance_issuer": spec.instance_issuer,
            },
            base_url=spec.base_url,
            extra_origins=list(spec.extra_origins),
            private_exceptions=exceptions,
        )
    except AdapterError as exc:
        stages.append({"name": "reachability_http", "ok": False, "detail": exc.message})
        return {
            "ok": False,
            "error": exc.code,
            "detail": exc.message,
            "stages": stages,
            "connection_id": spec.connection_id,
        }
    finally:
        client.close()
    if status in {401, 403}:
        stages.append({"name": "service_auth", "ok": False, "detail": f"http {status}"})
        return {
            "ok": False,
            "error": "auth_failed",
            "detail": f"http {status}",
            "stages": stages,
            "connection_id": spec.connection_id,
        }
    if status != 200 or body is None:
        reason = classify_unsupported(status, body, text)
        stages.append({"name": "reachability_http", "ok": False, "detail": reason})
        return {
            "ok": False,
            "error": reason,
            "detail": reason,
            "stages": stages,
            "connection_id": spec.connection_id,
        }
    stages.append({"name": "reachability_http", "ok": True, "detail": "http 200 json"})
    stages.append({"name": "service_auth", "ok": True, "detail": "accepted"})
    ok, reason, _missing = evaluate_handshake(body)
    stages.append(
        {
            "name": "version_and_features",
            "ok": ok,
            "detail": "compatible" if ok else (reason or "incompatible"),
        }
    )
    methods = list(((body or {}).get("features") or {}).get("user_auth_methods") or [])
    method_ok = spec.user_auth_method in methods
    stages.append(
        {
            "name": "user_auth_methods",
            "ok": method_ok,
            "detail": f"supported={','.join(str(m) for m in methods)}; configured={spec.user_auth_method}",
        }
    )
    if not ok or not method_ok:
        return {
            "ok": False,
            "error": reason or "user_auth_method_unsupported",
            "detail": reason or "user_auth_method_unsupported",
            "stages": stages,
            "connection_id": spec.connection_id,
            "protocol": PROTOCOL,
        }
    return {
        "ok": True,
        "error": None,
        "detail": "handshake ok (non-destructive; browser embed not evaluated)",
        "stages": stages,
        "connection_id": spec.connection_id,
        "protocol": PROTOCOL,
    }


def public_plan(env: dict[str, str] | None = None) -> dict[str, Any]:
    spec = parse_env_spec(env)
    if spec is None:
        return {"active": False}
    return {
        "active": True,
        "connection_id": spec.connection_id,
        "display_name": spec.display_name,
        "base_url": spec.base_url,
        "auth_method": spec.auth_method,
        "user_auth_method": spec.user_auth_method,
        "instance_issuer": spec.instance_issuer,
        "operator_user_id": spec.operator_user_id,
        "private_allow": list(spec.private_allow),
        "extra_origins": list(spec.extra_origins),
        "oauth_discovery_url": spec.oauth_discovery_url,
        "oauth_authorize_url": spec.oauth_authorize_url,
        "oauth_token_url": spec.oauth_token_url,
        "oauth_client_id": spec.oauth_client_id,
        "service_secret_file": spec.service_secret_file,
        "oauth_client_secret_file": spec.oauth_client_secret_file,
        "tls_ca_file": spec.tls_ca_file,
        "enabled": spec.enabled,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Business UI env health-check (plugin-only; no Dashboard Test button)"
    )
    parser.add_argument("command", choices=("test", "plan"))
    args = parser.parse_args(argv)
    try:
        payload = run_healthcheck() if args.command == "test" else public_plan()
    except EnvConfigError as exc:
        payload = {"ok": False, "error": exc.code, "detail": exc.message}
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    if args.command == "plan":
        return 0
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

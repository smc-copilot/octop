from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.plugins.host_contracts import PluginActionError, PluginActor
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.env_file import SEARCH_ENV_KEYS, overlay_stdio_spec_env
from octop.infra.utils.paths import PathLayout

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "business-ui"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from adapter.app import AdapterState, serve_tls  # noqa: E402
from adapter.certs import write_self_signed  # noqa: E402
from business_ui.env_cli import public_plan, run_healthcheck  # noqa: E402
from business_ui.env_config import (  # noqa: E402
    EnvConfigError,
    parse_env_spec,
    public_fingerprint,
    read_protected_file,
)
from tests.unit.plugins.test_business_ui_actions import (  # noqa: E402
    _activate_oauth,
    _bind,
    _save_fields,
    _scope,
    _users,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="secret file mode bits are POSIX-only")


@pytest.fixture
def services(tmp_path: Path) -> Any:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


@pytest.fixture(autouse=True)
def _clear_business_ui_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("BUSINESS_UI_"):
            monkeypatch.delenv(key, raising=False)


def _write_secret(path: Path, text: str, *, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if os.name == "posix":
        path.chmod(mode)
    return path


def _serve(tmp_path: Path, token: str = "env-service-token") -> tuple[Any, AdapterState, str, int]:
    cert, key, pem = write_self_signed(tmp_path)
    state = AdapterState(token)
    httpd = serve_tls(state, certfile=str(cert), keyfile=str(key), host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    return httpd, state, pem, port


def _env_map(
    tmp_path: Path,
    *,
    port: int,
    admin_id: int,
    pem: str,
    token: str = "env-service-token",
    method: str = "oauth2",
    connection_id: str = "site-prod",
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    secret = _write_secret(tmp_path / "secrets" / "service.token", token)
    client_secret = _write_secret(tmp_path / "secrets" / "oauth-client.secret", "bui-secret")
    ca = tmp_path / "secrets" / "adapter-ca.pem"
    ca.write_text(pem, encoding="utf-8")
    if os.name == "posix":
        ca.chmod(0o644)
    origin = f"https://127.0.0.1:{port}"
    values = {
        "BUSINESS_UI_CONNECTION_ID": connection_id,
        "BUSINESS_UI_DISPLAY_NAME": "Env Adapter",
        "BUSINESS_UI_INSTANCE_ISSUER": "https://127.0.0.1",
        "BUSINESS_UI_OPERATOR_USER_ID": str(admin_id),
        "BUSINESS_UI_BASE_URL": origin,
        "BUSINESS_UI_AUTH_METHOD": "api_token",
        "BUSINESS_UI_USER_AUTH_METHOD": method,
        "BUSINESS_UI_PRIVATE_ALLOW": "127.0.0.1/32",
        "BUSINESS_UI_ENABLED": "1",
        "BUSINESS_UI_OAUTH_DISCOVERY_URL": origin + "/.well-known/oauth-authorization-server",
        "BUSINESS_UI_OAUTH_CLIENT_ID": "bui-client",
        "BUSINESS_UI_OAUTH_SCOPES": "openid profile",
        "BUSINESS_UI_SERVICE_SECRET_FILE": str(secret),
        "BUSINESS_UI_OAUTH_CLIENT_SECRET_FILE": str(client_secret),
        "BUSINESS_UI_TLS_CA_FILE": str(ca),
    }
    if extra:
        values.update(extra)
    return values


def _apply_env(monkeypatch: pytest.MonkeyPatch, values: dict[str, str]) -> None:
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_parse_env_inactive_without_base_url() -> None:
    assert parse_env_spec({}) is None


def test_rejects_inline_secrets_and_missing_file_ref() -> None:
    with pytest.raises(EnvConfigError) as exc:
        parse_env_spec(
            {
                "BUSINESS_UI_BASE_URL": "https://adapter.example.com",
                "BUSINESS_UI_INSTANCE_ISSUER": "https://octop.example.com",
                "BUSINESS_UI_OPERATOR_USER_ID": "1",
                "BUSINESS_UI_SERVICE_SECRET": "inline-token",
                "BUSINESS_UI_USER_AUTH_METHOD": "native_login",
            }
        )
    assert exc.value.code == "ENV_SECRET_INLINE"
    with pytest.raises(EnvConfigError) as exc:
        parse_env_spec(
            {
                "BUSINESS_UI_BASE_URL": "https://127.0.0.1",
                "BUSINESS_UI_PRIVATE_ALLOW": "127.0.0.1/32",
                "BUSINESS_UI_INSTANCE_ISSUER": "https://octop.example.com",
                "BUSINESS_UI_OPERATOR_USER_ID": "1",
                "BUSINESS_UI_USER_AUTH_METHOD": "native_login",
            }
        )
    assert exc.value.code == "SECRET_REF_MISSING"


def test_ssrf_rejects_http_and_metadata_even_with_allowlist(tmp_path: Path) -> None:
    secret = _write_secret(tmp_path / "svc.token", "tok")
    base = {
        "BUSINESS_UI_INSTANCE_ISSUER": "https://octop.example.com",
        "BUSINESS_UI_OPERATOR_USER_ID": "1",
        "BUSINESS_UI_SERVICE_SECRET_FILE": str(secret),
        "BUSINESS_UI_USER_AUTH_METHOD": "native_login",
    }
    with pytest.raises(EnvConfigError) as exc:
        parse_env_spec({**base, "BUSINESS_UI_BASE_URL": "http://adapter.example.com"})
    assert exc.value.code == "UNSAFE_URL"
    with pytest.raises(EnvConfigError) as exc:
        parse_env_spec(
            {
                **base,
                "BUSINESS_UI_BASE_URL": "https://169.254.169.254/",
                "BUSINESS_UI_PRIVATE_ALLOW": "169.254.169.254/32",
            }
        )
    assert exc.value.code == "UNSAFE_URL"
    with pytest.raises(EnvConfigError) as exc:
        parse_env_spec({**base, "BUSINESS_UI_BASE_URL": "https://127.0.0.1/"})
    assert exc.value.code == "UNSAFE_URL"


def test_loopback_requires_explicit_allowlist(tmp_path: Path) -> None:
    secret = _write_secret(tmp_path / "svc.token", "tok")
    spec = parse_env_spec(
        {
            "BUSINESS_UI_BASE_URL": "https://127.0.0.1:8443",
            "BUSINESS_UI_INSTANCE_ISSUER": "https://octop.example.com",
            "BUSINESS_UI_OPERATOR_USER_ID": "1",
            "BUSINESS_UI_SERVICE_SECRET_FILE": str(secret),
            "BUSINESS_UI_USER_AUTH_METHOD": "native_login",
            "BUSINESS_UI_PRIVATE_ALLOW": "127.0.0.1/32",
        }
    )
    assert spec is not None
    assert spec.connection_id == "default"


@posix_only
def test_secret_file_rejects_insecure_permissions(tmp_path: Path) -> None:
    world_read = tmp_path / "open.token"
    world_read.write_text("tok", encoding="utf-8")
    world_read.chmod(0o644)
    with pytest.raises(EnvConfigError) as exc:
        read_protected_file(str(world_read), kind="service secret")
    assert exc.value.code == "SECRET_REF_INSECURE"
    relative = Path("relative.token")
    with pytest.raises(EnvConfigError) as exc:
        read_protected_file(str(relative), kind="service secret")
    assert exc.value.code == "SECRET_REF_INVALID"
    missing = tmp_path / "missing.token"
    with pytest.raises(EnvConfigError) as exc:
        read_protected_file(str(missing), kind="service secret")
    assert exc.value.code == "SECRET_REF_MISSING"


def test_stdio_overlay_copies_business_ui_keys_not_octop() -> None:
    overlaid = overlay_stdio_spec_env(
        {"transport": "stdio", "command": "mcp", "env": {}},
        {
            "BUSINESS_UI_BASE_URL": "https://adapter.example.com",
            "BUSINESS_UI_SERVICE_SECRET": "must-not-be-used",
            "OCTOP_HOME": "/hidden",
            "HOME": "/home/octop",
        },
    )
    env = overlaid["env"]
    assert env["BUSINESS_UI_BASE_URL"] == "https://adapter.example.com"
    assert "OCTOP_HOME" not in env
    assert "HOME" not in env
    assert "BUSINESS_UI_" not in "".join(SEARCH_ENV_KEYS)


def test_public_plan_omits_secret_material(tmp_path: Path) -> None:
    secret = _write_secret(tmp_path / "svc.token", "super-secret-token")
    env = {
        "BUSINESS_UI_BASE_URL": "https://127.0.0.1:8443",
        "BUSINESS_UI_PRIVATE_ALLOW": "127.0.0.1/32",
        "BUSINESS_UI_INSTANCE_ISSUER": "https://octop.example.com",
        "BUSINESS_UI_OPERATOR_USER_ID": "2",
        "BUSINESS_UI_SERVICE_SECRET_FILE": str(secret),
        "BUSINESS_UI_USER_AUTH_METHOD": "native_login",
        "BUSINESS_UI_CONNECTION_ID": "site-a",
    }
    plan = public_plan(env)
    blob = str(plan)
    assert "super-secret-token" not in blob
    assert plan["connection_id"] == "site-a"
    assert plan["service_secret_file"] == str(secret)


@pytest.mark.asyncio
async def test_env_bootstrap_list_and_no_secret_disclosure(
    services: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    httpd, _state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, user_id = _users(services)
    try:
        _apply_env(monkeypatch, _env_map(tmp_path, port=port, admin_id=admin_id, pem=pem))
        listed = await facade.invoke_action("connections.list", PluginActor(admin_id, True), {})
        assert listed["env_sync_error"] is None
        assert listed["env_managed_ids"] == ["site-prod"]
        row = listed["connections"][0]
        assert row["managed_by"] == "env"
        assert row["connection_id"] == "site-prod"
        assert row["user_auth_method"] == "oauth2"
        assert row["secret_configured"] is True
        blob = str(listed) + str(await facade.get_record("connections", "site-prod"))
        assert "env-service-token" not in blob
        assert "bui-secret" not in blob
        user_list = await facade.invoke_action("connections.list", PluginActor(user_id, False), {})
        assert user_list["env_sync_error"] is None
        assert user_list["connections"][0]["activation_status"] == "inactive"
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_env_precedence_blocks_chat_duplicate_and_reload_invalidates(
    services: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    httpd, _state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, user_id = _users(services)
    origin = f"https://127.0.0.1:{port}"
    try:
        _apply_env(monkeypatch, _env_map(tmp_path, port=port, admin_id=admin_id, pem=pem))
        listed = await facade.invoke_action("connections.list", PluginActor(admin_id, True), {})
        assert listed["connections"][0]["managed_by"] == "env"
        with pytest.raises(PluginActionError) as exc:
            await facade.invoke_action(
                "connections.save",
                PluginActor(admin_id, True),
                _save_fields(port, pem, connection_id="site-prod"),
            )
        assert exc.value.code == "ENV_MANAGED"
        with pytest.raises(PluginActionError) as exc:
            await facade.invoke_action(
                "connections.save",
                PluginActor(admin_id, True),
                _save_fields(port, pem, display_name="dup"),
            )
        assert exc.value.code == "ENV_MANAGED"
        with pytest.raises(PluginActionError) as exc:
            await facade.invoke_action(
                "connections.delete",
                PluginActor(admin_id, True),
                {"connection_id": "site-prod"},
            )
        assert exc.value.code == "ENV_MANAGED"
        agent_id, thread_id = _scope(services, user_id, "env-oauth")
        actor = PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id)
        await _activate_oauth(facade, actor, "site-prod", pem)
        active = await facade.invoke_action("connections.list", actor, {})
        assert active["connections"][0]["activation_status"] == "active"
        monkeypatch.setenv("BUSINESS_UI_USER_AUTH_METHOD", "native_login")
        reloaded = await facade.invoke_action("connections.list", actor, {})
        assert reloaded["connections"][0]["user_auth_method"] == "native_login"
        assert reloaded["connections"][0]["activation_status"] == "inactive"
        activation = await facade.get_record("activations", f"u{user_id}-site-prod")
        assert activation is not None
        assert activation.payload.get("status") == "stale_config"
        with pytest.raises(PluginActionError) as claim_exc:
            await facade.invoke_action(
                "interactions.claim",
                actor,
                {
                    "connection_id": "site-prod",
                    "form_ref": "generic.request.edit",
                    "call_id": "call-stale1",
                    "document_type": "generic_request",
                    "schema_version": "1",
                },
            )
        assert claim_exc.value.code == "ACTIVATION_REQUIRED"
        first_fp = public_fingerprint(
            {
                "connection_id": "site-prod",
                "base_url": origin,
                "auth_method": "api_token",
                "user_auth_method": "oauth2",
                "instance_issuer": "https://127.0.0.1",
                "oauth_client_id": "bui-client",
                "oauth_discovery_url": origin + "/.well-known/oauth-authorization-server",
                "oauth_authorize_url": "",
                "oauth_token_url": "",
            }
        )
        record = await facade.get_record("connections", "site-prod")
        assert record is not None
        assert record.payload["config_fingerprint"] != first_fp
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_missing_secret_file_fails_closed_without_skipping_auth(
    services: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    facade = _bind(services)
    admin_id, _user_id = _users(services)
    monkeypatch.setenv("BUSINESS_UI_BASE_URL", "https://127.0.0.1")
    monkeypatch.setenv("BUSINESS_UI_PRIVATE_ALLOW", "127.0.0.1/32")
    monkeypatch.setenv("BUSINESS_UI_INSTANCE_ISSUER", "https://octop.example.com")
    monkeypatch.setenv("BUSINESS_UI_OPERATOR_USER_ID", str(admin_id))
    monkeypatch.setenv("BUSINESS_UI_USER_AUTH_METHOD", "native_login")
    monkeypatch.setenv("BUSINESS_UI_SERVICE_SECRET_FILE", str(tmp_path / "no-such.token"))
    listed = await facade.invoke_action("connections.list", PluginActor(admin_id, True), {})
    assert listed["connections"] == []
    assert listed["env_sync_error"]
    assert "SECRET_REF" in listed["env_sync_error"]
    assert listed["env_managed_ids"] == []


@pytest.mark.asyncio
async def test_issuer_conflict_fails_closed(
    services: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    httpd, _state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, _user_id = _users(services)
    try:
        await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem, display_name="chat"),
        )
        values = _env_map(
            tmp_path, port=port, admin_id=admin_id, pem=pem, connection_id="env-other"
        )
        values["BUSINESS_UI_INSTANCE_ISSUER"] = "https://other.example.com"
        _apply_env(monkeypatch, values)
        listed = await facade.invoke_action("connections.list", PluginActor(admin_id, True), {})
        assert "INSTANCE_ISSUER_CONFLICT" in (listed["env_sync_error"] or "")
        ids = {row["connection_id"] for row in listed["connections"]}
        assert "env-other" not in ids
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_auth_isolation_and_handshake_method_validation(
    services: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    httpd, state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, user_id = _users(services)
    other = services.user_repo.create(username="bui-other", role="user")
    try:
        _apply_env(monkeypatch, _env_map(tmp_path, port=port, admin_id=admin_id, pem=pem))
        await facade.invoke_action("connections.list", PluginActor(admin_id, True), {})
        agent_a, thread_a = _scope(services, user_id, "iso-a")
        actor_a = PluginActor(user_id, False, agent_id=agent_a, thread_id=thread_a)
        await _activate_oauth(facade, actor_a, "site-prod", pem)
        agent_b, thread_b = _scope(services, other, "iso-b")
        actor_b = PluginActor(other, False, agent_id=agent_b, thread_id=thread_b)
        listed_b = await facade.invoke_action("connections.list", actor_b, {})
        assert listed_b["connections"][0]["activation_status"] == "inactive"
        with pytest.raises(PluginActionError) as exc:
            await facade.invoke_action(
                "interactions.claim",
                actor_b,
                {
                    "connection_id": "site-prod",
                    "form_ref": "generic.request.edit",
                    "call_id": "call-bbbbbbbb",
                    "document_type": "generic_request",
                    "schema_version": "1",
                },
            )
        assert exc.value.code == "ACTIVATION_REQUIRED"
        tested = await facade.invoke_action(
            "connections.test",
            PluginActor(admin_id, True),
            {"connection_id": "site-prod"},
        )
        assert tested["ok"] is True
        assert any(
            stage["name"] == "user_auth_methods" and stage["ok"] for stage in tested["stages"]
        )
        state.supported_user_auth_methods = ["oauth2"]
        monkeypatch.setenv("BUSINESS_UI_USER_AUTH_METHOD", "personal_access_token")
        listed = await facade.invoke_action("connections.list", PluginActor(admin_id, True), {})
        assert listed["connections"][0]["user_auth_method"] == "personal_access_token"
        tested_pat = await facade.invoke_action(
            "connections.test",
            PluginActor(admin_id, True),
            {"connection_id": "site-prod"},
        )
        assert tested_pat["ok"] is False
        assert tested_pat["unsupported_reason"] == "user_auth_method_unsupported"
        cli = run_healthcheck(dict(os.environ))
        assert cli["ok"] is False
        assert cli["error"] == "user_auth_method_unsupported"
        assert "env-service-token" not in str(cli)
        assert "bui-secret" not in str(cli)
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_cli_healthcheck_ok_and_does_not_need_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    httpd, _state, pem, port = _serve(tmp_path)
    try:
        values = _env_map(tmp_path, port=port, admin_id=1, pem=pem)
        _apply_env(monkeypatch, values)
        result = run_healthcheck(dict(os.environ))
        assert result["ok"] is True
        assert result["connection_id"] == "site-prod"
        assert "env-service-token" not in str(result)
        names = [stage["name"] for stage in result["stages"]]
        assert "user_auth_methods" in names
    finally:
        httpd.shutdown()


def test_relative_secret_ref_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(EnvConfigError) as exc:
        parse_env_spec(
            {
                "BUSINESS_UI_BASE_URL": "https://127.0.0.1",
                "BUSINESS_UI_PRIVATE_ALLOW": "127.0.0.1/32",
                "BUSINESS_UI_INSTANCE_ISSUER": "https://octop.example.com",
                "BUSINESS_UI_OPERATOR_USER_ID": "1",
                "BUSINESS_UI_USER_AUTH_METHOD": "native_login",
                "BUSINESS_UI_SERVICE_SECRET_FILE": "secrets/service.token",
            }
        )
    assert exc.value.code == "SECRET_REF_INVALID"
    from business_ui.env_config import load_secret_bundle

    spec = parse_env_spec(
        {
            "BUSINESS_UI_BASE_URL": "https://127.0.0.1",
            "BUSINESS_UI_PRIVATE_ALLOW": "127.0.0.1/32",
            "BUSINESS_UI_INSTANCE_ISSUER": "https://octop.example.com",
            "BUSINESS_UI_OPERATOR_USER_ID": "1",
            "BUSINESS_UI_USER_AUTH_METHOD": "native_login",
            "BUSINESS_UI_SERVICE_SECRET_FILE": str(tmp_path / "missing.token"),
        }
    )
    assert spec is not None
    with pytest.raises(EnvConfigError) as load_exc:
        load_secret_bundle(spec)
    assert load_exc.value.code == "SECRET_REF_MISSING"

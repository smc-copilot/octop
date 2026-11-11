from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.plugins.host_contracts import PluginActionError, PluginActor
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "business-ui"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from adapter.app import AdapterState, serve_tls  # noqa: E402
from adapter.certs import write_self_signed  # noqa: E402
from tests.unit.plugins.test_business_ui_actions import (  # noqa: E402
    _activate_oauth,
    _bind,
    _browser_approve,
    _save_fields,
    _scope,
    _users,
)


@pytest.fixture
def services(tmp_path: Path) -> Any:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


def _serve(tmp_path: Path, token: str = "tok") -> tuple[Any, AdapterState, str, int]:
    cert, key, pem = write_self_signed(tmp_path)
    state = AdapterState(token)
    httpd = serve_tls(state, certfile=str(cert), keyfile=str(key), host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    return httpd, state, pem, port


@pytest.mark.asyncio
async def test_oauth2_pkce_happy_path_and_replay(services: Any, tmp_path: Path) -> None:
    httpd, state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, user_id = _users(services)
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem),
        )
        agent_id, thread_id = _scope(services, user_id, "oauth")
        actor = PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id)
        started = await _activate_oauth(facade, actor, saved["connection_id"], pem)
        listed = await facade.invoke_action("connections.list", actor, {})
        row = listed["connections"][0]
        assert row["activation_status"] == "active"
        assert row["user_auth_method"] == "oauth2"
        blob = str(listed) + str(await facade.get_record("connections", saved["connection_id"]))
        pending = await facade.get_record("oauth_pending", started["state"])
        assert pending is not None
        blob += str(pending.payload)
        activation = await facade.get_record("activations", f"u{user_id}-{saved['connection_id']}")
        assert activation is not None
        blob += str(activation.payload)
        assert "bui-secret" not in blob
        assert "reusable-token" not in blob
        assert "demo-pass" not in blob
        assert "verifier" not in pending.payload
        assert pending.payload.get("verifier_credential_id")
        assert "access_token" not in activation.payload
        with pytest.raises(PluginActionError) as replay:
            await facade.invoke_action("activations.complete", actor, {"state": started["state"]})
        assert replay.value.code == "REPLAY"
        claimed = await facade.invoke_action(
            "interactions.claim",
            actor,
            {
                "call_id": "call-oauthok01",
                "connection_id": saved["connection_id"],
                "document_type": "generic_request",
                "form_ref": "generic.request.edit",
                "schema_version": "1",
            },
        )
        assert claimed["submission_status"] == "draft"
        assert state.user_tokens
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_oauth_state_mismatch_and_cross_user(services: Any, tmp_path: Path) -> None:
    httpd, _state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, user_id = _users(services)
    other = services  # same db
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem),
        )
        agent_a, thread_a = _scope(services, user_id, "oa")
        actor_a = PluginActor(user_id, False, agent_id=agent_a, thread_id=thread_a)
        started = await facade.invoke_action(
            "activations.start", actor_a, {"connection_id": saved["connection_id"]}
        )
        with pytest.raises(PluginActionError) as unknown:
            await facade.invoke_action(
                "activations.complete", actor_a, {"state": "not-a-real-state-value-xx"}
            )
        assert unknown.value.code == "INVALID_STATE"
        agent_b, thread_b = _scope(other, admin_id, "ob")
        actor_b = PluginActor(admin_id, True, agent_id=agent_b, thread_id=thread_b)
        with pytest.raises(PluginActionError) as stolen:
            await facade.invoke_action("activations.complete", actor_b, {"state": started["state"]})
        assert stolen.value.code == "ACCESS_DENIED"
        await _browser_approve(str(started["authorization_url"]), pem)
        done = await facade.invoke_action(
            "activations.complete", actor_a, {"state": started["state"]}
        )
        assert done["status"] == "active"
        with pytest.raises(PluginActionError) as missing:
            await facade.invoke_action(
                "interactions.claim",
                actor_b,
                {
                    "call_id": "call-oauthxb01",
                    "connection_id": saved["connection_id"],
                    "document_type": "generic_request",
                    "form_ref": "generic.request.edit",
                    "schema_version": "1",
                },
            )
        assert missing.value.code == "ACTIVATION_REQUIRED"
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_oauth_refresh_and_disconnect_revokes(
    services: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    httpd, state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, user_id = _users(services)
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem),
        )
        agent_id, thread_id = _scope(services, user_id, "ref")
        actor = PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id)
        await _activate_oauth(facade, actor, saved["connection_id"], pem)
        old_tokens = set(state.user_tokens)
        real_time = time.time
        monkeypatch.setattr(time, "time", lambda: real_time() + 4000)
        claimed = await facade.invoke_action(
            "interactions.claim",
            actor,
            {
                "call_id": "call-refresh01",
                "connection_id": saved["connection_id"],
                "document_type": "generic_request",
                "form_ref": "generic.request.edit",
                "schema_version": "1",
            },
        )
        assert claimed["interaction_id"]
        assert set(state.user_tokens) - old_tokens
        monkeypatch.undo()
        await facade.invoke_action(
            "activations.disconnect", actor, {"connection_id": saved["connection_id"]}
        )
        listed = await facade.invoke_action("connections.list", actor, {})
        assert listed["connections"][0]["activation_status"] == "inactive"
        with pytest.raises(PluginActionError) as after:
            await facade.invoke_action(
                "tickets.issue",
                actor,
                {
                    "interaction_id": claimed["interaction_id"],
                    "call_id": "call-refresh01",
                    "action": "edit",
                },
            )
        assert after.value.code == "ACTIVATION_REQUIRED"
        assert state.revoked
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_native_login_and_pat_activation(services: Any, tmp_path: Path) -> None:
    httpd, _state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, user_id = _users(services)
    try:
        native = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem, user_auth_method="native_login", display_name="native"),
        )
        pat = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem, user_auth_method="personal_access_token", display_name="pat"),
        )
        agent_id, thread_id = _scope(services, user_id, "mix")
        actor = PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id)
        with pytest.raises(PluginActionError) as bad:
            await facade.invoke_action(
                "activations.native",
                actor,
                {
                    "connection_id": native["connection_id"],
                    "username": "demo",
                    "password": "wrong",
                },
            )
        assert bad.value.status == 401
        done = await facade.invoke_action(
            "activations.native",
            actor,
            {
                "connection_id": native["connection_id"],
                "username": "demo",
                "password": "demo-pass",
            },
        )
        assert done["status"] == "active"
        records = str(
            await facade.get_record("activations", f"u{user_id}-{native['connection_id']}")
        )
        listed = str(await facade.invoke_action("connections.list", actor, {}))
        assert "demo-pass" not in records
        assert "demo-pass" not in listed
        with pytest.raises(PluginActionError) as bad_pat:
            await facade.invoke_action(
                "activations.pat",
                actor,
                {"connection_id": pat["connection_id"], "access_token": "not-a-pat"},
            )
        assert bad_pat.value.status == 401
        with pytest.raises(PluginActionError) as mismatch:
            await facade.invoke_action(
                "activations.pat",
                actor,
                {"connection_id": native["connection_id"], "access_token": "pat-secret99"},
            )
        assert mismatch.value.code == "METHOD_MISMATCH"
        pat_done = await facade.invoke_action(
            "activations.pat",
            actor,
            {"connection_id": pat["connection_id"], "access_token": "pat-secret99"},
        )
        assert pat_done["status"] == "active"
        pat_row = await facade.get_record("activations", f"u{user_id}-{pat['connection_id']}")
        assert pat_row is not None
        assert "pat-secret99" not in str(pat_row.payload)
        await facade.invoke_action(
            "interactions.claim",
            actor,
            {
                "call_id": "call-native001",
                "connection_id": native["connection_id"],
                "document_type": "generic_request",
                "form_ref": "generic.request.edit",
                "schema_version": "1",
            },
        )
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_handshake_rejects_unsupported_user_auth_method(
    services: Any, tmp_path: Path
) -> None:
    httpd, state, pem, port = _serve(tmp_path)
    state.supported_user_auth_methods = ["native_login"]
    facade = _bind(services)
    admin_id, _user_id = _users(services)
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem, user_auth_method="oauth2"),
        )
        test = await facade.invoke_action(
            "connections.test",
            PluginActor(admin_id, True),
            {"connection_id": saved["connection_id"]},
        )
        assert test["ok"] is False
        assert test["unsupported_reason"] == "user_auth_method_unsupported"
        assert any(s["name"] == "user_auth_methods" and s["ok"] is False for s in test["stages"])
    finally:
        httpd.shutdown()

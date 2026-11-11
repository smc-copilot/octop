from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
from octop_harness.plugins.context import PluginContext
from octop_harness.plugins.manifest import PluginManifest

from octop.config import OctopConfig
from octop.infra.agents.plugins.host import PluginHost
from octop.infra.agents.plugins.host_contracts import (
    PluginActionError,
    PluginActor,
    PluginHostError,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "business-ui"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from adapter.app import AdapterState, serve_tls  # noqa: E402
from adapter.certs import write_self_signed  # noqa: E402


@pytest.fixture
def services(tmp_path: Path) -> Any:
    db = SqlitePool(tmp_path / "octop.db")
    run_migrations(db)
    return build_shared_services(db=db, paths=PathLayout(tmp_path), config=OctopConfig())


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "business_ui_plugin",
        _PLUGIN_ROOT / "main.py",
        submodule_search_locations=[str(_PLUGIN_ROOT)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.setup


def _context() -> PluginContext:
    return PluginContext(
        manifest=PluginManifest(
            id="business-ui",
            version="0.1.0",
            name="Business UI",
            kind="tool",
            entry="main.py",
        ),
        source_path=_PLUGIN_ROOT,
    )


def _bind(services: Any) -> Any:
    host = PluginHost(lambda: services)
    ctx = _context()
    _load_plugin()(ctx)
    return host.bind_context(ctx, "0.1.0")


def _users(services: Any) -> tuple[int, int]:
    repo = UserRepo(services.db)
    admin = repo.create(username="bui-admin", role="admin")
    user = repo.create(username="bui-user", role="user")
    return admin, user


def _origin(port: int) -> str:
    return f"https://127.0.0.1:{port}"


def _save_fields(
    port: int,
    pem: str,
    *,
    secret: str = "tok",
    **extra: Any,
) -> dict[str, Any]:
    origin = _origin(port)
    payload: dict[str, Any] = {
        "display_name": extra.pop("display_name", "ref"),
        "base_url": origin,
        "auth_method": extra.pop("auth_method", "api_token"),
        "secret": secret,
        "tls_ca_pem": pem,
        "private_allow": ["127.0.0.1/32"],
        "instance_issuer": "https://127.0.0.1",
        "user_auth_method": extra.pop("user_auth_method", "oauth2"),
        "oauth_discovery_url": origin + "/.well-known/oauth-authorization-server",
        "oauth_client_id": "bui-client",
        "oauth_client_secret": "bui-secret",
    }
    payload.update(extra)
    return payload


async def _browser_approve(authorization_url: str, pem: str) -> None:
    import ssl
    from urllib.parse import parse_qs, urlparse

    import httpx

    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    ctx = ssl.create_default_context(cadata=pem)
    with httpx.Client(verify=ctx, follow_redirects=True, trust_env=False) as client:
        res = client.post(
            origin + "/v1/oauth/approve",
            data={
                "client_id": query["client_id"][0],
                "redirect_uri": query["redirect_uri"][0],
                "state": query["state"][0],
                "code_challenge": query["code_challenge"][0],
                "username": "demo",
            },
        )
        assert res.status_code == 200


async def _activate_oauth(
    facade: Any, actor: PluginActor, connection_id: str, pem: str
) -> dict[str, Any]:
    started = await facade.invoke_action(
        "activations.start", actor, {"connection_id": connection_id}
    )
    await _browser_approve(str(started["authorization_url"]), pem)
    done = await facade.invoke_action("activations.complete", actor, {"state": started["state"]})
    assert done["status"] == "active"
    return started


def _scope(services: Any, user_id: int, suffix: str) -> tuple[str, str]:
    agent_id = f"agent-{suffix}"
    thread_id = f"thread-{suffix}"
    services.agent_repo.create(agent_id=agent_id, user_id=user_id, name=suffix)
    services.thread_repo.insert(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=user_id,
        channel_type="dashboard",
        session_key=f"sess-{suffix}",
    )
    return agent_id, thread_id


@pytest.mark.asyncio
async def test_admin_permission_is_host_role_not_payload(services: Any) -> None:
    facade = _bind(services)
    admin_id, user_id = _users(services)
    with pytest.raises(PluginHostError) as exc:
        await facade.invoke_action(
            "connections.save",
            PluginActor(user_id, False),
            {
                "display_name": "x",
                "base_url": "https://127.0.0.1/",
                "auth_method": "api_token",
                "secret": "nope",
                "instance_issuer": "https://127.0.0.1",
            },
        )
    assert exc.value.code == "denied"


@pytest.mark.asyncio
async def test_secret_stays_out_of_records_and_list_payload(services: Any, tmp_path: Path) -> None:
    facade = _bind(services)
    admin_id, _user_id = _users(services)
    cert, key, pem = write_self_signed(tmp_path)
    state = AdapterState("reusable-token")
    httpd = serve_tls(state, certfile=str(cert), keyfile=str(key), host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.socket.getsockname()[1]
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem, secret="reusable-token"),
        )
        listed = await facade.invoke_action("connections.list", PluginActor(admin_id, True), {})
        blob = str(listed)
        assert "reusable-token" not in blob
        record = await facade.get_record("connections", saved["connection_id"])
        assert record is not None
        assert "reusable-token" not in str(record.payload)
        assert record.payload.get("credential_id")
        test = await facade.invoke_action(
            "connections.test",
            PluginActor(admin_id, True),
            {"connection_id": saved["connection_id"]},
        )
        assert test["ok"] is True
        assert test["protocol"] == "business-ui.v1"
        assert any(s["name"] == "browser_embed" and s["ok"] is False for s in test["stages"])
        auth_stage = next(s for s in test["stages"] if s["name"] == "user_auth_methods")
        assert auth_stage["ok"] is True
        assert "oauth2" in auth_stage["detail"]
        assert "native_login" in auth_stage["detail"]
        assert "personal_access_token" in auth_stage["detail"]
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_claim_fail_closed_without_scope_and_cross_user(
    services: Any, tmp_path: Path
) -> None:
    facade = _bind(services)
    admin_id, user_id = _users(services)
    cert, key, pem = write_self_signed(tmp_path)
    state = AdapterState("tok")
    httpd = serve_tls(state, certfile=str(cert), keyfile=str(key), host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem),
        )
        payload = {
            "call_id": "call-aaaaaaaa",
            "connection_id": saved["connection_id"],
            "document_type": "generic_request",
            "form_ref": "generic.request.edit",
            "schema_version": "1",
        }
        with pytest.raises(PluginActionError) as exc:
            await facade.invoke_action("interactions.claim", PluginActor(user_id, False), payload)
        assert exc.value.status == 403
        agent_id, thread_id = _scope(services, user_id, "u1")
        scoped = PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id)
        with pytest.raises(PluginActionError) as unactivated:
            await facade.invoke_action("interactions.claim", scoped, payload)
        assert unactivated.value.code == "ACTIVATION_REQUIRED"
        await _activate_oauth(facade, scoped, saved["connection_id"], pem)
        claimed = await facade.invoke_action("interactions.claim", scoped, payload)
        assert claimed["submission_status"] == "draft"
        assert claimed["interaction_id"].startswith("int-")
        other_agent, other_thread = _scope(services, admin_id, "u2")
        with pytest.raises(PluginActionError):
            await facade.invoke_action(
                "interactions.get",
                PluginActor(
                    admin_id,
                    True,
                    agent_id=other_agent,
                    thread_id=other_thread,
                ),
                {
                    "interaction_id": claimed["interaction_id"],
                    "call_id": "call-aaaaaaaa",
                },
            )
        with pytest.raises(PluginActionError):
            await facade.invoke_action(
                "interactions.claim",
                PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id),
                {**payload, "form_ref": "https://evil.example/form"},
            )
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_ticket_receipt_same_call_and_replay(services: Any, tmp_path: Path) -> None:
    facade = _bind(services)
    admin_id, user_id = _users(services)
    cert, key, pem = write_self_signed(tmp_path)
    state = AdapterState("tok")
    httpd = serve_tls(state, certfile=str(cert), keyfile=str(key), host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem),
        )
        agent_id, thread_id = _scope(services, user_id, "flow")
        actor = PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id)
        await _activate_oauth(facade, actor, saved["connection_id"], pem)
        claimed = await facade.invoke_action(
            "interactions.claim",
            actor,
            {
                "call_id": "call-bbbbbbbb",
                "connection_id": saved["connection_id"],
                "document_type": "generic_request",
                "form_ref": "generic.request.edit",
                "schema_version": "1",
                "summary": {"title": "招两名实施顾问"},
            },
        )
        ticket = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": "call-bbbbbbbb",
                "action": "edit",
            },
        )
        assert ticket["ticket"]
        assert ticket["redeem_url"].startswith("https://")
        import httpx

        ctx = __import__("ssl").create_default_context(cadata=pem)
        with httpx.Client(verify=ctx, follow_redirects=False, trust_env=False) as client:
            first = client.post(
                ticket["redeem_url"],
                data={"ticket": ticket["ticket"], "nonce": ticket["nonce"]},
            )
            assert first.status_code == 200
            replay = client.post(
                ticket["redeem_url"],
                data={"ticket": ticket["ticket"], "nonce": ticket["nonce"]},
            )
            assert replay.status_code == 403
            session = first.headers.get("set-cookie", "")
            submit = client.post(
                f"https://127.0.0.1:{port}/v1/documents/submit",
                data={"headcount": "2", "role": "implementation consultant", "op": "submit"},
                headers={"cookie": session.split(";", 1)[0]},
            )
            assert submit.status_code == 200
            again = client.post(
                f"https://127.0.0.1:{port}/v1/documents/submit",
                data={"headcount": "2", "role": "implementation consultant", "op": "submit"},
                headers={"cookie": session.split(";", 1)[0]},
            )
            assert again.json().get("idempotent") is True
        fetched = await facade.invoke_action(
            "interactions.get",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": "call-bbbbbbbb"},
        )
        assert fetched["submission_status"] == "submitted"
        assert fetched["approval_status"] == "pending"
        assert fetched["record_id"]
        with pytest.raises(PluginActionError) as cancel_exc:
            await facade.invoke_action(
                "interactions.cancel",
                actor,
                {"interaction_id": claimed["interaction_id"], "call_id": "call-bbbbbbbb"},
            )
        assert cancel_exc.value.status == 400
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_disabled_user_and_forged_payload_fail_closed(services: Any, tmp_path: Path) -> None:
    facade = _bind(services)
    admin_id, user_id = _users(services)
    cert, key, pem = write_self_signed(tmp_path)
    state = AdapterState("tok")
    httpd = serve_tls(state, certfile=str(cert), keyfile=str(key), host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            _save_fields(port, pem, auth_method="authorization_code"),
        )
        record = await facade.get_record("connections", saved["connection_id"])
        assert record is not None
        bundle = await facade.resolve_credential(
            str(record.payload["credential_id"]), record.owner_user_id
        )
        assert bundle.get("single_use") is True
        assert record.payload.get("secret") is None
        assert "secret" not in record.payload
        assert bundle.get("secret") == "tok"
        with pytest.raises(PluginHostError):
            await facade.invoke_action(
                "interactions.claim",
                PluginActor(user_id, False),
                {
                    "call_id": "call-cccccccc",
                    "connection_id": saved["connection_id"],
                    "document_type": "generic_request",
                    "form_ref": "generic.request.edit",
                    "schema_version": "1",
                    "user_id": admin_id,
                },
            )
        agent_id, thread_id = _scope(services, user_id, "dis")
        UserRepo(services.db).set_disabled(user_id, True)
        with pytest.raises(PluginActionError) as denied:
            await facade.invoke_action(
                "interactions.claim",
                PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id),
                {
                    "call_id": "call-dddddddd",
                    "connection_id": saved["connection_id"],
                    "document_type": "generic_request",
                    "form_ref": "generic.request.edit",
                    "schema_version": "1",
                },
            )
        assert denied.value.status == 403
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_html_website_handshake_is_unsupported(services: Any, tmp_path: Path) -> None:
    import ssl
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class HtmlHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def do_POST(self) -> None:  # noqa: N802
            raw = b"<!doctype html><html><body>login</body></html>"
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            self.do_POST()

    cert, key, pem = write_self_signed(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), HtmlHandler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(cert), str(key))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.socket.getsockname()[1]
    facade = _bind(services)
    admin_id, _user_id = _users(services)
    try:
        saved = await facade.invoke_action(
            "connections.save",
            PluginActor(admin_id, True),
            {
                "display_name": "site",
                "base_url": f"https://127.0.0.1:{port}",
                "auth_method": "api_token",
                "secret": "unused",
                "tls_ca_pem": pem,
                "private_allow": ["127.0.0.1/32"],
                "instance_issuer": "https://127.0.0.1",
                "user_auth_method": "native_login",
            },
        )
        test = await facade.invoke_action(
            "connections.test",
            PluginActor(admin_id, True),
            {"connection_id": saved["connection_id"]},
        )
        assert test["ok"] is False
        assert test["unsupported_reason"] in {"ordinary_website_html", "login_page_not_protocol"}
    finally:
        httpd.shutdown()

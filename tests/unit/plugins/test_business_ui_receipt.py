from __future__ import annotations

import ssl
import sys
import threading
from pathlib import Path
from typing import Any

import httpx
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
    return httpd, state, pem, httpd.socket.getsockname()[1]


async def _claimed(
    services: Any, tmp_path: Path, *, suffix: str = "rcpt"
) -> tuple[Any, Any, PluginActor, dict[str, Any], AdapterState, str, int]:
    httpd, state, pem, port = _serve(tmp_path)
    facade = _bind(services)
    admin_id, user_id = _users(services)
    saved = await facade.invoke_action(
        "connections.save", PluginActor(admin_id, True), _save_fields(port, pem)
    )
    agent_id, thread_id = _scope(services, user_id, suffix)
    actor = PluginActor(user_id, False, agent_id=agent_id, thread_id=thread_id)
    await _activate_oauth(facade, actor, saved["connection_id"], pem)
    claimed = await facade.invoke_action(
        "interactions.claim",
        actor,
        {
            "call_id": f"call-{suffix}-xx",
            "connection_id": saved["connection_id"],
            "document_type": "generic_request",
            "form_ref": "generic.request.edit",
            "schema_version": "1",
            "summary": {"title": "招两名实施顾问"},
        },
    )
    return httpd, facade, actor, claimed, state, pem, port


def _submit(pem: str, ticket: dict[str, Any], port: int) -> httpx.Response:
    ctx = ssl.create_default_context(cadata=pem)
    with httpx.Client(verify=ctx, follow_redirects=False, trust_env=False) as client:
        first = client.post(
            ticket["redeem_url"],
            data={"ticket": ticket["ticket"], "nonce": ticket["nonce"]},
        )
        assert first.status_code == 200
        session = first.headers.get("set-cookie", "")
        return client.post(
            f"https://127.0.0.1:{port}/v1/documents/submit",
            data={"headcount": "2", "role": "implementation consultant", "op": "submit"},
            headers={"cookie": session.split(";", 1)[0]},
        )


@pytest.mark.asyncio
async def test_scenario_a_success_and_detail(services: Any, tmp_path: Path) -> None:
    httpd, facade, actor, claimed, _state, pem, port = await _claimed(
        services, tmp_path, suffix="sca"
    )
    try:
        ticket = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "action": "edit",
            },
        )
        submit = _submit(pem, ticket, port)
        assert submit.status_code == 200
        fetched = await facade.invoke_action(
            "interactions.get",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
        )
        assert fetched["result"]["type"] == "SUCCESS"
        assert fetched["event"] == "BUSINESS_OPERATION_SUCCESS"
        assert fetched["record_id"]
        assert "view_document" in fetched["allowed_actions"]
        detail = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "action": "view_document",
            },
        )
        assert detail["page_mode"] == "readonly"
        assert "generic.request.detail" in detail["form_ref"]
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_scenario_b_permission_reject(services: Any, tmp_path: Path) -> None:
    httpd, facade, actor, claimed, state, pem, port = await _claimed(
        services, tmp_path, suffix="scb"
    )
    state.submit_outcome = "permission"
    try:
        ticket = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "action": "edit",
            },
        )
        _submit(pem, ticket, port)
        fetched = await facade.invoke_action(
            "interactions.get",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
        )
        assert fetched["result"]["type"] == "BUSINESS_REJECTED"
        assert fetched["result"]["code"] == "PERMISSION_DENIED"
        assert fetched["record_id"] is None
        assert "edit" not in fetched["allowed_actions"]
        assert "submit" not in fetched["allowed_actions"]
        assert "view_document" not in fetched["allowed_actions"]
        assert "request_permission" in fetched["allowed_actions"]
        with pytest.raises(PluginActionError):
            await facade.invoke_action(
                "tickets.issue",
                actor,
                {
                    "interaction_id": claimed["interaction_id"],
                    "call_id": claimed["call_id"],
                    "action": "view_document",
                },
            )
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_scenario_c_rule_reject_keeps_record(services: Any, tmp_path: Path) -> None:
    httpd, facade, actor, claimed, state, pem, port = await _claimed(
        services, tmp_path, suffix="scc"
    )
    state.seed_record_id = "REQ-KEEP"
    state.submit_outcome = "rule"
    try:
        ticket = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "action": "edit",
            },
        )
        _submit(pem, ticket, port)
        fetched = await facade.invoke_action(
            "interactions.get",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
        )
        assert fetched["result"]["type"] == "BUSINESS_REJECTED"
        assert fetched["record_id"] == "REQ-KEEP"
        assert "view_document" in fetched["allowed_actions"]
        assert "edit" not in fetched["allowed_actions"]
        assert "submit" not in fetched["allowed_actions"]
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_scenario_d_confirmed_failure_safe_retry(services: Any, tmp_path: Path) -> None:
    httpd, facade, actor, claimed, state, pem, port = await _claimed(
        services, tmp_path, suffix="scd"
    )
    state.submit_outcome = "failed"
    try:
        ticket = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "action": "edit",
            },
        )
        _submit(pem, ticket, port)
        fetched = await facade.invoke_action(
            "interactions.get",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
        )
        assert fetched["result"]["type"] == "TECHNICAL_ERROR"
        assert fetched["result"]["status"] == "FAILED"
        assert fetched["result"]["safe_retry"] is True
        assert "retry" in fetched["allowed_actions"]
        retried = await facade.invoke_action(
            "interactions.retry",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
        )
        assert retried["result"]["type"] == "SUCCESS"
        assert retried["record_id"]
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_scenario_e_unknown_query_status_resolves(services: Any, tmp_path: Path) -> None:
    httpd, facade, actor, claimed, state, pem, port = await _claimed(
        services, tmp_path, suffix="sce"
    )
    state.submit_outcome = "unknown"
    state.query_resolves_to = "success"
    try:
        ticket = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "action": "edit",
            },
        )
        _submit(pem, ticket, port)
        fetched = await facade.invoke_action(
            "interactions.get",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
        )
        assert fetched["result"]["type"] == "TECHNICAL_ERROR"
        assert fetched["result"]["status"] == "UNKNOWN"
        assert "query_status" in fetched["allowed_actions"]
        assert "retry" not in fetched["allowed_actions"]
        with pytest.raises(PluginActionError):
            await facade.invoke_action(
                "interactions.retry",
                actor,
                {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
            )
        resolved = await facade.invoke_action(
            "interactions.query_status",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "operation_id": fetched["operation_id"],
            },
        )
        assert resolved["result"]["type"] == "SUCCESS"
        assert resolved["event"] == "BUSINESS_OPERATION_RESOLVED"
        assert resolved["record_id"]
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_scenario_f_history_restore_lookup(services: Any, tmp_path: Path) -> None:
    httpd, facade, actor, claimed, _state, pem, port = await _claimed(
        services, tmp_path, suffix="scf"
    )
    try:
        ticket = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "action": "edit",
            },
        )
        _submit(pem, ticket, port)
        restored = await facade.invoke_action(
            "interactions.lookup", actor, {"call_id": claimed["call_id"]}
        )
        assert restored["interaction_id"] == claimed["interaction_id"]
        assert restored["result"]["type"] == "SUCCESS"
        other_agent, other_thread = _scope(services, actor.user_id, "scf2")
        with pytest.raises(PluginActionError):
            await facade.invoke_action(
                "interactions.lookup",
                PluginActor(actor.user_id, False, agent_id=other_agent, thread_id=other_thread),
                {"call_id": claimed["call_id"]},
            )
    finally:
        httpd.shutdown()


@pytest.mark.asyncio
async def test_idempotent_duplicate_and_stale_receipt_ordering(
    services: Any, tmp_path: Path
) -> None:
    httpd, facade, actor, claimed, _state, pem, port = await _claimed(
        services, tmp_path, suffix="sci"
    )
    try:
        ticket = await facade.invoke_action(
            "tickets.issue",
            actor,
            {
                "interaction_id": claimed["interaction_id"],
                "call_id": claimed["call_id"],
                "action": "edit",
            },
        )
        _submit(pem, ticket, port)
        first = await facade.invoke_action(
            "interactions.get",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
        )
        second = await facade.invoke_action(
            "interactions.get",
            actor,
            {"interaction_id": claimed["interaction_id"], "call_id": claimed["call_id"]},
        )
        assert second["receipt_sequence"] == first["receipt_sequence"]
        assert second["record_id"] == first["record_id"]
        record = await facade.get_record("interactions", claimed["interaction_id"])
        assert record is not None
        stale = dict(record.payload)
        stale["record_version"] = int(first["record_version"]) - 1
        stale["receipt_sequence"] = 0
        stale["record_id"] = "REQ-STALE"
        from business_ui.receipt import merge_receipt

        merged = merge_receipt(record.payload, stale)
        assert merged["record_id"] == first["record_id"]
    finally:
        httpd.shutdown()

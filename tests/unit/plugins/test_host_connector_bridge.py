"""Plugin host connector read-tool bridge (PRD D8 / NFR-1)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from octop.infra.agents.plugins.host import PluginHost
from octop.infra.agents.plugins.host_contracts import (
    PluginActionError,
    PluginActor,
    PluginHostError,
)


def _services(
    *,
    rows: list[Any] | None = None,
    decrypted: dict[str, Any] | None = None,
) -> SimpleNamespace:
    repo = MagicMock()
    repo.list_by_user.return_value = rows or []
    secret = MagicMock()
    return SimpleNamespace(
        connector_repo=repo,
        secret_repo=secret,
        _decrypted=decrypted or {"email": "a@b.com", "password": "secret"},
    )


@pytest.mark.asyncio
async def test_bridge_denies_write_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    host = PluginHost(lambda: _services())
    facade = host.bind("mail-assistant", "1.0.0")
    with pytest.raises(PluginHostError) as exc:
        await facade.invoke_connector_read_tool(
            PluginActor(1, False),
            "qq-mail",
            "send_email",
            {"to": "x"},
        )
    assert exc.value.code == "denied"


@pytest.mark.asyncio
async def test_bridge_missing_instance_guides_to_connectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = PluginHost(lambda: _services(rows=[]))
    facade = host.bind("mail-assistant", "1.0.0")
    with pytest.raises(PluginActionError) as exc:
        await facade.invoke_connector_read_tool(
            PluginActor(7, False, locale="en"),
            "qq-mail",
            "search_emails",
            {},
        )
    assert exc.value.code == "CONNECTOR_NOT_CONFIGURED"
    assert "connector" in exc.value.message.lower() or "Connectors" in exc.value.message


@pytest.mark.asyncio
async def test_bridge_calls_adapter_for_owner_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace(
        kind="qq-mail",
        status="active",
        user_id=3,
        instance_id="inst-a",
        credential_blob=b"blob",
    )
    services = _services(rows=[row])
    host = PluginHost(lambda: services)
    facade = host.bind("mail-assistant", "1.0.0")

    def fake_decrypt(_secret: Any, _blob: bytes) -> dict[str, Any]:
        return {"email": "a@b.com", "password": "secret", "imap_host": "imap.x"}

    def fake_call(kind: str, creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
        assert kind == "qq-mail"
        assert name == "search_emails"
        assert creds["password"] == "secret"
        assert creds["_user_id"] == 3
        assert creds["_instance_id"] == "inst-a"
        assert "password" not in args
        return json.dumps(
            {
                "octop_ui": {"renderer": "mail_card", "version": 1},
                "data": {"view": "list", "items": [], "password": "should-drop"},
                "text": "ok",
            }
        )

    monkeypatch.setattr(
        "octop.infra.connectors.crypto.decrypt_credentials",
        fake_decrypt,
    )
    monkeypatch.setattr(
        "octop.infra.connectors.gateway.registry.call_gateway_tool",
        fake_call,
    )

    result = await facade.invoke_connector_read_tool(
        PluginActor(3, False, locale="zh"),
        "qq-mail",
        "search_emails",
        {"unread": True},
    )
    assert result["text"] == "ok"
    assert result["data"]["view"] == "list"
    assert "password" not in result["data"]


@pytest.mark.asyncio
async def test_bridge_rejects_other_users_instance_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # list_by_user already scopes to actor; requesting a foreign instance_id yields empty.
    host = PluginHost(lambda: _services(rows=[]))
    facade = host.bind("mail-assistant", "1.0.0")
    with pytest.raises(PluginActionError) as exc:
        await facade.invoke_connector_read_tool(
            PluginActor(1, False),
            "qq-mail",
            "read_email",
            {"uid": "1"},
            instance_id="someone-elses",
        )
    assert exc.value.code == "CONNECTOR_NOT_CONFIGURED"

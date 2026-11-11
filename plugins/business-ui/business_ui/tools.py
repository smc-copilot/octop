"""LLM tools — display only. Never commit ownership or secrets."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from octop_harness.plugins import PluginContext

from octop.infra.agents.plugins.host_contracts import PluginActionError, PluginHostError

from .models import InteractionRefInput
from .receipt import mask_sensitive
from .service import BusinessUiService


def register_tools(ctx: PluginContext) -> Callable[[Any], None]:
    facade: Any | None = None

    def bind_facade(callback_facade: Any) -> None:
        nonlocal facade
        facade = callback_facade

    async def business_ui_draft(
        document_type: str = "generic_request",
        form_ref: str = "generic.request.edit",
        schema_version: str = "1",
        summary_title: str = "",
        summary_body: str = "",
    ) -> str:
        """Propose a business-form draft card. Does not create or own a record."""
        payload = {
            "octop_ui": {"renderer": "business_ui_card", "version": 1},
            "data": {
                "documentType": document_type,
                "recordId": None,
                "formRef": form_ref,
                "schemaVersion": schema_version,
                "recordVersion": 0,
                "allowedActions": ["edit", "cancel"],
                "interactionId": None,
                "claimRequired": True,
                "submissionStatus": "unclaimed",
                "approvalStatus": "not_applicable",
                "summary": {"title": summary_title, "body": summary_body},
                "result": None,
                "operationId": None,
                "event": None,
            },
            "text": summary_title or "Business form draft (not submitted)",
        }
        return json.dumps(payload, ensure_ascii=False)

    async def business_ui_connections() -> str:
        """Open the plugin-owned connection configuration card. Secrets are never returned."""
        payload = {
            "octop_ui": {"renderer": "business_ui_config", "version": 1},
            "data": {"kind": "config"},
            "text": "Business UI connections",
        }
        return json.dumps(payload, ensure_ascii=False)

    async def business_ui_receipt(interaction_id: str) -> str:
        """Read the verified receipt for an interaction. Do not continue the workflow."""
        if facade is None:
            raise PluginHostError("unavailable")
        execution = await facade.current_execution()
        actor = execution.actor
        service = BusinessUiService(facade)
        record = await facade.get_record("interactions", interaction_id)
        if record is None:
            return json.dumps({"ok": False, "error": "not_found"}, ensure_ascii=False)
        data = dict(record.payload)
        if int(data.get("user_id") or 0) != actor.user_id:
            return json.dumps({"ok": False, "error": "access_denied"}, ensure_ascii=False)
        try:
            state = await service.get_interaction(
                actor,
                InteractionRefInput(
                    interaction_id=interaction_id, call_id=str(data.get("call_id") or "")
                ),
            )
        except (PluginActionError, PluginHostError):
            state = service._state_from_payload(data)
        dumped = mask_sensitive(state.model_dump(mode="json"))
        dumped["auto_continue"] = False
        return json.dumps(
            {
                "ok": True,
                "interactionId": state.interaction_id,
                "receipt": dumped,
                "text": "Verified business receipt (read-only, do not auto-continue).",
            },
            ensure_ascii=False,
        )

    ctx.tool(
        "business_ui_draft",
        business_ui_draft,
        description=(
            "Show a business form summary card. Never claim the record was submitted. "
            "form_ref must be a logical registry name, never a URL."
        ),
    )
    ctx.tool(
        "business_ui_connections",
        business_ui_connections,
        description="Open the Business UI connection configuration card for administrators.",
    )
    ctx.tool(
        "business_ui_receipt",
        business_ui_receipt,
        description=(
            "Fetch the verified Business UI receipt for an interactionId from plugin records. "
            "Read-only. Do not continue, retry, or resubmit automatically."
        ),
    )
    return bind_facade

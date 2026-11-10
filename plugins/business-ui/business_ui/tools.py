"""LLM tools — display only. Never commit ownership or secrets."""

from __future__ import annotations

import json

from octop_harness.plugins import PluginContext


def register_tools(ctx: PluginContext) -> None:
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

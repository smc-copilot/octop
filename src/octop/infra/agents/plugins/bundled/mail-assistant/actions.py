"""Host actions for mail card browse (read-only connector bridge)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from octop.infra.agents.plugins.host_contracts import PluginActor


class ListInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    unread: bool | None = None
    from_addr: str | None = Field(default=None, alias="from")
    since_days: int | None = Field(default=None, ge=0, le=365)
    limit: int | None = Field(default=10, ge=1, le=50)
    offset: int | None = Field(default=0, ge=0, le=5000)
    query: str | None = None
    instance_id: str | None = None


class DetailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: str = Field(min_length=1)
    instance_id: str | None = None


class PrepareReplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: str = Field(min_length=1)
    instance_id: str | None = None


class EnvelopeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_version: Literal[1] = 1
    octop_ui: dict[str, Any] | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    text: str = ""


@dataclass(frozen=True)
class ActionSpec:
    name: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[..., Any]
    summary: str
    permission: Literal["authenticated", "admin", "agent_owner"]


def _as_envelope(payload: dict[str, Any]) -> EnvelopeOutput:
    return EnvelopeOutput(
        octop_ui=payload.get("octop_ui") if isinstance(payload.get("octop_ui"), dict) else None,
        data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
        text=str(payload.get("text") or ""),
    )


def register_actions(facade: Any) -> tuple[ActionSpec, ...]:
    async def mail_list(actor: PluginActor, payload: ListInput) -> EnvelopeOutput:
        args: dict[str, Any] = {}
        if payload.unread is not None:
            args["unread"] = payload.unread
        if payload.from_addr:
            args["from"] = payload.from_addr
        if payload.since_days is not None:
            args["since_days"] = payload.since_days
        if payload.limit is not None:
            args["limit"] = payload.limit
        if payload.offset:
            args["offset"] = payload.offset
        if payload.query:
            args["query"] = payload.query
        result = await facade.invoke_connector_read_tool(
            actor,
            "qq-mail",
            "search_emails",
            args,
            instance_id=payload.instance_id,
        )
        return _as_envelope(result)

    async def mail_detail(actor: PluginActor, payload: DetailInput) -> EnvelopeOutput:
        result = await facade.invoke_connector_read_tool(
            actor,
            "qq-mail",
            "read_email",
            {"uid": payload.uid},
            instance_id=payload.instance_id,
        )
        return _as_envelope(result)

    async def mail_prepare_reply(actor: PluginActor, payload: PrepareReplyInput) -> EnvelopeOutput:
        detail = await facade.invoke_connector_read_tool(
            actor,
            "qq-mail",
            "read_email",
            {"uid": payload.uid},
            instance_id=payload.instance_id,
        )
        data = detail.get("data") if isinstance(detail.get("data"), dict) else {}
        subject = str(data.get("subject") or "")
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        sender = str(data.get("from") or "")
        body = str(data.get("body") or "")
        quoted = "\n".join(f"> {line}" for line in body.splitlines())
        draft = {
            "view": "draft",
            "uid": payload.uid,
            "to": sender,
            "subject": reply_subject,
            "body": "",
            "quote": quoted,
            "original": {
                "from": sender,
                "subject": subject,
                "date": data.get("date"),
            },
        }
        return EnvelopeOutput(
            octop_ui={"renderer": "mail_card", "version": 1},
            data=draft,
            text=f"Reply draft to {sender}: {reply_subject}",
        )

    return (
        ActionSpec(
            "mail.list",
            ListInput,
            EnvelopeOutput,
            mail_list,
            "List mailbox messages with optional filters",
            "authenticated",
        ),
        ActionSpec(
            "mail.detail",
            DetailInput,
            EnvelopeOutput,
            mail_detail,
            "Load one message body by IMAP UID",
            "authenticated",
        ),
        ActionSpec(
            "mail.prepare_reply",
            PrepareReplyInput,
            EnvelopeOutput,
            mail_prepare_reply,
            "Prepare a reply draft from a message UID",
            "authenticated",
        ),
    )

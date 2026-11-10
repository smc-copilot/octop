"""Pydantic action envelopes. Secrets never appear on list/get outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


AuthMethod = Literal["api_token", "authorization_code"]
TicketAction = Literal["edit", "save", "submit", "view_detail"]


class EmptyInput(_Strict):
    pass


class ConnectionSaveInput(_Strict):
    connection_id: str | None = None
    display_name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=8, max_length=2048)
    auth_method: AuthMethod
    secret: str | None = Field(default=None, max_length=8192)
    extra_origins: list[str] = Field(default_factory=list, max_length=16)
    private_allow: list[str] = Field(default_factory=list, max_length=16)
    tls_ca_pem: str | None = Field(default=None, max_length=32_000)
    enabled: bool = True
    instance_issuer: str | None = Field(default=None, max_length=512)

    @field_validator("extra_origins", "private_allow")
    @classmethod
    def _strip_list(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]


class ConnectionIdInput(_Strict):
    connection_id: str = Field(min_length=1, max_length=80)


class ConnectionListOutput(_Strict):
    instance_issuer: str
    connections: list[dict[str, Any]]
    can_manage: bool


class ConnectionSaveOutput(_Strict):
    connection_id: str
    revision: int
    secret_configured: bool


class ConnectionDeleteOutput(_Strict):
    deleted: bool


class HandshakeStage(_Strict):
    name: str
    ok: bool
    detail: str


class ConnectionTestOutput(_Strict):
    ok: bool
    stages: list[HandshakeStage]
    protocol: str | None = None
    unsupported_reason: str | None = None


class ClaimInput(_Strict):
    call_id: str = Field(min_length=8, max_length=128)
    connection_id: str = Field(min_length=1, max_length=80)
    document_type: str = Field(min_length=1, max_length=80)
    form_ref: str = Field(min_length=1, max_length=120)
    schema_version: str = Field(min_length=1, max_length=40)
    record_id: str | None = Field(default=None, max_length=80)
    record_version: int = Field(default=0, ge=0, le=1_000_000)
    summary: dict[str, Any] = Field(default_factory=dict)


class InteractionRefInput(_Strict):
    interaction_id: str = Field(min_length=8, max_length=80)
    call_id: str = Field(min_length=8, max_length=128)


class TicketIssueInput(InteractionRefInput):
    action: TicketAction


class TicketIssueOutput(_Strict):
    redeem_url: str
    ticket: str
    expires_in: int
    nonce: str
    form_origin: str
    page_mode: Literal["edit", "readonly"]
    form_ref: str


class InteractionStateOutput(_Strict):
    interaction_id: str
    call_id: str
    connection_id: str
    document_type: str
    record_id: str | None
    form_ref: str
    schema_version: str
    record_version: int
    allowed_actions: list[str]
    submission_status: str
    approval_status: str
    summary: dict[str, Any]
    last_operation_id: str | None = None
    last_error: str | None = None
    navigation: dict[str, Any] | None = None


class ClaimOutput(InteractionStateOutput):
    bind_token: str


class CancelOutput(_Strict):
    interaction_id: str
    submission_status: str

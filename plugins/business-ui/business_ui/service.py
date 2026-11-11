"""Host-backed connection, interaction, and ticket orchestration."""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

from octop.infra.agents.plugins.host_contracts import (
    CredentialActivation,
    CredentialDeletion,
    PluginActionError,
    PluginActor,
    PluginHostError,
    RecordCheck,
    RecordWrite,
)

from . import PROTOCOL
from .activation import ActivationMixin
from .models import (
    ClaimInput,
    ClaimOutput,
    ConnectionDeleteOutput,
    ConnectionIdInput,
    ConnectionListOutput,
    ConnectionSaveInput,
    ConnectionSaveOutput,
    ConnectionTestOutput,
    HandshakeStage,
    InteractionRefInput,
    InteractionStateOutput,
    TicketIssueInput,
    TicketIssueOutput,
)
from .outbound import (
    AdapterError,
    build_client,
    classify_unsupported,
    evaluate_handshake,
    handshake_url,
    request_json,
)
from .security import (
    UnsafeUrl,
    origin_of,
    parse_exception_list,
    resolve_and_authorize,
    same_origin,
    validate_https_url_syntax,
)

CONNECTIONS = "connections"
INTERACTIONS = "interactions"
CALL_BINDS = "call_binds"
SETTINGS = "settings"
INSTANCE_KEY = "instance"
_ISSUER_RE = re.compile(r"^https://[A-Za-z0-9._:-]+(/[A-Za-z0-9._/-]*)?$")


def _err(code: str, message: str, status: int = 400) -> PluginActionError:
    return PluginActionError(code, message, status=status)


def _host_err(exc: PluginHostError) -> PluginActionError:
    mapping = {
        "denied": ("ACCESS_DENIED", 403),
        "conflict": ("CONFLICT", 409),
        "not_found": ("NOT_FOUND", 404),
        "unavailable": ("UNAVAILABLE", 503),
        "invalid": ("INVALID", 400),
    }
    code, status = mapping.get(exc.code, ("INVALID", 400))
    return _err(code, "host rejected the request", status)


def namespaced_actor(instance_issuer: str, user_id: int) -> dict[str, str]:
    return {"issuer": instance_issuer, "sub": f"{instance_issuer}|{user_id}"}


def _bind_key(agent_id: str, thread_id: str, call_id: str) -> str:
    digest = hashlib.sha256(f"{agent_id}\n{thread_id}\n{call_id}".encode()).hexdigest()[:40]
    return f"bind-{digest}"


def _public_connection(payload: dict[str, Any], *, include_admin: bool) -> dict[str, Any]:
    row = {
        "connection_id": payload["connection_id"],
        "display_name": payload["display_name"],
        "base_url": payload["base_url"],
        "auth_method": payload["auth_method"],
        "enabled": bool(payload.get("enabled")),
        "secret_configured": bool(payload.get("credential_id")),
        "extra_origins": list(payload.get("extra_origins") or []),
        "private_allow": list(payload.get("private_allow") or []),
        "user_auth_method": payload.get("user_auth_method") or "oauth2",
        "oauth_authorize_url": payload.get("oauth_authorize_url"),
        "oauth_token_url": payload.get("oauth_token_url"),
        "oauth_revoke_url": payload.get("oauth_revoke_url"),
        "oauth_discovery_url": payload.get("oauth_discovery_url"),
        "oauth_client_id": payload.get("oauth_client_id"),
        "oauth_scopes": payload.get("oauth_scopes"),
        "oauth_client_secret_configured": bool(payload.get("oauth_client_secret_configured")),
    }
    if include_admin:
        row["revision"] = payload.get("revision", 0)
        row["credential_owner_user_id"] = payload.get("credential_owner_user_id")
    return row


class BusinessUiService(ActivationMixin):
    def __init__(self, facade: Any) -> None:
        self._facade = facade

    async def _actor(self, actor: PluginActor, permission: str = "authenticated") -> PluginActor:
        try:
            return await self._facade.reauthorize_actor(actor, permission)
        except PluginHostError as exc:
            raise _host_err(exc) from exc

    async def instance_issuer(self) -> str:
        record = await self._facade.get_record(SETTINGS, INSTANCE_KEY)
        if record is None:
            return ""
        return str(record.payload.get("issuer") or "")

    async def _ensure_issuer(self, actor: PluginActor, proposed: str | None) -> str:
        current = await self.instance_issuer()
        if current:
            return current
        if not actor.is_admin:
            raise _err("INSTANCE_UNCONFIGURED", "administrator must set instance issuer", 403)
        issuer = (proposed or "").strip().rstrip("/")
        if not issuer or not _ISSUER_RE.match(issuer) or " " in issuer:
            raise _err(
                "INVALID_ISSUER", "instance issuer must be an https origin unique to this Octop"
            )
        try:
            validate_https_url_syntax(issuer if issuer.count("/") > 2 else issuer + "/")
        except UnsafeUrl as exc:
            raise _err("INVALID_ISSUER", str(exc)) from exc
        owner = actor.user_id
        await self._commit(
            [
                RecordWrite(
                    SETTINGS,
                    INSTANCE_KEY,
                    owner,
                    {"issuer": issuer},
                    0,
                )
            ]
        )
        return issuer

    async def _commit(
        self,
        writes: list[RecordWrite],
        activations: list[CredentialActivation] | None = None,
        *,
        checks: list[RecordCheck] | None = None,
        deletions: list[CredentialDeletion] | None = None,
    ) -> Any:
        try:
            return await self._facade.commit(
                writes,
                tuple(activations or ()),
                checks=tuple(checks or ()),
                credential_deletions=tuple(deletions or ()),
            )
        except PluginHostError as exc:
            raise _host_err(exc) from exc

    async def list_connections(self, actor: PluginActor) -> ConnectionListOutput:
        actor = await self._actor(actor, "authenticated")
        issuer = await self.instance_issuer()
        records = await self._facade.list_records(CONNECTIONS)
        can_manage = bool(actor.is_admin)
        items = []
        for record in records:
            payload = dict(record.payload)
            payload["revision"] = record.revision
            if payload.get("deleted"):
                continue
            if not can_manage and not payload.get("enabled"):
                continue
            public = _public_connection(payload, include_admin=can_manage)
            public.update(await self.activation_public(actor, str(payload["connection_id"])))
            items.append(public)
        return ConnectionListOutput(
            instance_issuer=issuer, connections=items, can_manage=can_manage
        )

    async def save_connection(
        self, actor: PluginActor, payload: ConnectionSaveInput
    ) -> ConnectionSaveOutput:
        actor = await self._actor(actor, "admin")
        issuer = await self._ensure_issuer(actor, payload.instance_issuer)
        try:
            validate_https_url_syntax(payload.base_url)
            origin_of(payload.base_url)
            exceptions = parse_exception_list(payload.private_allow)
            resolve_and_authorize(payload.base_url, private_exceptions=exceptions)
            for extra in payload.extra_origins:
                validate_https_url_syntax(extra)
                resolve_and_authorize(extra, private_exceptions=exceptions)
            for url in (
                payload.oauth_discovery_url,
                payload.oauth_authorize_url,
                payload.oauth_token_url,
                payload.oauth_revoke_url,
            ):
                if url:
                    validate_https_url_syntax(url)
                    resolve_and_authorize(url, private_exceptions=exceptions)
        except UnsafeUrl as exc:
            raise _err("UNSAFE_URL", str(exc)) from exc
        if payload.user_auth_method == "oauth2":
            has_discovery = bool(payload.oauth_discovery_url)
            has_pair = bool(payload.oauth_authorize_url and payload.oauth_token_url)
            if not payload.oauth_client_id or not (has_discovery or has_pair):
                raise _err(
                    "OAUTH_UNCONFIGURED",
                    "oauth2 requires client_id and discovery or authorize+token URLs",
                )
        connection_id = payload.connection_id or f"conn-{uuid4()}"
        existing = await self._facade.get_record(CONNECTIONS, connection_id)
        expected = existing.revision if existing is not None else 0
        if existing is not None and existing.owner_user_id != actor.user_id and not actor.is_admin:
            raise _err("ACCESS_DENIED", "cannot edit another operator's connection", 403)
        owner_id = existing.owner_user_id if existing is not None else actor.user_id
        credential_id = None if existing is None else existing.payload.get("credential_id")
        credential_owner = (
            int(existing.payload["credential_owner_user_id"])
            if existing is not None and existing.payload.get("credential_owner_user_id")
            else owner_id
        )
        activations: list[CredentialActivation] = []
        deletions: list[CredentialDeletion] = []
        secret_configured = bool(credential_id)
        credential_revision = (
            int(existing.payload.get("credential_revision") or 0) if existing else 0
        )
        existing_bundle: dict[str, Any] = {}
        if credential_id:
            try:
                existing_bundle = await self._facade.resolve_credential(
                    str(credential_id), owner_id
                )
            except PluginHostError:
                existing_bundle = {}
        if payload.secret or payload.oauth_client_secret or payload.tls_ca_pem:
            new_id = await self._facade.stage_credential(
                owner_id,
                {
                    "auth_method": payload.auth_method,
                    "secret": payload.secret or existing_bundle.get("secret"),
                    "single_use": payload.auth_method == "authorization_code",
                    "tls_ca_pem": payload.tls_ca_pem or existing_bundle.get("tls_ca_pem"),
                    "oauth_client_id": payload.oauth_client_id,
                    "oauth_client_secret": payload.oauth_client_secret
                    or existing_bundle.get("oauth_client_secret"),
                },
            )
            activations.append(CredentialActivation(new_id, owner_id, 1))
            old_id = credential_id
            if old_id and str(old_id) != new_id:
                deletions.append(
                    CredentialDeletion(str(old_id), credential_owner, credential_revision or 2)
                )
            credential_id = new_id
            credential_owner = owner_id
            secret_configured = True
            credential_revision = 2
        elif not secret_configured:
            raise _err("SECRET_REQUIRED", "secret is required when creating a connection")
        record_payload = {
            "connection_id": connection_id,
            "display_name": payload.display_name,
            "base_url": payload.base_url.rstrip("/"),
            "auth_method": payload.auth_method,
            "enabled": payload.enabled,
            "extra_origins": payload.extra_origins,
            "private_allow": payload.private_allow,
            "credential_id": credential_id,
            "credential_owner_user_id": credential_owner,
            "credential_revision": credential_revision,
            "instance_issuer": issuer,
            "user_auth_method": payload.user_auth_method,
            "oauth_discovery_url": payload.oauth_discovery_url,
            "oauth_authorize_url": payload.oauth_authorize_url,
            "oauth_token_url": payload.oauth_token_url,
            "oauth_revoke_url": payload.oauth_revoke_url,
            "oauth_client_id": payload.oauth_client_id,
            "oauth_scopes": payload.oauth_scopes,
            "oauth_client_secret_configured": bool(
                payload.oauth_client_secret or existing_bundle.get("oauth_client_secret")
            ),
        }
        rows = await self._commit(
            [RecordWrite(CONNECTIONS, connection_id, owner_id, record_payload, expected)],
            activations,
            deletions=deletions,
        )
        return ConnectionSaveOutput(
            connection_id=connection_id,
            revision=rows[0].revision,
            secret_configured=secret_configured,
        )

    async def delete_connection(
        self, actor: PluginActor, payload: ConnectionIdInput
    ) -> ConnectionDeleteOutput:
        actor = await self._actor(actor, "admin")
        existing = await self._facade.get_record(CONNECTIONS, payload.connection_id)
        if existing is None:
            raise _err("NOT_FOUND", "connection not found", 404)
        deletions: list[CredentialDeletion] = []
        cred_id = existing.payload.get("credential_id")
        if cred_id:
            deletions.append(
                CredentialDeletion(
                    str(cred_id),
                    int(existing.payload.get("credential_owner_user_id") or existing.owner_user_id),
                    int(existing.payload.get("credential_revision") or 2),
                )
            )
        # Removing the logical row: CAS to a tombstone without secret.
        await self._commit(
            [
                RecordWrite(
                    CONNECTIONS,
                    payload.connection_id,
                    existing.owner_user_id,
                    {
                        **{k: v for k, v in existing.payload.items() if k != "credential_id"},
                        "enabled": False,
                        "deleted": True,
                        "credential_id": None,
                    },
                    existing.revision,
                )
            ],
            deletions=deletions,
        )
        return ConnectionDeleteOutput(deleted=True)

    async def _load_enabled(self, connection_id: str) -> dict[str, Any]:
        record = await self._facade.get_record(CONNECTIONS, connection_id)
        if record is None or record.payload.get("deleted") or not record.payload.get("enabled"):
            raise _err("NOT_FOUND", "connection not found", 404)
        return {
            **record.payload,
            "revision": record.revision,
            "owner_user_id": record.owner_user_id,
        }

    async def _secret_bundle(self, conn: dict[str, Any]) -> dict[str, Any]:
        cred_id = conn.get("credential_id")
        owner = int(conn.get("credential_owner_user_id") or conn["owner_user_id"])
        if not cred_id:
            raise _err("SECRET_REQUIRED", "connection has no credential")
        try:
            bundle = await self._facade.resolve_credential(str(cred_id), owner)
        except PluginHostError as exc:
            raise _host_err(exc) from exc
        if bundle.get("single_use") and bundle.get("redeemed"):
            raise _err("CODE_REDEEMED", "authorization code already redeemed")
        return bundle

    async def test_connection(
        self, actor: PluginActor, payload: ConnectionIdInput
    ) -> ConnectionTestOutput:
        actor = await self._actor(actor, "admin")
        stages: list[HandshakeStage] = []
        try:
            conn = await self._load_enabled(payload.connection_id)
        except PluginActionError as exc:
            return ConnectionTestOutput(
                ok=False,
                stages=[HandshakeStage(name="registry", ok=False, detail=exc.message)],
                unsupported_reason="not_in_registry",
            )
        exceptions = parse_exception_list(list(conn.get("private_allow") or []))
        extra = list(conn.get("extra_origins") or [])
        try:
            resolve_and_authorize(conn["base_url"], private_exceptions=exceptions)
            stages.append(HandshakeStage(name="reachability_dns", ok=True, detail="resolved"))
        except UnsafeUrl as exc:
            stages.append(HandshakeStage(name="reachability_dns", ok=False, detail=str(exc)))
            return ConnectionTestOutput(ok=False, stages=stages, unsupported_reason="unsafe_url")
        try:
            bundle = await self._secret_bundle(conn)
        except PluginActionError as exc:
            stages.append(HandshakeStage(name="service_auth", ok=False, detail=exc.message))
            return ConnectionTestOutput(ok=False, stages=stages, unsupported_reason="auth")
        token = str(bundle.get("secret") or "")
        client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
        try:
            status, body, text = request_json(
                client,
                "POST",
                handshake_url(conn["base_url"]),
                token=token,
                body={
                    "protocol": PROTOCOL,
                    "destructive": False,
                    "instance_issuer": conn.get("instance_issuer") or await self.instance_issuer(),
                },
                base_url=conn["base_url"],
                extra_origins=extra,
                private_exceptions=exceptions,
            )
        except AdapterError as exc:
            stages.append(HandshakeStage(name="reachability_http", ok=False, detail=exc.message))
            return ConnectionTestOutput(ok=False, stages=stages, unsupported_reason=exc.code)
        finally:
            client.close()
        if status in {401, 403}:
            stages.append(HandshakeStage(name="service_auth", ok=False, detail=f"http {status}"))
            return ConnectionTestOutput(ok=False, stages=stages, unsupported_reason="auth_failed")
        if status != 200 or body is None:
            reason = classify_unsupported(status, body, text)
            stages.append(HandshakeStage(name="reachability_http", ok=False, detail=reason))
            return ConnectionTestOutput(
                ok=False, stages=stages, protocol=None, unsupported_reason=reason
            )
        stages.append(HandshakeStage(name="reachability_http", ok=True, detail="http 200 json"))
        stages.append(HandshakeStage(name="service_auth", ok=True, detail="accepted"))
        ok, reason, _missing = evaluate_handshake(body)
        stages.append(
            HandshakeStage(
                name="version_and_features",
                ok=ok,
                detail="compatible" if ok else (reason or "incompatible"),
            )
        )
        stages.append(
            HandshakeStage(
                name="browser_embed",
                ok=False,
                detail="not_evaluated_server_side",
            )
        )
        if not ok:
            return ConnectionTestOutput(
                ok=False,
                stages=stages,
                protocol=str((body or {}).get("protocol") or "") or None,
                unsupported_reason=reason,
            )
        methods = list((body.get("features") or {}).get("user_auth_methods") or [])
        configured = str(conn.get("user_auth_method") or "oauth2")
        oauth_ok = configured in methods
        stages.append(
            HandshakeStage(
                name="user_auth_methods",
                ok=oauth_ok,
                detail="supported="
                + ",".join(str(m) for m in methods)
                + f"; configured={configured}",
            )
        )
        if not oauth_ok:
            return ConnectionTestOutput(
                ok=False,
                stages=stages,
                protocol=PROTOCOL,
                unsupported_reason="user_auth_method_unsupported",
            )
        return ConnectionTestOutput(ok=True, stages=stages, protocol=PROTOCOL)

    def _require_scope(self, actor: PluginActor) -> tuple[str, str]:
        if not actor.agent_id or not actor.thread_id:
            raise _err("SCOPE_REQUIRED", "verified agent and thread context is required", 403)
        return actor.agent_id, actor.thread_id

    def _form_ref_for_action(self, data: dict[str, Any], action: str) -> str:
        if action != "view_detail":
            return str(data["form_ref"])
        nav = data.get("navigation") or {}
        ref = nav.get("form_ref") or nav.get("formRef")
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
        current = str(data["form_ref"])
        if current.endswith(".edit"):
            return current[: -len(".edit")] + ".detail"
        if current.endswith(".detail"):
            return current
        return current + ".detail"

    async def claim(self, actor: PluginActor, payload: ClaimInput) -> ClaimOutput:
        actor = await self._actor(actor, "authenticated")
        agent_id, thread_id = self._require_scope(actor)
        if "/" in payload.form_ref or payload.form_ref.lower().startswith("http"):
            raise _err("INVALID_FORM_REF", "formRef must be a registry name, not a URL")
        conn = await self._load_enabled(payload.connection_id)
        await self._user_access_token(actor, conn)
        issuer = str(conn.get("instance_issuer") or await self.instance_issuer())
        if not issuer:
            raise _err("INSTANCE_UNCONFIGURED", "instance issuer is not configured", 403)
        bind_key = _bind_key(agent_id, thread_id, payload.call_id)
        existing_bind = await self._facade.get_record(CALL_BINDS, bind_key)
        if existing_bind is not None:
            if int(existing_bind.payload.get("user_id")) != actor.user_id:
                raise _err("ACCESS_DENIED", "call is bound to another user", 403)
            if existing_bind.payload.get("thread_id") != thread_id:
                raise _err("ACCESS_DENIED", "call is bound to another thread", 403)
            interaction_id = str(existing_bind.payload["interaction_id"])
            record = await self._facade.get_record(INTERACTIONS, interaction_id)
            if record is None:
                raise _err("NOT_FOUND", "interaction missing", 404)
            bind_token = str(record.payload["bind_token"])
            return ClaimOutput(
                **self._state_from_payload(record.payload).model_dump(),
                bind_token=bind_token,
            )
        interaction_id = f"int-{uuid4()}"
        bind_token = secrets.token_urlsafe(32)
        state = {
            "interaction_id": interaction_id,
            "call_id": payload.call_id,
            "connection_id": payload.connection_id,
            "document_type": payload.document_type,
            "form_ref": payload.form_ref,
            "schema_version": payload.schema_version,
            "record_id": payload.record_id,
            "record_version": payload.record_version,
            "allowed_actions": ["edit", "save", "submit", "cancel"],
            "submission_status": "draft",
            "approval_status": "not_applicable",
            "summary": payload.summary if isinstance(payload.summary, dict) else {},
            "user_id": actor.user_id,
            "agent_id": agent_id,
            "thread_id": thread_id,
            "bind_token": bind_token,
            "instance_issuer": issuer,
            "namespaced_sub": namespaced_actor(issuer, actor.user_id)["sub"],
            "last_operation_id": None,
            "last_error": None,
            "navigation": None,
        }
        await self._commit(
            [
                RecordWrite(INTERACTIONS, interaction_id, actor.user_id, state, 0),
                RecordWrite(
                    CALL_BINDS,
                    bind_key,
                    actor.user_id,
                    {
                        "interaction_id": interaction_id,
                        "user_id": actor.user_id,
                        "agent_id": agent_id,
                        "thread_id": thread_id,
                        "call_id": payload.call_id,
                    },
                    0,
                ),
            ]
        )
        return ClaimOutput(**self._state_from_payload(state).model_dump(), bind_token=bind_token)

    def _state_from_payload(self, payload: dict[str, Any]) -> InteractionStateOutput:
        return InteractionStateOutput(
            interaction_id=str(payload["interaction_id"]),
            call_id=str(payload["call_id"]),
            connection_id=str(payload["connection_id"]),
            document_type=str(payload["document_type"]),
            record_id=payload.get("record_id"),
            form_ref=str(payload["form_ref"]),
            schema_version=str(payload["schema_version"]),
            record_version=int(payload.get("record_version") or 0),
            allowed_actions=list(payload.get("allowed_actions") or []),
            submission_status=str(payload.get("submission_status") or "draft"),
            approval_status=str(payload.get("approval_status") or "not_applicable"),
            summary=dict(payload.get("summary") or {}),
            last_operation_id=payload.get("last_operation_id"),
            last_error=payload.get("last_error"),
            navigation=payload.get("navigation"),
        )

    async def _load_owned(
        self, actor: PluginActor, payload: InteractionRefInput
    ) -> tuple[Any, dict[str, Any]]:
        agent_id, thread_id = self._require_scope(actor)
        record = await self._facade.get_record(INTERACTIONS, payload.interaction_id)
        if record is None:
            raise _err("NOT_FOUND", "interaction not found", 404)
        data = dict(record.payload)
        if int(data.get("user_id")) != actor.user_id:
            raise _err("ACCESS_DENIED", "interaction owned by another user", 403)
        if data.get("agent_id") != agent_id or data.get("thread_id") != thread_id:
            raise _err("ACCESS_DENIED", "interaction is not in this thread", 403)
        if data.get("call_id") != payload.call_id:
            raise _err("ACCESS_DENIED", "callId does not match this interaction", 403)
        return record, data

    async def get_interaction(
        self, actor: PluginActor, payload: InteractionRefInput
    ) -> InteractionStateOutput:
        actor = await self._actor(actor, "authenticated")
        record, data = await self._load_owned(actor, payload)
        conn = await self._load_enabled(str(data["connection_id"]))
        issuer = str(data.get("instance_issuer") or await self.instance_issuer())
        refreshed = await self._pull_receipt(actor, conn, data, issuer)
        if refreshed != data:
            await self._commit(
                [
                    RecordWrite(
                        INTERACTIONS,
                        record.logical_key,
                        record.owner_user_id,
                        refreshed,
                        record.revision,
                    )
                ],
                checks=[
                    RecordCheck(INTERACTIONS, record.logical_key, record.revision),
                ],
            )
            data = refreshed
        return self._state_from_payload(data)

    async def cancel(
        self, actor: PluginActor, payload: InteractionRefInput
    ) -> InteractionStateOutput:
        actor = await self._actor(actor, "authenticated")
        record, data = await self._load_owned(actor, payload)
        if data.get("submission_status") == "submitted":
            raise _err("INVALID", "submitted interactions cannot be cancelled")
        data["submission_status"] = "cancelled"
        data["allowed_actions"] = []
        await self._commit(
            [
                RecordWrite(
                    INTERACTIONS, record.logical_key, record.owner_user_id, data, record.revision
                )
            ]
        )
        return self._state_from_payload(data)

    async def issue_ticket(
        self, actor: PluginActor, payload: TicketIssueInput
    ) -> TicketIssueOutput:
        actor = await self._actor(actor, "authenticated")
        _record, data = await self._load_owned(actor, payload)
        if data.get("submission_status") == "cancelled":
            raise _err("INVALID", "cancelled interaction")
        if payload.action == "view_detail" and data.get("submission_status") != "submitted":
            raise _err("INVALID", "detail is only available after submit")
        conn = await self._load_enabled(str(data["connection_id"]))
        bundle = await self._secret_bundle(conn)
        token = await self._user_access_token(actor, conn)
        issuer = str(data.get("instance_issuer") or await self.instance_issuer())
        exceptions = parse_exception_list(list(conn.get("private_allow") or []))
        extra = list(conn.get("extra_origins") or [])
        nonce = secrets.token_urlsafe(16)
        client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
        try:
            status, body, _text = request_json(
                client,
                "POST",
                urljoin(conn["base_url"] + "/", "v1/tickets"),
                token=token,
                body={
                    "protocol": PROTOCOL,
                    "subject": namespaced_actor(issuer, actor.user_id),
                    "form_ref": self._form_ref_for_action(data, payload.action),
                    "record_id": data.get("record_id"),
                    "schema_version": data["schema_version"],
                    "record_version": data.get("record_version") or 0,
                    "action": payload.action,
                    "interaction_id": data["interaction_id"],
                    "nonce": nonce,
                    "connection_id": data["connection_id"],
                },
                base_url=conn["base_url"],
                extra_origins=extra,
                private_exceptions=exceptions,
            )
        except AdapterError as exc:
            raise _err(exc.code.upper(), exc.message, exc.status) from exc
        finally:
            client.close()
        if status != 200 or not body or not body.get("ticket") or not body.get("redeem_url"):
            raise _err("TICKET_FAILED", "adapter refused to issue a page ticket", 502)
        redeem_url = str(body["redeem_url"])
        try:
            validate_https_url_syntax(redeem_url)
            if not same_origin(redeem_url, conn["base_url"]) and origin_of(redeem_url) not in {
                origin_of(item) for item in extra
            }:
                raise UnsafeUrl("redeem url origin is not approved")
            resolve_and_authorize(redeem_url, private_exceptions=exceptions)
        except UnsafeUrl as exc:
            raise _err("UNSAFE_URL", str(exc)) from exc
        mode = "readonly" if payload.action == "view_detail" else "edit"
        return TicketIssueOutput(
            redeem_url=redeem_url,
            ticket=str(body["ticket"]),
            expires_in=int(body.get("expires_in") or 120),
            nonce=nonce,
            form_origin=origin_of(redeem_url),
            page_mode=mode,  # type: ignore[arg-type]
            form_ref=str(body.get("form_ref") or data["form_ref"]),
        )

    async def _pull_receipt(
        self,
        actor: PluginActor,
        conn: dict[str, Any],
        data: dict[str, Any],
        issuer: str,
    ) -> dict[str, Any]:
        bundle = await self._secret_bundle(conn)
        try:
            token = await self._user_access_token(actor, conn)
        except PluginActionError:
            return data
        exceptions = parse_exception_list(list(conn.get("private_allow") or []))
        extra = list(conn.get("extra_origins") or [])
        client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
        url = urljoin(conn["base_url"] + "/", f"v1/interactions/{data['interaction_id']}")
        try:
            status, body, _text = request_json(
                client,
                "POST",
                url,
                token=token,
                body={
                    "protocol": PROTOCOL,
                    "subject": namespaced_actor(issuer, actor.user_id),
                    "call_id": data["call_id"],
                },
                base_url=conn["base_url"],
                extra_origins=extra,
                private_exceptions=exceptions,
            )
        except AdapterError:
            return data
        finally:
            client.close()
        if status != 200 or not isinstance(body, dict) or not body.get("success"):
            return data
        if body.get("interaction_id") != data["interaction_id"]:
            return data
        if (
            body.get("subject_sub")
            and body["subject_sub"] != namespaced_actor(issuer, actor.user_id)["sub"]
        ):
            return data
        next_state = dict(data)
        if body.get("status"):
            next_state["submission_status"] = str(body["status"])
        if body.get("approval_status"):
            next_state["approval_status"] = str(body["approval_status"])
        if "record_id" in body:
            next_state["record_id"] = body.get("record_id")
        if body.get("record_version") is not None:
            next_state["record_version"] = int(body["record_version"])
        if body.get("operation_id"):
            next_state["last_operation_id"] = str(body["operation_id"])
        if body.get("navigation"):
            next_state["navigation"] = body["navigation"]
        if next_state.get("submission_status") == "submitted":
            next_state["allowed_actions"] = ["view_detail"]
            next_state["last_error"] = body.get("detail_error")
        return next_state

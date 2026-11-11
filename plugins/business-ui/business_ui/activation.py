"""Per-user activation: OAuth2+PKCE, native login, or personal access token."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

from octop.infra.agents.plugins.host_contracts import (
    CredentialActivation,
    CredentialDeletion,
    PluginActionError,
    PluginActor,
    PluginHostError,
    RecordWrite,
)

from .models import (
    ActivationCompleteInput,
    ActivationDisconnectOutput,
    ActivationNativeInput,
    ActivationPatInput,
    ActivationStartOutput,
    ActivationStatusOutput,
    ConnectionIdInput,
)
from .oauth import (
    OAUTH_PENDING_TTL,
    build_authorization_url,
    new_pkce_pair,
    new_state,
    parse_discovery,
)
from .outbound import AdapterError, build_client, request_form, request_json
from .security import (
    UnsafeUrl,
    parse_exception_list,
    resolve_and_authorize,
    validate_https_url_syntax,
)

ACTIVATIONS = "activations"
OAUTH_PENDING = "oauth_pending"


def _err(code: str, message: str, status: int = 400) -> PluginActionError:
    return PluginActionError(code, message, status=status)


def namespaced_actor(instance_issuer: str, user_id: int) -> dict[str, str]:
    return {"issuer": instance_issuer, "sub": f"{instance_issuer}|{user_id}"}


def activation_key(user_id: int, connection_id: str) -> str:
    return f"u{user_id}-{connection_id}"


class ActivationMixin:
    async def _oauth_urls(self, conn: dict[str, Any], bundle: dict[str, Any]) -> dict[str, str]:
        exceptions = parse_exception_list(list(conn.get("private_allow") or []))
        extra = list(conn.get("extra_origins") or [])
        discovery = str(conn.get("oauth_discovery_url") or "")
        authorize = str(conn.get("oauth_authorize_url") or "")
        token = str(conn.get("oauth_token_url") or "")
        revoke = str(conn.get("oauth_revoke_url") or "")
        if discovery:
            client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
            try:
                status, body, _text = request_json(
                    client,
                    "GET",
                    discovery,
                    token="",
                    body=None,
                    base_url=conn["base_url"],
                    extra_origins=extra,
                    private_exceptions=exceptions,
                )
            finally:
                client.close()
            if status != 200 or not body:
                raise _err("DISCOVERY_FAILED", "oauth discovery failed", 502)
            try:
                parsed = parse_discovery(body)
            except ValueError as exc:
                raise _err("DISCOVERY_FAILED", str(exc), 502) from exc
            authorize = parsed["authorize_url"]
            token = parsed["token_url"]
            revoke = parsed.get("revoke_url") or revoke
        if not authorize or not token:
            raise _err("OAUTH_UNCONFIGURED", "authorize and token URLs are required")
        for url in (authorize, token, *([revoke] if revoke else [])):
            try:
                validate_https_url_syntax(url)
                resolve_and_authorize(url, private_exceptions=exceptions)
            except UnsafeUrl as exc:
                raise _err("UNSAFE_URL", str(exc)) from exc
        return {"authorize_url": authorize, "token_url": token, "revoke_url": revoke}

    async def _activation_row(self, actor: PluginActor, connection_id: str) -> Any:
        return await self._facade.get_record(
            ACTIVATIONS, activation_key(actor.user_id, connection_id)
        )

    async def activation_public(
        self,
        actor: PluginActor,
        connection_id: str,
        *,
        config_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        record = await self._activation_row(actor, connection_id)
        if record is None or record.payload.get("status") in {
            None,
            "revoked",
            "pending",
            "stale_config",
        }:
            return {"activation_status": "inactive"}
        stored_fp = str(record.payload.get("config_fingerprint") or "")
        if config_fingerprint and stored_fp != config_fingerprint:
            return {"activation_status": "inactive"}
        expires = record.payload.get("expires_at")
        status = str(record.payload.get("status") or "inactive")
        if status == "active" and expires and int(expires) < int(time.time()):
            status = "expired"
        return {
            "activation_status": status,
            "activation_method": record.payload.get("method"),
            "expires_at": expires,
        }

    async def _store_user_tokens(
        self,
        actor: PluginActor,
        conn: dict[str, Any],
        tokens: dict[str, Any],
        method: str,
        extra_deletions: list[CredentialDeletion] | None = None,
    ) -> None:
        access = str(tokens.get("access_token") or "")
        if not access:
            raise _err("TOKEN_FAILED", "authorization server returned no access_token", 502)
        expires_in = int(tokens.get("expires_in") or 3600)
        expires_at = int(time.time()) + max(expires_in, 60)
        existing = await self._activation_row(actor, conn["connection_id"])
        deletions = list(extra_deletions or [])
        if existing and existing.payload.get("credential_id"):
            deletions.append(
                CredentialDeletion(
                    str(existing.payload["credential_id"]),
                    actor.user_id,
                    int(existing.payload.get("credential_revision") or 2),
                )
            )
        new_id = await self._facade.stage_credential(
            actor.user_id,
            {
                "kind": "user_token",
                "access_token": access,
                "refresh_token": tokens.get("refresh_token"),
                "token_type": tokens.get("token_type") or "Bearer",
                "expires_at": expires_at,
                "connection_id": conn["connection_id"],
            },
        )
        expected = existing.revision if existing is not None else 0
        await self._commit(
            [
                RecordWrite(
                    ACTIVATIONS,
                    activation_key(actor.user_id, conn["connection_id"]),
                    actor.user_id,
                    {
                        "connection_id": conn["connection_id"],
                        "user_id": actor.user_id,
                        "status": "active",
                        "method": method,
                        "credential_id": new_id,
                        "credential_revision": 2,
                        "expires_at": expires_at,
                        "config_fingerprint": conn.get("config_fingerprint"),
                    },
                    expected,
                )
            ],
            [CredentialActivation(new_id, actor.user_id, 1)],
            deletions=deletions,
        )

    async def _user_access_token(self, actor: PluginActor, conn: dict[str, Any]) -> str:
        record = await self._activation_row(actor, conn["connection_id"])
        if record is None or record.payload.get("status") != "active":
            raise _err("ACTIVATION_REQUIRED", "需要激活/重新激活", 403)
        stored_fp = str(record.payload.get("config_fingerprint") or "")
        current_fp = str(conn.get("config_fingerprint") or "")
        if current_fp and stored_fp != current_fp:
            raise _err("ACTIVATION_REQUIRED", "需要激活/重新激活", 403)
        if int(record.payload.get("user_id") or 0) != actor.user_id:
            raise _err("ACCESS_DENIED", "activation belongs to another user", 403)
        try:
            bundle = await self._facade.resolve_credential(
                str(record.payload["credential_id"]), actor.user_id
            )
        except PluginHostError as exc:
            raise _err("ACTIVATION_REQUIRED", "需要激活/重新激活", 403) from exc
        expires_at = int(bundle.get("expires_at") or record.payload.get("expires_at") or 0)
        token = str(bundle.get("access_token") or "")
        if expires_at and expires_at < int(time.time()) + 30:
            refresh = str(bundle.get("refresh_token") or "")
            if not refresh:
                raise _err("ACTIVATION_REQUIRED", "需要激活/重新激活", 403)
            token = await self._refresh_user_token(actor, conn, record, bundle)
        if not token:
            raise _err("ACTIVATION_REQUIRED", "需要激活/重新激活", 403)
        return token

    async def _refresh_user_token(
        self, actor: PluginActor, conn: dict[str, Any], record: Any, bundle: dict[str, Any]
    ) -> str:
        service = await self._secret_bundle(conn)
        urls = await self._oauth_urls(conn, service)
        if not urls.get("token_url"):
            raise _err("ACTIVATION_REQUIRED", "需要激活/重新激活", 403)
        exceptions = parse_exception_list(list(conn.get("private_allow") or []))
        extra = list(conn.get("extra_origins") or [])
        client = build_client(tls_ca_pem=service.get("tls_ca_pem"))
        fields = {
            "grant_type": "refresh_token",
            "refresh_token": str(bundle.get("refresh_token") or ""),
            "client_id": str(conn.get("oauth_client_id") or service.get("oauth_client_id") or ""),
        }
        secret = str(service.get("oauth_client_secret") or "")
        if secret:
            fields["client_secret"] = secret
        try:
            status, body, _text = request_form(
                client,
                urls["token_url"],
                token="",
                fields=fields,
                base_url=conn["base_url"],
                extra_origins=extra,
                private_exceptions=exceptions,
            )
        except AdapterError as exc:
            raise _err("ACTIVATION_REQUIRED", "需要激活/重新激活", 403) from exc
        finally:
            client.close()
        if status != 200 or not body or not body.get("access_token"):
            raise _err("ACTIVATION_REQUIRED", "需要激活/重新激活", 403)
        merged = {
            "access_token": body["access_token"],
            "refresh_token": body.get("refresh_token") or bundle.get("refresh_token"),
            "expires_in": body.get("expires_in") or 3600,
            "token_type": body.get("token_type") or "Bearer",
        }
        await self._store_user_tokens(
            actor, conn, merged, str(record.payload.get("method") or "oauth2")
        )
        return str(merged["access_token"])

    async def start_activation(
        self, actor: PluginActor, payload: ConnectionIdInput
    ) -> ActivationStartOutput:
        actor = await self._actor(actor, "authenticated")
        conn = await self._load_enabled(payload.connection_id)
        method = str(conn.get("user_auth_method") or "oauth2")
        if method != "oauth2":
            return ActivationStartOutput(
                connection_id=conn["connection_id"],
                method=method,  # type: ignore[arg-type]
                status="awaiting_credentials",
            )
        bundle = await self._secret_bundle(conn)
        urls = await self._oauth_urls(conn, bundle)
        client_id = str(conn.get("oauth_client_id") or bundle.get("oauth_client_id") or "")
        if not client_id:
            raise _err("OAUTH_UNCONFIGURED", "oauth client_id is required")
        redirect_uri = urljoin(conn["base_url"] + "/", "v1/oauth/callback")
        try:
            validate_https_url_syntax(redirect_uri)
        except UnsafeUrl as exc:
            raise _err("UNSAFE_URL", str(exc)) from exc
        state = new_state()
        verifier, challenge = new_pkce_pair()
        verifier_id = await self._facade.stage_credential(
            actor.user_id,
            {
                "kind": "pkce_verifier",
                "verifier": verifier,
                "state": state,
                "connection_id": conn["connection_id"],
                "redirect_uri": redirect_uri,
            },
        )
        await self._commit(
            [
                RecordWrite(
                    OAUTH_PENDING,
                    state,
                    actor.user_id,
                    {
                        "user_id": actor.user_id,
                        "connection_id": conn["connection_id"],
                        "redirect_uri": redirect_uri,
                        "verifier_credential_id": verifier_id,
                        "expires_at": int(time.time()) + OAUTH_PENDING_TTL,
                        "consumed": False,
                    },
                    0,
                )
            ],
            [CredentialActivation(verifier_id, actor.user_id, 1)],
        )
        auth_url = build_authorization_url(
            urls["authorize_url"],
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=challenge,
            scopes=str(conn.get("oauth_scopes") or "openid profile"),
        )
        return ActivationStartOutput(
            connection_id=conn["connection_id"],
            method="oauth2",
            authorization_url=auth_url,
            state=state,
            expires_in=OAUTH_PENDING_TTL,
            popup=True,
            status="pending",
        )

    async def complete_activation(
        self, actor: PluginActor, payload: ActivationCompleteInput
    ) -> ActivationStatusOutput:
        actor = await self._actor(actor, "authenticated")
        pending = await self._facade.get_record(OAUTH_PENDING, payload.state)
        if pending is None:
            raise _err("INVALID_STATE", "unknown or expired activation state", 403)
        data = dict(pending.payload)
        if int(data.get("user_id") or 0) != actor.user_id:
            raise _err("ACCESS_DENIED", "state belongs to another user", 403)
        if data.get("consumed"):
            raise _err("REPLAY", "activation state already used", 409)
        if int(data.get("expires_at") or 0) < int(time.time()):
            raise _err("EXPIRED", "activation state expired", 403)
        conn = await self._load_enabled(str(data["connection_id"]))
        bundle = await self._secret_bundle(conn)
        try:
            verifier_bundle = await self._facade.resolve_credential(
                str(data["verifier_credential_id"]), actor.user_id
            )
        except PluginHostError as exc:
            raise _err("INVALID_STATE", "pkce verifier missing", 403) from exc
        if verifier_bundle.get("state") != payload.state:
            raise _err("INVALID_STATE", "pkce verifier mismatch", 403)
        exceptions = parse_exception_list(list(conn.get("private_allow") or []))
        extra = list(conn.get("extra_origins") or [])
        client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
        try:
            status, body, _text = request_json(
                client,
                "POST",
                urljoin(conn["base_url"] + "/", "v1/oauth/consume"),
                token=str(bundle.get("secret") or ""),
                body={"state": payload.state, "protocol": "business-ui.v1"},
                base_url=conn["base_url"],
                extra_origins=extra,
                private_exceptions=exceptions,
            )
        except AdapterError as exc:
            if exc.code == "upstream" or exc.status == 404:
                return ActivationStatusOutput(
                    connection_id=conn["connection_id"], status="pending", method="oauth2"
                )
            raise _err(exc.code.upper(), exc.message, exc.status) from exc
        finally:
            client.close()
        if status == 404 or (body and body.get("pending")):
            return ActivationStatusOutput(
                connection_id=conn["connection_id"], status="pending", method="oauth2"
            )
        if status != 200 or not body or not body.get("code"):
            raise _err("TOKEN_FAILED", "authorization code was not available", 502)
        urls = await self._oauth_urls(conn, bundle)
        client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
        fields = {
            "grant_type": "authorization_code",
            "code": str(body["code"]),
            "redirect_uri": str(data["redirect_uri"]),
            "code_verifier": str(verifier_bundle.get("verifier") or ""),
            "client_id": str(conn.get("oauth_client_id") or bundle.get("oauth_client_id") or ""),
        }
        secret = str(bundle.get("oauth_client_secret") or "")
        if secret:
            fields["client_secret"] = secret
        try:
            t_status, t_body, _t = request_form(
                client,
                urls["token_url"],
                token="",
                fields=fields,
                base_url=conn["base_url"],
                extra_origins=extra,
                private_exceptions=exceptions,
            )
        except AdapterError as exc:
            raise _err("TOKEN_FAILED", exc.message, 502) from exc
        finally:
            client.close()
        if t_status != 200 or not t_body:
            raise _err("TOKEN_FAILED", "token endpoint rejected the code", 502)
        await self._commit(
            [
                RecordWrite(
                    OAUTH_PENDING,
                    payload.state,
                    pending.owner_user_id,
                    {**data, "consumed": True},
                    pending.revision,
                )
            ],
            deletions=[
                CredentialDeletion(str(data["verifier_credential_id"]), actor.user_id, 2),
            ],
        )
        await self._store_user_tokens(actor, conn, t_body, "oauth2")
        stored = await self._activation_row(actor, conn["connection_id"])
        return ActivationStatusOutput(
            connection_id=conn["connection_id"],
            status="active",
            method="oauth2",
            expires_at=None if stored is None else stored.payload.get("expires_at"),
        )

    async def native_activation(
        self, actor: PluginActor, payload: ActivationNativeInput
    ) -> ActivationStatusOutput:
        actor = await self._actor(actor, "authenticated")
        conn = await self._load_enabled(payload.connection_id)
        if str(conn.get("user_auth_method") or "") != "native_login":
            raise _err("METHOD_MISMATCH", "connection is not native_login")
        bundle = await self._secret_bundle(conn)
        issuer = str(conn.get("instance_issuer") or await self.instance_issuer())
        exceptions = parse_exception_list(list(conn.get("private_allow") or []))
        extra = list(conn.get("extra_origins") or [])
        client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
        try:
            status, body, _text = request_json(
                client,
                "POST",
                urljoin(conn["base_url"] + "/", "v1/auth/native"),
                token=str(bundle.get("secret") or ""),
                body={
                    "protocol": "business-ui.v1",
                    "username": payload.username,
                    "password": payload.password,
                    "subject": namespaced_actor(issuer, actor.user_id),
                },
                base_url=conn["base_url"],
                extra_origins=extra,
                private_exceptions=exceptions,
            )
        except AdapterError as exc:
            raise _err("AUTH_FAILED", "native login failed", 401) from exc
        finally:
            client.close()
        if status in {401, 403}:
            raise _err("AUTH_FAILED", "native login failed", 401)
        if status != 200 or not body or not body.get("access_token"):
            raise _err("TOKEN_FAILED", "adapter did not return a user token", 502)
        await self._store_user_tokens(actor, conn, body, "native_login")
        stored = await self._activation_row(actor, conn["connection_id"])
        return ActivationStatusOutput(
            connection_id=conn["connection_id"],
            status="active",
            method="native_login",
            expires_at=None if stored is None else stored.payload.get("expires_at"),
        )

    async def pat_activation(
        self, actor: PluginActor, payload: ActivationPatInput
    ) -> ActivationStatusOutput:
        actor = await self._actor(actor, "authenticated")
        conn = await self._load_enabled(payload.connection_id)
        if str(conn.get("user_auth_method") or "") != "personal_access_token":
            raise _err("METHOD_MISMATCH", "connection is not personal_access_token")
        bundle = await self._secret_bundle(conn)
        issuer = str(conn.get("instance_issuer") or await self.instance_issuer())
        exceptions = parse_exception_list(list(conn.get("private_allow") or []))
        extra = list(conn.get("extra_origins") or [])
        client = build_client(tls_ca_pem=bundle.get("tls_ca_pem"))
        try:
            status, body, _text = request_json(
                client,
                "POST",
                urljoin(conn["base_url"] + "/", "v1/auth/pat"),
                token=str(bundle.get("secret") or ""),
                body={
                    "protocol": "business-ui.v1",
                    "access_token": payload.access_token,
                    "subject": namespaced_actor(issuer, actor.user_id),
                },
                base_url=conn["base_url"],
                extra_origins=extra,
                private_exceptions=exceptions,
            )
        except AdapterError as exc:
            raise _err("AUTH_FAILED", "personal access token rejected", 401) from exc
        finally:
            client.close()
        if status in {401, 403}:
            raise _err("AUTH_FAILED", "personal access token rejected", 401)
        if status != 200 or not body or body.get("ok") is not True:
            raise _err("AUTH_FAILED", "personal access token rejected", 401)
        await self._store_user_tokens(
            actor,
            conn,
            {
                "access_token": payload.access_token,
                "expires_in": body.get("expires_in") or 86400,
                "token_type": "Bearer",
            },
            "personal_access_token",
        )
        stored = await self._activation_row(actor, conn["connection_id"])
        return ActivationStatusOutput(
            connection_id=conn["connection_id"],
            status="active",
            method="personal_access_token",
            expires_at=None if stored is None else stored.payload.get("expires_at"),
        )

    async def disconnect_activation(
        self, actor: PluginActor, payload: ConnectionIdInput
    ) -> ActivationDisconnectOutput:
        actor = await self._actor(actor, "authenticated")
        record = await self._activation_row(actor, payload.connection_id)
        if record is None:
            return ActivationDisconnectOutput(disconnected=True)
        deletions: list[CredentialDeletion] = []
        cred_id = record.payload.get("credential_id")
        if cred_id:
            deletions.append(
                CredentialDeletion(
                    str(cred_id), actor.user_id, int(record.payload.get("credential_revision") or 2)
                )
            )
            try:
                bundle = await self._facade.resolve_credential(str(cred_id), actor.user_id)
            except PluginHostError:
                bundle = {}
            conn_row = await self._facade.get_record("connections", payload.connection_id)
            if (
                conn_row is not None
                and bundle.get("access_token")
                and str(conn_row.payload.get("user_auth_method") or "") == "oauth2"
            ):
                conn = {**conn_row.payload, "owner_user_id": conn_row.owner_user_id}
                try:
                    service = await self._secret_bundle(conn)
                    urls = await self._oauth_urls(conn, service)
                    if urls.get("revoke_url"):
                        client = build_client(tls_ca_pem=service.get("tls_ca_pem"))
                        try:
                            request_form(
                                client,
                                urls["revoke_url"],
                                token="",
                                fields={
                                    "token": str(bundle.get("access_token") or ""),
                                    "client_id": str(conn.get("oauth_client_id") or ""),
                                },
                                base_url=conn["base_url"],
                                extra_origins=list(conn.get("extra_origins") or []),
                                private_exceptions=parse_exception_list(
                                    list(conn.get("private_allow") or [])
                                ),
                            )
                        except (AdapterError, UnsafeUrl):
                            pass
                        finally:
                            client.close()
                except (AdapterError, PluginActionError, PluginHostError, UnsafeUrl):
                    pass
        await self._commit(
            [
                RecordWrite(
                    ACTIVATIONS,
                    record.logical_key,
                    actor.user_id,
                    {
                        **{k: v for k, v in record.payload.items() if k != "credential_id"},
                        "status": "revoked",
                        "credential_id": None,
                    },
                    record.revision,
                )
            ],
            deletions=deletions,
        )
        return ActivationDisconnectOutput(disconnected=True)

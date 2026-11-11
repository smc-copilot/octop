"""In-process reference adapter implementing business-ui.v1.

This is a protocol fixture, not a customer ERP. Recruitment formRefs exist only
as sample registry entries here.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

PROTOCOL = "business-ui.v1"
TICKET_TTL = 120

FORMS = {
    "generic.request.edit": {"mode": "edit", "title": "Generic request"},
    "generic.request.detail": {"mode": "readonly", "title": "Generic request (official)"},
    "recruitment.request.edit": {"mode": "edit", "title": "Recruitment request"},
    "recruitment.request.detail": {"mode": "readonly", "title": "Recruitment request (official)"},
}


class AdapterState:
    def __init__(
        self,
        connection_token: str,
        *,
        fail_detail: bool = False,
        oauth_client_id: str = "bui-client",
        oauth_client_secret: str = "bui-secret",
    ) -> None:
        self.connection_token = connection_token
        self.fail_detail = fail_detail
        self.oauth_client_id = oauth_client_id
        self.oauth_client_secret = oauth_client_secret
        self.tickets: dict[str, dict[str, Any]] = {}
        self.used_tickets: set[str] = set()
        self.sessions: dict[str, dict[str, Any]] = {}
        self.interactions: dict[str, dict[str, Any]] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self.oauth_authz: dict[str, dict[str, Any]] = {}
        self.oauth_codes: dict[str, dict[str, Any]] = {}
        self.oauth_by_state: dict[str, str] = {}
        self.user_tokens: dict[str, dict[str, Any]] = {}
        self.refresh_tokens: dict[str, str] = {}
        self.revoked: set[str] = set()
        self.native_users = {"demo": "demo-pass"}
        self.supported_user_auth_methods = [
            "oauth2",
            "native_login",
            "personal_access_token",
        ]
        self.submit_outcome = "success"
        self.seed_record_id: str | None = None
        self.query_resolves_to = "success"
        self.receipt_sequence = 0
        self.delay_receipt = False

    def next_sequence(self) -> int:
        self.receipt_sequence += 1
        return self.receipt_sequence

    def auth_ok(self, header: str) -> bool:
        if not header.startswith("Bearer "):
            return False
        return header.removeprefix("Bearer ").strip() == self.connection_token

    def user_ok(self, header: str) -> dict[str, Any] | None:
        if not header.startswith("Bearer "):
            return None
        token = header.removeprefix("Bearer ").strip()
        if token in self.revoked:
            return None
        meta = self.user_tokens.get(token)
        if meta is None or float(meta.get("exp") or 0) < time.time():
            return None
        return meta

    def issue_user_token(self, sub: str, *, expires: int = 3600) -> dict[str, Any]:
        access = secrets.token_urlsafe(24)
        refresh = secrets.token_urlsafe(24)
        self.user_tokens[access] = {"sub": sub, "exp": time.time() + expires, "refresh": refresh}
        self.refresh_tokens[refresh] = access
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": expires,
            "token_type": "Bearer",
        }


def _json(handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
    raw = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(raw)))
    handler.send_header("cache-control", "private, no-store")
    handler.end_headers()
    handler.wfile.write(raw)


def _html(
    handler: BaseHTTPRequestHandler, status: int, body: str, *, cookie: str | None = None
) -> None:
    raw = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "text/html; charset=utf-8")
    handler.send_header("content-length", str(len(raw)))
    handler.send_header("cache-control", "private, no-store")
    handler.send_header(
        "content-security-policy",
        "frame-ancestors *; default-src 'self'; script-src 'self' 'unsafe-inline'",
    )
    if cookie:
        handler.send_header("set-cookie", cookie)
    handler.end_headers()
    handler.wfile.write(raw)


def make_handler(state: AdapterState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("content-length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                loaded = json.loads(raw.decode("utf-8"))
            except ValueError:
                return {}
            return loaded if isinstance(loaded, dict) else {}

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/v1/tickets/redeem":
                self._redeem()
                return
            if path == "/v1/documents/save":
                self._mutate("save")
                return
            if path == "/v1/documents/submit":
                self._mutate("submit")
                return
            if path == "/v1/oauth/approve":
                self._oauth_approve()
                return
            if path == "/v1/oauth/token":
                self._oauth_token()
                return
            if path == "/v1/oauth/revoke":
                self._oauth_revoke()
                return
            if not state.auth_ok(self.headers.get("authorization") or ""):
                if (
                    path in {"/v1/tickets"}
                    or path.startswith("/v1/interactions/")
                    or path.startswith("/v1/operations/")
                ):
                    if state.user_ok(self.headers.get("authorization") or "") is None:
                        _json(self, 401, {"ok": False, "error": "auth_failed"})
                        return
                else:
                    _json(self, 401, {"ok": False, "error": "auth_failed"})
                    return
            if path == "/v1/handshake":
                self._handshake()
                return
            if path == "/v1/oauth/consume":
                self._oauth_consume()
                return
            if path == "/v1/auth/native":
                self._native()
                return
            if path == "/v1/auth/pat":
                self._pat()
                return
            if path == "/v1/tickets":
                if state.user_ok(self.headers.get("authorization") or "") is None:
                    _json(self, 401, {"ok": False, "error": "user_token_required"})
                    return
                self._issue_ticket()
                return
            if path.startswith("/v1/interactions/"):
                if state.user_ok(self.headers.get("authorization") or "") is None:
                    _json(self, 401, {"ok": False, "error": "user_token_required"})
                    return
                self._get_interaction(path.rsplit("/", 1)[-1])
                return
            if path.startswith("/v1/operations/"):
                if state.user_ok(self.headers.get("authorization") or "") is None:
                    _json(self, 401, {"ok": False, "error": "user_token_required"})
                    return
                rest = path[len("/v1/operations/") :]
                if rest.endswith("/retry"):
                    self._retry_operation(rest[: -len("/retry")])
                    return
                self._query_operation(rest)
                return
            _json(self, 404, {"ok": False, "error": "not_found"})

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path in {"/.well-known/oauth-authorization-server", "/v1/oauth/discovery"}:
                self._discovery()
                return
            if path == "/v1/oauth/authorize":
                self._oauth_authorize()
                return
            if path == "/v1/oauth/callback":
                self._oauth_callback()
                return
            _html(self, 404, "<html><body>not a business-ui adapter GET</body></html>")

        def _handshake(self) -> None:
            body = self._read_json()
            if body.get("destructive") is True:
                _json(self, 400, {"ok": False, "error": "destructive_not_allowed"})
                return
            _json(
                self,
                200,
                {
                    "protocol": PROTOCOL,
                    "ok": True,
                    "kind": "business-ui-adapter",
                    "service": {"name": "reference-adapter", "environment": "fixture"},
                    "auth": {"identity": "connection", "mode": "bearer"},
                    "features": {
                        "form_registry": True,
                        "tickets": True,
                        "receipts": True,
                        "interactions": True,
                        "user_auth_methods": list(state.supported_user_auth_methods),
                        "oauth_authorization_code": True,
                        "oauth_pkce_s256": True,
                        "receipt_schema_v11": True,
                        "query_status": True,
                        "safe_retry": True,
                    },
                    "operation_path": "/v1/operations/{id}",
                    "ticket_path": "/v1/tickets",
                    "redeem_path": "/v1/tickets/redeem",
                    "interaction_path": "/v1/interactions/{id}",
                    "resolve_path": "/v1/forms/resolve",
                    "save_path": "/v1/documents/save",
                    "submit_path": "/v1/documents/submit",
                },
            )

        def _issue_ticket(self) -> None:
            body = self._read_json()
            form_ref = str(body.get("form_ref") or "")
            if form_ref not in FORMS:
                _json(self, 400, {"ok": False, "error": "unknown_form_ref"})
                return
            if not isinstance(body.get("subject"), dict) or not body["subject"].get("sub"):
                _json(self, 400, {"ok": False, "error": "subject_required"})
                return
            ticket = secrets.token_urlsafe(24)
            state.tickets[ticket] = {
                "subject": body["subject"],
                "form_ref": form_ref,
                "record_id": body.get("record_id"),
                "action": body.get("action"),
                "interaction_id": body.get("interaction_id"),
                "nonce": body.get("nonce"),
                "schema_version": body.get("schema_version"),
                "record_version": body.get("record_version") or 0,
                "exp": time.time() + TICKET_TTL,
            }
            host = self.headers.get("host") or "127.0.0.1"
            _json(
                self,
                200,
                {
                    "ok": True,
                    "ticket": ticket,
                    "redeem_url": f"https://{host}/v1/tickets/redeem",
                    "expires_in": TICKET_TTL,
                    "form_ref": form_ref,
                },
            )

        def _redeem(self) -> None:
            length = int(self.headers.get("content-length") or "0")
            raw = self.rfile.read(length) if length else b""
            fields = parse_qs(raw.decode("utf-8"))
            ticket = (fields.get("ticket") or [""])[0]
            nonce = (fields.get("nonce") or [""])[0]
            meta = state.tickets.get(ticket)
            if meta is None or ticket in state.used_tickets:
                _html(self, 403, "<html><body>ticket replay or unknown</body></html>")
                return
            if meta["exp"] < time.time():
                _html(self, 403, "<html><body>ticket expired</body></html>")
                return
            if nonce and meta.get("nonce") and nonce != meta["nonce"]:
                _html(self, 403, "<html><body>nonce mismatch</body></html>")
                return
            state.used_tickets.add(ticket)
            session = secrets.token_urlsafe(24)
            state.sessions[session] = {**meta, "session": session}
            interaction_id = str(meta["interaction_id"])
            state.interactions.setdefault(
                interaction_id,
                {
                    "interaction_id": interaction_id,
                    "status": "draft",
                    "approval_status": "not_applicable",
                    "record_id": meta.get("record_id"),
                    "record_version": meta.get("record_version") or 0,
                    "subject_sub": meta["subject"]["sub"],
                    "form_ref": meta["form_ref"],
                    "fields": {},
                    "detail_error": None,
                },
            )
            readonly = meta.get("action") == "view_detail"
            if readonly and state.fail_detail:
                state.interactions[interaction_id]["detail_error"] = "detail_unavailable"
                _html(
                    self,
                    503,
                    "<html><body data-detail-error='1'>detail unavailable</body></html>",
                    cookie=f"bui_session={session}; Path=/; HttpOnly; SameSite=None; Secure",
                )
                return
            title = FORMS[meta["form_ref"]]["title"]
            disabled = "disabled" if readonly else ""
            rec = state.interactions[interaction_id]
            body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body data-business-ui-form="1" data-mode="{"readonly" if readonly else "edit"}">
<h1>{title}</h1>
<form id="f" method="post" action="/v1/documents/{"submit" if not readonly else "save"}">
<input name="headcount" value="{rec.get("fields", {}).get("headcount", "2")}" {disabled}>
<input name="role" value="{rec.get("fields", {}).get("role", "implementation consultant")}" {disabled}>
<button type="submit" name="op" value="save" {disabled}>Save</button>
<button type="submit" name="op" value="submit" {disabled}>Submit</button>
</form>
<script>
document.getElementById('f').addEventListener('submit', async (ev) => {{
  ev.preventDefault();
  const op = ev.submitter && ev.submitter.value === 'submit' ? 'submit' : 'save';
  const body = new URLSearchParams(new FormData(ev.target));
  body.set('op', op);
  const res = await fetch('/v1/documents/' + op, {{method:'POST', body, credentials:'include'}});
  const data = await res.json();
  window.parent.postMessage({{
    type: 'business-ui/hint',
    interactionId: {json.dumps(interaction_id)},
    nonce: {json.dumps(meta.get("nonce"))},
    kind: op,
    success: !!(data && data.ok)
  }}, '*');
}});
</script>
</body></html>"""
            _html(
                self,
                200,
                body,
                cookie=f"bui_session={session}; Path=/; HttpOnly; SameSite=None; Secure",
            )

        def _session(self) -> dict[str, Any] | None:
            cookie = self.headers.get("cookie") or ""
            for part in cookie.split(";"):
                name, _, value = part.strip().partition("=")
                if name == "bui_session":
                    return state.sessions.get(value)
            return None

        def _mutate(self, kind: str) -> None:
            session = self._session()
            if session is None:
                _json(self, 401, {"ok": False, "error": "no_session"})
                return
            length = int(self.headers.get("content-length") or "0")
            fields = parse_qs(self.rfile.read(length).decode("utf-8") if length else "")
            interaction_id = str(session["interaction_id"])
            rec = state.interactions[interaction_id]
            rec["interaction_id"] = interaction_id
            expected = int(session.get("record_version") or rec.get("record_version") or 0)
            if expected != int(rec.get("record_version") or 0):
                _json(
                    self,
                    409,
                    {"ok": False, "error": "conflict", "record_version": rec["record_version"]},
                )
                return
            rec["fields"] = {
                "headcount": (fields.get("headcount") or ["2"])[0],
                "role": (fields.get("role") or [""])[0],
            }
            if kind == "save":
                rec["record_version"] = expected + 1
                session["record_version"] = rec["record_version"]
                rec["status"] = rec.get("status") or "draft"
                _json(
                    self,
                    200,
                    {"ok": True, "status": rec["status"], "record_version": rec["record_version"]},
                )
                return
            if rec.get("status") == "submitted" and rec.get("result", {}).get("type") == "SUCCESS":
                _json(self, 200, self._receipt_body(rec, idempotent=True))
                return
            op_id = f"op-{secrets.token_hex(4)}"
            rec["operation_id"] = op_id
            rec["receipt_sequence"] = state.next_sequence()
            existing_record = rec.get("record_id") or state.seed_record_id
            outcome = state.submit_outcome
            if outcome == "permission":
                rec["status"] = "draft"
                rec["result"] = {
                    "type": "BUSINESS_REJECTED",
                    "status": "BUSINESS_REJECTED",
                    "code": "PERMISSION_DENIED",
                    "message": "当前账号无权提交该单据。",
                    "disclosable": True,
                    "safe_retry": False,
                    "idempotent": True,
                    "side_effect": False,
                }
                rec["allowed_actions"] = ["request_permission", "close"]
                rec["record_id"] = existing_record
            elif outcome == "rule":
                rec["status"] = rec.get("status") or "draft"
                rec["result"] = {
                    "type": "BUSINESS_REJECTED",
                    "status": "BUSINESS_REJECTED",
                    "code": "BUSINESS_RULE",
                    "message": "业务规则拒绝了本次操作。",
                    "disclosable": True,
                    "safe_retry": False,
                    "idempotent": True,
                    "side_effect": False,
                }
                rec["record_id"] = existing_record
                rec["allowed_actions"] = (
                    ["view_document", "close"] if existing_record else ["close"]
                )
            elif outcome == "failed":
                rec["status"] = "draft"
                rec["result"] = {
                    "type": "TECHNICAL_ERROR",
                    "status": "FAILED",
                    "code": "UPSTREAM_FAILED",
                    "message": "提交失败，未产生业务副作用，可以安全重试。",
                    "disclosable": True,
                    "safe_retry": True,
                    "idempotent": True,
                    "side_effect": False,
                }
                rec["allowed_actions"] = ["retry", "close"]
                rec["record_id"] = existing_record
            elif outcome == "unknown":
                rec["status"] = "pending"
                rec["result"] = {
                    "type": "TECHNICAL_ERROR",
                    "status": "UNKNOWN",
                    "code": "RESULT_UNKNOWN",
                    "message": "结果未知，请查询状态，不要重复提交。",
                    "disclosable": True,
                    "safe_retry": False,
                    "idempotent": False,
                    "side_effect": None,
                }
                rec["allowed_actions"] = ["query_status", "close"]
                rec["record_id"] = existing_record
            else:
                rec["record_version"] = expected + 1
                session["record_version"] = rec["record_version"]
                rec["status"] = "submitted"
                rec["approval_status"] = "pending"
                rec["record_id"] = existing_record or f"REQ-{secrets.token_hex(3)}"
                rec["result"] = {
                    "type": "SUCCESS",
                    "status": "SUCCESS",
                    "code": None,
                    "message": None,
                    "disclosable": True,
                    "safe_retry": False,
                    "idempotent": True,
                    "side_effect": True,
                }
                rec["allowed_actions"] = ["view_document", "close"]
                detail_ref = (
                    "recruitment.request.detail"
                    if str(rec.get("form_ref", "")).startswith("recruitment")
                    else "generic.request.detail"
                )
                rec["navigation"] = {
                    "view": "detail",
                    "form_ref": detail_ref,
                    "formRef": detail_ref,
                    "mode": "readonly",
                }
            state.operations[op_id] = dict(rec)
            _json(self, 200, self._receipt_body(rec))

        def _origin(self) -> str:
            host = self.headers.get("host") or "127.0.0.1"
            return f"https://{host}"

        def _discovery(self) -> None:
            origin = self._origin()
            _json(
                self,
                200,
                {
                    "issuer": origin,
                    "authorization_endpoint": origin + "/v1/oauth/authorize",
                    "token_endpoint": origin + "/v1/oauth/token",
                    "revocation_endpoint": origin + "/v1/oauth/revoke",
                    "code_challenge_methods_supported": ["S256"],
                    "grant_types_supported": ["authorization_code", "refresh_token"],
                },
            )

        def _oauth_authorize(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            client_id = (query.get("client_id") or [""])[0]
            redirect_uri = (query.get("redirect_uri") or [""])[0]
            state_q = (query.get("state") or [""])[0]
            challenge = (query.get("code_challenge") or [""])[0]
            method = (query.get("code_challenge_method") or [""])[0]
            if (
                client_id != state.oauth_client_id
                or method != "S256"
                or not challenge
                or not state_q
                or "/v1/oauth/callback" not in redirect_uri
            ):
                _html(self, 400, "<html><body>invalid authorize request</body></html>")
                return
            body = f"""<!DOCTYPE html><html><body>
<form method="post" action="/v1/oauth/approve">
<input type="hidden" name="client_id" value="{escape(client_id)}">
<input type="hidden" name="redirect_uri" value="{escape(redirect_uri)}">
<input type="hidden" name="state" value="{escape(state_q)}">
<input type="hidden" name="code_challenge" value="{escape(challenge)}">
<input name="username" value="demo">
<button type="submit">Sign in</button>
</form></body></html>"""
            _html(self, 200, body)

        def _read_form(self) -> dict[str, str]:
            length = int(self.headers.get("content-length") or "0")
            raw = self.rfile.read(length) if length else b""
            parsed = parse_qs(raw.decode("utf-8"))
            return {key: (vals[0] if vals else "") for key, vals in parsed.items()}

        def _oauth_approve(self) -> None:
            fields = self._read_form()
            username = fields.get("username") or "demo"
            if username not in state.native_users:
                _html(self, 401, "<html><body>unknown user</body></html>")
                return
            code = secrets.token_urlsafe(24)
            state.oauth_codes[code] = {
                "state": fields.get("state"),
                "challenge": fields.get("code_challenge"),
                "redirect_uri": fields.get("redirect_uri"),
                "sub": username,
                "exp": time.time() + 120,
            }
            loc = fields.get("redirect_uri") or ""
            loc += ("&" if "?" in loc else "?") + urlencode(
                {"code": code, "state": fields.get("state") or ""}
            )
            self.send_response(302)
            self.send_header("location", loc)
            self.send_header("content-length", "0")
            self.end_headers()

        def _oauth_callback(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            code = (query.get("code") or [""])[0]
            st = (query.get("state") or [""])[0]
            if code and st and code in state.oauth_codes:
                state.oauth_by_state[st] = code
            _html(
                self,
                200,
                "<html><body data-oauth-complete='1'>You can close this window.</body></html>",
            )

        def _oauth_consume(self) -> None:
            body = self._read_json()
            st = str(body.get("state") or "")
            code = state.oauth_by_state.pop(st, None)
            if not code:
                _json(self, 404, {"ok": False, "pending": True})
                return
            _json(self, 200, {"ok": True, "code": code})

        def _oauth_token(self) -> None:
            fields = self._read_form()
            if fields.get("client_id") != state.oauth_client_id:
                _json(self, 401, {"error": "invalid_client"})
                return
            if fields.get("client_secret") != state.oauth_client_secret:
                _json(self, 401, {"error": "invalid_client"})
                return
            if fields.get("grant_type") == "refresh_token":
                old_access = state.refresh_tokens.get(fields.get("refresh_token") or "")
                if not old_access or old_access not in state.user_tokens:
                    _json(self, 400, {"error": "invalid_grant"})
                    return
                sub = str(state.user_tokens[old_access]["sub"])
                state.revoked.add(old_access)
                _json(self, 200, state.issue_user_token(sub))
                return
            code = fields.get("code") or ""
            meta = state.oauth_codes.pop(code, None)
            if meta is None or meta["exp"] < time.time():
                _json(self, 400, {"error": "invalid_grant"})
                return
            if fields.get("redirect_uri") != meta["redirect_uri"]:
                _json(self, 400, {"error": "invalid_grant"})
                return
            verifier = fields.get("code_verifier") or ""
            digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            challenge = digest.rstrip(b"=").decode("ascii")
            if challenge != meta["challenge"]:
                _json(self, 400, {"error": "invalid_grant"})
                return
            _json(self, 200, state.issue_user_token(str(meta["sub"])))

        def _oauth_revoke(self) -> None:
            fields = self._read_form()
            token = fields.get("token") or ""
            state.revoked.add(token)
            _json(self, 200, {"ok": True})

        def _native(self) -> None:
            body = self._read_json()
            username = str(body.get("username") or "")
            password = str(body.get("password") or "")
            if state.native_users.get(username) != password:
                _json(self, 401, {"ok": False, "error": "invalid_credentials"})
                return
            sub = str((body.get("subject") or {}).get("sub") or username)
            _json(self, 200, state.issue_user_token(sub))

        def _pat(self) -> None:
            body = self._read_json()
            token = str(body.get("access_token") or "")
            if not token.startswith("pat-") or len(token) < 8:
                _json(self, 401, {"ok": False, "error": "invalid_pat"})
                return
            sub = str((body.get("subject") or {}).get("sub") or "pat")
            state.user_tokens[token] = {"sub": sub, "exp": time.time() + 86400, "refresh": None}
            _json(self, 200, {"ok": True, "expires_in": 86400})

        def _receipt_body(self, rec: dict[str, Any], *, idempotent: bool = False) -> dict[str, Any]:
            interaction_id = str(rec.get("interaction_id") or "")
            result = rec.get("result") or {
                "type": "SUCCESS" if rec.get("status") == "submitted" else None
            }
            if rec.get("status") == "submitted" and not rec.get("result"):
                result = {
                    "type": "SUCCESS",
                    "status": "SUCCESS",
                    "code": None,
                    "message": None,
                    "disclosable": True,
                    "safe_retry": False,
                    "idempotent": True,
                    "side_effect": True,
                }
            return {
                "success": True,
                "protocol": PROTOCOL,
                "receipt_schema": "1.1",
                "idempotent": idempotent,
                "interactionId": interaction_id,
                "interaction_id": interaction_id,
                "operationId": rec.get("operation_id"),
                "operation_id": rec.get("operation_id"),
                "status": rec.get("status"),
                "approval_status": rec.get("approval_status"),
                "record_id": rec.get("record_id"),
                "record_version": rec.get("record_version"),
                "receipt_sequence": rec.get("receipt_sequence") or 0,
                "subject_sub": rec.get("subject_sub"),
                "navigation": rec.get("navigation"),
                "summary": rec.get("summary") or {},
                "form_ref": rec.get("form_ref"),
                "schema_version": rec.get("schema_version") or "1",
                "allowed_actions": rec.get("allowed_actions"),
                "result": result,
                "detail_error": rec.get("detail_error"),
                "documentType": "generic_request",
            }

        def _get_interaction(self, interaction_id: str) -> None:
            body = self._read_json()
            rec = state.interactions.get(interaction_id)
            if rec is None:
                _json(self, 404, {"ok": False, "error": "not_found"})
                return
            if rec.get("subject_sub") != (body.get("subject") or {}).get("sub"):
                _json(self, 403, {"ok": False, "error": "subject_mismatch"})
                return
            rec["interaction_id"] = interaction_id
            _json(self, 200, self._receipt_body(rec))

        def _query_operation(self, operation_id: str) -> None:
            rec = state.operations.get(operation_id)
            if rec is None:
                _json(self, 404, {"ok": False, "error": "not_found"})
                return
            if str((rec.get("result") or {}).get("status") or "") == "UNKNOWN":
                resolve = state.query_resolves_to
                rec["receipt_sequence"] = state.next_sequence()
                if resolve == "success":
                    rec["status"] = "submitted"
                    rec["record_id"] = rec.get("record_id") or f"REQ-{secrets.token_hex(3)}"
                    rec["record_version"] = int(rec.get("record_version") or 0) + 1
                    rec["result"] = {
                        "type": "SUCCESS",
                        "status": "SUCCESS",
                        "code": None,
                        "message": None,
                        "disclosable": True,
                        "safe_retry": False,
                        "idempotent": True,
                        "side_effect": True,
                    }
                    rec["allowed_actions"] = ["view_document", "close"]
                    rec["navigation"] = {
                        "view": "detail",
                        "form_ref": "generic.request.detail",
                        "formRef": "generic.request.detail",
                        "mode": "readonly",
                    }
                elif resolve == "rejected":
                    rec["result"] = {
                        "type": "BUSINESS_REJECTED",
                        "status": "BUSINESS_REJECTED",
                        "code": "BUSINESS_RULE",
                        "message": "查询后确认业务拒绝。",
                        "disclosable": True,
                        "safe_retry": False,
                        "idempotent": True,
                        "side_effect": False,
                    }
                    rec["allowed_actions"] = ["close"]
                else:
                    rec["result"] = {
                        "type": "TECHNICAL_ERROR",
                        "status": "FAILED",
                        "code": "UPSTREAM_FAILED",
                        "message": "查询后确认失败，未产生副作用。",
                        "disclosable": True,
                        "safe_retry": True,
                        "idempotent": True,
                        "side_effect": False,
                    }
                    rec["allowed_actions"] = ["retry", "close"]
                interaction_id = str(rec.get("interaction_id") or "")
                if interaction_id and interaction_id in state.interactions:
                    state.interactions[interaction_id].update(rec)
            _json(self, 200, self._receipt_body(rec))

        def _retry_operation(self, operation_id: str) -> None:
            rec = state.operations.get(operation_id)
            if rec is None:
                _json(self, 404, {"ok": False, "error": "not_found"})
                return
            result = rec.get("result") or {}
            if result.get("type") != "TECHNICAL_ERROR" or result.get("status") != "FAILED":
                _json(self, 400, {"ok": False, "error": "retry_not_allowed"})
                return
            if not result.get("safe_retry") or result.get("side_effect") is True:
                _json(self, 400, {"ok": False, "error": "retry_not_safe"})
                return
            rec["receipt_sequence"] = state.next_sequence()
            rec["status"] = "submitted"
            rec["record_id"] = rec.get("record_id") or f"REQ-{secrets.token_hex(3)}"
            rec["record_version"] = int(rec.get("record_version") or 0) + 1
            rec["result"] = {
                "type": "SUCCESS",
                "status": "SUCCESS",
                "code": None,
                "message": None,
                "disclosable": True,
                "safe_retry": False,
                "idempotent": True,
                "side_effect": True,
            }
            rec["allowed_actions"] = ["view_document", "close"]
            rec["navigation"] = {
                "view": "detail",
                "form_ref": "generic.request.detail",
                "formRef": "generic.request.detail",
                "mode": "readonly",
            }
            interaction_id = str(rec.get("interaction_id") or "")
            if interaction_id and interaction_id in state.interactions:
                state.interactions[interaction_id].update(rec)
            _json(self, 200, self._receipt_body(rec))

    return Handler


def serve_tls(
    state: AdapterState,
    *,
    certfile: str,
    keyfile: str,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    import ssl

    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile, keyfile)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    return httpd

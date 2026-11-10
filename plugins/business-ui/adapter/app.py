"""In-process reference adapter implementing business-ui.v1.

This is a protocol fixture, not a customer ERP. Recruitment formRefs exist only
as sample registry entries here.
"""

from __future__ import annotations

import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs

PROTOCOL = "business-ui.v1"
TICKET_TTL = 120

FORMS = {
    "generic.request.edit": {"mode": "edit", "title": "Generic request"},
    "generic.request.detail": {"mode": "readonly", "title": "Generic request (official)"},
    "recruitment.request.edit": {"mode": "edit", "title": "Recruitment request"},
    "recruitment.request.detail": {"mode": "readonly", "title": "Recruitment request (official)"},
}


class AdapterState:
    def __init__(self, connection_token: str, *, fail_detail: bool = False) -> None:
        self.connection_token = connection_token
        self.fail_detail = fail_detail
        self.tickets: dict[str, dict[str, Any]] = {}
        self.used_tickets: set[str] = set()
        self.sessions: dict[str, dict[str, Any]] = {}
        self.interactions: dict[str, dict[str, Any]] = {}
        self.operations: dict[str, dict[str, Any]] = {}

    def auth_ok(self, header: str) -> bool:
        if not header.startswith("Bearer "):
            return False
        return header.removeprefix("Bearer ").strip() == self.connection_token


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
            if not state.auth_ok(self.headers.get("authorization") or ""):
                _json(self, 401, {"ok": False, "error": "auth_failed"})
                return
            if path == "/v1/handshake":
                self._handshake()
                return
            if path == "/v1/tickets":
                self._issue_ticket()
                return
            if path.startswith("/v1/interactions/"):
                self._get_interaction(path.rsplit("/", 1)[-1])
                return
            _json(self, 404, {"ok": False, "error": "not_found"})

        def do_GET(self) -> None:  # noqa: N802
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
                    },
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
            rec["record_version"] = expected + 1
            session["record_version"] = rec["record_version"]
            op_id = f"op-{secrets.token_hex(4)}"
            if kind == "submit":
                if rec.get("status") == "submitted":
                    _json(
                        self,
                        200,
                        {
                            "ok": True,
                            "idempotent": True,
                            "operation_id": rec.get("operation_id"),
                            "status": "submitted",
                        },
                    )
                    return
                rec["status"] = "submitted"
                rec["approval_status"] = "pending"
                rec["record_id"] = rec.get("record_id") or f"REQ-{secrets.token_hex(3)}"
                rec["operation_id"] = op_id
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
            state.operations[op_id] = rec
            _json(
                self,
                200,
                {
                    "ok": True,
                    "operation_id": op_id,
                    "status": rec["status"],
                    "record_id": rec.get("record_id"),
                    "record_version": rec["record_version"],
                },
            )

        def _get_interaction(self, interaction_id: str) -> None:
            body = self._read_json()
            rec = state.interactions.get(interaction_id)
            if rec is None:
                _json(self, 404, {"ok": False, "error": "not_found"})
                return
            if rec.get("subject_sub") != (body.get("subject") or {}).get("sub"):
                _json(self, 403, {"ok": False, "error": "subject_mismatch"})
                return
            _json(
                self,
                200,
                {
                    "success": True,
                    "interactionId": interaction_id,
                    "interaction_id": interaction_id,
                    "operationId": rec.get("operation_id"),
                    "operation_id": rec.get("operation_id"),
                    "status": rec.get("status"),
                    "approval_status": rec.get("approval_status"),
                    "record_id": rec.get("record_id"),
                    "record_version": rec.get("record_version"),
                    "subject_sub": rec.get("subject_sub"),
                    "navigation": rec.get("navigation"),
                    "detail_error": rec.get("detail_error"),
                    "documentType": "recruitment_request"
                    if str(rec.get("form_ref", "")).startswith("recruitment")
                    else "generic_request",
                },
            )

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

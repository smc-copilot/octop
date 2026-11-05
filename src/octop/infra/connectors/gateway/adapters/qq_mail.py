"""QQ mail and other IMAP/SMTP mailbox gateway."""

from __future__ import annotations

import contextlib
import email
import imaplib
import json
import re
import smtplib
from html.parser import HTMLParser
from datetime import datetime, timedelta
from email import policy
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from octop.i18n import tr
from octop.infra.connectors.gateway.confirmations import STORE as _CONFIRMATIONS
from octop.infra.connectors.mail_servers import (
    IMAP_CONNECT_TIMEOUT,
    NETEASE_IMAP_HOSTS,
    correct_netease_imap_host,
    correct_netease_smtp_host,
)

_RENDERER = "mail_card"
_WRITES = frozenset({"send_email", "reply_email"})
_TOKEN_RE = re.compile(r"^[0-9a-f]{48}$")

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_emails",
        "description": "Search recent emails in INBOX (IMAP). Prefer unread/from/since_days over raw query.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "unread": {
                    "type": "boolean",
                    "description": "When true, only unseen (UNSEEN) messages",
                },
                "from": {
                    "type": "string",
                    "description": "Substring match against From header (IMAP FROM)",
                },
                "since_days": {
                    "type": "integer",
                    "description": "Only messages since N days ago (server timezone)",
                },
                "query": {
                    "type": "string",
                    "description": "Legacy raw IMAP SEARCH criteria; ignored when structured filters are set",
                },
                "limit": {"type": "integer", "description": "Page size, default 10, max 50"},
                "offset": {
                    "type": "integer",
                    "description": "Skip this many newest matches before the page (0 = first page)",
                },
            },
        },
    },
    {
        "name": "read_email",
        "description": "Read a single email body by UID without marking it seen (BODY.PEEK)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uid": {"type": "string", "description": "IMAP UID"},
            },
            "required": ["uid"],
        },
    },
    {
        "name": "send_email",
        "description": (
            "Prepare or confirm sending a plain-text email via SMTP (two-phase confirmation)"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "confirmation_token": {
                    "type": "string",
                    "description": "Token from the dry-run response; required to actually send",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "reply_email",
        "description": (
            "Prepare or confirm a reply to an INBOX message by UID "
            "(threading headers + Re: subject; two-phase confirmation)"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "uid": {"type": "string", "description": "IMAP UID of the message to reply to"},
                "body": {"type": "string"},
                "confirmation_token": {
                    "type": "string",
                    "description": "Token from the dry-run response; required to actually send",
                },
            },
            "required": ["uid", "body"],
        },
    },
]

_IMAP_ID_ARGS = (
    '("name" "Octop" "version" "1.0.0" "vendor" "Octop" "support-email" "support@octop.local")'
)

# imaplib 默认未注册 ID 命令。
imaplib.Commands["ID"] = ("AUTH", "NONAUTH", "SELECTED")


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "search_emails":
        return _email_search(creds, args)
    if name == "read_email":
        return _email_read(creds, args)
    if name == "send_email":
        return _email_send(creds, args)
    if name == "reply_email":
        return _email_reply(creds, args)
    raise ValueError(_err(creds, "unknown_tool", tool=name))


def write_tool_names(mcp_server_name: str) -> list[str]:
    from octop.infra.agents.plugins.plugin_tool_names import sanitize_plugin_tool_name

    used: set[str] = set()
    return [
        sanitize_plugin_tool_name(f"{mcp_server_name}_{name}", used=used)
        for name in sorted(_WRITES)
    ]


def _confirm_when(req: Any) -> bool:
    tool_call = getattr(req, "tool_call", None) or {}
    raw_args = tool_call.get("args") if isinstance(tool_call, dict) else {}
    token = raw_args.get("confirmation_token") if isinstance(raw_args, dict) else None
    return isinstance(token, str) and bool(token.strip())


def write_interrupt_on(mcp_server_names: list[str]) -> dict[str, Any]:
    """Always interrupt the confirm call, even when global HITL is off."""
    entry: dict[str, Any] = {"allowed_decisions": ["approve", "reject"], "when": _confirm_when}
    return {name: dict(entry) for server in mcp_server_names for name in write_tool_names(server)}


def _locale(creds: dict[str, Any]) -> str:
    return str(creds.get("_locale") or "en")


def _err(creds: dict[str, Any], key: str, **kwargs: Any) -> str:
    return tr(f"connector.qq_mail.{key}", _locale(creds), **kwargs)


def _server_tz(creds: dict[str, Any]) -> ZoneInfo:
    name = str(creds.get("_timezone") or "").strip()
    if not name:
        try:
            from octop.config import load_config
            from octop.infra.utils.paths import PathLayout

            name = load_config(PathLayout.from_env().config).default_timezone
        except Exception:
            name = "Asia/Shanghai"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai")


def _envelope(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {
            "octop_ui": {"renderer": _RENDERER, "version": 1},
            "data": data,
            "text": text,
        },
        ensure_ascii=False,
    )


def _build_search_criteria(creds: dict[str, Any], args: dict[str, Any]) -> str:
    parts: list[str] = []
    if args.get("unread") is True:
        parts.append("UNSEEN")
    from_filter = str(args.get("from") or "").strip()
    if from_filter:
        # IMAP FROM takes a quoted string; escape embedded quotes.
        safe = from_filter.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'FROM "{safe}"')
    since_days = args.get("since_days")
    if since_days is not None:
        days = int(since_days)
        if days < 0:
            raise ValueError(_err(creds, "invalid_arguments"))
        since = datetime.now(_server_tz(creds)).date() - timedelta(days=days)
        # IMAP SINCE day-month-year (English month abbrev).
        parts.append(f"SINCE {since.strftime('%d-%b-%Y')}")
    if parts:
        return f"({' '.join(parts)})" if len(parts) > 1 else parts[0]
    query = str(args.get("query") or "ALL").strip() or "ALL"
    return query


def _parse_message(raw: bytes) -> email.message.Message:
    """Parse raw RFC822 bytes with ``email.policy.default``.

    The default compat32 policy returns ``email.header.Header`` objects for
    header fields carrying raw (non MIME-encoded) non-ASCII bytes; those are
    not JSON serializable and crash ``search_emails``/``read_email`` with
    ``TypeError: Object of type Header is not JSON serializable``. The modern
    policy always yields ``str`` subclasses and additionally decodes
    MIME-encoded words (so subjects render as readable text instead of
    ``=?utf-8?q?...?=``).
    """
    return email.message_from_bytes(raw, policy=policy.default)


def _safe_header(msg: email.message.Message, field: str) -> str:
    """Return *field* as a plain ``str``, safe for JSON under any policy."""
    return str(msg.get(field, "") or "")


def _email_search(creds: dict[str, Any], args: dict[str, Any]) -> str:
    criteria = _build_search_criteria(creds, args)
    limit = int(args.get("limit") or 10)
    if limit < 1:
        limit = 10
    if limit > 50:
        limit = 50
    offset = int(args.get("offset") or 0)
    if offset < 0:
        offset = 0
    imap = _imap_login(creds)
    try:
        imap.select("INBOX")
        # NetEase rejects CHARSET UTF-8 on UID SEARCH; omit charset for compatibility.
        _typ, data = imap.uid("search", criteria)
        uids = (data[0] or b"").split()
        newest_first = list(reversed(uids))
        total = len(newest_first)
        page = newest_first[offset : offset + limit]
        out: list[dict[str, str]] = []
        for uid in page:
            _typ, msg_data = imap.uid(
                "fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            )
            if not msg_data or not msg_data[0]:
                continue
            hdr = _parse_message(msg_data[0][1])
            out.append(
                {
                    "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "from": _safe_header(hdr, "From"),
                    "subject": _safe_header(hdr, "Subject"),
                    "date": _safe_header(hdr, "Date"),
                }
            )
        text = _err(creds, "list_text", count=len(out))
        if not out:
            text = _err(creds, "list_empty")
        payload: dict[str, Any] = {
            "view": "list",
            "items": out,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(out) < total,
        }
        if args.get("unread") is True:
            payload["unread"] = True
        from_filter = str(args.get("from") or "").strip()
        if from_filter:
            payload["from"] = from_filter
        if args.get("since_days") is not None:
            payload["since_days"] = int(args["since_days"])
        query = str(args.get("query") or "").strip()
        if query and query.upper() != "ALL" and "unread" not in payload and "from" not in payload:
            if "since_days" not in payload:
                payload["query"] = query
        return _envelope(payload, text)
    finally:
        with contextlib.suppress(Exception):
            imap.logout()


def _email_read(creds: dict[str, Any], args: dict[str, Any]) -> str:
    uid = str(args.get("uid") or "").strip()
    if not uid:
        raise ValueError(_err(creds, "uid_required"))
    imap = _imap_login(creds)
    try:
        imap.select("INBOX")
        # BODY.PEEK avoids setting \\Seen (PRD D10).
        _typ, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
        if not msg_data or not msg_data[0]:
            raise ValueError(_err(creds, "uid_not_found", uid=uid))
        raw = msg_data[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            raise ValueError(_err(creds, "uid_not_found", uid=uid))
        msg = _parse_message(bytes(raw))
        body, body_html = _extract_bodies(msg)
        attachments = _list_attachment_names(msg)
        payload = {
            "view": "detail",
            "uid": uid,
            "from": _safe_header(msg, "From"),
            "subject": _safe_header(msg, "Subject"),
            "date": _safe_header(msg, "Date"),
            "body": body,
            "attachments": attachments,
        }
        if body_html:
            payload["body_html"] = body_html
        text = _err(
            creds,
            "detail_text",
            subject=payload["subject"] or "(no subject)",
            sender=payload["from"] or "(unknown)",
        )
        return _envelope(payload, text)
    finally:
        with contextlib.suppress(Exception):
            imap.logout()


def _write_phase(
    creds: dict[str, Any],
    tool: str,
    parameters: dict[str, Any],
    token: str | None,
    *,
    send: Any,
) -> str:
    """Two-phase confirmation: dry-run issues a token; confirm consumes it then sends."""
    locale = _locale(creds)
    user_id = creds.get("_user_id")
    instance_id = creds.get("_instance_id")
    uid_int = int(user_id) if isinstance(user_id, int) else None
    inst = str(instance_id) if instance_id else None

    if token is None or not str(token).strip():
        issued, expires_in = _CONFIRMATIONS.issue(
            tool=tool,
            args=parameters,
            user_id=uid_int,
            instance_id=inst,
        )
        summary = {"action": tool, **parameters}
        # Never put full body into card text; keep a short preview.
        body = str(parameters.get("body") or "")
        preview = body if len(body) <= 200 else body[:200] + "…"
        data = {
            "view": "draft",
            "confirmation_required": True,
            "confirmation_token": issued,
            "expires_in": expires_in,
            "summary": {**summary, "body_preview": preview},
        }
        text = tr(
            "connector.qq_mail.confirmation_required",
            locale,
            to=str(parameters.get("to") or ""),
            subject=str(parameters.get("subject") or ""),
        )
        return _envelope(data, text)

    clean = str(token).strip()
    if not _TOKEN_RE.fullmatch(clean):
        raise ValueError(_err(creds, "invalid_confirmation"))
    try:
        _CONFIRMATIONS.consume(
            clean,
            tool=tool,
            args=parameters,
            user_id=uid_int,
            instance_id=inst,
        )
    except ValueError:
        raise ValueError(_err(creds, "invalid_confirmation")) from None
    send()
    data = {
        "view": "sent",
        "ok": True,
        "to": str(parameters.get("to") or ""),
        "subject": str(parameters.get("subject") or ""),
    }
    text = tr(
        "connector.qq_mail.send_ok",
        locale,
        to=data["to"],
        subject=data["subject"],
    )
    return _envelope(data, text)


def _smtp_send(
    creds: dict[str, Any],
    *,
    to_addr: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> None:
    from_addr = str(creds.get("email") or "")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    host = correct_netease_smtp_host(from_addr, creds.get("smtp_host"))
    port = int(creds.get("smtp_port") or 587)
    with smtplib.SMTP(host, port, timeout=IMAP_CONNECT_TIMEOUT) as smtp:
        smtp.starttls()
        smtp.login(from_addr, str(creds.get("password") or ""))
        smtp.send_message(msg)


def _email_send(creds: dict[str, Any], args: dict[str, Any]) -> str:
    to_addr = str(args.get("to") or "").strip()
    subject = str(args.get("subject") or "")
    body = str(args.get("body") or "")
    if not to_addr:
        raise ValueError(_err(creds, "to_required"))
    parameters = {"to": to_addr, "subject": subject, "body": body}
    token = args.get("confirmation_token")
    token_s = str(token).strip() if isinstance(token, str) else None

    def send() -> None:
        _smtp_send(creds, to_addr=to_addr, subject=subject, body=body)

    return _write_phase(creds, "send_email", parameters, token_s, send=send)


def _reply_subject(original: str) -> str:
    subject = (original or "").strip()
    if re.match(r"(?i)^re:\s*", subject):
        return subject
    return f"Re: {subject}" if subject else "Re:"


def _email_reply(creds: dict[str, Any], args: dict[str, Any]) -> str:
    uid = str(args.get("uid") or "").strip()
    body = str(args.get("body") or "")
    if not uid:
        raise ValueError(_err(creds, "uid_required"))
    token = args.get("confirmation_token")
    token_s = str(token).strip() if isinstance(token, str) else None

    # Fetch original headers for dry-run summary and for confirm send.
    imap = _imap_login(creds)
    try:
        imap.select("INBOX")
        _typ, msg_data = imap.uid(
            "fetch",
            uid,
            "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID REFERENCES REPLY-TO)])",
        )
        if not msg_data or not msg_data[0]:
            raise ValueError(_err(creds, "uid_not_found", uid=uid))
        raw = msg_data[0][1]
        if not isinstance(raw, (bytes, bytearray)):
            raise ValueError(_err(creds, "uid_not_found", uid=uid))
        original = _parse_message(bytes(raw))
    finally:
        with contextlib.suppress(Exception):
            imap.logout()

    reply_to = _safe_header(original, "Reply-To") or _safe_header(original, "From")
    _name, to_addr = parseaddr(reply_to)
    if not to_addr:
        to_addr = reply_to.strip()
    if not to_addr:
        raise ValueError(_err(creds, "invalid_arguments"))
    subject = _reply_subject(_safe_header(original, "Subject"))
    message_id = _safe_header(original, "Message-ID").strip()
    prior_refs = _safe_header(original, "References").strip()
    references = " ".join(part for part in (prior_refs, message_id) if part).strip() or None
    # confirmation store keys must match confirm-call args; callers pass uid+body (+token).
    store_params = {"uid": uid, "body": body}

    def send() -> None:
        _smtp_send(
            creds,
            to_addr=to_addr,
            subject=subject,
            body=body,
            in_reply_to=message_id or None,
            references=references,
        )

    # Dry-run / confirm keyed on uid+body; summary includes resolved to/subject.
    result = _write_phase(creds, "reply_email", store_params, token_s, send=send)
    # Enrich draft view with resolved addressing for the card.
    try:
        parsed = json.loads(result)
        if isinstance(parsed.get("data"), dict) and parsed["data"].get("confirmation_required"):
            summary = dict(parsed["data"].get("summary") or {})
            summary.update({"to": to_addr, "subject": subject, "uid": uid})
            parsed["data"]["summary"] = summary
            return json.dumps(parsed, ensure_ascii=False)
        if isinstance(parsed.get("data"), dict) and parsed["data"].get("ok"):
            parsed["data"]["to"] = to_addr
            parsed["data"]["subject"] = subject
            return json.dumps(parsed, ensure_ascii=False)
    except (TypeError, ValueError):
        pass
    return result


def _should_send_imap_id(imap: imaplib.IMAP4_SSL, host: str) -> bool:
    if host in NETEASE_IMAP_HOSTS:
        return True
    caps = {str(c).upper() for c in (imap.capabilities or ())}
    return "ID" in caps


def _imap_send_id(imap: imaplib.IMAP4_SSL) -> None:
    typ, _data = imap._simple_command("ID", _IMAP_ID_ARGS)
    if typ != "OK":
        raise imaplib.IMAP4.error(f"IMAP ID failed: {typ}")


def _imap_login(creds: dict[str, Any]) -> imaplib.IMAP4_SSL:
    user = str(creds.get("email") or "")
    host = correct_netease_imap_host(user, creds.get("imap_host"))
    port = int(creds.get("imap_port") or 993)
    password = str(creds.get("password") or "")
    imap: imaplib.IMAP4_SSL = imaplib.IMAP4_SSL(host, port, timeout=IMAP_CONNECT_TIMEOUT)
    if _should_send_imap_id(imap, host):
        _imap_send_id(imap)
    imap.login(user, password)
    return imap


def probe_credentials(creds: dict[str, Any]) -> None:
    """Validate mailbox credentials via IMAP login + INBOX select."""
    imap = _imap_login(creds)
    try:
        typ, _data = imap.select("INBOX")
        if typ != "OK":
            raise imaplib.IMAP4.error(f"SELECT INBOX failed: {_data}")
    finally:
        with contextlib.suppress(Exception):
            imap.logout()


def _decode_payload(part: email.message.Message, payload: bytes) -> str:
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        # Declared charset has no installed codec (e.g. "unknown-8bit", or a
        # bogus name from a broken client): fall back to UTF-8 instead of
        # crashing the whole read_email call.
        return payload.decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)</p>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _list_attachment_names(msg: email.message.Message) -> list[str]:
    names: list[str] = []
    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            disposition = str(part.get("Content-Disposition") or "")
            if "attachment" not in disposition.lower():
                continue
            filename = "attachment"
        names.append(str(filename))
    return names


_RICH_TAGS = frozenset(
    {
        "a",
        "b",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "hr",
        "i",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "s",
        "span",
        "strong",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "tr",
        "u",
        "ul",
    }
)
_VOID_TAGS = frozenset({"br", "hr", "img"})
_DROP_WITH_CHILDREN = frozenset(
    {"script", "style", "iframe", "object", "embed", "form", "svg", "math"}
)
_SAFE_URL = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)
_UNSAFE_CSS = re.compile(r"(expression\s*\(|javascript:|url\s*\()", re.IGNORECASE)


def _attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _safe_url(value: str) -> str | None:
    text = value.strip()
    if _SAFE_URL.match(text):
        return _attr(text)
    return None


def _safe_style(value: str) -> str | None:
    text = " ".join(value.split())
    if not text or _UNSAFE_CSS.search(text):
        return None
    return _attr(text[:500])


class _MailHtmlSanitizer(HTMLParser):
    """Rebuild mail HTML with an allowlisted tag set (no scripts or active URLs)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in _DROP_WITH_CHILDREN:
            self._skip += 1
            return
        if self._skip or name not in _RICH_TAGS:
            return
        rendered = _render_open_tag(name, attrs)
        if rendered:
            self._parts.append(rendered)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _DROP_WITH_CHILDREN and self._skip:
            self._skip -= 1
            return
        if self._skip or name not in _RICH_TAGS or name in _VOID_TAGS:
            return
        self._parts.append(f"</{name}>")

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        self._parts.append(
            data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    def result(self) -> str:
        return "".join(self._parts).strip()


def _render_open_tag(name: str, attrs: list[tuple[str, str | None]]) -> str:
    kept: list[str] = []
    for key, raw in attrs:
        attr = key.lower()
        value = raw or ""
        if attr == "style":
            style = _safe_style(value)
            if style:
                kept.append(f'style="{style}"')
        elif name == "a" and attr == "href":
            href = _safe_url(value)
            if href:
                kept.append(f'href="{href}"')
                kept.append('rel="noopener noreferrer"')
                kept.append('target="_blank"')
        elif name == "img" and attr in {"src", "alt", "width", "height"}:
            if attr == "src":
                src = _safe_url(value)
                if src:
                    kept.append(f'src="{src}"')
            elif attr == "alt":
                kept.append(f'alt="{_attr(value[:200])}"')
            elif value.isdigit():
                kept.append(f'{attr}="{value}"')
        elif name in {"td", "th"} and attr in {"colspan", "rowspan"} and value.isdigit():
            kept.append(f'{attr}="{value}"')
    attrs_html = (" " + " ".join(kept)) if kept else ""
    if name in _VOID_TAGS:
        return f"<{name}{attrs_html}>"
    return f"<{name}{attrs_html}>"


def _sanitize_mail_html(html: str) -> str:
    parser = _MailHtmlSanitizer()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return ""
    return parser.result()


def _extract_bodies(msg: email.message.Message) -> tuple[str, str]:
    """Return ``(plain, sanitized_html)``.

    ``plain`` prefers text/plain and otherwise strips HTML. ``sanitized_html``
    is empty when the message has no HTML part.
    """
    plain = ""
    html = ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes):
                continue
            if ctype == "text/plain" and not plain:
                plain = _decode_payload(part, payload)
            elif ctype == "text/html" and not html:
                html = _decode_payload(part, payload)
    else:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            text = _decode_payload(msg, payload)
            if msg.get_content_type() == "text/html":
                html = text
            else:
                plain = text
        elif payload:
            plain = str(payload)
    safe_html = _sanitize_mail_html(html) if html else ""
    if not plain and html:
        plain = _strip_html(html)
    return plain, safe_html


def _extract_body(msg: email.message.Message) -> str:
    """Plain-text body for IM and the model (HTML is stripped)."""
    return _extract_bodies(msg)[0]

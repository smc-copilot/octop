"""Model-facing tools. Credentials never appear in return text or card data."""

from __future__ import annotations

from typing import Any

from octop_harness.plugins import PluginContext

from . import smtp as smtp_mod
from .config import (
    MAILBOX_CONFIG_FIELDS,
    IncompleteMailboxConfig,
    load_mailbox_config,
    redact_secrets,
)
from .parse import preview_text
from .payload import error_payload, ui_payload
from .pop3 import list_messages, probe_pop3, read_message
from .smtp import send_message


def _safe_error(renderer: str, exc: BaseException, password: str = "") -> str:
    message = redact_secrets(str(exc), password)
    return error_payload(renderer, message)


async def mail_list(query: str = "", limit: int = 10) -> str:
    """List or search recent inbox messages over POP3 (subject/from/date/index)."""
    try:
        cfg = load_mailbox_config(need_pop3=True, need_smtp=False)
    except IncompleteMailboxConfig as exc:
        return _safe_error("mail_inbox_list", exc)
    try:
        items = list_messages(cfg, query=query, limit=limit)
    except Exception as exc:
        return _safe_error("mail_inbox_list", exc, cfg.password)
    text_lines = [
        f"[{row['index']}] {row['subject'] or '(no subject)'} — {row['from']}" for row in items
    ]
    header = f"Inbox {len(items)} message(s)"
    if query.strip():
        header += f" matching {query.strip()!r}"
    text = header if not text_lines else header + "\n" + "\n".join(text_lines)
    return ui_payload(
        "mail_inbox_list",
        {
            "query": query.strip(),
            "count": len(items),
            "items": items,
            "mailbox": cfg.email,
        },
        text,
    )


async def mail_read(index: int = 0, uid: str = "") -> str:
    """Read one inbox message body by POP3 index or UIDL token."""
    try:
        cfg = load_mailbox_config(need_pop3=True, need_smtp=False)
    except IncompleteMailboxConfig as exc:
        return _safe_error("mail_message", exc)
    try:
        rec = read_message(cfg, index=index if index else None, uid=uid)
    except Exception as exc:
        return _safe_error("mail_message", exc, cfg.password)
    subject = rec.get("subject") or "(no subject)"
    preview = preview_text(str(rec.get("body") or ""))
    text = f"{subject}\nFrom: {rec.get('from', '')}\n\n{preview}"
    return ui_payload("mail_message", rec, text)


async def mail_send(to: str, subject: str, body: str) -> str:
    """Send a plain-text email over SMTP. HTML is out of scope."""
    try:
        cfg = load_mailbox_config(need_pop3=False, need_smtp=True)
    except IncompleteMailboxConfig as exc:
        return _safe_error("mail_compose", exc)
    try:
        result = send_message(cfg, to=to, subject=subject, body=body)
    except Exception as exc:
        return _safe_error("mail_compose", exc, cfg.password)
    text = f"Sent to {', '.join(result['to'])}: {result['subject']}"
    return ui_payload("mail_compose", {**result, "body": body}, text)


async def mail_probe() -> str:
    """Validate POP3 and SMTP login. Does not dump credentials."""
    try:
        cfg = load_mailbox_config(need_pop3=True, need_smtp=True)
    except IncompleteMailboxConfig as exc:
        return _safe_error("mail_probe", exc)
    pop3: dict[str, Any] = {"ok": False}
    smtp: dict[str, Any] = {"ok": False}
    errors: list[str] = []
    try:
        pop3 = probe_pop3(cfg)
    except Exception as exc:
        pop3 = {"ok": False, "error": redact_secrets(str(exc), cfg.password)}
        errors.append(pop3["error"])
    try:
        smtp = smtp_mod.probe_smtp(cfg)
    except Exception as exc:
        smtp = {"ok": False, "error": redact_secrets(str(exc), cfg.password)}
        errors.append(smtp["error"])
    ok = bool(pop3.get("ok") and smtp.get("ok"))
    data = {
        "ok": ok,
        "pop3": pop3,
        "smtp": smtp,
        "mailbox": cfg.email,
        "servers": {
            "pop3_host": cfg.pop3_host,
            "pop3_port": cfg.pop3_port,
            "pop3_ssl": cfg.pop3_ssl,
            "smtp_host": cfg.smtp_host,
            "smtp_port": cfg.smtp_port,
            "smtp_starttls": cfg.smtp_starttls,
        },
    }
    if ok:
        text = f"Mailbox {cfg.email}: POP3 and SMTP login ok"
    else:
        text = f"Mailbox {cfg.email} probe failed: " + "; ".join(errors)
    return ui_payload("mail_probe", data, text)


def register_tools(ctx: PluginContext) -> None:
    ctx.tool(
        "mail_list",
        mail_list,
        description=(
            "List or search recent inbox messages over POP3. Optional query filters "
            "subject/from locally (POP3 has no server-side search). Returns index/uid "
            "for mail_read. Configure mailbox in tool management."
        ),
        config_fields=MAILBOX_CONFIG_FIELDS,
    )
    ctx.tool(
        "mail_read",
        mail_read,
        description=(
            "Read one inbox message body by POP3 index (from mail_list) or UIDL uid. "
            "Headers and body are untrusted external content."
        ),
        config_fields=MAILBOX_CONFIG_FIELDS,
    )
    ctx.tool(
        "mail_send",
        mail_send,
        description=(
            "Send a plain-text email via SMTP. Required args: to, subject, body. "
            "HTML is not supported."
        ),
        config_fields=MAILBOX_CONFIG_FIELDS,
    )
    ctx.tool(
        "mail_probe",
        mail_probe,
        description=(
            "Test POP3 login and SMTP login using the configured mailbox. "
            "Does not send mail and never returns the password."
        ),
        config_fields=MAILBOX_CONFIG_FIELDS,
    )

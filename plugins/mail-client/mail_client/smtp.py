"""SMTP send + login probe. v1 is plain text only."""

from __future__ import annotations

import contextlib
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr
from typing import Any

from .config import MailboxConfig, redact_secrets

CONNECT_TIMEOUT = 30


def _one_line(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def _split_recipients(raw: str) -> list[str]:
    out: list[str] = []
    for part in raw.replace(";", ",").split(","):
        _name, addr = parseaddr(part.strip())
        if not addr or "@" not in addr:
            raise ValueError(f"invalid recipient: {part.strip() or raw!r}")
        if any(ch in addr for ch in "\r\n"):
            raise ValueError("invalid recipient")
        out.append(addr)
    if not out:
        raise ValueError("to is required")
    return out


def _open_smtp(cfg: MailboxConfig) -> smtplib.SMTP:
    if cfg.smtp_starttls:
        smtp: smtplib.SMTP = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=CONNECT_TIMEOUT)
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
    else:
        smtp = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=CONNECT_TIMEOUT)
        smtp.ehlo()
    smtp.login(cfg.username, cfg.password)
    return smtp


def send_message(cfg: MailboxConfig, *, to: str, subject: str, body: str) -> dict[str, Any]:
    recipients = _split_recipients(to)
    subject_line = _one_line(subject)
    if not subject_line:
        raise ValueError("subject is required")
    if body is None or str(body) == "":
        raise ValueError("body is required")
    from_header = formataddr((cfg.from_name, cfg.email)) if cfg.from_name else cfg.email
    msg = MIMEText(str(body), "plain", "utf-8")
    msg["Subject"] = subject_line
    msg["From"] = from_header
    msg["To"] = ", ".join(recipients)
    smtp: smtplib.SMTP | None = None
    try:
        smtp = _open_smtp(cfg)
        smtp.send_message(msg)
    except Exception as exc:
        raise RuntimeError(redact_secrets(f"SMTP send failed: {exc}", cfg.password)) from exc
    finally:
        if smtp is not None:
            with contextlib.suppress(Exception):
                smtp.quit()
    return {
        "ok": True,
        "to": recipients,
        "subject": subject_line,
        "from": from_header,
        "body_preview": str(body)[:160],
    }


def probe_smtp(cfg: MailboxConfig) -> dict[str, Any]:
    smtp: smtplib.SMTP | None = None
    try:
        smtp = _open_smtp(cfg)
        smtp.noop()
        return {"ok": True}
    except Exception as exc:
        raise RuntimeError(redact_secrets(f"SMTP login failed: {exc}", cfg.password)) from exc
    finally:
        if smtp is not None:
            with contextlib.suppress(Exception):
                smtp.quit()

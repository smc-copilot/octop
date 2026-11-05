"""POP3 list / read / probe. Message numbers are session-scoped (not IMAP UIDs)."""

from __future__ import annotations

import contextlib
import poplib
from typing import Any

from .config import MailboxConfig, redact_secrets
from .parse import clip_body, extract_body, parse_message, preview_text, safe_header

CONNECT_TIMEOUT = 30
_MAX_LIST = 50


def _connect(cfg: MailboxConfig) -> poplib.POP3:
    cls = poplib.POP3_SSL if cfg.pop3_ssl else poplib.POP3
    pop = cls(cfg.pop3_host, cfg.pop3_port, timeout=CONNECT_TIMEOUT)
    pop.user(cfg.username)
    pop.pass_(cfg.password)
    return pop


def _join_lines(lines: list[bytes]) -> bytes:
    return b"\r\n".join(lines) + b"\r\n"


def _uid_map(pop: poplib.POP3) -> dict[int, str]:
    mapping: dict[int, str] = {}
    try:
        _resp, rows, _octets = pop.uidl()
    except poplib.error_proto:
        return mapping
    for row in rows:
        parts = row.split()
        if len(parts) < 2:
            continue
        try:
            mapping[int(parts[0])] = parts[1].decode("ascii", errors="replace")
        except (TypeError, ValueError):
            continue
    return mapping


def _fetch_headers(pop: poplib.POP3, index: int) -> bytes:
    try:
        _resp, lines, _octets = pop.top(index, 0)
        return _join_lines(lines)
    except poplib.error_proto:
        _resp, lines, _octets = pop.retr(index)
        return _join_lines(lines)


def _matches_query(record: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = f"{record.get('subject', '')} {record.get('from', '')}".lower()
    return query in haystack


def list_messages(
    cfg: MailboxConfig,
    *,
    query: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return newest-first header summaries. *query* filters subject/from locally."""
    needle = query.strip().lower()
    cap = max(1, min(int(limit or 10), _MAX_LIST))
    pop: poplib.POP3 | None = None
    try:
        pop = _connect(cfg)
        count, _octets = pop.stat()
        uids = _uid_map(pop)
        out: list[dict[str, Any]] = []
        for index in range(count, 0, -1):
            raw = _fetch_headers(pop, index)
            msg = parse_message(raw)
            record = {
                "index": index,
                "uid": uids.get(index, str(index)),
                "from": safe_header(msg, "From"),
                "subject": safe_header(msg, "Subject"),
                "date": safe_header(msg, "Date"),
                "preview": preview_text(extract_body(msg)),
            }
            if not _matches_query(record, needle):
                continue
            out.append(record)
            if len(out) >= cap:
                break
        return out
    except Exception as exc:
        raise RuntimeError(redact_secrets(f"POP3 list failed: {exc}", cfg.password)) from exc
    finally:
        if pop is not None:
            with contextlib.suppress(Exception):
                pop.quit()


def read_message(
    cfg: MailboxConfig,
    *,
    index: int | None = None,
    uid: str = "",
) -> dict[str, Any]:
    pop: poplib.POP3 | None = None
    try:
        pop = _connect(cfg)
        target = index
        resolved_uid = uid.strip()
        uids = _uid_map(pop)
        if target is None or target < 1:
            if not resolved_uid:
                raise ValueError("index or uid is required")
            reverse = {value: key for key, value in uids.items()}
            target = reverse.get(resolved_uid)
            if target is None:
                raise ValueError(f"message uid {resolved_uid} not found")
        _resp, lines, _octets = pop.retr(target)
        msg = parse_message(_join_lines(lines))
        body, truncated = clip_body(extract_body(msg))
        return {
            "index": target,
            "uid": uids.get(target, resolved_uid or str(target)),
            "from": safe_header(msg, "From"),
            "to": safe_header(msg, "To"),
            "subject": safe_header(msg, "Subject"),
            "date": safe_header(msg, "Date"),
            "body": body,
            "truncated": truncated,
        }
    except Exception as exc:
        raise RuntimeError(redact_secrets(f"POP3 read failed: {exc}", cfg.password)) from exc
    finally:
        if pop is not None:
            with contextlib.suppress(Exception):
                pop.quit()


def probe_pop3(cfg: MailboxConfig) -> dict[str, Any]:
    pop: poplib.POP3 | None = None
    try:
        pop = _connect(cfg)
        count, octets = pop.stat()
        return {"ok": True, "message_count": int(count), "octets": int(octets)}
    except Exception as exc:
        raise RuntimeError(redact_secrets(f"POP3 login failed: {exc}", cfg.password)) from exc
    finally:
        if pop is not None:
            with contextlib.suppress(Exception):
                pop.quit()

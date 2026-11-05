"""Regression tests for qq-mail header/body decoding and PRD v0.2 features.

Covers the crash reported in TECH-REPORT-qq-mail-header-bug.md and the
mail-expert connector extensions (structured search, BODY.PEEK, octop_ui
envelope, two-phase send/reply).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from octop.infra.connectors.gateway import confirmations as conf_mod
from octop.infra.connectors.gateway.adapters import qq_mail

_CREDS: dict[str, Any] = {
    "email": "user@example.com",
    "password": "auth-code",
    "imap_host": "imap.example.com",
    "_locale": "en",
    "_timezone": "Asia/Shanghai",
}


def _fake_imap_with_messages(messages: dict[bytes, bytes]) -> MagicMock:
    """IMAP4_SSL mock: UID search returns the keys of *messages*; UID fetch
    returns the raw RFC822-ish bytes. Captures the last search criteria."""

    state: dict[str, Any] = {"last_search": None, "last_fetch_spec": None}

    def uid(command: str, *args: object) -> tuple[str, list[Any]]:
        if command == "search":
            # imaplib form: uid("search", charset, criteria) or legacy
            # uid("search", criteria).
            if len(args) >= 2:
                state["last_search"] = args[1]
            elif args:
                state["last_search"] = args[0]
            data = b" ".join(sorted(messages.keys(), key=int))
            return "OK", [data]
        if command == "fetch":
            arg = args[0]
            state["last_fetch_spec"] = args[1] if len(args) > 1 else None
            target = arg if isinstance(arg, bytes) else str(arg).encode()
            raw = messages[target]
            return "OK", [(b"header", raw), b")"]
        raise AssertionError(f"unexpected uid command: {command}")

    fake = MagicMock()
    fake.uid.side_effect = uid
    fake._state = state
    return fake


def _items(envelope: str) -> list[dict[str, Any]]:
    parsed = json.loads(envelope)
    assert parsed["octop_ui"]["renderer"] == "mail_card"
    assert parsed["data"]["view"] == "list"
    assert isinstance(parsed["text"], str)
    return list(parsed["data"]["items"])


# ---------------------------------------------------------------------------
# _email_search: the reported 100%-crash path
# ---------------------------------------------------------------------------


def test_search_emails_raw_utf8_headers_do_not_crash_json() -> None:
    """Bare non-ASCII header bytes (no MIME encoding) must serialize."""
    raw = (
        "From: 张三 <a@b.com>\r\n"
        "Subject: 测试邮件\r\n"
        "Date: Wed, 30 Sep 2026 10:00:00 +0800\r\n"
        "\r\n"
        "body"
    ).encode()
    fake = _fake_imap_with_messages({b"30": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "search_emails", {})

    rows = _items(result)
    assert len(rows) == 1
    assert rows[0]["uid"] == "30"
    assert rows[0]["from"] == "张三 <a@b.com>"
    assert rows[0]["subject"] == "测试邮件"
    assert rows[0]["date"].startswith("Wed, 30 Sep 2026")


def test_search_emails_ascii_headers_unchanged() -> None:
    raw = (
        b"From: Alice <a@b.com>\r\n"
        b"Subject: test email\r\n"
        b"Date: Wed, 30 Sep 2026 10:00:00 +0800\r\n"
        b"\r\n"
        b"body"
    )
    fake = _fake_imap_with_messages({b"1": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "search_emails", {})

    rows = _items(result)
    assert rows[0]["from"] == "Alice <a@b.com>"
    assert rows[0]["subject"] == "test email"


def test_search_emails_mime_encoded_words_render_readable() -> None:
    """Bonus of policy.default: encoded words decode to readable text."""
    raw = (
        b"From: =?utf-8?q?=E5=BC=A0=E4=B8=89?= <a@b.com>\r\n"
        b"Subject: =?utf-8?q?=E6=B5=8B=E8=AF=95?=\r\n"
        b"\r\n"
        b"body"
    )
    fake = _fake_imap_with_messages({b"7": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "search_emails", {})

    rows = _items(result)
    assert rows[0]["from"] == "张三 <a@b.com>"
    assert rows[0]["subject"] == "测试"


# @lat: [[tests#Mail expert connector#Structured search and BODY.PEEK]]
def test_search_emails_structured_filters_build_imap_criteria() -> None:
    fake = _fake_imap_with_messages({})
    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        qq_mail.call_tool(
            _CREDS,
            "search_emails",
            {"unread": True, "from": "alice@x.com", "since_days": 7, "limit": 5},
        )
    criteria = str(fake._state["last_search"])
    assert "UNSEEN" in criteria
    assert 'FROM "alice@x.com"' in criteria
    assert "SINCE " in criteria


def test_search_emails_offset_pages_newest_first() -> None:
    messages: dict[bytes, bytes] = {}
    for index in range(1, 6):
        messages[str(index).encode()] = (
            f"From: u{index}@x.com\r\nSubject: s{index}\r\n\r\n".encode()
        )
    fake = _fake_imap_with_messages(messages)
    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(
            _CREDS, "search_emails", {"limit": 2, "offset": 2}
        )
    data = json.loads(result)["data"]
    assert [row["uid"] for row in data["items"]] == ["3", "2"]
    assert data["total"] == 5
    assert data["offset"] == 2
    assert data["limit"] == 2
    assert data["has_more"] is True


# ---------------------------------------------------------------------------
# _email_read: BODY.PEEK + envelope + unknown-charset body
# ---------------------------------------------------------------------------


def test_read_email_uses_body_peek_and_envelope() -> None:
    raw = (
        "From: 张三 <a@b.com>\r\n"
        "Subject: 测试邮件\r\n"
        'Content-Type: text/plain; charset="unknown-8bit"\r\n'
        "\r\n"
        "正文内容"
    ).encode()
    fake = _fake_imap_with_messages({b"30": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "read_email", {"uid": "30"})

    assert "BODY.PEEK[]" in str(fake._state["last_fetch_spec"])
    rec = json.loads(result)
    assert rec["octop_ui"]["renderer"] == "mail_card"
    assert rec["data"]["view"] == "detail"
    assert rec["data"]["from"] == "张三 <a@b.com>"
    assert rec["data"]["subject"] == "测试邮件"
    assert rec["data"]["body"] == "正文内容"
    assert isinstance(rec["text"], str)


def test_read_email_ascii_message_unchanged() -> None:
    raw = (
        b"From: Alice <a@b.com>\r\n"
        b"Subject: hello\r\n"
        b'Content-Type: text/plain; charset="utf-8"\r\n'
        b"\r\n"
        b"plain body"
    )
    fake = _fake_imap_with_messages({b"1": raw})

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "read_email", {"uid": "1"})

    rec = json.loads(result)["data"]
    assert rec["from"] == "Alice <a@b.com>"
    assert rec["body"] == "plain body"


def test_read_email_html_only_strips_to_text() -> None:
    raw = (
        b"From: Alice <a@b.com>\r\n"
        b"Subject: html\r\n"
        b'Content-Type: text/html; charset="utf-8"\r\n'
        b"\r\n"
        b"<p>Hello <b>world</b></p>"
    )
    fake = _fake_imap_with_messages({b"2": raw})
    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "read_email", {"uid": "2"})
    data = json.loads(result)["data"]
    body = data["body"]
    assert "Hello" in body
    assert "world" in body
    assert "<b>" not in body
    assert "<b>" in data["body_html"]
    assert "<script" not in data["body_html"]


def test_read_email_html_drops_active_content() -> None:
    raw = (
        b"From: Alice <a@b.com>\r\n"
        b"Subject: html\r\n"
        b'Content-Type: text/html; charset="utf-8"\r\n'
        b"\r\n"
        b'<p>Hi</p><script>alert(1)</script>'
        b'<a href="javascript:alert(1)">bad</a>'
        b'<a href="https://example.com">ok</a>'
    )
    fake = _fake_imap_with_messages({b"3": raw})
    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        result = qq_mail.call_tool(_CREDS, "read_email", {"uid": "3"})
    html = json.loads(result)["data"]["body_html"]
    assert "<script" not in html
    assert "javascript:" not in html
    assert 'href="https://example.com"' in html
    assert ">ok<" in html


# ---------------------------------------------------------------------------
# Two-phase send / reply
# ---------------------------------------------------------------------------


# @lat: [[tests#Mail expert connector#Two-phase send confirmation]]
def test_send_email_dry_run_then_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    conf_mod.STORE.clear()
    sent: list[tuple[str, str, str]] = []

    def fake_smtp_send(
        creds: dict[str, Any],
        *,
        to_addr: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> None:
        sent.append((to_addr, subject, body))

    monkeypatch.setattr(qq_mail, "_smtp_send", fake_smtp_send)

    dry = json.loads(
        qq_mail.call_tool(
            _CREDS,
            "send_email",
            {"to": "a@b.com", "subject": "hi", "body": "hello"},
        )
    )
    assert dry["data"]["confirmation_required"] is True
    token = dry["data"]["confirmation_token"]
    assert sent == []

    confirmed = json.loads(
        qq_mail.call_tool(
            _CREDS,
            "send_email",
            {
                "to": "a@b.com",
                "subject": "hi",
                "body": "hello",
                "confirmation_token": token,
            },
        )
    )
    assert confirmed["data"]["ok"] is True
    assert sent == [("a@b.com", "hi", "hello")]

    # Replay must fail (one-shot).
    with pytest.raises(ValueError):
        qq_mail.call_tool(
            _CREDS,
            "send_email",
            {
                "to": "a@b.com",
                "subject": "hi",
                "body": "hello",
                "confirmation_token": token,
            },
        )


def test_reply_email_dry_run_resolves_threading(monkeypatch: pytest.MonkeyPatch) -> None:
    conf_mod.STORE.clear()
    raw = (
        b"From: Alice <alice@x.com>\r\n"
        b"Subject: Hello\r\n"
        b"Message-ID: <mid-1@x.com>\r\n"
        b"References: <mid-0@x.com>\r\n"
        b"\r\n"
        b"orig"
    )
    fake = _fake_imap_with_messages({b"9": raw})
    captured: dict[str, Any] = {}

    def fake_smtp_send(
        creds: dict[str, Any],
        *,
        to_addr: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> None:
        captured.update(
            {
                "to": to_addr,
                "subject": subject,
                "body": body,
                "in_reply_to": in_reply_to,
                "references": references,
            }
        )

    monkeypatch.setattr(qq_mail, "_smtp_send", fake_smtp_send)
    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        dry = json.loads(
            qq_mail.call_tool(_CREDS, "reply_email", {"uid": "9", "body": "thanks"})
        )
    assert dry["data"]["confirmation_required"] is True
    assert dry["data"]["summary"]["to"] == "alice@x.com"
    assert dry["data"]["summary"]["subject"] == "Re: Hello"
    token = dry["data"]["confirmation_token"]

    with patch(
        "octop.infra.connectors.gateway.adapters.qq_mail.imaplib.IMAP4_SSL",
        return_value=fake,
    ):
        confirmed = json.loads(
            qq_mail.call_tool(
                _CREDS,
                "reply_email",
                {"uid": "9", "body": "thanks", "confirmation_token": token},
            )
        )
    assert confirmed["data"]["ok"] is True
    assert captured["to"] == "alice@x.com"
    assert captured["subject"] == "Re: Hello"
    assert captured["in_reply_to"] == "<mid-1@x.com>"
    assert "<mid-0@x.com>" in (captured["references"] or "")
    assert "<mid-1@x.com>" in (captured["references"] or "")


def test_write_interrupt_on_only_when_token_present() -> None:
    mapping = qq_mail.write_interrupt_on(["qq-mail__abc"])
    assert mapping
    when = next(iter(mapping.values()))["when"]

    class _Req:
        def __init__(self, args: dict[str, Any]) -> None:
            self.tool_call = {"args": args}

    assert when(_Req({"confirmation_token": "abc"})) is True
    assert when(_Req({})) is False


# ---------------------------------------------------------------------------
# Unit-level: parsing helpers
# ---------------------------------------------------------------------------


def test_parse_message_never_returns_header_objects() -> None:
    """The exact regression from the report: compat32 returned Header here."""
    raw = "From: 张三 <a@b.com>\r\nSubject: 测试邮件\r\n\r\n".encode()
    msg = qq_mail._parse_message(raw)

    value = msg.get("From", "")
    assert isinstance(value, str), f"expected str, got {type(value).__name__}"

    # And the whole search-shaped record must be serializable.
    record = {"from": qq_mail._safe_header(msg, "From")}
    assert json.dumps(record, ensure_ascii=False)


def test_parse_message_survives_broken_mime_words() -> None:
    raw = b"Subject: =?utf-8?q?=E6=B5=8B\r\n\r\nbody"
    msg = qq_mail._parse_message(raw)

    assert isinstance(qq_mail._safe_header(msg, "Subject"), str)


def test_extract_body_falls_back_to_utf8_on_unknown_charset() -> None:
    raw = b'Content-Type: text/plain; charset="unknown-8bit"\r\n\r\n' + "正文内容".encode()
    msg = qq_mail._parse_message(raw)

    assert qq_mail._extract_body(msg) == "正文内容"


def test_extract_body_multipart_plain_part() -> None:
    raw = (
        b'Content-Type: multipart/mixed; boundary="X"\r\n'
        b"\r\n"
        b"--X\r\n"
        b'Content-Type: text/plain; charset="utf-8"\r\n'
        b"\r\n"
        b"hello\r\n"
        b"--X--\r\n"
    )
    msg = qq_mail._parse_message(raw)

    assert qq_mail._extract_body(msg) == "hello"


def test_safe_header_missing_field_returns_empty_string() -> None:
    msg = qq_mail._parse_message(b"From: a@b.com\r\n\r\n")
    assert qq_mail._safe_header(msg, "Subject") == ""


@pytest.mark.parametrize(
    "field",
    ["From", "Subject", "Date"],
)
def test_safe_header_always_plain_str(field: str) -> None:
    raw = "From: 张三 <a@b.com>\r\nSubject: 测试\r\nDate: Wed, 30 Sep 2026 10:00:00\r\n".encode()
    msg = qq_mail._parse_message(raw)
    value = qq_mail._safe_header(msg, field)
    assert type(value) is str


def test_confirmation_store_one_shot() -> None:
    store = conf_mod.ConfirmationStore(ttl_s=60)
    token, ttl = store.issue(tool="send_email", args={"to": "a"}, user_id=1)
    assert ttl == 60
    store.consume(token, tool="send_email", args={"to": "a"}, user_id=1)
    with pytest.raises(ValueError):
        store.consume(token, tool="send_email", args={"to": "a"}, user_id=1)

"""Unit tests for plugins/mail-client POP3/SMTP helpers (no real mail servers)."""

from __future__ import annotations

import json
import sys
from email.message import Message
from pathlib import Path
from typing import Any

import pytest
from octop_harness.plugins import PluginRegistry, load_plugin_dir

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "mail-client"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from mail_client.config import (  # noqa: E402
    IncompleteMailboxConfig,
    MailboxConfig,
    load_mailbox_config,
    parse_bool,
    redact_secrets,
)
from mail_client.parse import (  # noqa: E402
    extract_body,
    parse_message,
    preview_text,
    safe_header,
)
from mail_client.pop3 import list_messages, probe_pop3, read_message  # noqa: E402
from mail_client.smtp import probe_smtp, send_message  # noqa: E402
from mail_client.tools import mail_list, mail_probe, mail_read, mail_send  # noqa: E402

_SECRET = "s3cret-auth-code"

_CFG = MailboxConfig(
    pop3_host="pop.example.com",
    pop3_port=995,
    pop3_ssl=True,
    smtp_host="smtp.example.com",
    smtp_port=587,
    smtp_starttls=True,
    email="user@example.com",
    username="user@example.com",
    password=_SECRET,
    from_name="Ada",
)


def _raw_message(
    *,
    subject: str = "hello",
    sender: str = "Alice <a@b.com>",
    body: str = "plain body",
    extra_headers: str = "",
) -> bytes:
    return (
        f"From: {sender}\r\n"
        f"To: user@example.com\r\n"
        f"Subject: {subject}\r\n"
        f"Date: Wed, 30 Sep 2026 10:00:00 +0800\r\n"
        f"{extra_headers}"
        "\r\n"
        f"{body}"
    ).encode()


class FakePOP:
    def __init__(
        self,
        messages: dict[int, bytes],
        uids: dict[int, str] | None = None,
        *,
        fail_login: str | None = None,
        fail_top: bool = False,
    ) -> None:
        self.messages = messages
        self.uids = uids or {idx: f"uid-{idx}" for idx in messages}
        self.fail_login = fail_login
        self.fail_top = fail_top
        self.user_name = ""
        self.password = ""
        self.quit_called = False

    def user(self, name: str) -> None:
        self.user_name = name

    def pass_(self, password: str) -> None:
        self.password = password
        if self.fail_login:
            raise error_proto(self.fail_login)

    def stat(self) -> tuple[int, int]:
        return len(self.messages), sum(len(v) for v in self.messages.values())

    def uidl(self, which: object = None) -> tuple[bytes, list[bytes], int]:
        rows = [f"{idx} {uid}".encode() for idx, uid in self.uids.items()]
        return b"+OK", rows, 0

    def top(self, index: int, n: int) -> tuple[bytes, list[bytes], int]:
        if self.fail_top:
            raise error_proto("TOP not supported")
        return self.retr(index)

    def retr(self, index: int) -> tuple[bytes, list[bytes], int]:
        raw = self.messages[int(index)]
        return b"+OK", raw.split(b"\r\n"), len(raw)

    def quit(self) -> None:
        self.quit_called = True


class error_proto(Exception):
    pass


def _patch_pop(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakePOP,
    *,
    ssl: bool = True,
) -> FakePOP:
    import mail_client.pop3 as pop3_mod

    monkeypatch.setattr(pop3_mod.poplib, "error_proto", error_proto)
    cls_name = "POP3_SSL" if ssl else "POP3"
    monkeypatch.setattr(pop3_mod.poplib, cls_name, lambda *a, **k: fake)
    return fake


class FakeSMTP:
    def __init__(self, host: str, port: int, timeout: object = None) -> None:
        self.host = host
        self.port = port
        self.logged_in: tuple[str, str] | None = None
        self.sent: Message | None = None
        self.starttls_called = False
        self.quit_called = False
        self.noop_called = False

    def ehlo(self) -> None:
        return None

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def send_message(self, msg: Message) -> None:
        self.sent = msg

    def noop(self) -> None:
        self.noop_called = True

    def quit(self) -> None:
        self.quit_called = True


def _patch_smtp(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeSMTP,
    *,
    starttls: bool = True,
) -> FakeSMTP:
    import mail_client.smtp as smtp_mod

    name = "SMTP" if starttls else "SMTP_SSL"
    monkeypatch.setattr(smtp_mod.smtplib, name, lambda *a, **k: fake)
    return fake


def _stub_tool_config(monkeypatch: pytest.MonkeyPatch, cfg: dict[str, Any] | None) -> None:
    import mail_client.config as config_mod

    monkeypatch.setattr(config_mod, "get_tool_config", lambda name: cfg)


# ---------------------------------------------------------------------------
# parse / config
# ---------------------------------------------------------------------------


def test_parse_message_raw_utf8_headers_are_plain_str() -> None:
    raw = "From: 张三 <a@b.com>\r\nSubject: 测试邮件\r\n\r\n正文".encode()
    msg = parse_message(raw)
    assert safe_header(msg, "From") == "张三 <a@b.com>"
    assert safe_header(msg, "Subject") == "测试邮件"
    assert extract_body(msg) == "正文"
    json.dumps({"from": safe_header(msg, "From")}, ensure_ascii=False)


def test_extract_body_unknown_charset_and_multipart() -> None:
    unknown = b'Content-Type: text/plain; charset="unknown-8bit"\r\n\r\n' + "正文内容".encode()
    assert extract_body(parse_message(unknown)) == "正文内容"

    multi = (
        b'Content-Type: multipart/mixed; boundary="X"\r\n\r\n'
        b'--X\r\nContent-Type: text/plain; charset="utf-8"\r\n\r\nhello\r\n'
        b"--X--\r\n"
    )
    assert extract_body(parse_message(multi)) == "hello"


def test_parse_bool_and_redact() -> None:
    assert parse_bool("true") is True
    assert parse_bool("off", default=True) is False
    assert parse_bool(None, default=True) is True
    assert parse_bool(0, default=True) is False
    assert "s3cret" not in redact_secrets("login failed s3cret", "s3cret")


def test_load_mailbox_config_defaults_and_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_tool_config(
        monkeypatch,
        {
            "email": "you@example.com",
            "password": _SECRET,
            "pop3_host": "pop.example.com",
            "smtp_host": "smtp.example.com",
        },
    )
    cfg = load_mailbox_config(need_pop3=True, need_smtp=True)
    assert cfg.pop3_port == 995
    assert cfg.smtp_port == 587
    assert cfg.pop3_ssl is True
    assert cfg.smtp_starttls is True
    assert cfg.username == "you@example.com"
    assert "password" not in cfg.public_identity()

    _stub_tool_config(monkeypatch, {"email": "you@example.com"})
    with pytest.raises(IncompleteMailboxConfig, match="missing password, pop3_host"):
        load_mailbox_config(need_pop3=True, need_smtp=False)


def test_load_mailbox_config_merges_sibling_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    import mail_client.config as config_mod

    def fake_get(name: str) -> dict[str, Any] | None:
        if name == "mail_list":
            return {"pop3_host": "pop.example.com", "email": "you@example.com"}
        if name == "mail_send":
            return {"smtp_host": "smtp.example.com", "password": _SECRET}
        return {}

    monkeypatch.setattr(config_mod, "get_tool_config", fake_get)
    cfg = load_mailbox_config(need_pop3=True, need_smtp=True)
    assert cfg.pop3_host == "pop.example.com"
    assert cfg.smtp_host == "smtp.example.com"
    assert cfg.password == _SECRET


# ---------------------------------------------------------------------------
# POP3
# ---------------------------------------------------------------------------


def test_list_messages_newest_first_and_local_search(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePOP(
        {
            1: _raw_message(subject="old invoice", sender="billing@x.com"),
            2: _raw_message(subject="Hello Ada", sender="Bob <b@c.com>"),
        }
    )
    _patch_pop(monkeypatch, fake)
    rows = list_messages(_CFG, query="ada", limit=10)
    assert [row["index"] for row in rows] == [2]
    assert rows[0]["uid"] == "uid-2"
    assert rows[0]["from"] == "Bob <b@c.com>"
    assert fake.password == _SECRET
    assert fake.quit_called is True


def test_list_messages_top_fallback_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePOP(
        {
            1: _raw_message(subject="one"),
            2: _raw_message(subject="two"),
            3: _raw_message(subject="three"),
        },
        fail_top=True,
    )
    _patch_pop(monkeypatch, fake)
    rows = list_messages(_CFG, limit=2)
    assert [row["subject"] for row in rows] == ["three", "two"]


def test_read_message_by_uid_and_index(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePOP({1: _raw_message(subject="alpha", body="正文内容")})
    _patch_pop(monkeypatch, fake)
    rec = read_message(_CFG, uid="uid-1")
    assert rec["index"] == 1
    assert rec["subject"] == "alpha"
    assert rec["body"] == "正文内容"
    assert rec["truncated"] is False

    rec2 = read_message(_CFG, index=1)
    assert rec2["uid"] == "uid-1"


def test_probe_pop3_redacts_password_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakePOP({}, fail_login=f"auth failed {_SECRET}")
    _patch_pop(monkeypatch, fake)
    with pytest.raises(RuntimeError) as exc:
        probe_pop3(_CFG)
    assert _SECRET not in str(exc.value)
    assert "***" in str(exc.value)


# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------


def test_send_message_starttls_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSMTP("smtp.example.com", 587)
    _patch_smtp(monkeypatch, fake)
    result = send_message(_CFG, to="ada@example.com", subject="Hi\nthere", body="hello")
    assert result["ok"] is True
    assert result["to"] == ["ada@example.com"]
    assert result["subject"] == "Hi there"
    assert fake.starttls_called is True
    assert fake.logged_in == ("user@example.com", _SECRET)
    assert fake.sent is not None
    assert fake.sent.get_content_type() == "text/plain"
    assert fake.sent["From"] == "Ada <user@example.com>"
    dumped = json.dumps(result, ensure_ascii=False)
    assert _SECRET not in dumped


def test_send_message_requires_to_subject_body(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSMTP("smtp.example.com", 587)
    _patch_smtp(monkeypatch, fake)
    with pytest.raises(ValueError, match="invalid recipient"):
        send_message(_CFG, to="not-an-email", subject="s", body="b")
    with pytest.raises(ValueError, match="subject is required"):
        send_message(_CFG, to="ada@example.com", subject="  ", body="b")
    with pytest.raises(ValueError, match="body is required"):
        send_message(_CFG, to="ada@example.com", subject="s", body="")
    assert fake.sent is None


def test_probe_smtp_ssl_path(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = MailboxConfig(
        **{
            **_CFG.__dict__,
            "smtp_starttls": False,
            "smtp_port": 465,
        }
    )
    fake = FakeSMTP("smtp.example.com", 465)
    _patch_smtp(monkeypatch, fake, starttls=False)
    assert probe_smtp(cfg) == {"ok": True}
    assert fake.starttls_called is False
    assert fake.logged_in == ("user@example.com", _SECRET)
    assert fake.noop_called is True


# ---------------------------------------------------------------------------
# tools + load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_list_envelope_omits_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tool_config(
        monkeypatch,
        {
            "email": "user@example.com",
            "password": _SECRET,
            "pop3_host": "pop.example.com",
        },
    )
    fake = FakePOP({1: _raw_message(subject="card")})
    _patch_pop(monkeypatch, fake)
    payload = json.loads(await mail_list())
    assert set(payload) == {"octop_ui", "data", "text"}
    assert payload["octop_ui"] == {"renderer": "mail_inbox_list", "version": 1}
    assert payload["data"]["items"][0]["subject"] == "card"
    blob = json.dumps(payload, ensure_ascii=False)
    assert _SECRET not in blob
    assert "password" not in payload["data"]


@pytest.mark.asyncio
async def test_tools_fail_clearly_when_config_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_tool_config(monkeypatch, {})
    listed = json.loads(await mail_list())
    assert "missing" in listed["text"]
    assert listed["data"]["error"].startswith("Mailbox not configured")
    sent = json.loads(await mail_send("a@b.com", "s", "b"))
    assert "smtp_host" in sent["text"] or "password" in sent["text"]
    read = json.loads(await mail_read(index=1))
    assert read["octop_ui"]["renderer"] == "mail_message"
    probed = json.loads(await mail_probe())
    assert probed["octop_ui"]["renderer"] == "mail_probe"
    assert _SECRET not in json.dumps(listed) + json.dumps(sent) + json.dumps(read) + json.dumps(
        probed
    )


@pytest.mark.asyncio
async def test_mail_send_and_probe_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_tool_config(
        monkeypatch,
        {
            "email": "user@example.com",
            "password": _SECRET,
            "pop3_host": "pop.example.com",
            "smtp_host": "smtp.example.com",
        },
    )
    _patch_pop(monkeypatch, FakePOP({1: _raw_message()}))
    smtp = FakeSMTP("smtp.example.com", 587)
    _patch_smtp(monkeypatch, smtp)
    sent = json.loads(await mail_send("ada@example.com", "Hello", "body text"))
    assert sent["octop_ui"]["renderer"] == "mail_compose"
    assert sent["data"]["ok"] is True
    assert sent["data"]["body"] == "body text"
    probed = json.loads(await mail_probe())
    assert probed["data"]["ok"] is True
    assert probed["data"]["pop3"]["ok"] is True
    assert probed["data"]["smtp"]["ok"] is True
    assert _SECRET not in json.dumps(sent) + json.dumps(probed)


def test_plugin_loads_via_registry() -> None:
    PluginRegistry.reset()
    try:
        loaded = load_plugin_dir(_PLUGIN_ROOT, install_deps=False)
        assert loaded.manifest.id == "mail-client"
        assert loaded.manifest.kind == "tool"
        names = [tool.name for tool in loaded.tools]
        assert names == ["mail_list", "mail_read", "mail_send", "mail_probe"]
        assert all(tool.config_fields for tool in loaded.tools)
        password_fields = [
            field
            for tool in loaded.tools
            for field in tool.config_fields
            if field.get("name") == "password"
        ]
        assert password_fields
        assert all(field.get("type") == "password" for field in password_fields)
        ui_dir = _PLUGIN_ROOT / "ui" / "dist"
        assert (ui_dir / "index.js").is_file()
        assert (ui_dir / "manifest.json").is_file()
    finally:
        PluginRegistry.reset()


def test_preview_text_flattens_newlines() -> None:
    assert "\n" not in preview_text("a\nb\nc" * 40)
    assert len(preview_text("x" * 400)) <= 160

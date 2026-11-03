"""Per-agent mailbox settings from tool config_fields.

Dashboard tool forms currently render ``text`` / ``password`` / ``number``
only — there is no switch widget. Boolean fields are stored as text
(``true`` / ``false``) and parsed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from octop_harness.plugins import get_tool_config

TOOL_NAMES: tuple[str, ...] = ("mail_list", "mail_read", "mail_send", "mail_probe")

MAILBOX_CONFIG_FIELDS: list[dict[str, Any]] = [
    {
        "name": "pop3_host",
        "type": "text",
        "required": True,
        "label": "POP3 Host",
        "placeholder": "pop.example.com",
        "help": "收件服务器，例如 pop.qq.com / pop.163.com",
    },
    {
        "name": "pop3_port",
        "type": "number",
        "required": False,
        "label": "POP3 Port",
        "placeholder": "995",
        "help": "默认 995（SSL）或 110（明文）",
    },
    {
        "name": "pop3_ssl",
        "type": "text",
        "required": False,
        "label": "POP3 SSL",
        "placeholder": "true",
        "help": "true/false，默认 true。工具配置暂无开关控件，请填文本。",
    },
    {
        "name": "smtp_host",
        "type": "text",
        "required": True,
        "label": "SMTP Host",
        "placeholder": "smtp.example.com",
        "help": "发件服务器，例如 smtp.qq.com / smtp.163.com",
    },
    {
        "name": "smtp_port",
        "type": "number",
        "required": False,
        "label": "SMTP Port",
        "placeholder": "587",
        "help": "默认 587（STARTTLS）或 465（隐式 SSL）",
    },
    {
        "name": "smtp_starttls",
        "type": "text",
        "required": False,
        "label": "SMTP STARTTLS",
        "placeholder": "true",
        "help": "true=SMTP+STARTTLS（常用 587）；false=SMTP_SSL（常用 465）。请填文本。",
    },
    {
        "name": "email",
        "type": "text",
        "required": True,
        "label": "Email",
        "placeholder": "you@example.com",
        "help": "邮箱地址，同时作为默认登录名与发件 From",
    },
    {
        "name": "username",
        "type": "text",
        "required": False,
        "label": "Username",
        "placeholder": "",
        "help": "登录名，留空则使用 Email",
    },
    {
        "name": "password",
        "type": "password",
        "required": True,
        "label": "Password",
        "help": "邮箱密码或授权码。不会出现在工具返回文本或卡片数据里。",
    },
    {
        "name": "from_name",
        "type": "text",
        "required": False,
        "label": "From name",
        "placeholder": "",
        "help": "可选发件显示名",
    },
]

_TRUE = frozenset({"1", "true", "yes", "on", "y"})
_FALSE = frozenset({"0", "false", "no", "off", "n"})


class IncompleteMailboxConfig(ValueError):
    """Raised when required mailbox fields are missing."""


@dataclass(frozen=True)
class MailboxConfig:
    pop3_host: str
    pop3_port: int
    pop3_ssl: bool
    smtp_host: str
    smtp_port: int
    smtp_starttls: bool
    email: str
    username: str
    password: str
    from_name: str

    def public_identity(self) -> dict[str, Any]:
        """Safe subset for UI / model text — never includes the password."""
        return {
            "email": self.email,
            "from_name": self.from_name,
            "pop3_host": self.pop3_host,
            "pop3_port": self.pop3_port,
            "pop3_ssl": self.pop3_ssl,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "smtp_starttls": self.smtp_starttls,
        }


def parse_bool(value: object, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    key = str(value).strip().lower()
    if key in _TRUE:
        return True
    if key in _FALSE:
        return False
    return default


def _merge_tool_configs() -> dict[str, Any]:
    """Prefer a complete form on any sibling tool so users fill one card."""
    merged: dict[str, Any] = {}
    for name in TOOL_NAMES:
        cfg = get_tool_config(name) or {}
        if not isinstance(cfg, dict):
            continue
        for key, value in cfg.items():
            if value in (None, ""):
                continue
            if key not in merged:
                merged[key] = value
    return merged


def _as_port(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        port = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise IncompleteMailboxConfig(f"invalid port: {value!r}") from exc
    if port < 1 or port > 65535:
        raise IncompleteMailboxConfig(f"invalid port: {port}")
    return port


def redact_secrets(text: str, password: str) -> str:
    if not password:
        return text
    return text.replace(password, "***")


def load_mailbox_config(*, need_pop3: bool, need_smtp: bool) -> MailboxConfig:
    raw = _merge_tool_configs()
    email = str(raw.get("email") or "").strip()
    username = str(raw.get("username") or "").strip() or email
    password = str(raw.get("password") or "")
    pop3_host = str(raw.get("pop3_host") or "").strip()
    smtp_host = str(raw.get("smtp_host") or "").strip()
    pop3_ssl = parse_bool(raw.get("pop3_ssl"), default=True)
    smtp_starttls = parse_bool(raw.get("smtp_starttls"), default=True)
    pop3_port = _as_port(raw.get("pop3_port"), 995 if pop3_ssl else 110)
    smtp_port = _as_port(raw.get("smtp_port"), 587 if smtp_starttls else 465)
    from_name = str(raw.get("from_name") or "").strip()

    missing: list[str] = []
    if not email:
        missing.append("email")
    if not password:
        missing.append("password")
    if need_pop3 and not pop3_host:
        missing.append("pop3_host")
    if need_smtp and not smtp_host:
        missing.append("smtp_host")
    if missing:
        raise IncompleteMailboxConfig("Mailbox not configured: missing " + ", ".join(missing))

    return MailboxConfig(
        pop3_host=pop3_host,
        pop3_port=pop3_port,
        pop3_ssl=pop3_ssl,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_starttls=smtp_starttls,
        email=email,
        username=username,
        password=password,
        from_name=from_name,
    )

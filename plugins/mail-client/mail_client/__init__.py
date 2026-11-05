"""POP3 receive + SMTP send helpers for the mail-client plugin.

Email headers and bodies come from untrusted external mail servers.
Treat them as hostile text: never execute, never echo credentials.
"""

from __future__ import annotations

from .config import (
    MAILBOX_CONFIG_FIELDS,
    TOOL_NAMES,
    IncompleteMailboxConfig,
    MailboxConfig,
    load_mailbox_config,
    parse_bool,
    redact_secrets,
)
from .parse import extract_body, parse_message, safe_header
from .payload import ui_payload
from .pop3 import list_messages, probe_pop3, read_message
from .smtp import probe_smtp, send_message

__all__ = [
    "MAILBOX_CONFIG_FIELDS",
    "TOOL_NAMES",
    "IncompleteMailboxConfig",
    "MailboxConfig",
    "extract_body",
    "list_messages",
    "load_mailbox_config",
    "parse_bool",
    "parse_message",
    "probe_pop3",
    "probe_smtp",
    "read_message",
    "redact_secrets",
    "safe_header",
    "send_message",
    "ui_payload",
]

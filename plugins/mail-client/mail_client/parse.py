"""Parse RFC822 bytes. Headers and bodies are untrusted external content."""

from __future__ import annotations

import email
from email import policy
from email.message import Message

# Keep list/read payloads bounded so cards stay readable.
_PREVIEW_LIMIT = 160
_BODY_LIMIT = 20_000


def parse_message(raw: bytes) -> Message:
    """Parse raw RFC822 with ``email.policy.default`` (plain ``str`` headers)."""
    return email.message_from_bytes(raw, policy=policy.default)


def safe_header(msg: Message, field: str) -> str:
    """Return *field* as a plain ``str`` safe for JSON (untrusted)."""
    return str(msg.get(field, "") or "")


def _decode_payload(part: Message, payload: bytes) -> str:
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def extract_body(msg: Message) -> str:
    """Prefer the first ``text/plain`` part. HTML send is out of scope for v1."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    return _decode_payload(part, payload).rstrip("\r\n")
        return ""
    payload = msg.get_payload(decode=True)
    if isinstance(payload, bytes):
        return _decode_payload(msg, payload).rstrip("\r\n")
    return str(payload or "").rstrip("\r\n")


def truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def preview_text(text: str) -> str:
    snippet, _cut = truncate(text.replace("\r\n", "\n").strip(), _PREVIEW_LIMIT)
    return snippet.replace("\n", " ")


def clip_body(text: str) -> tuple[str, bool]:
    return truncate(text, _BODY_LIMIT)

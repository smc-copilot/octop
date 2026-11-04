"""In-memory two-phase write confirmation tokens for gateway mail adapters.

Tokens are process-local, TTL-bound, and consumed once. Restart invalidates
pending drafts (acceptable for mail draft confirmation).
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

_DEFAULT_TTL_S = 300


@dataclass(frozen=True)
class ConfirmationRecord:
    tool: str
    args: dict[str, Any]
    user_id: int | None
    instance_id: str | None
    expires: float


class ConfirmationStore:
    """Thread-safe in-memory confirmation token table."""

    def __init__(self, *, ttl_s: int = _DEFAULT_TTL_S) -> None:
        self._ttl_s = ttl_s
        self._lock = threading.Lock()
        self._items: dict[str, ConfirmationRecord] = {}

    def issue(
        self,
        *,
        tool: str,
        args: dict[str, Any],
        user_id: int | None = None,
        instance_id: str | None = None,
    ) -> tuple[str, int]:
        self.purge_expired()
        token = secrets.token_hex(24)
        expires = time.time() + self._ttl_s
        with self._lock:
            self._items[token] = ConfirmationRecord(
                tool=tool,
                args=dict(args),
                user_id=user_id,
                instance_id=instance_id,
                expires=expires,
            )
        return token, self._ttl_s

    def consume(
        self,
        token: str,
        *,
        tool: str,
        args: dict[str, Any],
        user_id: int | None = None,
        instance_id: str | None = None,
    ) -> ConfirmationRecord:
        """Claim *token* once. Raises ``ValueError`` on mismatch/expiry/replay."""
        with self._lock:
            record = self._items.pop(token, None)
        if record is None:
            raise ValueError("invalid confirmation token")
        if record.expires < time.time():
            raise ValueError("confirmation token expired")
        if record.tool != tool or record.args != args:
            raise ValueError("confirmation token mismatch")
        if user_id is not None and record.user_id is not None and record.user_id != user_id:
            raise ValueError("confirmation token mismatch")
        if (
            instance_id is not None
            and record.instance_id is not None
            and record.instance_id != instance_id
        ):
            raise ValueError("confirmation token mismatch")
        return record

    def purge_expired(self) -> None:
        now = time.time()
        with self._lock:
            expired = [key for key, rec in self._items.items() if rec.expires < now]
            for key in expired:
                del self._items[key]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


# Process-wide store shared by qq-mail (and future gateway write adapters).
STORE = ConfirmationStore()

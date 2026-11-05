"""``octop_ui`` envelopes for chat cards."""

from __future__ import annotations

import json
from typing import Any


def ui_payload(renderer: str, data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {
            "octop_ui": {"renderer": renderer, "version": 1},
            "data": data,
            "text": text,
        },
        ensure_ascii=False,
    )


def error_payload(renderer: str, message: str, *, extra: dict[str, Any] | None = None) -> str:
    data: dict[str, Any] = {"error": message}
    if extra:
        data.update(extra)
    return ui_payload(renderer, data, message)

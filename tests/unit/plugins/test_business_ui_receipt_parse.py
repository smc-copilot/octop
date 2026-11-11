from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "business-ui"
sys.path.insert(0, str(_PLUGIN_ROOT))

from business_ui.receipt import (  # noqa: E402
    EVENT_REJECTED,
    EVENT_SUCCESS,
    RESULT_ERROR,
    RESULT_REJECTED,
    RESULT_SUCCESS,
    STATUS_FAILED,
    STATUS_UNKNOWN,
    apply_result_constraints,
    buttons_for,
    coerce_legacy_result,
    disclosable_message,
    is_duplicate,
    is_stale,
    mask_sensitive,
    merge_receipt,
    parse_result,
    unknown_timeout_patch,
)


def test_parse_result_types_and_safe_retry() -> None:
    ok = parse_result({"type": "SUCCESS"})
    assert ok is not None
    assert ok["type"] == RESULT_SUCCESS
    rejected = parse_result(
        {"type": "BUSINESS_REJECTED", "code": "PERMISSION_DENIED", "message": "no"}
    )
    assert rejected is not None
    assert rejected["type"] == RESULT_REJECTED
    failed = parse_result(
        {
            "type": "TECHNICAL_ERROR",
            "status": "FAILED",
            "safe_retry": True,
            "idempotent": True,
            "side_effect": False,
            "message": "failed",
        }
    )
    assert failed is not None
    assert failed["status"] == STATUS_FAILED
    assert failed["safe_retry"] is True
    unsafe = parse_result(
        {
            "type": "TECHNICAL_ERROR",
            "status": "FAILED",
            "safe_retry": True,
            "side_effect": True,
        }
    )
    assert unsafe is not None
    assert unsafe["safe_retry"] is False
    unknown = parse_result({"type": "TECHNICAL_ERROR"})
    assert unknown is not None
    assert unknown["status"] == STATUS_UNKNOWN
    assert parse_result({"type": "NOPE"}) is None


def test_disclosable_and_masking() -> None:
    assert disclosable_message("INTERNAL_TRACE", "stack", disclosable=True) is None
    assert disclosable_message("PERMISSION_DENIED", "no access", disclosable=True) == "no access"
    assert disclosable_message("X", "hidden", disclosable=False) is None
    masked = mask_sensitive({"title": "ok", "password": "supersecret", "token": "abcdef"})
    assert masked["title"] == "ok"
    assert "supersecret" not in str(masked)
    assert "abcdef" not in str(masked)


def test_legacy_submitted_maps_to_success() -> None:
    parsed = coerce_legacy_result({"status": "submitted", "record_id": "REQ-1"})
    assert parsed is not None
    assert parsed["type"] == RESULT_SUCCESS


def test_buttons_policy_and_rejected_keeps_record() -> None:
    success = apply_result_constraints(
        {
            "record_id": "REQ-1",
            "result": {"type": RESULT_SUCCESS, "status": RESULT_SUCCESS},
            "allowed_actions": ["view_document", "edit", "submit", "close"],
        }
    )
    assert success["event"] == EVENT_SUCCESS
    assert "edit" not in success["allowed_actions"]
    assert "view_document" in success["allowed_actions"]
    permission = apply_result_constraints(
        {
            "record_id": None,
            "result": {
                "type": RESULT_REJECTED,
                "status": RESULT_REJECTED,
                "code": "PERMISSION_DENIED",
            },
            "allowed_actions": ["edit", "submit", "view_document", "request_permission", "close"],
        }
    )
    assert permission["event"] == EVENT_REJECTED
    assert "edit" not in permission["allowed_actions"]
    assert "view_document" not in permission["allowed_actions"]
    assert "request_permission" in permission["allowed_actions"]
    kept = {
        "record_id": "REQ-KEEP",
        "record_version": 3,
        "result": {"type": RESULT_REJECTED, "status": RESULT_REJECTED, "code": "BUSINESS_RULE"},
        "allowed_actions": ["view_document", "edit", "close"],
    }
    constrained = apply_result_constraints(kept)
    assert constrained["record_id"] == "REQ-KEEP"
    assert "view_document" in constrained["allowed_actions"]
    assert "edit" not in constrained["allowed_actions"]
    unknown = apply_result_constraints(
        {
            "result": {"type": RESULT_ERROR, "status": STATUS_UNKNOWN},
            "allowed_actions": ["query_status", "retry", "submit", "close"],
        }
    )
    assert unknown["allowed_actions"] == ["query_status", "close"]
    failed = apply_result_constraints(
        {
            "result": {
                "type": RESULT_ERROR,
                "status": STATUS_FAILED,
                "safe_retry": True,
            },
            "allowed_actions": ["retry", "submit", "close"],
        }
    )
    assert "retry" in failed["allowed_actions"]
    assert "submit" not in failed["allowed_actions"]


def test_stale_and_duplicate_receipts_do_not_overwrite() -> None:
    current = {
        "record_version": 4,
        "receipt_sequence": 8,
        "operation_id": "op-1",
        "result": {"type": RESULT_SUCCESS, "status": RESULT_SUCCESS, "code": None},
        "record_id": "REQ-NEW",
    }
    stale_ver = {**current, "record_version": 3, "receipt_sequence": 9, "record_id": "REQ-OLD"}
    assert is_stale(current, stale_ver)
    assert merge_receipt(current, stale_ver)["record_id"] == "REQ-NEW"
    stale_seq = {**current, "receipt_sequence": 7}
    assert is_stale(current, stale_seq)
    dup = dict(current)
    assert is_duplicate(current, dup)
    assert merge_receipt(current, dup)["record_id"] == "REQ-NEW"
    newer = {
        **current,
        "record_version": 5,
        "receipt_sequence": 9,
        "operation_id": "op-2",
        "result": {"type": RESULT_REJECTED, "status": RESULT_REJECTED, "code": "BUSINESS_RULE"},
        "record_id": "REQ-NEW",
        "allowed_actions": ["view_document", "close"],
    }
    merged = merge_receipt(current, newer)
    assert merged["result"]["type"] == RESULT_REJECTED
    assert merged["record_id"] == "REQ-NEW"


def test_timeout_marks_unknown_not_silent() -> None:
    current = {"submission_status": "draft", "allowed_actions": ["submit"], "operation_id": "op-x"}
    patched = unknown_timeout_patch(current, operation_id="op-x")
    assert patched["result"]["type"] == RESULT_ERROR
    assert patched["result"]["status"] == STATUS_UNKNOWN
    assert "query_status" in patched["allowed_actions"]
    assert buttons_for(patched) == ["query_status", "close"]

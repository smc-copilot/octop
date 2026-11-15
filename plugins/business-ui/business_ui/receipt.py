"""business-ui.v1.1 unified receipt: parse, order, and button policy."""

from __future__ import annotations

from typing import Any, Literal

RESULT_SUCCESS = "SUCCESS"
RESULT_REJECTED = "BUSINESS_REJECTED"
RESULT_ERROR = "TECHNICAL_ERROR"
STATUS_FAILED = "FAILED"
STATUS_UNKNOWN = "UNKNOWN"

EVENT_SUCCESS = "BUSINESS_OPERATION_SUCCESS"
EVENT_REJECTED = "BUSINESS_OPERATION_REJECTED"
EVENT_ERROR = "BUSINESS_OPERATION_ERROR"
EVENT_RESOLVED = "BUSINESS_OPERATION_RESOLVED"
EVENT_VIEW = "DOCUMENT_VIEW_REQUESTED"

ALLOWED_RESULT_TYPES = {RESULT_SUCCESS, RESULT_REJECTED, RESULT_ERROR}
TECH_STATUSES = {STATUS_FAILED, STATUS_UNKNOWN}

VIEW_ACTIONS = {"view_document", "view_detail"}
MUTATING_ACTIONS = {"edit", "save", "submit"}
RETRY_ACTIONS = {"retry"}
QUERY_ACTIONS = {"query_status", "queryStatus"}
PERMISSION_ACTIONS = {"request_permission", "requestPermission"}
CONTINUE_ACTIONS = {"continue"}
CLOSE_ACTIONS = {"close"}

_SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "ssn",
    "id_card",
    "bank_account",
    "pan",
    "cvv",
}

_INTERNAL_CODE_PREFIXES = ("INTERNAL_", "STACK_", "TRACE_", "SQL_")


def mask_value(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


def mask_sensitive(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if (
                lowered in _SENSITIVE_KEYS
                or lowered.endswith("_secret")
                or lowered.endswith("_token")
            ):
                out[key] = mask_value(str(value)) if value is not None else "****"
            else:
                out[key] = mask_sensitive(value)
        return out
    if isinstance(payload, list):
        return [mask_sensitive(item) for item in payload]
    return payload


def disclosable_message(code: str | None, message: str | None, *, disclosable: bool) -> str | None:
    if not disclosable:
        return None
    if code and any(code.startswith(prefix) for prefix in _INTERNAL_CODE_PREFIXES):
        return None
    if not message:
        return None
    text = str(message).strip()
    if not text:
        return None
    return text[:2000]


def event_for(result_type: str, *, resolved: bool = False) -> str:
    if resolved:
        return EVENT_RESOLVED
    if result_type == RESULT_SUCCESS:
        return EVENT_SUCCESS
    if result_type == RESULT_REJECTED:
        return EVENT_REJECTED
    return EVENT_ERROR


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_result(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    result_type = str(raw.get("type") or "").upper()
    if result_type not in ALLOWED_RESULT_TYPES:
        return None
    status = raw.get("status")
    status_text = str(status).upper() if status else None
    if result_type == RESULT_ERROR:
        if status_text not in TECH_STATUSES:
            status_text = STATUS_UNKNOWN
    elif result_type == RESULT_SUCCESS:
        status_text = RESULT_SUCCESS
    else:
        status_text = RESULT_REJECTED
    code = raw.get("code")
    code_text = str(code) if code else None
    disclosable = raw.get("disclosable")
    if disclosable is None:
        disclosable = True
    message = disclosable_message(code_text, raw.get("message"), disclosable=bool(disclosable))
    safe_retry = bool(raw.get("safe_retry") or raw.get("safeRetry"))
    idempotent = bool(raw.get("idempotent"))
    side_effect = raw.get("side_effect")
    if side_effect is None:
        side_effect = raw.get("sideEffect")
    if result_type != RESULT_ERROR:
        safe_retry = False
    if status_text != STATUS_FAILED:
        safe_retry = False
    if side_effect is True:
        safe_retry = False
    return {
        "type": result_type,
        "status": status_text,
        "code": code_text,
        "message": message,
        "disclosable": bool(disclosable) and message is not None,
        "safe_retry": safe_retry and idempotent or (safe_retry and side_effect is False),
        "idempotent": idempotent,
        "side_effect": None if side_effect is None else bool(side_effect),
    }


def coerce_legacy_result(body: dict[str, Any]) -> dict[str, Any] | None:
    parsed = parse_result(body.get("result"))
    if parsed is not None:
        return parsed
    status = str(body.get("status") or body.get("submission_status") or "")
    if status == "submitted":
        return {
            "type": RESULT_SUCCESS,
            "status": RESULT_SUCCESS,
            "code": None,
            "message": None,
            "disclosable": True,
            "safe_retry": False,
            "idempotent": bool(body.get("idempotent")),
            "side_effect": True,
        }
    return None


def normalize_actions(actions: list[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in actions or []:
        name = str(item).strip()
        if name == "queryStatus":
            name = "query_status"
        if name == "requestPermission":
            name = "request_permission"
        if name == "view_detail":
            name = "view_document"
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def buttons_for(state: dict[str, Any]) -> list[str]:
    result = state.get("result") if isinstance(state.get("result"), dict) else {}
    result_type = str(result.get("type") or "")
    status = str(result.get("status") or "")
    allowed = normalize_actions(list(state.get("allowed_actions") or []))
    record_id = state.get("record_id")
    buttons: list[str] = []

    def take(*names: str) -> None:
        for name in names:
            if name in allowed and name not in buttons:
                buttons.append(name)

    if result_type == RESULT_SUCCESS:
        if record_id:
            take("view_document")
        take("continue", "close")
        return buttons
    if result_type == RESULT_REJECTED:
        if record_id:
            take("view_document")
        take("request_permission", "continue", "close")
        return buttons
    if result_type == RESULT_ERROR and status == STATUS_UNKNOWN:
        take("query_status", "close")
        return buttons
    if result_type == RESULT_ERROR and status == STATUS_FAILED:
        if result.get("safe_retry"):
            take("retry")
        take("close")
        return buttons
    take("edit", "save", "submit", "cancel", "close")
    return buttons


def apply_result_constraints(state: dict[str, Any]) -> dict[str, Any]:
    next_state = dict(state)
    result = next_state.get("result") if isinstance(next_state.get("result"), dict) else None
    if result is None:
        next_state["allowed_actions"] = buttons_for(next_state)
        return next_state
    result_type = str(result.get("type") or "")
    if result_type == RESULT_REJECTED and not next_state.get("record_id"):
        next_state["record_id"] = None
    if result_type == RESULT_SUCCESS:
        next_state["submission_status"] = "submitted"
    elif result_type == RESULT_REJECTED:
        if next_state.get("submission_status") not in {"submitted", "draft"}:
            next_state["submission_status"] = "draft"
    elif result_type == RESULT_ERROR and str(result.get("status")) == STATUS_UNKNOWN:
        if next_state.get("submission_status") == "submitted":
            pass
        else:
            next_state["submission_status"] = "pending"
    next_state["allowed_actions"] = buttons_for(next_state)
    next_state["event"] = event_for(
        result_type, resolved=bool(next_state.get("resolved_from_unknown"))
    )
    return next_state


def is_stale(current: dict[str, Any], incoming: dict[str, Any]) -> bool:
    cur_ver = _int(current.get("record_version"))
    new_ver = _int(incoming.get("record_version"))
    if new_ver < cur_ver:
        return True
    cur_seq = _int(current.get("receipt_sequence"))
    new_seq = _int(incoming.get("receipt_sequence"))
    return bool(new_ver == cur_ver and new_seq < cur_seq)


def is_duplicate(current: dict[str, Any], incoming: dict[str, Any]) -> bool:
    cur_op = current.get("operation_id") or current.get("last_operation_id")
    new_op = incoming.get("operation_id") or incoming.get("last_operation_id")
    if not cur_op or not new_op or cur_op != new_op:
        return False
    cur_result = current.get("result") if isinstance(current.get("result"), dict) else {}
    new_result = incoming.get("result") if isinstance(incoming.get("result"), dict) else {}
    return (
        cur_result.get("type") == new_result.get("type")
        and cur_result.get("status") == new_result.get("status")
        and cur_result.get("code") == new_result.get("code")
        and _int(current.get("receipt_sequence")) == _int(incoming.get("receipt_sequence"))
    )


def merge_receipt(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if is_stale(current, incoming) or is_duplicate(current, incoming):
        return current
    merged = dict(current)
    for key in (
        "form_ref",
        "schema_version",
        "document_type",
        "navigation",
        "summary",
        "approval_status",
        "submission_status",
        "operation_id",
        "last_operation_id",
        "receipt_sequence",
        "record_version",
        "result",
        "allowed_actions",
        "last_error",
        "event",
        "resolved_from_unknown",
    ):
        if key in incoming and incoming[key] is not None:
            merged[key] = incoming[key]
    incoming_record = incoming.get("record_id")
    if incoming_record or (
        str((incoming.get("result") or {}).get("type") or "") != RESULT_REJECTED
        and "record_id" in incoming
    ):
        merged["record_id"] = incoming_record
    return apply_result_constraints(merged)


def unknown_timeout_patch(current: dict[str, Any], *, operation_id: str | None) -> dict[str, Any]:
    next_state = dict(current)
    next_state["result"] = {
        "type": RESULT_ERROR,
        "status": STATUS_UNKNOWN,
        "code": "RECEIPT_TIMEOUT",
        "message": "操作结果未知，请查询状态，不要重复提交。",
        "disclosable": True,
        "safe_retry": False,
        "idempotent": False,
        "side_effect": None,
    }
    if operation_id:
        next_state["operation_id"] = operation_id
        next_state["last_operation_id"] = operation_id
    allowed = normalize_actions(list(next_state.get("allowed_actions") or []))
    if "query_status" not in allowed:
        allowed.append("query_status")
    if "close" not in allowed:
        allowed.append("close")
    next_state["allowed_actions"] = allowed
    next_state["event"] = EVENT_ERROR
    next_state["submission_status"] = "pending"
    return apply_result_constraints(next_state)


ReceiptEvent = Literal[
    "BUSINESS_OPERATION_SUCCESS",
    "BUSINESS_OPERATION_REJECTED",
    "BUSINESS_OPERATION_ERROR",
    "BUSINESS_OPERATION_RESOLVED",
    "DOCUMENT_VIEW_REQUESTED",
]

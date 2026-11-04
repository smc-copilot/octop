"""Admin overview/audit/metrics router."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from octop.api.deps import get_server, require_permission
from octop.config import DEFAULT_MARKET_MODE, VALID_MARKET_MODES, parse_market_mode
from octop.infra.db.repos.market_policy import (
    EFFECT_ALLOW,
    EFFECT_DENY,
    RESOURCE_SKILL,
    RESOURCE_SKILLSET,
    VALID_EFFECTS,
    VALID_RESOURCE_TYPES,
)
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


class MarketPolicyRuleCreateBody(BaseModel):
    resource_type: Literal["skill", "skillset"]
    slug: str = Field(..., min_length=1, max_length=200)
    effect: Literal["allow", "deny"] = "allow"
    user_group_id: str | None = None
    priority: int = 0


def _market_mode_of(server: Any) -> str:
    config = getattr(getattr(server, "services", None), "config", None)
    raw = (
        getattr(config, "market_mode", DEFAULT_MARKET_MODE)
        if config is not None
        else (DEFAULT_MARKET_MODE)
    )
    return parse_market_mode(raw, default=DEFAULT_MARKET_MODE)


def _rule_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "resource_type": row.resource_type,
        "slug": row.slug,
        "effect": row.effect,
        "user_group_id": row.user_group_id,
        "priority": row.priority,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("/overview")
async def overview(
    _: Any = Depends(require_permission("admin_console")), server: Any = Depends(get_server)
) -> dict[str, Any]:
    assert server.app_runtime is not None
    users = []
    for user in server.user_manager.list():
        users.append(
            {
                "username": user.username,
                "role": user.role,
                "agents": [],  # agents are now global, not per-user
            }
        )
    agents = [
        {
            "id": r.id,
            "agent_id": r.agent_id,
            "name": r.name,
            "state": r.last_state or "unknown",
        }
        for r in server.app_runtime.agent_registry.list_rows()
    ]
    return {
        "users": users,
        "agents": agents,
        "totals": {
            "users": len(users),
            "agents": len(agents),
        },
    }


# The largest page the Settings → Security audit panel offers.
AUDIT_LOG_MAX_LIMIT = 500


@router.get("/audit-log")
async def audit_log(
    since: int | None = None,
    actor: str | None = None,
    action: str | None = None,
    limit: int = Query(
        default=100,
        ge=1,
        le=AUDIT_LOG_MAX_LIMIT,
        description=f"Maximum rows to return, between 1 and {AUDIT_LOG_MAX_LIMIT}.",
    ),
    _: Any = Depends(require_permission("admin_console")),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    rows = server.services.audit_repo.query(since=since, actor=actor, action=action, limit=limit)
    return [
        {
            "id": r.id,
            "ts": r.ts,
            "actor": r.actor,
            "action": r.action,
            "target": r.target,
            "payload": r.payload,
        }
        for r in rows
    ]


@router.get("/metrics")
async def metrics(
    _: Any = Depends(require_permission("admin_console")), server: Any = Depends(get_server)
) -> dict[str, Any]:
    from octop.infra.metrics import METRICS

    assert server.app_runtime is not None
    METRICS.set(
        "agent_active",
        len(server.app_runtime.agent_registry.list_rows()),
    )
    return METRICS.snapshot()


@router.get(
    "/market-policy",
    summary="List market policy rules and current market_mode",
)
async def list_market_policy(
    _: Any = Depends(require_permission("admin_console")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    rows = server.services.market_policy_repo.list_all()
    return {
        "market_mode": _market_mode_of(server),
        "valid_modes": sorted(VALID_MARKET_MODES),
        "valid_resource_types": sorted(VALID_RESOURCE_TYPES),
        "valid_effects": sorted(VALID_EFFECTS),
        "rules": [_rule_dict(row) for row in rows],
    }


@router.post(
    "/market-policy/rules",
    status_code=201,
    summary="Add a market slug allow/deny rule",
)
async def create_market_policy_rule(
    body: MarketPolicyRuleCreateBody,
    user: Any = Depends(require_permission("admin_console")),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    if body.resource_type not in (RESOURCE_SKILL, RESOURCE_SKILLSET):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid resource_type")
    if body.effect not in (EFFECT_ALLOW, EFFECT_DENY):
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "invalid effect")
    group_id = (body.user_group_id or "").strip() or None
    if group_id is not None:
        group = server.services.user_group_repo.get(group_id)
        if group is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"user group {group_id!r} not found")
    try:
        row = server.services.market_policy_repo.create(
            resource_type=body.resource_type,
            slug=body.slug.strip(),
            effect=body.effect,
            user_group_id=group_id,
            priority=int(body.priority),
        )
    except ValueError as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, str(exc)) from exc
    server.services.audit_repo.write(
        actor=user.username,
        action="market.policy.create",
        target=row.id,
        payload=f"{row.resource_type}:{row.slug}:{row.effect}",
    )
    return _rule_dict(row)


@router.delete(
    "/market-policy/rules/{rule_id}",
    status_code=204,
    summary="Delete a market policy rule",
)
async def delete_market_policy_rule(
    rule_id: str,
    user: Any = Depends(require_permission("admin_console")),
    server: Any = Depends(get_server),
) -> None:
    existing = server.services.market_policy_repo.get(rule_id)
    if existing is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"market policy rule {rule_id!r} not found")
    server.services.market_policy_repo.delete(rule_id)
    server.services.audit_repo.write(
        actor=user.username,
        action="market.policy.delete",
        target=rule_id,
        payload=f"{existing.resource_type}:{existing.slug}:{existing.effect}",
    )

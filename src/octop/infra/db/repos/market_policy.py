"""Allow/deny rules for SkillHub skill and skillset market slugs."""

from __future__ import annotations

import time
from dataclasses import dataclass

from octop.infra.db.pool import DatabasePool
from octop.infra.utils.ulid import new_ulid

RESOURCE_SKILL = "skill"
RESOURCE_SKILLSET = "skillset"
EFFECT_ALLOW = "allow"
EFFECT_DENY = "deny"
VALID_RESOURCE_TYPES = frozenset({RESOURCE_SKILL, RESOURCE_SKILLSET})
VALID_EFFECTS = frozenset({EFFECT_ALLOW, EFFECT_DENY})


@dataclass(frozen=True)
class MarketPolicyRuleRow:
    id: str
    resource_type: str
    slug: str
    effect: str
    user_group_id: str | None
    priority: int
    created_at: int
    updated_at: int
    pk: int = 0

    @classmethod
    def from_row(cls, r: object) -> MarketPolicyRuleRow:
        keys = set(r.keys())  # type: ignore[attr-defined]
        group_raw = r["user_group_id"] if "user_group_id" in keys else None  # type: ignore[index]
        group_id = str(group_raw).strip() if group_raw is not None else None
        if group_id == "":
            group_id = None
        return cls(
            id=str(r["rule_id"]),  # type: ignore[index]
            resource_type=str(r["resource_type"]),  # type: ignore[index]
            slug=str(r["slug"]),  # type: ignore[index]
            effect=str(r["effect"]),  # type: ignore[index]
            user_group_id=group_id,
            priority=int(r["priority"] or 0),  # type: ignore[index]
            created_at=int(r["created_at"]),  # type: ignore[index]
            updated_at=int(r["updated_at"]),  # type: ignore[index]
            pk=int(r["id"]) if "id" in keys else 0,  # type: ignore[index]
        )


class MarketPolicyRepo:
    def __init__(self, db: DatabasePool) -> None:
        self._db = db

    def list_all(self) -> list[MarketPolicyRuleRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM market_policy_rules"
                " ORDER BY resource_type, priority DESC, slug, rule_id"
            ).fetchall()
        return [MarketPolicyRuleRow.from_row(row) for row in rows]

    def list_for_type(self, resource_type: str) -> list[MarketPolicyRuleRow]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM market_policy_rules WHERE resource_type = ?"
                " ORDER BY priority DESC, slug, rule_id",
                (resource_type,),
            ).fetchall()
        return [MarketPolicyRuleRow.from_row(row) for row in rows]

    def get(self, rule_id: str) -> MarketPolicyRuleRow | None:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM market_policy_rules WHERE rule_id = ?",
                (rule_id,),
            ).fetchone()
        return MarketPolicyRuleRow.from_row(row) if row is not None else None

    def create(
        self,
        *,
        resource_type: str,
        slug: str,
        effect: str,
        user_group_id: str | None = None,
        priority: int = 0,
        rule_id: str | None = None,
    ) -> MarketPolicyRuleRow:
        if resource_type not in VALID_RESOURCE_TYPES:
            raise ValueError(f"invalid resource_type: {resource_type!r}")
        if effect not in VALID_EFFECTS:
            raise ValueError(f"invalid effect: {effect!r}")
        clean_slug = str(slug or "").strip()
        if not clean_slug:
            raise ValueError("slug is required")
        group = (user_group_id or "").strip() or None
        public_id = (rule_id or "").strip() or new_ulid()
        ts = int(time.time() * 1000)
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO market_policy_rules("
                "rule_id, resource_type, slug, effect, user_group_id, priority,"
                " created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    public_id,
                    resource_type,
                    clean_slug,
                    effect,
                    group,
                    int(priority),
                    ts,
                    ts,
                ),
            )
        row = self.get(public_id)
        assert row is not None
        return row

    def delete(self, rule_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM market_policy_rules WHERE rule_id = ?",
                (rule_id,),
            )
        return int(cursor.rowcount or 0) > 0

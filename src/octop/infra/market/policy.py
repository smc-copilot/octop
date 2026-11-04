"""Market catalog policy: mode gates, slug allowlists, and mirror sources."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from octop.config import DEFAULT_MARKET_MODE, VALID_MARKET_MODES, parse_market_mode
from octop.infra.db.repos.market_policy import (
    EFFECT_ALLOW,
    EFFECT_DENY,
    RESOURCE_SKILL,
    RESOURCE_SKILLSET,
    MarketPolicyRepo,
    MarketPolicyRuleRow,
)
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)


# @lat: [[domain#Market governance]]
class MarketCatalogPolicy:
    """Single gate for SkillHub skill / skillset market operations."""

    def __init__(
        self,
        *,
        market_mode: str,
        policy_repo: MarketPolicyRepo | None,
        member_group_ids: Callable[[int], set[str]] | None = None,
        audit: Callable[..., None] | None = None,
    ) -> None:
        self._mode = parse_market_mode(market_mode, default=DEFAULT_MARKET_MODE)
        self._policy_repo = policy_repo
        self._member_group_ids = member_group_ids or (lambda _uid: set())
        self._audit = audit

    @property
    def mode(self) -> str:
        return self._mode

    def assert_market_enabled(self) -> None:
        if self._mode == "off":
            raise OctopError(
                ErrorCode.MARKET_DISABLED,
                "skill / expert market is disabled",
                details={"market_mode": self._mode},
            )

    def assert_remote_catalog_allowed(self) -> None:
        """Raise when the caller must not hit SkillHub list/search endpoints."""
        self.assert_market_enabled()
        if self._mode == "mirror_only":
            raise OctopError(
                ErrorCode.MARKET_DISABLED,
                "remote market catalog is disabled in mirror_only mode",
                details={"market_mode": self._mode},
            )

    def assert_install_skill(self, user_id: int, slug: str, *, is_admin: bool = False) -> None:
        self.assert_market_enabled()
        self._assert_slug_allowed(
            user_id,
            RESOURCE_SKILL,
            slug,
            is_admin=is_admin,
        )

    def assert_install_skillset(
        self,
        user_id: int,
        slug: str,
        *,
        child_skill_slugs: Sequence[str] = (),
        is_admin: bool = False,
    ) -> None:
        self.assert_market_enabled()
        self._assert_slug_allowed(
            user_id,
            RESOURCE_SKILLSET,
            slug,
            is_admin=is_admin,
        )
        for child in child_skill_slugs:
            clean = str(child or "").strip()
            if not clean:
                continue
            self._assert_slug_allowed(
                user_id,
                RESOURCE_SKILL,
                clean,
                is_admin=is_admin,
            )

    def filter_skill_slugs(
        self,
        user_id: int,
        slugs: Sequence[str],
        *,
        is_admin: bool = False,
    ) -> list[str]:
        self.assert_market_enabled()
        if self._mode in {"public", "mirror_only"} or is_admin:
            return [str(s).strip() for s in slugs if str(s).strip()]
        return [
            clean
            for raw in slugs
            if (clean := str(raw or "").strip())
            and self._slug_allowed(user_id, RESOURCE_SKILL, clean, is_admin=False)
        ]

    def filter_skillset_items(
        self,
        user_id: int,
        items: Sequence[Any],
        *,
        slug_of: Callable[[Any], str],
        is_admin: bool = False,
    ) -> list[Any]:
        self.assert_market_enabled()
        if self._mode in {"public", "mirror_only"} or is_admin:
            return list(items)
        kept: list[Any] = []
        for item in items:
            slug = str(slug_of(item) or "").strip()
            if slug and self._slug_allowed(user_id, RESOURCE_SKILLSET, slug, is_admin=False):
                kept.append(item)
        return kept

    def record(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        payload: str = "",
    ) -> None:
        if self._audit is None:
            return
        try:
            self._audit(actor=actor, action=action, target=target, payload=payload)
        except Exception:
            logger.exception("market audit write failed action=%s target=%s", action, target)

    def _assert_slug_allowed(
        self,
        user_id: int,
        resource_type: str,
        slug: str,
        *,
        is_admin: bool,
    ) -> None:
        clean = str(slug or "").strip()
        if not clean:
            raise OctopError(ErrorCode.MARKET_SLUG_DENIED, "empty market slug")
        if self._slug_allowed(user_id, resource_type, clean, is_admin=is_admin):
            return
        raise OctopError(
            ErrorCode.MARKET_SLUG_DENIED,
            f"market slug not allowed: {clean}",
            details={"resource_type": resource_type, "slug": clean, "market_mode": self._mode},
        )

    def _slug_allowed(
        self,
        user_id: int,
        resource_type: str,
        slug: str,
        *,
        is_admin: bool,
    ) -> bool:
        if is_admin:
            return True
        if self._mode in {"public", "mirror_only"}:
            return True
        if self._mode != "allowlist":
            return False
        if self._policy_repo is None:
            return False
        rules = self._policy_repo.list_for_type(resource_type)
        return _evaluate_allowlist(
            rules,
            slug=slug,
            member_groups=self._member_group_ids(user_id),
        )


def _evaluate_allowlist(
    rules: Sequence[MarketPolicyRuleRow],
    *,
    slug: str,
    member_groups: set[str],
) -> bool:
    """Deny wins over allow. Group rules override global for the same slug.

    No matching allow → denied (default-closed).
    """
    matching = [rule for rule in rules if rule.slug == slug]
    if not matching:
        return False

    group_rules = [
        rule for rule in matching if rule.user_group_id and rule.user_group_id in member_groups
    ]
    global_rules = [rule for rule in matching if rule.user_group_id is None]
    effective = group_rules if group_rules else global_rules
    if not effective:
        return False

    # Higher priority first; deny beats allow at the same priority.
    ordered = sorted(
        effective,
        key=lambda rule: (rule.priority, 1 if rule.effect == EFFECT_DENY else 0),
        reverse=True,
    )
    top_priority = ordered[0].priority
    top = [rule for rule in ordered if rule.priority == top_priority]
    if any(rule.effect == EFFECT_DENY for rule in top):
        return False
    return any(rule.effect == EFFECT_ALLOW for rule in top)


def market_policy_from_server(server: Any) -> MarketCatalogPolicy:
    """Build a policy bound to the running server's config and repos."""
    services = getattr(server, "services", None)
    config = getattr(services, "config", None) if services is not None else None
    mode = (
        getattr(config, "market_mode", DEFAULT_MARKET_MODE)
        if config is not None
        else (DEFAULT_MARKET_MODE)
    )
    if mode not in VALID_MARKET_MODES:
        mode = DEFAULT_MARKET_MODE

    policy_repo = None
    member_fn: Callable[[int], set[str]] | None = None
    audit_fn: Callable[..., None] | None = None
    repos = getattr(services, "repos", None) if services is not None else None
    if repos is not None:
        policy_repo = getattr(repos, "market_policy_repo", None)
        member_repo = getattr(repos, "user_group_member_repo", None)
        if member_repo is not None:

            def _groups(uid: int) -> set[str]:
                return set(member_repo.group_ids_for_user(uid))

            member_fn = _groups
        audit_repo = getattr(services, "audit_repo", None)
        if audit_repo is not None:

            def _audit(
                *,
                actor: str,
                action: str,
                target: str,
                payload: str = "",
            ) -> None:
                audit_repo.write(
                    actor=actor,
                    action=action,
                    target=target,
                    payload=payload[:200] if payload else None,
                )

            audit_fn = _audit

    return MarketCatalogPolicy(
        market_mode=str(mode),
        policy_repo=policy_repo,
        member_group_ids=member_fn,
        audit=audit_fn,
    )

"""Unit tests for MarketCatalogPolicy mode and allowlist resolution."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.market.policy import MarketCatalogPolicy, _evaluate_allowlist


@dataclass(frozen=True)
class _Rule:
    id: str
    resource_type: str
    slug: str
    effect: str
    user_group_id: str | None
    priority: int
    created_at: int = 0
    updated_at: int = 0


class _FakeRepo:
    def __init__(self, rules: list[_Rule]) -> None:
        self._rules = rules

    def list_for_type(self, resource_type: str) -> list[_Rule]:
        return [rule for rule in self._rules if rule.resource_type == resource_type]


def _policy(
    mode: str,
    *,
    rules: list[_Rule] | None = None,
    groups: set[str] | None = None,
    audits: list[tuple[str, str, str]] | None = None,
) -> MarketCatalogPolicy:
    audit_sink = audits

    def _audit(*, actor: str, action: str, target: str, payload: str = "") -> None:
        if audit_sink is not None:
            audit_sink.append((action, target, payload))

    return MarketCatalogPolicy(
        market_mode=mode,
        policy_repo=_FakeRepo(rules or []) if rules is not None else None,
        member_group_ids=lambda _uid: set(groups or ()),
        audit=_audit if audit_sink is not None else None,
    )


# @lat: [[tests#Market catalog policy#Off mode blocks market]]
def test_off_mode_blocks_market() -> None:
    policy = _policy("off")
    with pytest.raises(OctopError) as exc:
        policy.assert_market_enabled()
    assert exc.value.code == ErrorCode.MARKET_DISABLED


# @lat: [[tests#Market catalog policy#Public mode allows install]]
def test_public_mode_allows_install() -> None:
    policy = _policy("public")
    policy.assert_install_skill(1, "demo-skill")
    policy.assert_install_skillset(1, "demo-set", child_skill_slugs=["a", "b"])


# @lat: [[tests#Market catalog policy#Mirror only blocks remote catalog]]
def test_mirror_only_blocks_remote_catalog_but_allows_install() -> None:
    policy = _policy("mirror_only")
    with pytest.raises(OctopError) as exc:
        policy.assert_remote_catalog_allowed()
    assert exc.value.code == ErrorCode.MARKET_DISABLED
    policy.assert_install_skill(1, "any-skill")


# @lat: [[tests#Market catalog policy#Allowlist default deny]]
def test_allowlist_default_deny_without_rules() -> None:
    policy = _policy("allowlist", rules=[])
    with pytest.raises(OctopError) as exc:
        policy.assert_install_skill(1, "missing")
    assert exc.value.code == ErrorCode.MARKET_SLUG_DENIED


# @lat: [[tests#Market catalog policy#Group rule overrides global]]
def test_group_rule_overrides_global() -> None:
    rules = [
        _Rule("1", "skill", "foo", "deny", None, 10),
        _Rule("2", "skill", "foo", "allow", "eng", 10),
    ]
    denied = _policy("allowlist", rules=rules, groups=set())
    with pytest.raises(OctopError):
        denied.assert_install_skill(1, "foo")
    allowed = _policy("allowlist", rules=rules, groups={"eng"})
    allowed.assert_install_skill(1, "foo")


# @lat: [[tests#Market catalog policy#Deny beats allow at same priority]]
def test_deny_beats_allow_at_same_priority() -> None:
    rules = [
        _Rule("1", "skill", "foo", "allow", None, 5),
        _Rule("2", "skill", "foo", "deny", None, 5),
    ]
    assert (
        _evaluate_allowlist(rules, slug="foo", member_groups=set()) is False  # type: ignore[arg-type]
    )


# @lat: [[tests#Market catalog policy#Skillset children filtered]]
def test_skillset_install_checks_child_slugs() -> None:
    rules = [
        _Rule("1", "skillset", "set-a", "allow", None, 1),
        _Rule("2", "skill", "child-ok", "allow", None, 1),
    ]
    policy = _policy("allowlist", rules=rules)
    policy.assert_install_skillset(1, "set-a", child_skill_slugs=["child-ok"])
    with pytest.raises(OctopError) as exc:
        policy.assert_install_skillset(1, "set-a", child_skill_slugs=["child-bad"])
    assert exc.value.code == ErrorCode.MARKET_SLUG_DENIED


# @lat: [[tests#Market catalog policy#Filter skillset items]]
def test_filter_skillset_items() -> None:
    rules = [_Rule("1", "skillset", "keep-me", "allow", None, 1)]
    policy = _policy("allowlist", rules=rules)

    class Item:
        def __init__(self, slug: str) -> None:
            self.slug = slug

    kept = policy.filter_skillset_items(
        1,
        [Item("keep-me"), Item("drop-me")],
        slug_of=lambda item: item.slug,
    )
    assert [item.slug for item in kept] == ["keep-me"]


# @lat: [[tests#Market catalog policy#Audit record]]
def test_record_writes_audit() -> None:
    audits: list[tuple[str, str, str]] = []
    policy = _policy("public", audits=audits)
    policy.record(actor="alice", action="market.search", target="skill", payload="n=1")
    assert audits == [("market.search", "skill", "n=1")]

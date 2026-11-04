# Market governance

Octop gates SkillHub skill and expert (skillset) markets with three layers:

1. **Instance mode** — `config.json` → `market_mode` (env `OCTOP_MARKET_MODE`)
2. **Permissions** — `skill_market` / `expert_market` (default ON for new and existing non-admin users)
3. **Slug policy** — `market_policy_rules` allow/deny list (used when `market_mode=allowlist`)

All hub list/search/install routes go through `MarketCatalogPolicy` in
`octop.infra.market.policy`. The dashboard only hides tabs; it does not replace
server checks.

## Modes

| Mode | Catalog | Install by slug |
|------|---------|-----------------|
| `public` (default) | Remote SkillHub | Allowed |
| `off` | Disabled (403) | Disabled (403) |
| `allowlist` | Remote, filtered by rules | Only allowed slugs (default-closed) |
| `mirror_only` | Local only: `published_experts` / visible `skill_packages` | Still allowed (admin mirror path) |

## Permissions

| Key | Gates |
|-----|-------|
| `expert_market` | `/api/experts/hub*` |
| `skill_market` | `/api/skills/hub*`, `/api/agents/{id}/skills/hub*`, `/api/skill-packages/hub*`, `/from-skillhub`, package hub install |

Other skill-package CRUD keeps `skill_packages`.

## Allowlist rules

Table `market_policy_rules` (migration 026):

- `resource_type`: `skill` | `skillset`
- `effect`: `allow` | `deny`
- `user_group_id`: `NULL` = global default; otherwise a `user_group` id
- Group rules override global for the same slug; deny wins over allow at the same priority
- No matching allow → denied

Admin UI: **Security → Market policy** (`GET/POST/DELETE /api/admin/market-policy*`).
Mode itself is config-only (restart after change).

## Mirror / internal templates

In `mirror_only`:

- Expert market cards come from `published_experts`
- Skill market rows come from local shared/visible skill packages
- Admins can still import from SkillHub via install / `from-skillhub` (audited as `market.mirror_import`)

## Audit

Actions: `market.search`, `market.install_skill`, `market.install_skillset`,
`market.mirror_import`, `market.policy.create`, `market.policy.delete`.

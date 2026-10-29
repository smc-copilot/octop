# Decisions

Accepted architecture choices that constrain implementation. Prefer these sections over rediscovering rationale from scattered comments.

Human ADRs: `docs/adr/001-single-process-model.md`, `docs/adr/002-database-backends.md`. Workspace I/O: `docs/agent-backend-file-io.md`.

## Single process, no external queue

Everything runs in one Python/uvicorn process: HTTP, agent runtimes, IM channels, and cron. No Redis, Celery, or separate worker.

Self-hosted install should stay `pip install` + `octop init`. Workloads are LLM-bound asyncio I/O; restart rebuilds state from the control-plane DB. Blocking work must use `run_in_executor`. See [[layers#Process boot]].

## Dual database backends

Control-plane persistence is SQLite (default) or PostgreSQL with a shared schema: parallel `NNN_*.sql` / `NNN_*.pg.sql` migrations.

Do not conflate three storage layers: (1) Octop control plane, (2) harness checkpoints, (3) agent memory (octop-memory). Workspace **content** files remain via [[domain#Workspace|BackendWorkspace]], not SQL. Details: [[persistence#Three storage layers]].

## Workspace via BackendWorkspace

All agent workspace content reads/writes go through harness `BackendWorkspace` so local and remote backends share one path model.

Octop must not branch on backend type or `virtual_mode` for content I/O, and must not use raw `Path` under the agent home for SOUL/skills/inbound. HTTP normalizes dashboard paths in [[src/octop/api/common/workspace.py#workspace_api_path]].

## Server i18n

User-facing server strings (slash, IM status, API errors, tool labels, CLI) come from `src/octop/i18n/` JSON bundles (`zh` + `en`), not hard-coded English in `infra/`.

Lookup via [[src/octop/i18n/loader.py#tr]]. Locale resolution: user preference → Accept-Language → channel hints ([[src/octop/infra/utils/locale.py#resolve_user_locale]], [[src/octop/infra/utils/locale.py#resolve_request_locale]]). Dashboard mirrors `apiErrors` and may hydrate tools from the API.

## Server timezone

User-visible datetimes and cron defaults use [[src/octop/config.py#OctopConfig]] `default_timezone` (env `OCTOP_DEFAULT_TIMEZONE`; legacy `cron_timezone` accepted), not the browser's local zone.

Dashboard formats with server TZ hooks. Language is **not** a `config.json` key — locale stays preference / Accept-Language / channel driven.

## Resource public ids

API-visible resources use integer surrogate `id` plus public string `{entity}_id` (ULID/short). Child FKs reference the **string** id, never the integer PK.

Exceptions stay documented in `AGENTS.md` §7 (users, name-keyed config, append-only logs, KV, 1:1 extensions). Migration narrative: `infra/db/migrations/007_resource_identity_and_profile.sql`. See [[persistence#Resource identity]].

## Slash commands

Slash UX is shared across IM, dashboard, and CLI. [[src/octop/infra/gateway/slash/dispatcher.py#SlashDispatcher]] routes; handlers live under `handlers/`; [[src/octop/infra/gateway/slash/dispatcher.py#build_default_dispatcher]] builds the catalog-backed default.

Some commands stay in gateway handlers; others delegate to harness runtime slash. Catalog drives help and UI labels with i18n keys.

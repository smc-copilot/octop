# Persistence

Octop separates control-plane SQL from harness checkpoints, agent memory, and workspace files so operators can choose backends without merging schemas.

Default control plane is SQLite WAL under `~/.octop`. Optional PostgreSQL shares one logical schema via parallel migrations. Decision context: [[decisions#Dual database backends]].

## Three storage layers

Layer 1 is the Octop control plane (users, agents, channels, cron, settings, secrets) via [[domain#SharedServices]]. Layer 2 is harness checkpoints. Layer 3 is agent memory (octop-memory).

Workspace content (SOUL, skills, inbound) is not SQL — it uses [[domain#Workspace|BackendWorkspace]]. Control-plane `*.pg.sql` must not `CREATE EXTENSION`; extensions are ops/docker concerns.

## Migrations

Schema changes ship as numbered pairs `infra/db/migrations/00N_*.sql` and `00N_*.pg.sql`, with a version assertion in tests.

Unreleased work on `develop` folds into the current unreleased `00N` rather than inventing `00N+1` early. `_schema_version` is an applied-migration watermark, not a changelog of every edit. Rebuild helpers in `migrate.py` stay idempotent for SQLite `ADD COLUMN` and skipped-version DBs.

## Resource identity

API-visible entities use integer `id` plus public `{entity}_id`. APIs, paths, and child FKs use the string id; keep integer as `row.pk` when both are needed.

Do not force this onto users (integer `user_id`), name-keyed config tables, append-only logs, KV settings/secrets, or ephemeral rows. Rationale: [[decisions#Resource public ids]].

## Repo access

SQL lives in `infra/db/repos/` — one repo per table. Repos may import `infra/db/_base` and `infra/utils/` only; they must not import agents, gateway, or API.

Call sites go through [[domain#SharedServices]]. Sealed repos wrap providers/backends/voice credentials with the secrets store so plaintext secrets are not scattered in domain code.

# Layer boundaries

Dependencies flow inward: surfaces call HTTP or domain adapters; domain never imports HTTP, CLI, or the composition root.

```
dashboard / CLI / IM  →  api/ or gateway  →  infra/  →  utils, repos, config
```

`launch.py` is the only module that may import both `infra/server` and `api/app`. Contributor rules live in `AGENTS.md` §5; this file captures the **why**.

## Config

[[src/octop/config.py#OctopConfig]] and [[src/octop/config.py#load_config]] load `config.json` plus env overrides without booting the server.

Config must stay free of `infra/`, `api/`, and `cli/` imports so tools and tests can read settings without a runtime tree.

## Domain (infra)

`src/octop/infra/` owns business logic and orchestration: agents, gateway, cron, users, DB, connectors, history, setup, and control surfaces.

Domain code must not import `api/`, `cli/`, `launch.py`, or the dashboard. Leaf packages (`infra/utils/`, `infra/db/repos/`) must not import higher orchestration so SQL and pure helpers stay reusable.

## HTTP adapter (api)

FastAPI routers, JWT middleware, and error mapping live under `src/octop/api/`. Handlers validate HTTP, call `infra/`, and map [[src/octop/infra/errors.py#OctopError|OctopError]] — they do not invent domain rules.

Routers receive [[src/octop/infra/server.py#OctopServer]] via [[src/octop/api/deps.py#get_server]]. App factory: [[src/octop/api/app.py#build_app]].

## CLI

Click commands under `src/octop/cli/` provide terminal UX. They must not import `api/`; `octop run` goes through [[layers#Composition root|launch]].

Transport modes: **offline** (local SQLite via repos), **embedded** (short-lived OctopServer for harness/gateway), **external** (OS/daemon). CLI trusts local `~/.octop` access — there is no `octop user login`.

## Composition root

[[src/octop/launch.py#run_foreground]] boots the domain server, attaches FastAPI via [[src/octop/api/app.py#build_app]], serves with uvicorn, then shuts down cleanly.

[[src/octop/launch.py#run_foreground_blocking]] is the sync entry for CLI and tests. Keeping wiring here prevents domain modules from depending on HTTP.

## Dashboard

Source is `dashboard/` (Vite + React). Built artifact mounts from `src/octop/dashboard/` — do not edit the artifact by hand; run `make build-frontend`.

The SPA talks to Octop only over `/api` HTTP/WebSocket so the browser never holds DB credentials or Python module layout.

## Process boot

[[src/octop/infra/server.py#OctopServer]] is the process owner; [[src/octop/infra/server.py#OctopServer#start]] builds the runtime tree from paths, config, DB migrations, [[domain#SharedServices]], catalogs, [[domain#Agent|AgentManager]], [[domain#Gateway]], [[domain#Cron|CronManager]], and [[domain#Users and auth|UserManager]].

[[src/octop/infra/server.py#AppRuntime]] holds live singletons that API and CLI reach after boot. Greenfield setup may defer the control-plane DB until the wizard binds it, then [[src/octop/infra/server.py#AppRuntime#replace_services]] retargets repos without restarting the process.

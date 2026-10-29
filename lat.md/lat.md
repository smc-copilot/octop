This directory defines the high-level concepts, business logic, and architecture of this project using markdown. It is managed by [lat.md](https://www.npmjs.com/package/lat.md) — a tool that anchors source code to these definitions. Install the `lat` command with `npm i -g lat.md` and run `lat --help`.

- [[decisions]] — Accepted architecture choices that constrain implementation
- [[domain]] — Core control-plane entities and ownership boundaries
- [[layers]] — Module boundaries, composition root, and process boot
- [[message-flow]] — Ingress to harness turn pipeline
- [[persistence]] — Control-plane storage layers, migrations, and identity

# Octop

Octop is a self-hosted multi-user, multi-agent AI assistant platform shipped as one Python wheel: FastAPI, React dashboard, and Click CLI in a single process.

It glues **octop-harness** (LangGraph agent runtime) and **octop-gateway** (IM channel pipeline) with a local control plane (SQLite by default, optional PostgreSQL). There is no external queue and no required service beyond an LLM provider. Human overview: `docs/architecture.md`. Agent handbook: `AGENTS.md`.

## Concept map

Cross-linked anchors for agents and contributors. Prefer these over re-deriving boundaries from source alone.

| Topic | Section |
|-------|---------|
| Layering & composition root | [[layers#Layer boundaries]] |
| Boot & runtime singletons | [[layers#Process boot]] |
| Agents, threads, gateway | [[domain#Agent]], [[domain#Thread]], [[domain#Gateway]] |
| Workspace I/O | [[domain#Workspace]] |
| Cron, skills, connectors | [[domain#Cron]], [[domain#Skills]], [[domain#Connectors]] |
| Users, history, DI | [[domain#Users and auth]], [[domain#History]], [[domain#SharedServices]] |
| Design decisions | [[decisions]] |
| Ingress → harness turn | [[message-flow]] |
| Control-plane persistence | [[persistence]] |

## Surfaces

Dashboard, CLI, and IM channels share one agent runtime; each surface uses a different wire but the same [[domain#Gateway|Gateway]] and [[domain#Agent|Agent]] path.

| Surface | How it reaches the runtime |
|---------|----------------------------|
| Dashboard | HTTP/WebSocket `/api` only — never imports Python or opens the DB |
| CLI | Offline repos, embedded [[layers#Process boot]] (OctopServer), or OS-level ops — never imports `api/` |
| IM | octop-gateway `ChannelManager` → [[message-flow#GlobalProcessor]] |

## Code anchors

Primary symbols carry `# @lat:` backlinks so `lat refs` can walk from concept to implementation.

| Symbol | Section |
|--------|---------|
| [[src/octop/config.py#OctopConfig]] | [[layers#Config]] |
| [[src/octop/launch.py#run_foreground]] | [[layers#Composition root]] |
| [[src/octop/infra/server.py#OctopServer]] | [[layers#Process boot]] |
| [[src/octop/infra/agents/manager.py#AgentManager]] | [[domain#Agent]] |
| [[src/octop/infra/gateway/gateway.py#Gateway]] | [[domain#Gateway]] |
| [[src/octop/infra/gateway/threads.py#ThreadRegistry]] | [[domain#Thread]] |
| [[src/octop/infra/db/services.py#SharedServices]] | [[domain#SharedServices]] |
| [[src/octop/infra/gateway/process/processor.py#GlobalProcessor]] | [[message-flow#GlobalProcessor]] |
| [[src/octop/infra/gateway/process/stream_project.py#project_stream]] | [[message-flow#Stream projection]] |
| [[src/octop/infra/gateway/slash/dispatcher.py#SlashDispatcher]] | [[decisions#Slash commands]] |

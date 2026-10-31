# Domain concepts

Core control-plane entities Octop orchestrates. Each section states the concept and its ownership boundary — not a code walkthrough.

## Agent

An agent is a DB row plus an on-demand harness runtime. Process-wide [[src/octop/infra/agents/manager.py#AgentManager]] owns start/stop, providers, MCP assembly, and workspace access.

Ownership is `agents.user_id` (admin bypass allowed). There is no per-user manager — one global registry keeps admin and cross-user tooling simple. Content I/O goes through [[domain#Workspace]], not raw filesystem paths.

## Thread

A thread is the conversation history unit. Public `thread_id` does not encode origin; origin lives on session/thread columns.

[[src/octop/infra/gateway/threads.py#ThreadRegistry]] maps `session_key` (`agent:channel:subject:chat_type`) to the active thread. Virtual channels include dashboard, cli, and mcp. See [[message-flow]] for how ingress binds a thread before a turn.

## Gateway

[[src/octop/infra/gateway/gateway.py#Gateway]] is the global AI interaction entry: IM via octop-gateway `ChannelManager`, dashboard [[domain#WebSocket hub|WebSocketHub]], CLI hub, [[message-flow#GlobalProcessor]], and slash dispatch.

For IM, `InboundMessage.tenant_id` is the agent public id. Cron and other push paths also enter through Gateway rather than calling harness directly.

## WebSocket hub

Dashboard chat streams over bidirectional WebSocket so the client can send slash/`/compact` mid-turn; legacy SSE stream was replaced for that reason.

HITL resume may still use SSE. Hub wiring lives on [[src/octop/infra/gateway/gateway.py#Gateway]] alongside IM channels.

## Workspace

Agent content files (SOUL, skills, inbound uploads) go through harness `BackendWorkspace`, never direct `Path` writes under `~/.octop/agents/<id>/` for content.

HTTP uses [[src/octop/api/common/workspace.py#require_running_workspace]]; gateway/media uses harness workspace helpers. Spec resolution: [[src/octop/infra/backend/resolver.py#resolve_agent_backend_spec]]. Remote storage is named via `storage_backends`. System-scoped files live under `{workspace}/.octop/` for new agents.

## Cron

Process-wide [[src/octop/infra/cron/manager.py#CronManager]] (APScheduler) triggers jobs through [[domain#Gateway]] — text push or agent turn — using the server timezone from [[decisions#Server timezone|config]].

Jobs store `session_key` (often the owner's dashboard key). Cron is loaded at boot; CLI config writes take effect after restart when the server is already running.

## Skills

Skill packages are DB-tracked packages plus workspace skill trees. Agents reference `skill_package_ids`; SkillHub is the market client under `infra/skills/`.

Builtin and expert library skills ship in-repo; enablement is per-agent. Do not confuse skill package rows with connector MCP tools. Public SkillHub browse/install is governed by [[domain#Market governance]].

## Market governance

Instance `market_mode` plus `skill_market`/`expert_market` permissions and `market_policy_rules` control SkillHub hubs via [[src/octop/infra/market/policy.py#MarketCatalogPolicy]].

Modes: `off` | `public` | `allowlist` | `mirror_only`. Allowlist is default-closed and group-aware; `mirror_only` serves local `published_experts` / skill packages. See `docs/market-governance.md`.

## Connectors

Connectors cover OAuth/MCP catalog metadata, credential crypto, and MCP gateway assembly for agents (`infra/connectors/`, `catalog.json`).

HTTP surface is `api/routers/connectors.py`. Agent start assembles MCP servers from connector bindings rather than hard-coding vendor SDKs in the harness.

## Users and auth

[[src/octop/infra/users/manager.py#UserManager]] owns password hashing, roles, and preferences (including locale). Dashboard/API auth is JWT via `api/deps.py` and middleware.

SSO and LDAP attach as process-level services on OctopServer. CLI does not implement login — local filesystem access to `~/.octop` is the trust boundary.

## History

Turn projection writes `thread_messages`; optional versioned archive and trajectory capture richer event streams under `infra/history/`.

Streaming turns use history trackers alongside [[message-flow#Stream projection]]. Trajectory is optional on the runtime and must not be required for basic chat.

## SharedServices

[[src/octop/infra/db/services.py#SharedServices]] is the DI container: [[src/octop/config.py#OctopConfig]], path layout, and [[src/octop/infra/db/services.py#RepoBundle]].

[[src/octop/infra/db/services.py#RepoBundle#from_pool]] builds one repo per table. Routers and managers use `server.services.*_repo` — do not import repos at module level outside SharedServices / RepoBundle. Factory: [[src/octop/infra/db/services.py#build_shared_services]].

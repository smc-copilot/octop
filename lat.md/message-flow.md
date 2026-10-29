# Message flow

Ingress from IM, dashboard, CLI, or cron converges on one turn pipeline: bind session/thread, route slash or HITL, then stream a harness turn.

Team replies and cron pushes reuse the same Gateway entry so channel constraints and history stay consistent. Architecture overview: `docs/architecture.md` §3 and §6.

## GlobalProcessor

[[src/octop/infra/gateway/process/processor.py#GlobalProcessor]] is the shared turn orchestrator. IM entry is [[src/octop/infra/gateway/process/processor.py#GlobalProcessor#__call__]]; team follow-ups use [[src/octop/infra/gateway/process/processor.py#GlobalProcessor#on_reply]].

It owns plugin lease checks, slash/HITL pre-routing, harness request assembly (model route, MCP/connectors, multimodal content), and handoff to [[message-flow#Stream projection]].

## Session and thread binding

Before a turn, derive `session_key` and resolve or create a [[domain#Thread]] via [[src/octop/infra/gateway/threads.py#ThreadRegistry]].

`thread_id` is opaque; origin is stored on the row. Virtual surfaces (dashboard, cli, mcp) use the same registry shape as IM channels.

## Slash and HITL pre-routing

If the inbound text is a slash command, [[decisions#Slash commands|SlashDispatcher]] handles it (gateway handler or harness runtime) and may short-circuit the LLM turn.

HITL ask-user / resume paths interrupt or continue an in-flight turn without treating the reply as a fresh free-form message when a lease is active.

## Stream projection

[[src/octop/infra/gateway/process/stream_project.py#project_stream]] drives the harness stream into `MessageEvent` chunks for channels and the dashboard.

Tool start/end events carry localized `tool_name` and `tool_hint_text` for IM. Post-turn work includes usage audit, [[domain#History|history]] projection, thread touch, and optional team `on_reply` to a parent thread.

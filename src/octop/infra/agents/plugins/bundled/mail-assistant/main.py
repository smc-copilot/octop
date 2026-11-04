"""Mail assistant — skill plugin + host actions for card browse bridge (PRD D7/D8)."""

from __future__ import annotations

from typing import Any

from octop_harness.plugins import PluginContext

from octop.infra.agents.plugins.host import register_host_setup

from .actions import register_actions


def setup(ctx: PluginContext) -> None:
    ctx.skills("skills")

    def register(facade: Any) -> None:
        for action in register_actions(facade):
            facade.register_action(
                action.name,
                action.input_model,
                action.output_model,
                action.handler,
                action.summary,
                action.permission,
            )

    register_host_setup(ctx, register)

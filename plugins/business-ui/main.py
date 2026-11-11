"""Harness entry: tools + Host actions. No FastAPI routes."""

from __future__ import annotations

from typing import Any

from octop_harness.plugins import PluginContext

from octop.infra.agents.plugins.host import register_host_setup

from .business_ui.actions import register_actions
from .business_ui.service import BusinessUiService
from .business_ui.tools import register_tools


def setup(ctx: PluginContext) -> None:
    bind_tools = register_tools(ctx)

    def register(facade: Any) -> None:
        bind_tools(facade)
        facade.register_read_only_tools(["business_ui_receipt"])
        for name, input_model, output_model, handler, summary, permission in register_actions(
            facade
        ):
            facade.register_action(name, input_model, output_model, handler, summary, permission)
        service = BusinessUiService(facade)

        async def env_sync_worker(wake: Any) -> None:
            await service.run_env_sync_loop(wake, interval=20)

        facade.register_background_worker("env_sync", env_sync_worker)

    register_host_setup(ctx, register)

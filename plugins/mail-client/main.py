"""Mail Client — POP3 receive + SMTP send (kind=tool) with chat UI cards.

Loaded by octop-harness as package ``harness_plugin_mail_client``; local
helpers live in the ``mail_client`` subpackage.
"""

from __future__ import annotations

from octop_harness.plugins import PluginContext

from .mail_client.tools import register_tools


def setup(ctx: PluginContext) -> None:
    register_tools(ctx)

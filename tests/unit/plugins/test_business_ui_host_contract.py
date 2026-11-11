"""Compatibility checks against Octop host files this plugin consumes (read-only)."""

from __future__ import annotations

from pathlib import Path

import yaml
from octop_harness.plugins import PluginManifest

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "plugins" / "business-ui"
UI_HOST_METHODS = (
    "registerRenderer",
    "getToolContext",
    "patchResult",
    "request",
    "openSidePanel",
    "closeSidePanel",
)
FACADE_DEFS = (
    "register_host_setup",
    "register_action",
    "register_read_only_tools",
    "reauthorize_actor",
    "current_execution",
    "get_record",
    "list_records",
    "stage_credential",
    "commit",
    "register_background_worker",
)


def _read(rel: str) -> str:
    path = REPO / rel
    assert path.is_file(), f"missing host file this plugin depends on: {rel}"
    return path.read_text(encoding="utf-8")


def test_plugin_yaml_matches_harness_and_octop_ui_keys() -> None:
    manifest_path = PLUGIN / "plugin.yaml"
    loaded = PluginManifest.load(manifest_path)
    assert loaded.id == "business-ui"
    assert loaded.kind == "tool"
    assert loaded.entry == "main.py"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert raw["ui"]["entry"] == "ui/index.js"
    assert raw["ui"]["manifest"] == "ui/manifest.json"
    assert (PLUGIN / raw["ui"]["entry"]).is_file()
    assert "description" in raw
    assert loaded.description == str(raw["description"]).strip()


def test_ui_host_exposes_six_methods_and_side_panel_shape() -> None:
    types = _read("dashboard/src/plugins/toolRenderers/types.ts")
    for name in UI_HOST_METHODS:
        assert f"{name}(" in types or f"{name}<" in types
    assert "callId: string" in types
    assert "title?: string" in types
    assert "toolName?: string" in types
    host = _read("dashboard/src/plugins/toolRenderers/host.ts")
    assert "patchToolResultData" in host
    assert "setPluginUiDockHandlers" in host
    store = _read("dashboard/src/pages/Chat/hooks/chatStore.ts")
    assert "export function patchToolResultData" in store
    parse = _read("dashboard/src/plugins/toolRenderers/parseToolOutput.ts")
    assert "export function mergePatchedToolOutput" in parse


def test_esm_loader_and_react_globals() -> None:
    loader = _read("dashboard/src/plugins/toolRenderers/loader.ts")
    assert "importPluginEsm" in loader
    assert "__vite-ignore" in loader or "vite-ignore" in loader
    builtins = _read("dashboard/src/plugins/toolRenderers/ensureBuiltins.ts")
    assert "__OCTOP_REACT__" in builtins
    assert "__OCTOP_JSX__" in builtins
    shim = (PLUGIN / "ui" / "build.mjs").read_text(encoding="utf-8")
    assert "window.__OCTOP_REACT__" in shim


def test_dock_reuses_call_id_and_live_tool_message() -> None:
    dock = _read("dashboard/src/pages/Chat/components/ChatDockToolUiContent.tsx")
    assert "useToolMessageByCallId" in dock
    hook = _read("dashboard/src/pages/Chat/hooks/useToolMessageByCallId.ts")
    assert "toolData?.callId === callId" in hook
    tabs = _read("dashboard/src/pages/Chat/hooks/useChatDockPanel.ts")
    assert "openToolUiTab" in tabs
    chat = _read("dashboard/src/pages/Chat/index.tsx")
    assert "openSidePanel: openToolUiTab" in chat


def test_theme_vars_and_ant_fallbacks() -> None:
    theme = _read("dashboard/src/styles/theme-vars.css")
    assert 'data-theme="light"' in theme
    assert 'data-theme="dark"' in theme
    styles = (PLUGIN / "ui" / "src" / "styles.ts").read_text(encoding="utf-8")
    assert "--ant-color-" in styles


def test_history_is_append_only() -> None:
    messages = _read("src/octop/infra/db/repos/thread_messages.py")
    assert "def append_if_ready" in messages
    assert "UPDATE thread_messages SET" not in messages
    history = _read("src/octop/infra/history/service.py")
    assert "class HistoryArchive" in history
    api = _read("src/octop/api/routers/chat/history.py")
    assert "patchToolResult" not in api


def test_jwt_plugin_action_routes_and_records_cas() -> None:
    actions = _read("src/octop/api/routers/plugin_actions.py")
    assert '"/{plugin_id}/actions/{action}"' in actions
    assert "Depends(current_user)" in actions
    plugins = _read("src/octop/api/routers/plugins.py")
    assert 'prefix="/plugins"' in plugins
    assert '"/{plugin_id}/ui/{file_path:path}"' in plugins
    host = _read("src/octop/infra/agents/plugins/host.py")
    for name in FACADE_DEFS:
        assert f"def {name}" in host
    assert "permission not in _PERMISSIONS" in host
    contracts = _read("src/octop/infra/agents/plugins/host_contracts.py")
    assert "class RecordWrite" in contracts
    assert "class RecordCheck" in contracts
    records = _read("src/octop/infra/db/repos/plugin_records.py")
    assert "def cas(" in records
    manager = _read("src/octop/infra/agents/plugins/manager.py")
    assert "def parse_plugin_ui_meta" in manager


def test_global_env_replace_is_immediate_and_mcp_copies_non_octop() -> None:
    env_file = _read("src/octop/infra/utils/env_file.py")
    assert "def apply_env_file(" in env_file
    assert "does not unset missing keys" in env_file
    assert "def apply_env_file_replace(" in env_file
    assert "SEARCH_ENV_KEYS" in env_file
    assert "TAVILY_API_KEY" in env_file
    assert "BUSINESS_UI_" not in env_file
    assert 'key.startswith("OCTOP_")' in env_file
    envs = _read("src/octop/api/routers/envs.py")
    assert "apply_env_file_replace" in envs
    assert "search_env_changed" in envs


def test_plugin_management_has_single_plain_description_field() -> None:
    panel = _read("dashboard/src/pages/Admin/Plugins/InstalledPluginsPanel.tsx")
    assert "{detail.description" in panel
    assert "drawerDesc" in panel
    assert "cardDesc" in panel
    assert "ReactMarkdown" not in panel
    assert "dangerouslySetInnerHTML" not in panel
    css = _read("dashboard/src/pages/Admin/Plugins/index.module.less")
    assert "-webkit-line-clamp: 2" in css
    drawer_block = css.split(".drawerDesc")[1].split("}")[0]
    assert "pre-wrap" not in drawer_block
    assert "white-space" not in drawer_block
    manager = _read("src/octop/infra/agents/plugins/manager.py")
    assert '"description": manifest.description' in manager
    assert "long_description" not in manager

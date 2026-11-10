from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from octop_harness.plugins import PluginRegistry, load_plugin_dir

from octop.infra.agents.plugins.manager import PluginManager

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "business-ui"


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    PluginRegistry.reset()
    yield
    PluginRegistry.reset()


def _plugin_zip() -> bytes:
    buf = io.BytesIO()
    skip = {".adapter-certs", "__pycache__", ".pytest_cache"}
    with zipfile.ZipFile(buf, "w") as zf:
        for path in _PLUGIN_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skip or part.endswith(".pyc") for part in path.parts):
                continue
            zf.write(path, arcname=f"business-ui/{path.relative_to(_PLUGIN_ROOT).as_posix()}")
    return buf.getvalue()


def test_harness_loads_plugin_tools() -> None:
    loaded = load_plugin_dir(_PLUGIN_ROOT, install_deps=False)
    assert loaded.manifest.id == "business-ui"
    names = {tool.name for tool in loaded.tools}
    assert names == {"business_ui_draft", "business_ui_connections"}


@pytest.mark.asyncio
async def test_draft_tool_does_not_grant_ownership() -> None:
    loaded = load_plugin_dir(_PLUGIN_ROOT, install_deps=False)
    draft = next(tool for tool in loaded.tools if tool.name == "business_ui_draft")
    raw = await draft.fn(
        document_type="generic_request",
        form_ref="generic.request.edit",
        schema_version="1",
        summary_title="招两名实施顾问",
        summary_body="样例，非生产单据",
    )
    payload = json.loads(raw)
    assert payload["octop_ui"]["renderer"] == "business_ui_card"
    assert payload["data"]["interactionId"] is None
    assert payload["data"]["claimRequired"] is True
    assert payload["data"]["submissionStatus"] == "unclaimed"
    assert "secret" not in json.dumps(payload)


def test_manager_installs_zip(tmp_path: Path) -> None:
    archive = tmp_path / "business-ui.zip"
    archive.write_bytes(_plugin_zip())
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=tmp_path / "config.json")
    loaded = mgr.install_archive(archive, force=True)
    assert loaded.manifest.id == "business-ui"
    dest = tmp_path / "plugins" / "business-ui"
    assert (dest / "plugin.yaml").is_file()
    assert (dest / "ui" / "index.js").is_file()
    listing = mgr.list_installed()
    assert any(item.get("id") == "business-ui" for item in listing)

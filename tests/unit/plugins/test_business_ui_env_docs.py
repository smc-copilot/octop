from __future__ import annotations

import sys
from pathlib import Path

import yaml
from octop_harness.plugins.manifest import PluginManifest

from octop.infra.agents.plugins.manager import PluginManager

_PLUGIN_ROOT = Path(__file__).resolve().parents[3] / "plugins" / "business-ui"
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from business_ui.env_config import ENV_KEY_SPECS  # noqa: E402

_DOCS = _PLUGIN_ROOT / "docs"


def _yaml_description() -> str:
    raw = yaml.safe_load((_PLUGIN_ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    return str(raw["description"])


def test_plugin_yaml_description_is_plain_chinese_env_guidance() -> None:
    loaded = PluginManifest.load(_PLUGIN_ROOT / "plugin.yaml")
    text = loaded.description
    assert text == _yaml_description().strip()
    assert text.startswith("聊天内嵌已发布业务表单。连接用全局 BUSINESS_UI_* 配置。")
    lead = text.split("填写位置")[0]
    assert len(lead) <= 48
    assert "**" not in text
    assert "`" not in text
    assert "```" not in text
    assert text.count("#") == 0
    assert "高级设置" in text
    assert "环境变量" in text
    assert "*_FILE" in text
    assert "python -m business_ui test" in text
    assert "不必重启" in text
    assert "须重启" in text
    assert "单独激活" in text
    for spec in ENV_KEY_SPECS:
        assert spec.name in text, spec.name


def test_docs_and_template_list_every_env_key() -> None:
    deploy = (_DOCS / "env-deploy.md").read_text(encoding="utf-8")
    template = (_DOCS / "env.template").read_text(encoding="utf-8")
    readme = (_PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")
    for spec in ENV_KEY_SPECS:
        assert spec.name in deploy, spec.name
        assert spec.name in template, spec.name
        assert spec.name in readme, spec.name
    assert "BUSINESS_UI_SERVICE_SECRET=" not in template
    assert "native_login" in deploy
    assert "python -m business_ui test" in deploy
    assert deploy.count("| `BUSINESS_UI_") == len(ENV_KEY_SPECS)


def test_env_key_specs_match_parser_defaults_and_values() -> None:
    by_name = {spec.name: spec for spec in ENV_KEY_SPECS}
    assert by_name["BUSINESS_UI_CONNECTION_ID"].default == "default"
    assert by_name["BUSINESS_UI_AUTH_METHOD"].default == "api_token"
    assert by_name["BUSINESS_UI_AUTH_METHOD"].values == ("api_token", "authorization_code")
    assert by_name["BUSINESS_UI_USER_AUTH_METHOD"].default == "oauth2"
    assert by_name["BUSINESS_UI_USER_AUTH_METHOD"].values == (
        "oauth2",
        "native_login",
        "personal_access_token",
    )
    assert by_name["BUSINESS_UI_ENABLED"].default == "1"
    assert by_name["BUSINESS_UI_OAUTH_SCOPES"].default == "openid profile"
    required = {s.name for s in ENV_KEY_SPECS if s.requiredness == "required_if_active"}
    assert required == {
        "BUSINESS_UI_BASE_URL",
        "BUSINESS_UI_INSTANCE_ISSUER",
        "BUSINESS_UI_OPERATOR_USER_ID",
        "BUSINESS_UI_SERVICE_SECRET_FILE",
    }
    oauth = {s.name for s in ENV_KEY_SPECS if s.requiredness == "conditional_oauth2"}
    assert "BUSINESS_UI_OAUTH_CLIENT_ID" in oauth
    assert "BUSINESS_UI_OAUTH_DISCOVERY_URL" in oauth


def test_list_installed_exposes_description_from_yaml(tmp_path: Path) -> None:
    dest = tmp_path / "plugins" / "business-ui"
    dest.mkdir(parents=True)
    (dest / "plugin.yaml").write_text(
        (_PLUGIN_ROOT / "plugin.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    mgr = PluginManager(plugins_dir=tmp_path / "plugins", config_path=tmp_path / "config.json")
    rows = mgr.list_installed()
    row = next(item for item in rows if item.get("id") == "business-ui")
    assert "BUSINESS_UI_BASE_URL" in str(row.get("description") or "")
    assert "python -m business_ui test" in str(row.get("description") or "")

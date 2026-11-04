"""Config parsing for market_mode / OCTOP_MARKET_MODE."""

from __future__ import annotations

from pathlib import Path

from octop.config import DEFAULT_MARKET_MODE, load_config, parse_market_mode


def test_parse_market_mode_accepts_known_values() -> None:
    assert parse_market_mode("allowlist") == "allowlist"
    assert parse_market_mode("mirror_only") == "mirror_only"
    assert parse_market_mode("bogus") == DEFAULT_MARKET_MODE


def test_load_config_reads_market_mode_from_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OCTOP_MARKET_MODE", raising=False)
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"market_mode": "off"}', encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.market_mode == "off"


def test_load_config_env_overrides_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOP_MARKET_MODE", "allowlist")
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text('{"market_mode": "off"}', encoding="utf-8")
    cfg = load_config(cfg_path)
    assert cfg.market_mode == "allowlist"

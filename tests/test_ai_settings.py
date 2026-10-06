from __future__ import annotations

from pathlib import Path

from chronoscope.ai.settings import (
    AISettings,
    load_ai_settings,
    resolve_api_key,
    save_ai_settings,
)
from chronoscope.coloring.config import load_color_rules, save_color_rules
from chronoscope.coloring.rules import OffHoursRule, default_rules


def test_default_settings_when_file_missing(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    s = load_ai_settings(cfg)
    assert s == AISettings()
    # Loading must not write the file (matches the color-rules behavior).
    assert not cfg.exists()


def test_round_trip(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    custom = AISettings(
        enabled=True,
        base_url="https://example.com/v1",
        model="custom-model",
        api_key_env="MY_KEY",
        max_tool_iterations=5,
        max_results_per_call=42,
    )
    save_ai_settings(custom, cfg)
    assert load_ai_settings(cfg) == custom


def test_save_preserves_color_rules_section(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    # Two writers share the same TOML file. The AI save must not erase the
    # color-rules section that the coloring module owns.
    custom_rules = default_rules()
    save_color_rules(custom_rules, cfg)
    save_ai_settings(AISettings(enabled=True), cfg)
    assert load_color_rules(cfg) == custom_rules
    assert load_ai_settings(cfg) == AISettings(enabled=True)


def test_save_color_rules_preserves_ai_section(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    save_ai_settings(AISettings(model="kept"), cfg)
    save_color_rules(default_rules(), cfg)
    assert load_ai_settings(cfg) == AISettings(model="kept")


def test_resolve_api_key_reads_configured_env(monkeypatch):
    monkeypatch.setenv("XYZ_KEY", "abc123")
    assert resolve_api_key(AISettings(api_key_env="XYZ_KEY")) == "abc123"


def test_resolve_api_key_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("XYZ_KEY", raising=False)
    assert resolve_api_key(AISettings(api_key_env="XYZ_KEY")) is None


def test_resolve_api_key_treats_empty_as_unset(monkeypatch):
    monkeypatch.setenv("XYZ_KEY", "")
    assert resolve_api_key(AISettings(api_key_env="XYZ_KEY")) is None

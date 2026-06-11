from __future__ import annotations

from pathlib import Path

from chronoscope.coloring.config import (
    default_config_path,
    load_color_rules,
    save_color_rules,
)
from chronoscope.coloring.rules import (
    ColorRules,
    OffHoursRule,
    default_rules,
)


def test_load_returns_defaults_without_writing_when_missing(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    rules = load_color_rules(cfg)
    # Loading must not touch disk — the file is only written when the user
    # explicitly saves a change. This keeps test runs from polluting $HOME.
    assert not cfg.exists()
    assert rules == default_rules()


def test_save_then_load_round_trips(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    custom = ColorRules(
        rules=(
            OffHoursRule(
                id="off_hours", name="Night", enabled=True, color="magenta",
                start_hour=23, end_hour=5,
            ),
        )
    )
    save_color_rules(custom, cfg)
    reloaded = load_color_rules(cfg)
    assert reloaded == custom


def test_unknown_rule_type_is_ignored(tmp_path: Path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        'schema = 1\n'
        '[[color_rules]]\n'
        'type = "future_rule"\n'
        'id = "x"\n'
        'name = "X"\n'
        'enabled = true\n'
        'color = "red"\n'
    )
    # No usable rules survive decoding → fall back to defaults.
    assert load_color_rules(cfg) == default_rules()


def test_default_config_path_uses_xdg(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    p = default_config_path()
    assert p == tmp_path / "chronoscope" / "config.toml"


def test_default_config_path_falls_back_to_home(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    p = default_config_path()
    # Path.home() reads $HOME on POSIX — verify our fallback resolves there.
    assert p.parent.name == "chronoscope"
    assert p.name == "config.toml"

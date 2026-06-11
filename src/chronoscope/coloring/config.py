from __future__ import annotations

import os
from pathlib import Path

import tomli_w

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore[no-redef]

from .rules import (
    ColorRule,
    ColorRules,
    OffHoursRule,
    default_rules,
)

CONFIG_SCHEMA_VERSION = 1


def default_config_path() -> Path:
    """Tool-wide config path. Honors XDG_CONFIG_HOME, falls back to ~/.config."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "chronoscope" / "config.toml"


def load_color_rules(path: Path | None = None) -> ColorRules:
    """Read color rules from the tool-wide config. Returns sensible defaults
    in-memory (without writing) if the file does not exist; the file is only
    created the first time the user saves a change."""
    p = path or default_config_path()
    if not p.exists():
        return default_rules()
    with p.open("rb") as f:
        data = tomllib.load(f)
    return _decode(data)


def save_color_rules(rules: ColorRules, path: Path | None = None) -> None:
    p = path or default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Preserve any non-color sections (e.g. [ai]) that other modules own in
    # the same tool-wide config file.
    if p.exists():
        with p.open("rb") as f:
            doc = tomllib.load(f)
    else:
        doc = {}
    doc["schema"] = CONFIG_SCHEMA_VERSION
    doc["color_rules"] = [_encode_rule(r) for r in rules.rules]
    with p.open("wb") as f:
        tomli_w.dump(doc, f)


def _encode(rules: ColorRules) -> dict:
    out: dict = {"schema": CONFIG_SCHEMA_VERSION, "color_rules": []}
    for r in rules.rules:
        out["color_rules"].append(_encode_rule(r))
    return out


def _encode_rule(r: ColorRule) -> dict:
    if isinstance(r, OffHoursRule):
        return {
            "type": "off_hours",
            "id": r.id,
            "name": r.name,
            "enabled": bool(r.enabled),
            "color": r.color,
            "start_hour": int(r.start_hour),
            "end_hour": int(r.end_hour),
        }
    raise ValueError(f"unsupported rule type: {type(r).__name__}")


def _decode(data: dict) -> ColorRules:
    raw = data.get("color_rules") or []
    out: list[ColorRule] = []
    for entry in raw:
        rule = _decode_rule(entry)
        if rule is not None:
            out.append(rule)
    if not out:
        return default_rules()
    return ColorRules(rules=tuple(out))


def _decode_rule(entry: dict) -> ColorRule | None:
    kind = entry.get("type")
    if kind == "off_hours":
        return OffHoursRule(
            id=str(entry.get("id", "off_hours")),
            name=str(entry.get("name", "Off-hours")),
            enabled=bool(entry.get("enabled", False)),
            color=str(entry.get("color", "red")),
            start_hour=int(entry.get("start_hour", 22)),
            end_hour=int(entry.get("end_hour", 4)),
        )
    return None

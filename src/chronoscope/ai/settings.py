from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

import tomli_w

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore[no-redef]

from ..coloring.config import default_config_path

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_MAX_TOOL_ITERATIONS = 12
DEFAULT_MAX_RESULTS_PER_CALL = 200


@dataclass(frozen=True, slots=True)
class AISettings:
    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key_env: str = DEFAULT_API_KEY_ENV
    max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS
    max_results_per_call: int = DEFAULT_MAX_RESULTS_PER_CALL

    def with_changes(self, **kwargs) -> "AISettings":
        return replace(self, **kwargs)


def resolve_api_key(settings: AISettings) -> str | None:
    """Look up the API key from the configured env var. Returns None if unset
    or empty so callers can render a clear "not configured" message."""
    val = os.environ.get(settings.api_key_env)
    return val if val else None


def load_ai_settings(path: Path | None = None) -> AISettings:
    p = path or default_config_path()
    if not p.exists():
        return AISettings()
    with p.open("rb") as f:
        doc = tomllib.load(f)
    section = doc.get("ai") or {}
    return _decode(section)


def save_ai_settings(settings: AISettings, path: Path | None = None) -> None:
    p = path or default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        with p.open("rb") as f:
            doc = tomllib.load(f)
    else:
        doc = {}
    doc["ai"] = _encode(settings)
    with p.open("wb") as f:
        tomli_w.dump(doc, f)


def _encode(s: AISettings) -> dict:
    return {
        "enabled": bool(s.enabled),
        "base_url": s.base_url,
        "model": s.model,
        "api_key_env": s.api_key_env,
        "max_tool_iterations": int(s.max_tool_iterations),
        "max_results_per_call": int(s.max_results_per_call),
    }


def _decode(section: dict) -> AISettings:
    defaults = AISettings()
    return AISettings(
        enabled=bool(section.get("enabled", defaults.enabled)),
        base_url=str(section.get("base_url", defaults.base_url)),
        model=str(section.get("model", defaults.model)),
        api_key_env=str(section.get("api_key_env", defaults.api_key_env)),
        max_tool_iterations=int(
            section.get("max_tool_iterations", defaults.max_tool_iterations)
        ),
        max_results_per_call=int(
            section.get("max_results_per_call", defaults.max_results_per_call)
        ),
    )

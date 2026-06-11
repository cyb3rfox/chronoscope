from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

MAX_ENTRIES = 20


@dataclass(frozen=True, slots=True)
class RecentEntry:
    path: str
    name: str
    last_opened: str  # ISO-8601 UTC, seconds precision


def _config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "chronoscope" / "recent.json"


def load() -> list[RecentEntry]:
    path = _config_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"chronoscope: warning: could not read {path}: {exc}", file=sys.stderr)
        return []
    if not isinstance(raw, list):
        return []
    out: list[RecentEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                RecentEntry(
                    path=str(item["path"]),
                    name=str(item["name"]),
                    last_opened=str(item["last_opened"]),
                )
            )
        except KeyError:
            continue
    out.sort(key=lambda e: e.last_opened, reverse=True)
    return out


def _save(entries: list[RecentEntry]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="recent.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump([asdict(e) for e in entries], f, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        print(f"chronoscope: warning: could not write {path}: {exc}", file=sys.stderr)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def touch(case_path: Path, name: str) -> None:
    resolved = str(Path(case_path).resolve())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    existing = [e for e in load() if e.path != resolved]
    existing.insert(0, RecentEntry(path=resolved, name=name, last_opened=now))
    if len(existing) > MAX_ENTRIES:
        existing = existing[:MAX_ENTRIES]
    _save(existing)


def remove(case_path: Path) -> None:
    resolved = str(Path(case_path).resolve())
    kept = [e for e in load() if e.path != resolved]
    _save(kept)

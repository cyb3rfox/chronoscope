from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import tomli_w

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore[no-redef]

from .schema import apply_pragmas, migrate
from .timeline_colors import resolve_color

SCHEMA_VERSION = 1


class CaseError(Exception): ...


class CaseExistsError(CaseError): ...


class CaseNotFoundError(CaseError): ...


@dataclass
class Case:
    path: Path
    name: str
    con: sqlite3.Connection


def init_case(path: Path, *, name: str) -> None:
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        raise CaseExistsError(f"{path} is not empty")
    path.mkdir(parents=True, exist_ok=True)
    (path / "tmp").mkdir()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timeline": [],
    }
    _write_manifest(path, manifest)
    con = sqlite3.connect(path / "events.db")
    try:
        apply_pragmas(con)
        migrate(con)
    finally:
        con.close()


@contextmanager
def open_case(path: Path):
    path = Path(path)
    if not (path / "case.toml").exists():
        raise CaseNotFoundError(f"no case.toml in {path}")
    manifest = _read_manifest(path)
    con = sqlite3.connect(path / "events.db")
    apply_pragmas(con)
    migrate(con)
    try:
        yield Case(path=path, name=manifest["name"], con=con)
    finally:
        con.close()


@dataclass(frozen=True, slots=True)
class TimelineInfo:
    id: str
    name: str
    source_path: str
    event_count: int
    color: str
    order_index: int


def list_timelines(con: sqlite3.Connection) -> list[TimelineInfo]:
    """Return timelines in add-order with effective colors resolved."""
    out: list[TimelineInfo] = []
    for i, row in enumerate(
        con.execute(
            "SELECT id, name, source_path, event_count, color "
            "FROM timeline ORDER BY ingested_at ASC, id ASC"
        )
    ):
        tid, name, source_path, event_count, color = row
        out.append(
            TimelineInfo(
                id=str(tid),
                name=str(name),
                source_path=str(source_path),
                event_count=int(event_count),
                color=resolve_color(color, i),
                order_index=i,
            )
        )
    return out


def _manifest_path(path: Path) -> Path:
    return path / "case.toml"


def _read_manifest(path: Path) -> dict:
    with _manifest_path(path).open("rb") as f:
        return tomllib.load(f)


def _write_manifest(path: Path, manifest: dict) -> None:
    with _manifest_path(path).open("wb") as f:
        tomli_w.dump(manifest, f)

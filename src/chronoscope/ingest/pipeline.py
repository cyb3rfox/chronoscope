from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import ulid

from ..core.case import open_case
from ..core.event import Event
from ..core.extra import dump_extra, flatten_extra
from . import plaso_store
from .detect import detect_format
from .jsonl import iter_events as iter_jsonl_events

BATCH = 10_000

ProgressCallback = Callable[[int, "int | None"], None]


class UnsupportedSourceError(Exception):
    """Source file is neither JSONL nor a supported plaso storage file."""


@dataclass
class IngestReport:
    timeline_id: str
    inserted: int
    skipped: int
    already_present: bool


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_file(
    case_path: Path,
    source: Path,
    *,
    name: str,
    progress: ProgressCallback | None = None,
) -> IngestReport:
    source = Path(source)
    fmt = detect_format(source)
    if fmt == "unsupported":
        raise UnsupportedSourceError(
            f"{source.name}: not a JSONL or plaso file"
        )
    source_sha = _sha256_of(source)
    with open_case(case_path) as c:
        existing = c.con.execute(
            "SELECT id FROM timeline WHERE source_sha256=?", (source_sha,)
        ).fetchone()
        if existing is not None:
            return IngestReport(
                timeline_id=existing[0],
                inserted=0,
                skipped=0,
                already_present=True,
            )
        timeline_id = f"tl_{ulid.new()}"
        if fmt == "jsonl":
            inserted, skipped = _bulk_insert_jsonl(
                c.con, timeline_id, source, progress=progress
            )
        else:
            inserted, skipped = _bulk_insert_plaso(
                c.con, timeline_id, source, progress=progress
            )
        c.con.execute(
            "INSERT INTO timeline(id,name,source_path,source_kind,source_sha256,"
            "event_count,ingested_at,color) VALUES(?,?,?,?,?,?,?,?)",
            (
                timeline_id,
                name,
                str(source.resolve()),
                fmt,
                source_sha,
                inserted,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                None,
            ),
        )
        c.con.commit()
        return IngestReport(
            timeline_id=timeline_id,
            inserted=inserted,
            skipped=skipped,
            already_present=False,
        )


def _bulk_insert_jsonl(
    con: sqlite3.Connection,
    timeline_id: str,
    source: Path,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[int, int]:
    rows: list[tuple] = []
    skipped = 0

    def on_error(_lineno: int, _reason: str) -> None:
        nonlocal skipped
        skipped += 1

    inserted = 0
    if progress is not None:
        progress(0, None)
    with source.open("rb") as f:
        for ev in iter_jsonl_events(f, on_error=on_error):
            rows.append(_row_from_event(timeline_id, ev))
            if len(rows) >= BATCH:
                inserted += _flush(con, rows)
                rows.clear()
                if progress is not None:
                    progress(inserted, None)
        if rows:
            inserted += _flush(con, rows)
    if progress is not None:
        progress(inserted, None)
    return inserted, skipped


def _bulk_insert_plaso(
    con: sqlite3.Connection,
    timeline_id: str,
    source: Path,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[int, int]:
    rows: list[tuple] = []
    inserted = 0
    total = plaso_store.event_count(source) if progress is not None else None
    if progress is not None:
        progress(0, total)
    for raw in plaso_store.iter_events(source):
        ev = Event.from_dict(raw)
        rows.append(_row_from_event(timeline_id, ev))
        if len(rows) >= BATCH:
            inserted += _flush(con, rows)
            rows.clear()
            if progress is not None:
                progress(inserted, total)
    if rows:
        inserted += _flush(con, rows)
    if progress is not None:
        progress(inserted, total)
    return inserted, 0


def _row_from_event(timeline_id: str, ev: Event) -> tuple:
    return (
        timeline_id,
        ev.event_hash,
        ev.ts_usec,
        ev.ts_desc,
        ev.data_type,
        ev.parser,
        ev.source_short,
        ev.source_long,
        ev.display_name,
        ev.message,
        dump_extra(ev.extra),
        flatten_extra(ev.extra),
    )


_INSERT = (
    "INSERT OR IGNORE INTO event(timeline_id,event_hash,ts_usec,ts_desc,data_type,parser,"
    "source_short,source_long,display_name,message,extra,extra_text) "
    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
)


def _flush(con: sqlite3.Connection, rows: list[tuple]) -> int:
    cur = con.executemany(_INSERT, rows)
    return cur.rowcount

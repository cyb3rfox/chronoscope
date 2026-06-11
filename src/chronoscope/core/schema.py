from __future__ import annotations

import sqlite3

from .extra import flatten_extra, load_extra

CURRENT_VERSION = 4

_DDL_V1 = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS timeline (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  source_path   TEXT NOT NULL,
  source_kind   TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  event_count   INTEGER NOT NULL DEFAULT 0,
  ingested_at   TEXT NOT NULL,
  color         TEXT
);

CREATE TABLE IF NOT EXISTS event (
  id            INTEGER PRIMARY KEY,
  timeline_id   TEXT NOT NULL REFERENCES timeline(id),
  event_hash    BLOB NOT NULL,
  ts_usec       INTEGER NOT NULL,
  ts_desc       TEXT NOT NULL,
  data_type     TEXT NOT NULL,
  parser        TEXT,
  source_short  TEXT,
  source_long   TEXT,
  display_name  TEXT,
  message       TEXT NOT NULL,
  extra         BLOB NOT NULL,
  UNIQUE (timeline_id, event_hash)
);

CREATE INDEX IF NOT EXISTS ix_event_ts       ON event(ts_usec);
CREATE INDEX IF NOT EXISTS ix_event_datatype ON event(data_type, ts_usec);
CREATE INDEX IF NOT EXISTS ix_event_parser   ON event(parser, ts_usec);
CREATE INDEX IF NOT EXISTS ix_event_hash     ON event(event_hash);
CREATE INDEX IF NOT EXISTS ix_event_timeline ON event(timeline_id, ts_usec);
"""

_DDL_V2 = """
CREATE TABLE IF NOT EXISTS annotation_tag (
  event_hash BLOB NOT NULL,
  tag        TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (event_hash, tag)
);

CREATE TABLE IF NOT EXISTS annotation_star (
  event_hash BLOB PRIMARY KEY,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotation_comment (
  id         INTEGER PRIMARY KEY,
  event_hash BLOB NOT NULL,
  body       TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_ann_comment_hash ON annotation_comment(event_hash);
CREATE INDEX IF NOT EXISTS ix_ann_tag_tag      ON annotation_tag(tag);
"""


_DDL_V4 = """
CREATE TABLE IF NOT EXISTS exhibit (
  id          INTEGER PRIMARY KEY,
  title       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  body        TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
);
"""


def migrate(con: sqlite3.Connection) -> None:
    con.executescript(_DDL_V1)
    row = con.execute("SELECT version FROM schema_version").fetchone()
    current = int(row[0]) if row is not None else 0
    fresh = row is None

    if current < 2:
        con.executescript(_DDL_V2)

    if fresh or current < 3:
        _migrate_v3(con, fresh=fresh)

    # No `fresh or` needed (unlike v3): CREATE TABLE IF NOT EXISTS handles a
    # brand-new db too, since a fresh db has current == 0 < 4.
    if current < 4:
        con.executescript(_DDL_V4)

    if row is None:
        con.execute(
            "INSERT INTO schema_version(version) VALUES(?)", (CURRENT_VERSION,)
        )
    elif current < CURRENT_VERSION:
        con.execute("UPDATE schema_version SET version=?", (CURRENT_VERSION,))
    con.commit()


def _migrate_v3(con: sqlite3.Connection, *, fresh: bool) -> None:
    """Add event.extra_text and backfill it from existing extra blobs."""
    if not _has_column(con, "event", "extra_text"):
        con.execute(
            "ALTER TABLE event ADD COLUMN extra_text TEXT NOT NULL DEFAULT ''"
        )
    if fresh:
        return
    cur = con.execute(
        "SELECT id, extra FROM event WHERE extra_text = ''"
    )
    batch: list[tuple[str, int]] = []
    for row_id, blob in cur:
        try:
            d = load_extra(blob)
        except Exception:
            continue
        batch.append((flatten_extra(d), row_id))
        if len(batch) >= 1000:
            con.executemany(
                "UPDATE event SET extra_text=? WHERE id=?", batch
            )
            batch.clear()
    if batch:
        con.executemany("UPDATE event SET extra_text=? WHERE id=?", batch)


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def apply_pragmas(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA mmap_size=30000000000")

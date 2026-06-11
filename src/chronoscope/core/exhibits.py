from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Exhibit:
    """A standalone piece of text evidence attached to a case (a script, a
    file dump, a config snippet) — not a timeline event."""
    id: int
    title: str
    description: str
    body: str
    created_at: str
    updated_at: str


def add_exhibit(
    con: sqlite3.Connection, *, title: str, description: str, body: str
) -> int:
    t = title.strip()
    if not t:
        raise ValueError("title must be non-empty")
    if not body:
        raise ValueError("body must be non-empty")
    now = _now()
    cur = con.execute(
        "INSERT INTO exhibit(title, description, body, created_at, updated_at) "
        "VALUES(?,?,?,?,?)",
        (t, description, body, now, now),
    )
    con.commit()
    return int(cur.lastrowid)


def list_exhibits(con: sqlite3.Connection) -> list[Exhibit]:
    return [
        _row_to_exhibit(r)
        for r in con.execute(
            "SELECT id, title, description, body, created_at, updated_at "
            "FROM exhibit ORDER BY id ASC"
        )
    ]


def get_exhibit(con: sqlite3.Connection, exhibit_id: int) -> Exhibit | None:
    r = con.execute(
        "SELECT id, title, description, body, created_at, updated_at "
        "FROM exhibit WHERE id=?",
        (exhibit_id,),
    ).fetchone()
    return _row_to_exhibit(r) if r is not None else None


def update_exhibit(
    con: sqlite3.Connection,
    exhibit_id: int,
    *,
    title: str,
    description: str,
    body: str,
) -> None:
    t = title.strip()
    if not t:
        raise ValueError("title must be non-empty")
    if not body:
        raise ValueError("body must be non-empty")
    con.execute(
        "UPDATE exhibit SET title=?, description=?, body=?, updated_at=? WHERE id=?",
        (t, description, body, _now(), exhibit_id),
    )
    con.commit()


def remove_exhibit(con: sqlite3.Connection, exhibit_id: int) -> None:
    con.execute("DELETE FROM exhibit WHERE id=?", (exhibit_id,))
    con.commit()


def count_exhibits(con: sqlite3.Connection) -> int:
    return int(con.execute("SELECT COUNT(*) FROM exhibit").fetchone()[0])


def _row_to_exhibit(r) -> Exhibit:
    return Exhibit(
        id=int(r[0]),
        title=str(r[1]),
        description=str(r[2]),
        body=str(r[3]),
        created_at=str(r[4]),
        updated_at=str(r[5]),
    )

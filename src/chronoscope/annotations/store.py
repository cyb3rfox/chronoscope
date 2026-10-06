from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tag_normalize(tag: str) -> str:
    """Lowercase, trim, collapse whitespace to '-'. Empty raises ValueError."""
    t = re.sub(r"\s+", "-", tag.strip().lower())
    if not t:
        raise ValueError("empty tag")
    return t


def set_star(con: sqlite3.Connection, event_hash: bytes, on: bool) -> None:
    if on:
        con.execute(
            "INSERT OR IGNORE INTO annotation_star(event_hash, created_at) VALUES(?,?)",
            (event_hash, _now()),
        )
    else:
        con.execute("DELETE FROM annotation_star WHERE event_hash=?", (event_hash,))
    con.commit()


def get_star(con: sqlite3.Connection, event_hash: bytes) -> bool:
    row = con.execute(
        "SELECT 1 FROM annotation_star WHERE event_hash=?", (event_hash,)
    ).fetchone()
    return row is not None


def toggle_star(con: sqlite3.Connection, event_hash: bytes) -> bool:
    new_state = not get_star(con, event_hash)
    set_star(con, event_hash, new_state)
    return new_state


def add_tag(con: sqlite3.Connection, event_hash: bytes, tag: str) -> None:
    t = tag_normalize(tag)
    con.execute(
        "INSERT OR IGNORE INTO annotation_tag(event_hash, tag, created_at) VALUES(?,?,?)",
        (event_hash, t, _now()),
    )
    con.commit()


def remove_tag(con: sqlite3.Connection, event_hash: bytes, tag: str) -> None:
    t = tag_normalize(tag)
    con.execute(
        "DELETE FROM annotation_tag WHERE event_hash=? AND tag=?", (event_hash, t)
    )
    con.commit()


def tags_for(con: sqlite3.Connection, event_hash: bytes) -> list[str]:
    return [
        row[0]
        for row in con.execute(
            "SELECT tag FROM annotation_tag WHERE event_hash=? ORDER BY tag",
            (event_hash,),
        )
    ]


def all_tags_with_counts(con: sqlite3.Connection) -> list[tuple[str, int]]:
    return [
        (r[0], int(r[1]))
        for r in con.execute(
            "SELECT tag, COUNT(*) FROM annotation_tag GROUP BY tag ORDER BY COUNT(*) DESC, tag"
        )
    ]


def rename_tag(con: sqlite3.Connection, old: str, new: str) -> None:
    old_n = tag_normalize(old)
    new_n = tag_normalize(new)
    if old_n == new_n:
        return
    con.execute(
        "UPDATE OR IGNORE annotation_tag SET tag=? WHERE tag=?", (new_n, old_n)
    )
    con.execute("DELETE FROM annotation_tag WHERE tag=?", (old_n,))
    con.commit()


def delete_tag(con: sqlite3.Connection, tag: str) -> int:
    t = tag_normalize(tag)
    cur = con.execute("DELETE FROM annotation_tag WHERE tag=?", (t,))
    con.commit()
    return cur.rowcount


def add_comment(con: sqlite3.Connection, event_hash: bytes, body: str) -> int:
    now = _now()
    cur = con.execute(
        "INSERT INTO annotation_comment(event_hash, body, created_at, updated_at) "
        "VALUES(?,?,?,?)",
        (event_hash, body, now, now),
    )
    con.commit()
    return int(cur.lastrowid)


def update_comment(con: sqlite3.Connection, comment_id: int, body: str) -> None:
    con.execute(
        "UPDATE annotation_comment SET body=?, updated_at=? WHERE id=?",
        (body, _now(), comment_id),
    )
    con.commit()


def delete_comment(con: sqlite3.Connection, comment_id: int) -> None:
    con.execute("DELETE FROM annotation_comment WHERE id=?", (comment_id,))
    con.commit()


def comments_for(con: sqlite3.Connection, event_hash: bytes) -> list[dict]:
    return [
        {"id": int(r[0]), "body": r[1], "created_at": r[2], "updated_at": r[3]}
        for r in con.execute(
            "SELECT id, body, created_at, updated_at FROM annotation_comment "
            "WHERE event_hash=? ORDER BY id",
            (event_hash,),
        )
    ]


def latest_comment_id(con: sqlite3.Connection, event_hash: bytes) -> int | None:
    row = con.execute(
        "SELECT id FROM annotation_comment WHERE event_hash=? "
        "ORDER BY id DESC LIMIT 1",
        (event_hash,),
    ).fetchone()
    return int(row[0]) if row else None

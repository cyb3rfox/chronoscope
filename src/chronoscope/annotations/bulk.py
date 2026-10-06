from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone

from .store import tag_normalize


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def bulk_star(con: sqlite3.Connection, hashes: Iterable[bytes], *, on: bool) -> None:
    rows = [(h,) for h in hashes]
    if not rows:
        return
    try:
        con.execute("BEGIN")
        if on:
            now = _now()
            con.executemany(
                "INSERT OR IGNORE INTO annotation_star(event_hash, created_at) VALUES(?, ?)",
                [(h, now) for (h,) in rows],
            )
        else:
            con.executemany(
                "DELETE FROM annotation_star WHERE event_hash=?",
                rows,
            )
        con.commit()
    except BaseException:
        con.rollback()
        raise


def bulk_tag(con: sqlite3.Connection, hashes: Iterable[bytes], tag: str) -> None:
    t = tag_normalize(tag)
    hs = list(hashes)
    if not hs:
        return
    now = _now()
    try:
        con.execute("BEGIN")
        con.executemany(
            "INSERT OR IGNORE INTO annotation_tag(event_hash, tag, created_at) VALUES(?,?,?)",
            [(h, t, now) for h in hs],
        )
        con.commit()
    except BaseException:
        con.rollback()
        raise


def bulk_untag(con: sqlite3.Connection, hashes: Iterable[bytes], tag: str) -> None:
    t = tag_normalize(tag)
    hs = list(hashes)
    if not hs:
        return
    try:
        con.execute("BEGIN")
        con.executemany(
            "DELETE FROM annotation_tag WHERE event_hash=? AND tag=?",
            [(h, t) for h in hs],
        )
        con.commit()
    except BaseException:
        con.rollback()
        raise

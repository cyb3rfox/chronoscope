from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass

from ..query.builder import build_sql
from ..query.state import QueryState


@dataclass(frozen=True, slots=True)
class HistogramBucket:
    start_usec: int
    end_usec: int
    total: int
    tagged: int
    starred: int


def _where_clause(state: QueryState) -> tuple[str, tuple]:
    where, params, _ = build_sql(state)
    return where, params


def _min_max_ts(
    con: sqlite3.Connection, where: str, params: tuple
) -> tuple[int | None, int | None, int]:
    base = "FROM event" + (f" WHERE {where}" if where else "")
    row = con.execute(
        f"SELECT MIN(ts_usec), MAX(ts_usec), COUNT(*) {base}", params
    ).fetchone()
    lo, hi, total = row
    if lo is None:
        return None, None, 0
    return int(lo), int(hi), int(total)


def build_histogram(
    con: sqlite3.Connection, state: QueryState, *, buckets: int = 60
) -> list[HistogramBucket]:
    if buckets < 1:
        raise ValueError("buckets must be >= 1")
    # Call build_sql once; pass (where, params) into _min_max_ts to avoid a
    # second compilation of the same QueryState.
    where, params, _ = build_sql(state)
    lo, hi, total = _min_max_ts(con, where, params)
    if lo is None or total == 0:
        return []
    # Inclusive range length.
    span = hi - lo + 1
    bucket_width = max(1, math.ceil(span / buckets))

    base_where = where
    base = "FROM event" + (f" WHERE {base_where}" if base_where else "")
    # For the JOIN-ing tagged/starred queries, qualify bare event_hash refs
    # emitted by build_sql (IN / NOT IN subqueries) to e.event_hash so they
    # are not ambiguous with the joined annotation_* table's event_hash.
    join_where = _qualify_event_hash(base_where) if base_where else ""
    join_and_where = f" AND {join_where}" if join_where else ""

    # Totals per bucket.
    total_rows = dict(
        con.execute(
            f"SELECT (ts_usec - ?) / ? AS bkt, COUNT(*) {base} GROUP BY bkt",
            (lo, bucket_width) + params,
        )
    )
    # Tagged: DISTINCT to avoid double-counting when an event has multiple tags.
    tagged_rows = dict(
        con.execute(
            f"SELECT (e.ts_usec - ?) / ? AS bkt, COUNT(DISTINCT e.event_hash) "
            f"FROM event e JOIN annotation_tag t ON t.event_hash = e.event_hash "
            f"WHERE 1=1{join_and_where} GROUP BY bkt",
            (lo, bucket_width) + params,
        )
    )
    # Starred: one row per event max.
    starred_rows = dict(
        con.execute(
            f"SELECT (e.ts_usec - ?) / ? AS bkt, COUNT(*) "
            f"FROM event e JOIN annotation_star s ON s.event_hash = e.event_hash "
            f"WHERE 1=1{join_and_where} GROUP BY bkt",
            (lo, bucket_width) + params,
        )
    )

    result: list[HistogramBucket] = []
    for i in range(buckets):
        bstart = lo + i * bucket_width
        bend = bstart + bucket_width
        result.append(
            HistogramBucket(
                start_usec=bstart,
                end_usec=bend,
                total=int(total_rows.get(i, 0)),
                tagged=int(tagged_rows.get(i, 0)),
                starred=int(starred_rows.get(i, 0)),
            )
        )
    return result


def _qualify_event_hash(where: str) -> str:
    """Qualify bare event_hash references from build_sql for use in JOINs.

    build_sql emits bare ``event_hash IN`` / ``event_hash NOT IN`` clauses.
    When the query aliases the event table as ``e`` and JOINs another table
    that also has an event_hash column, SQLite raises "ambiguous column name".
    This helper rewrites those bare references to ``e.event_hash``.
    """
    return (
        where
        .replace("event_hash IN", "e.event_hash IN")
        .replace("event_hash NOT IN", "e.event_hash NOT IN")
    )


@dataclass(frozen=True, slots=True)
class TagStat:
    tag: str
    count: int
    first_usec: int
    last_usec: int


@dataclass(frozen=True, slots=True)
class StarredOrCommentedEvent:
    event_id: int
    ts_usec: int
    data_type: str
    message: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class OverviewData:
    total: int
    tagged: int
    starred: int
    commented: int
    first_usec: int | None
    last_usec: int | None
    per_tag: list[TagStat]
    histogram: list[HistogramBucket]
    starred_events: list[StarredOrCommentedEvent]
    commented_events: list[StarredOrCommentedEvent]
    per_timeline: list[tuple[str, int]]
    filter_summary: str


def _count_where_annotation(
    con: sqlite3.Connection,
    state: QueryState,
    annotation_sql: str,
    annotation_params: tuple = (),
) -> int:
    """Count DISTINCT event_hashes in the filtered set that are also in
    the given annotation table."""
    where, params = _where_clause(state)
    base_where = where
    # Qualify bare event_hash refs when used alongside the event alias 'e'.
    join_where = _qualify_event_hash(base_where) if base_where else ""
    base = "FROM event e" + (f" WHERE {join_where}" if join_where else "")
    sep = " AND " if join_where else " WHERE "
    sql = (
        f"SELECT COUNT(DISTINCT e.event_hash) {base}"
        f"{sep}e.event_hash IN ({annotation_sql})"
    )
    row = con.execute(sql, params + annotation_params).fetchone()
    return int(row[0])


def _per_tag(
    con: sqlite3.Connection, state: QueryState
) -> list[TagStat]:
    where, params = _where_clause(state)
    base_where = where
    join_where = _qualify_event_hash(base_where) if base_where else ""
    sep = " AND " if join_where else ""
    sql = (
        "SELECT at.tag, COUNT(DISTINCT at.event_hash), "
        "MIN(e.ts_usec), MAX(e.ts_usec) "
        "FROM annotation_tag at JOIN event e ON e.event_hash = at.event_hash "
        f"WHERE 1=1{sep}{join_where} "
        "GROUP BY at.tag "
        "ORDER BY COUNT(DISTINCT at.event_hash) DESC, at.tag ASC"
    )
    rows = con.execute(sql, params).fetchall()
    return [
        TagStat(tag=r[0], count=int(r[1]), first_usec=int(r[2]), last_usec=int(r[3]))
        for r in rows
    ]


def _starred_events(
    con: sqlite3.Connection, state: QueryState, *, limit: int = 10
) -> list[StarredOrCommentedEvent]:
    where, params = _where_clause(state)
    base_where = where
    join_where = _qualify_event_hash(base_where) if base_where else ""
    sep = " AND " if join_where else " WHERE "
    sql = (
        "SELECT e.id, e.ts_usec, e.data_type, e.message FROM event e "
        + (f"WHERE {join_where} " if join_where else "")
        + f"{sep}e.event_hash IN (SELECT event_hash FROM annotation_star) "
        "ORDER BY e.ts_usec ASC LIMIT ?"
    )
    rows = con.execute(sql, params + (limit,)).fetchall()
    return [
        StarredOrCommentedEvent(
            event_id=int(r[0]),
            ts_usec=int(r[1]),
            data_type=str(r[2]),
            message=str(r[3] or ""),
        )
        for r in rows
    ]


def _commented_events(
    con: sqlite3.Connection, state: QueryState, *, limit: int = 10
) -> list[StarredOrCommentedEvent]:
    where, params = _where_clause(state)
    base_where = where
    join_where = _qualify_event_hash(base_where) if base_where else ""
    sep = " AND " if join_where else " WHERE "
    sql = (
        "SELECT e.id, e.ts_usec, e.data_type, e.message, "
        " (SELECT body FROM annotation_comment c2 WHERE c2.event_hash = e.event_hash "
        "  ORDER BY c2.id DESC LIMIT 1) AS latest_body "
        "FROM event e "
        + (f"WHERE {join_where} " if join_where else "")
        + f"{sep}e.event_hash IN (SELECT event_hash FROM annotation_comment) "
        "ORDER BY e.ts_usec ASC LIMIT ?"
    )
    rows = con.execute(sql, params + (limit,)).fetchall()
    result: list[StarredOrCommentedEvent] = []
    for r in rows:
        body = str(r[4] or "")
        first_line = body.splitlines()[0] if body else ""
        result.append(
            StarredOrCommentedEvent(
                event_id=int(r[0]),
                ts_usec=int(r[1]),
                data_type=str(r[2]),
                message=str(r[3] or ""),
                note=first_line,
            )
        )
    return result


def _per_timeline(
    con: sqlite3.Connection, state: QueryState
) -> list[tuple[str, int]]:
    tl_count = int(
        con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0]
    )
    if tl_count < 2:
        return []
    where, params = _where_clause(state)
    base_where = where
    if base_where:
        sql = (
            "SELECT t.name, COUNT(*) FROM event e "
            "JOIN timeline t ON t.id = e.timeline_id "
            f"WHERE {base_where} "
            "GROUP BY t.id ORDER BY t.ingested_at ASC"
        )
    else:
        sql = (
            "SELECT t.name, COUNT(*) FROM event e "
            "JOIN timeline t ON t.id = e.timeline_id "
            "GROUP BY t.id ORDER BY t.ingested_at ASC"
        )
    rows = con.execute(sql, params).fetchall()
    return [(str(n), int(c)) for n, c in rows]


def build_overview(
    con: sqlite3.Connection, state: QueryState, *, buckets: int = 60
) -> OverviewData:
    where, params = _where_clause(state)
    lo, hi, total = _min_max_ts(con, where, params)
    tagged = _count_where_annotation(
        con, state, "SELECT event_hash FROM annotation_tag"
    )
    starred = _count_where_annotation(
        con, state, "SELECT event_hash FROM annotation_star"
    )
    commented = _count_where_annotation(
        con, state, "SELECT event_hash FROM annotation_comment"
    )
    histogram = build_histogram(con, state, buckets=buckets)
    per_tag = _per_tag(con, state) if total > 0 else []
    starred_events = _starred_events(con, state) if total > 0 else []
    commented_events = _commented_events(con, state) if total > 0 else []
    per_timeline = _per_timeline(con, state)
    return OverviewData(
        total=total,
        tagged=tagged,
        starred=starred,
        commented=commented,
        first_usec=lo,
        last_usec=hi,
        per_tag=per_tag,
        histogram=histogram,
        starred_events=starred_events,
        commented_events=commented_events,
        per_timeline=per_timeline,
        filter_summary=state.summary(),
    )

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import orjson

from ..core.case import open_case
from ..core.extra import load_extra
from .builder import build_sql
from .state import QueryState

_PROGRESS_INTERVAL = 10_000

_HEADER = [
    "id", "event_hash", "timeline_id", "timeline_name",
    "datetime_utc", "ts_usec", "ts_desc",
    "data_type", "parser", "source_short", "source_long",
    "display_name", "message",
    "starred", "tags", "comments", "extras",
]

_SELECT_TEMPLATE = """
SELECT
  e.id, e.event_hash, e.timeline_id, t.name AS timeline_name,
  e.ts_usec, e.ts_desc, e.data_type, e.parser,
  e.source_short, e.source_long, e.display_name, e.message, e.extra,
  EXISTS (
    SELECT 1 FROM annotation_star s WHERE s.event_hash = e.event_hash
  ) AS starred,
  (
    SELECT GROUP_CONCAT(tag, ';')
    FROM (
      SELECT tag FROM annotation_tag
      WHERE event_hash = e.event_hash
      ORDER BY tag
    )
  ) AS tags,
  (
    SELECT GROUP_CONCAT(body, ' | ')
    FROM (
      SELECT body FROM annotation_comment
      WHERE event_hash = e.event_hash
      ORDER BY created_at
    )
  ) AS comments
FROM event e
LEFT JOIN (SELECT id AS tl_id, name FROM timeline) t ON t.tl_id = e.timeline_id
{where_clause}
ORDER BY {order_by}
"""


def export_filtered_csv(
    case_path: Path,
    state: QueryState,
    out_path: Path,
    *,
    progress: Callable[[int], None] | None = None,
) -> int:
    """Stream events matching ``state`` to ``out_path`` as CSV.

    Writes to a sibling .tmp file then atomically renames into place.
    Raises FileExistsError if ``out_path`` already exists.
    """
    out_path = Path(out_path)
    if out_path.exists():
        raise FileExistsError(f"refusing to overwrite existing file: {out_path}")

    where_sql, params, order_by = build_sql(state)
    where_clause = f"WHERE {where_sql}" if where_sql else ""
    sql = _SELECT_TEMPLATE.format(where_clause=where_clause, order_by=order_by)

    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    rows_written = 0
    try:
        with open_case(case_path) as c, tmp_path.open(
            "w", newline="", encoding="utf-8"
        ) as fp:
            writer = csv.writer(fp)
            writer.writerow(_HEADER)
            cur = c.con.execute(sql, params)
            for row in cur:
                writer.writerow(_format_row(row))
                rows_written += 1
                if progress and rows_written % _PROGRESS_INTERVAL == 0:
                    progress(rows_written)
        os.replace(tmp_path, out_path)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise
    if progress:
        progress(rows_written)
    return rows_written


def _format_row(row: tuple) -> list[str]:
    (
        ev_id, event_hash, timeline_id, timeline_name,
        ts_usec, ts_desc, data_type, parser_,
        source_short, source_long, display_name, message, extra_blob,
        starred, tags, comments,
    ) = row
    return [
        str(ev_id),
        bytes(event_hash).hex(),
        timeline_id or "",
        timeline_name or "",
        _fmt_datetime(ts_usec),
        str(ts_usec),
        ts_desc or "",
        data_type or "",
        parser_ or "",
        source_short or "",
        source_long or "",
        display_name or "",
        _flatten_newlines(message or ""),
        "true" if starred else "false",
        tags or "",
        _flatten_newlines(comments or ""),
        _extras_json(extra_blob),
    ]


def _fmt_datetime(ts_usec: int) -> str:
    if ts_usec is None or ts_usec <= 0:
        return ""
    return datetime.fromtimestamp(
        ts_usec / 1_000_000, tz=timezone.utc
    ).isoformat(timespec="seconds")


def _flatten_newlines(text: str) -> str:
    if "\r" not in text and "\n" not in text:
        return text
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def _extras_json(blob: bytes | None) -> str:
    if not blob:
        return "{}"
    try:
        d = load_extra(bytes(blob))
    except Exception:
        return "{}"
    return orjson.dumps(d).decode("utf-8")

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from rich.markup import escape
from rich.text import Text
from textual.widgets import DataTable

from ...coloring import ColorRules
from ...coloring.render import colorize_timestamp
from ...core.case import list_timelines
from ...query.builder import build_sql
from ...query.state import QueryState

@dataclass(frozen=True, slots=True)
class WindowData:
    """One window load's results, safe to hand back from a worker thread."""
    total_filtered: int
    window_offset: int
    rows: list[tuple]
    annot: dict[int, tuple[bool, int, int]]


_TIMELINE_COLUMN_KEY = "timeline"
_TIMELINE_COLUMN_HEADER = "T"
COLUMNS = ("★", "C", "Tg", "datetime", "ts_desc", "data_type", "message")


def _fmt_ts(ts_usec: int) -> str:
    if ts_usec <= 0:
        return "—"
    return datetime.fromtimestamp(ts_usec / 1_000_000, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _render_ts(ts_usec: int, color_rules: ColorRules) -> Text:
    text = _fmt_ts(ts_usec)
    if ts_usec <= 0:
        return Text(text)
    matches = color_rules.matching(ts_usec)
    return colorize_timestamp(text, tuple(r.color for r in matches))


def _gutter_star(starred: bool) -> Text:
    return Text("★", style="yellow") if starred else Text("")


def _gutter_count(prefix: str, n: int, style: str) -> Text:
    if n <= 0:
        return Text("")
    if n == 1:
        return Text(prefix, style=style)
    return Text(f"{prefix}{n}", style=style)


class EventTable(DataTable):
    """Scrollable event table over a sliding window of the full filtered set,
    with gutter columns for star / comment-count / tag-count annotations."""

    WINDOW_SIZE = 5000
    PAGE_TRIGGER = 250  # rows from a window edge before we auto-shift

    def __init__(self, con: sqlite3.Connection) -> None:
        super().__init__(zebra_stripes=True, cursor_type="row")
        self.con = con
        self._state = QueryState()
        self._ts_list: list[int] = []
        self._id_list: list[int] = []
        self._hash_list: list[bytes] = []
        self._window_offset: int = 0
        self._total_filtered: int = 0
        self._annot: dict[int, tuple[bool, int, int]] = {}
        self._paging: bool = False  # re-entrancy guard during auto-shift
        self._show_timeline_column: bool = False
        self._timeline_colors: dict[str, str] = {}
        self._color_rules: ColorRules = ColorRules()
        self._selected_rows: set[int] = set()

    def set_color_rules(self, rules: ColorRules) -> None:
        self._color_rules = rules
        if self._ts_list:
            self._load_window()

    def set_selection(self, rows: set[int]) -> None:
        """Mark rows as selected and update only the cells whose state flipped.

        Selection is rendered with reverse video on the timestamp cell so the
        active range is visible above the existing color-rule styling without
        shifting layout.
        """
        new = {r for r in rows if 0 <= r < len(self._ts_list)}
        changed = self._selected_rows.symmetric_difference(new)
        self._selected_rows = new
        for row in changed:
            self._refresh_ts_cell(row)

    def clear_selection(self) -> None:
        self.set_selection(set())

    def _ts_cell(self, row_idx: int, ts_usec: int) -> Text:
        text = _render_ts(ts_usec, self._color_rules)
        if row_idx in self._selected_rows:
            text.stylize("reverse")
        return text

    def _ts_column_index(self) -> int:
        # gutters (★, C, Tg) come after the optional timeline column
        return (1 if self._show_timeline_column else 0) + 3

    def _refresh_ts_cell(self, row: int) -> None:
        if not (0 <= row < len(self._ts_list)):
            return
        self.update_cell_at(
            (row, self._ts_column_index()),
            self._ts_cell(row, self._ts_list[row]),
        )

    def on_mount(self) -> None:
        timelines = list_timelines(self.con)
        if len(timelines) >= 2:
            self._show_timeline_column = True
            self._timeline_colors = {t.id: t.color for t in timelines}
            self.add_column(_TIMELINE_COLUMN_HEADER, key=_TIMELINE_COLUMN_KEY)
        for col in COLUMNS:
            self.add_column(col, key=col)
        # Initial data load is driven by MainScreen via the async filter path.

    def apply_query(self, state: QueryState) -> None:
        self._state = state
        self._window_offset = 0
        self._load_window()

    def query_window(
        self, con: sqlite3.Connection, state: QueryState, offset: int
    ) -> WindowData:
        """Pure, read-only window read. Mutates no widget state, so it is safe
        to call from a worker thread with that thread's own connection."""
        where, params, order_by = build_sql(state)
        base = "FROM event" + (f" WHERE {where}" if where else "")
        total = int(con.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0])
        max_offset = max(0, total - self.WINDOW_SIZE)
        offset = max(0, min(offset, max_offset))
        sql = (
            f"SELECT id, ts_usec, ts_desc, data_type, message, event_hash, timeline_id "
            f"{base} ORDER BY {order_by} LIMIT ? OFFSET ?"
        )
        rows = list(con.execute(sql, params + (self.WINDOW_SIZE, offset)))
        annot = self._fetch_annotations(con, [r[0] for r in rows])
        return WindowData(
            total_filtered=total, window_offset=offset, rows=rows, annot=annot
        )

    def populate(self, state: QueryState, data: WindowData) -> None:
        """UI-thread: replace the table contents from a WindowData bundle."""
        self._state = state
        self._total_filtered = data.total_filtered
        self._window_offset = data.window_offset
        self._ts_list = []
        self._id_list = []
        self._hash_list = []
        self._selected_rows = set()
        self.clear()
        self._annot = data.annot
        for row_idx, row in enumerate(data.rows):
            event_id, ts_usec, ts_desc, data_type, message, event_hash, timeline_id = row
            self._ts_list.append(int(ts_usec))
            self._id_list.append(int(event_id))
            self._hash_list.append(bytes(event_hash))
            starred, cmt_n, tag_n = self._annot.get(int(event_id), (False, 0, 0))
            cells: list = []
            if self._show_timeline_column:
                color = self._timeline_colors.get(str(timeline_id), "white")
                cells.append(Text("█", style=color))
            cells.extend([
                _gutter_star(starred),
                _gutter_count("C", cmt_n, "cyan"),
                _gutter_count("T", tag_n, "magenta"),
                self._ts_cell(row_idx, ts_usec),
                escape(ts_desc or ""),
                escape(data_type or ""),
                escape((message or "").replace("\n", " ")[:200]),
            ])
            self.add_row(*cells, key=str(event_id))

    def _load_window(self) -> None:
        """Synchronous window load — used by paging, jump, color-rule and
        timeline reloads. Filter changes go through MainScreen's async path."""
        data = self.query_window(self.con, self._state, self._window_offset)
        self.populate(self._state, data)

    def _fetch_annotations(
        self, con: sqlite3.Connection, ids: list[int]
    ) -> dict[int, tuple[bool, int, int]]:
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        sql = f"""
            SELECT e.id,
                   (s.event_hash IS NOT NULL) AS starred,
                   (SELECT COUNT(*) FROM annotation_comment c
                     WHERE c.event_hash = e.event_hash) AS cmt_n,
                   (SELECT COUNT(*) FROM annotation_tag t
                     WHERE t.event_hash = e.event_hash) AS tag_n
            FROM event e
            LEFT JOIN annotation_star s ON s.event_hash = e.event_hash
            WHERE e.id IN ({placeholders})
        """
        out: dict[int, tuple[bool, int, int]] = {}
        for r in con.execute(sql, ids):
            out[int(r[0])] = (bool(r[1]), int(r[2]), int(r[3]))
        return out

    def _annot_for_row(self, row: int) -> tuple[bool, int, int]:
        if row < 0 or row >= len(self._id_list):
            return (False, 0, 0)
        return self._annot.get(self._id_list[row], (False, 0, 0))

    def refresh_annotation_row(self, row: int) -> None:
        if row < 0 or row >= len(self._id_list):
            return
        event_id = self._id_list[row]
        fresh = self._fetch_annotations(self.con, [event_id])
        starred, cmt_n, tag_n = fresh.get(event_id, (False, 0, 0))
        self._annot[event_id] = (starred, cmt_n, tag_n)
        base_col = 1 if self._show_timeline_column else 0
        self.update_cell_at((row, base_col + 0), _gutter_star(starred))
        self.update_cell_at((row, base_col + 1), _gutter_count("C", cmt_n, "cyan"))
        self.update_cell_at((row, base_col + 2), _gutter_count("T", tag_n, "magenta"))

    def filtered_count(self) -> int:
        return self._total_filtered

    @property
    def window_offset(self) -> int:
        return self._window_offset

    def current_hash(self) -> bytes | None:
        row = self.cursor_row
        if row is None or row < 0 or row >= len(self._hash_list):
            return None
        return self._hash_list[row]

    def visible_hashes(self) -> list[bytes]:
        return list(self._hash_list)

    def jump_to_ts(self, target_usec: int) -> bool:
        if self._state.sort.column != "ts_usec":
            return False
        if self._total_filtered == 0:
            return True
        where, params, _ = build_sql(self._state)
        base = "FROM event" + (f" WHERE {where}" if where else "")
        connector = " AND " if where else " WHERE "
        cmp = "<" if self._state.sort.direction == "ASC" else ">"
        rank_sql = f"SELECT COUNT(*) {base}{connector}ts_usec {cmp} ?"
        rank = int(
            self.con.execute(rank_sql, params + (target_usec,)).fetchone()[0]
        )
        rank = max(0, min(rank, self._total_filtered - 1))
        window_start = self._window_offset
        window_end = self._window_offset + len(self._ts_list)
        if not (window_start <= rank < window_end):
            self._window_offset = max(0, rank - self.WINDOW_SIZE // 2)
            self._load_window()
        local_idx = rank - self._window_offset
        local_idx = max(0, min(local_idx, len(self._ts_list) - 1))
        self.move_cursor(row=local_idx)
        return True

    def jump_to_event(self, event_id: int) -> bool:
        """Move the cursor to the event with the given id (respects current
        filters via jump_to_ts)."""
        row = self.con.execute(
            "SELECT ts_usec FROM event WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            return False
        return self.jump_to_ts(int(row[0]))

    def cursor_ts_usec(self) -> int | None:
        row = self.cursor_row
        if row is None or row < 0 or row >= len(self._ts_list):
            return None
        return self._ts_list[row]

    def data_ts_range(self) -> tuple[int, int] | None:
        where, params, _ = build_sql(self._state)
        base = "FROM event" + (f" WHERE {where}" if where else "")
        row = self.con.execute(
            f"SELECT MIN(ts_usec), MAX(ts_usec) {base}", params
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return (int(row[0]), int(row[1]))

    # -- auto-paging -----------------------------------------------------

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """When the cursor nears an edge, re-center the window on the cursor."""
        if self._paging or not self._ts_list:
            return
        row = self.cursor_row
        if row is None:
            return
        near_bottom = row >= len(self._ts_list) - self.PAGE_TRIGGER
        near_top = row < self.PAGE_TRIGGER
        if not (near_bottom or near_top):
            return
        abs_idx = self._window_offset + int(row)
        # Target: cursor lands in the middle of the new window.
        target_offset = abs_idx - self.WINDOW_SIZE // 2
        max_offset = max(0, self._total_filtered - self.WINDOW_SIZE)
        new_offset = max(0, min(target_offset, max_offset))
        if new_offset == self._window_offset:
            return
        self._paging = True
        try:
            self._window_offset = new_offset
            self._load_window()
            local = abs_idx - self._window_offset
            local = max(0, min(local, len(self._ts_list) - 1))
            self.move_cursor(row=local)
        finally:
            self._paging = False

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from ...query.state import QueryState
from ...report.data import OverviewData


@dataclass(frozen=True, slots=True)
class OverviewJump:
    """Dismiss result telling MainScreen to jump the cursor to an event id.

    Produced by the summary panel's starred/commented event rows (Task 4/5).
    """
    event_id: int


_TOTAL_GLYPHS = (" ", "▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")   # 0..8
_TAGGED_LOW   = "─"
_TAGGED_MID   = "═"
_TAGGED_HIGH  = "▓"
_TAGGED_NONE  = "·"


def _fmt_ts_min(u: int | None) -> str:
    if u is None:
        return "—"
    return datetime.fromtimestamp(
        u / 1_000_000, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M")


def _fmt_span(lo: int | None, hi: int | None) -> str:
    if lo is None or hi is None or hi < lo:
        return ""
    secs = (hi - lo) // 1_000_000
    if secs < 3600:
        return f"{max(0, secs // 60)}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _total_glyph(count: int, max_total: int) -> str:
    if count <= 0 or max_total <= 0:
        return _TOTAL_GLYPHS[0]
    level = round(count * 8 / max_total)
    return _TOTAL_GLYPHS[max(0, min(level, 8))]


def _tagged_glyph(count: int, max_tagged: int) -> str:
    if count <= 0:
        return _TAGGED_NONE
    if max_tagged <= 1:
        return _TAGGED_MID
    frac = count / max_tagged
    if frac <= 1 / 3:
        return _TAGGED_LOW
    if frac <= 2 / 3:
        return _TAGGED_MID
    return _TAGGED_HIGH


class OverviewScreen(ModalScreen["QueryState | OverviewJump | None"]):
    """Histogram + summary view of the current filtered slice.

    Dismisses with one of:
      - None                — no change.
      - QueryState          — apply a new bracket or tag filter.
      - OverviewJump(id)    — jump the main table cursor to an event.
    """

    DEFAULT_CSS = """
    OverviewScreen { align: center middle; }
    OverviewScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 90; height: 90%;
    }
    OverviewScreen #hist-total { color: $text; }
    OverviewScreen #hist-tagged { color: $warning; }
    OverviewScreen #status { color: $text-muted; }
    """

    BINDINGS = [
        ("left",  "cursor_prev",  "Prev bucket"),
        ("right", "cursor_next",  "Next bucket"),
        ("home",  "cursor_first", "First"),
        ("end",   "cursor_last",  "Last"),
        ("plus",  "zoom_in",      "Zoom in"),
        ("minus", "zoom_out",     "Zoom out"),
        ("r",     "refresh",      "Refresh"),
        Binding("enter", "apply", "Apply", priority=True),
        ("escape", "cancel", "Cancel"),
        ("q",      "cancel", "Cancel"),
    ]

    def __init__(
        self,
        state: QueryState,
        data: OverviewData,
        *,
        con: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__()
        self._state = state
        self._data = data
        self._con = con
        self._cursor_bucket = self._initial_cursor()
        self._buckets = len(data.histogram) if data.histogram else 60

    def _initial_cursor(self) -> int:
        h = self._data.histogram
        if not h:
            return 0
        max_tagged = max((b.tagged for b in h), default=0)
        if max_tagged > 0:
            for i, b in enumerate(h):
                if b.tagged == max_tagged:
                    return i
        return len(h) // 2

    def compose(self) -> ComposeResult:
        title = f"Overview  (filters: {self._data.filter_summary})"
        with Vertical():
            yield Label(title, markup=False)
            yield Static(self._render_status(), id="status", markup=False)
            yield Static(self._render_total_row(), id="hist-total", markup=False)
            yield Static(self._render_tagged_row(), id="hist-tagged", markup=False)
            with VerticalScroll(id="summary-scroll"):
                yield Static(self._render_summary(), id="summary", markup=False)
                if self._data.per_tag:
                    yield Label("Tags")
                    yield OptionList(*self._tag_options(), id="tags-list", markup=False)
                if self._data.starred_events:
                    yield Label("★ Starred events")
                    yield OptionList(*self._starred_options(), id="starred-list", markup=False)
                if self._data.commented_events:
                    yield Label("💬 Commented events")
                    yield OptionList(*self._commented_options(), id="commented-list", markup=False)
            yield Static(
                "←/→ move · +/- zoom · Enter apply · Tab jump to tags · Esc close",
                id="hints",
                markup=False,
            )

    def _render_status(self) -> str:
        lo = _fmt_ts_min(self._data.first_usec)
        hi = _fmt_ts_min(self._data.last_usec)
        span = _fmt_span(self._data.first_usec, self._data.last_usec)
        span_txt = f"  ({span})" if span else ""
        bracket_txt = ""
        b = self._state.bracket
        if not b.is_empty():
            bracket_txt = "  (bracket active)"
        return f"Time  {lo}  ─  {hi}{span_txt}   total: {self._data.total:,}{bracket_txt}"

    def _render_total_row(self) -> str:
        h = self._data.histogram
        if not h:
            return "(no events in current filter)"
        max_total = max((b.total for b in h), default=0)
        chars: list[str] = []
        for i, b in enumerate(h):
            g = _total_glyph(b.total, max_total)
            if i == self._cursor_bucket:
                chars.append(f"[{g}]")  # rendered inline as literal brackets
            else:
                chars.append(g)
        return "Total  " + "".join(chars)

    def _render_tagged_row(self) -> str:
        h = self._data.histogram
        if not h:
            return ""
        max_tagged = max((b.tagged for b in h), default=0)
        chars: list[str] = []
        for i, b in enumerate(h):
            g = _tagged_glyph(b.tagged, max_tagged)
            if i == self._cursor_bucket:
                chars.append(f"[{g}]")
            else:
                chars.append(g)
        return "Tagged " + "".join(chars)

    def _render_summary(self) -> str:
        d = self._data
        lines: list[str] = []
        total_line = f"Events     {d.total:,}"
        if d.per_timeline:
            pieces = " · ".join(f"{n}: {c:,}" for n, c in d.per_timeline)
            total_line += f"  ({pieces})"
        lines.append(total_line)
        lines.append(f"Tagged     {d.tagged:,}")
        lines.append(f"Starred    {d.starred:,}")
        lines.append(f"Commented  {d.commented:,}")
        if d.first_usec is not None and d.last_usec is not None:
            span = _fmt_span(d.first_usec, d.last_usec)
            span_txt = f"  ({span})" if span else ""
            lines.append(
                f"Time span  {_fmt_ts_min(d.first_usec)} → "
                f"{_fmt_ts_min(d.last_usec)}{span_txt}"
            )
        return "\n".join(lines)

    def _tag_options(self) -> list[Option]:
        opts: list[Option] = []
        for t in self._data.per_tag:
            label = (
                f"{t.tag:<28}  {t.count:>6}   "
                f"{_fmt_ts_min(t.first_usec)[-5:]}  {_fmt_ts_min(t.last_usec)[-5:]}"
            )
            opts.append(Option(label, id=f"tag:{t.tag}"))
        return opts

    def _starred_options(self) -> list[Option]:
        opts: list[Option] = []
        for e in self._data.starred_events:
            excerpt = (e.message or "").replace("\n", " ")[:50]
            label = f"{_fmt_ts_min(e.ts_usec)[-5:]}  {e.data_type:<28}  {excerpt}"
            opts.append(Option(label, id=f"ev:{e.event_id}"))
        return opts

    def _commented_options(self) -> list[Option]:
        opts: list[Option] = []
        for e in self._data.commented_events:
            note = e.note.replace("\n", " ")[:40]
            label = f"{_fmt_ts_min(e.ts_usec)[-5:]}  {e.data_type:<28}  {note}"
            opts.append(Option(label, id=f"ev:{e.event_id}"))
        return opts

    def _refresh_histogram(self) -> None:
        try:
            self.query_one("#hist-total", Static).update(self._render_total_row())
            self.query_one("#hist-tagged", Static).update(self._render_tagged_row())
        except NoMatches:
            pass

    def _clamp_cursor(self) -> None:
        n = len(self._data.histogram)
        if n == 0:
            self._cursor_bucket = 0
            return
        self._cursor_bucket = max(0, min(self._cursor_bucket, n - 1))

    # -- bindings --------------------------------------------------------

    def action_cursor_prev(self) -> None:
        self._cursor_bucket -= 1
        self._clamp_cursor()
        self._refresh_histogram()

    def action_cursor_next(self) -> None:
        self._cursor_bucket += 1
        self._clamp_cursor()
        self._refresh_histogram()

    def action_cursor_first(self) -> None:
        self._cursor_bucket = 0
        self._refresh_histogram()

    def action_cursor_last(self) -> None:
        self._cursor_bucket = max(0, len(self._data.histogram) - 1)
        self._refresh_histogram()

    def action_zoom_in(self) -> None:
        new = max(15, min(240, self._buckets * 2))
        if new == self._buckets:
            return
        self._buckets = new
        self._reload_data()

    def action_zoom_out(self) -> None:
        new = max(15, min(240, self._buckets // 2))
        if new == self._buckets:
            return
        self._buckets = new
        self._reload_data()

    def action_refresh(self) -> None:
        self._reload_data()

    def _reload_data(self) -> None:
        """Recompute overview data from the DB at the current bucket count.

        No-op when no DB connection was provided (older tests construct the
        screen with pre-built data only)."""
        if self._con is None:
            self._refresh_histogram()
            return
        from ...report.data import build_overview
        self._data = build_overview(self._con, self._state, buckets=self._buckets)
        self._clamp_cursor()
        # Re-render the screen contents that depend on _data.
        self._refresh_histogram()
        try:
            self.query_one("#status", Static).update(self._render_status())
            self.query_one("#summary", Static).update(self._render_summary())
        except NoMatches:
            pass

    def action_apply(self) -> None:
        focused = self.focused
        # Focused widget determines the Enter semantics.
        if isinstance(focused, OptionList):
            idx = focused.highlighted
            if idx is None:
                return
            opt = focused.get_option_at_index(idx)
            rid = opt.id if opt is not None else None
            if rid is None:
                return
            if rid.startswith("tag:"):
                tag = rid[len("tag:"):]
                self.dismiss(
                    self._state.set_tag_filter(include={tag}, exclude=set())
                )
                return
            if rid.startswith("ev:"):
                event_id = int(rid[len("ev:"):])
                self.dismiss(OverviewJump(event_id=event_id))
                return
            return
        # Otherwise: apply the histogram bucket as a bracket.
        if not self._data.histogram:
            self.dismiss(None)
            return
        b = self._data.histogram[self._cursor_bucket]
        # end_usec is exclusive; bracket wants inclusive — subtract 1 usec.
        self.dismiss(self._state.set_bracket(b.start_usec, b.end_usec - 1))

    def action_cancel(self) -> None:
        self.dismiss(None)

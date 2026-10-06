from __future__ import annotations

from collections.abc import Callable

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from ...query.state import (
    FILTERABLE_COLUMNS,
    SORTABLE_COLUMNS,
    CategoricalFilter,
    FilterKind,
    QueryState,
    SubstringFilter,
)
from .star_filter import StarFilterScreen
from .text_picker import TextPickerScreen
from .timeline_panel import TimelinePanelScreen
from .value_picker import ValuePickerScreen

CountsProvider = Callable[[str], list[tuple[str, int]]]


class ColumnPickerScreen(ModalScreen["QueryState"]):
    DEFAULT_CSS = """
    ColumnPickerScreen {
        align: center middle;
    }
    ColumnPickerScreen > Vertical {
        background: $panel;
        border: solid $primary;
        padding: 1 2;
        width: 80;
        height: 80%;
    }
    ColumnPickerScreen OptionList {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "commit", "Close"),
        ("q", "commit", "Close"),
        ("r", "clear_column", "Clear column"),
        ("R", "clear_all", "Clear all"),
        ("s", "toggle_sort", "Sort direction"),
        Binding("enter", "activate", "Edit", priority=True),
    ]

    _SORT_ROW_ID = "__sort__"

    def __init__(
        self,
        state: QueryState,
        counts_provider: CountsProvider,
        timeline_total: int = 0,
        timelines_supplier=None,
    ) -> None:
        super().__init__()
        self._state = state
        self._counts_provider = counts_provider
        self._timeline_total = timeline_total
        self._timelines_supplier = timelines_supplier

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Filter / Sort")
            yield OptionList(*self._render_rows())
            yield Static(
                "Enter: edit  |  s: toggle sort direction  |  "
                "r: clear column  |  R: clear all  |  Esc/q: close"
            )

    def _render_rows(self) -> list[Option | None]:
        rows: list[Option | None] = []
        for col, label, kind in FILTERABLE_COLUMNS:
            summary = self._summary_for(col, kind)
            rows.append(Option(escape(f"{label:<18} {summary}"), id=col))
        tag_summary = self._tag_summary()
        rows.append(Option(escape(f"{'Tags':<18} {tag_summary}"), id="__tags__"))
        star_summary = self._star_summary()
        rows.append(Option(escape(f"{'Stars':<18} {star_summary}"), id="__stars__"))
        timeline_summary = self._timeline_summary()
        rows.append(Option(escape(f"{'Timelines':<18} {timeline_summary}"), id="__timelines__"))
        rows.append(None)
        sort_label = next(
            label for col, label in SORTABLE_COLUMNS if col == self._state.sort.column
        )
        arrow = "↑" if self._state.sort.direction == "ASC" else "↓"
        rows.append(
            Option(escape(f"{'Sort':<18} {sort_label} {arrow}{self._state.sort.direction}"),
                   id=self._SORT_ROW_ID)
        )
        return rows

    def _summary_for(self, col: str, kind: FilterKind) -> str:
        if kind == FilterKind.CATEGORICAL:
            cf = self._state.categorical.get(col)
            if cf is None or cf.is_empty():
                return "—"
            parts = []
            if cf.include:
                parts.append(f"IN({len(cf.include)})")
            if cf.exclude:
                parts.append(f"NOT IN({len(cf.exclude)})")
            return " ".join(parts)
        else:
            sf = self._state.substring.get(col)
            if sf is None or sf.is_empty():
                return "—"
            return f"*{sf.needle}*"

    def _tag_summary(self) -> str:
        tf = self._state.tag_filter
        if tf.is_empty():
            return "—"
        parts = []
        if tf.include:
            parts.append(f"IN({len(tf.include)})")
        if tf.exclude:
            parts.append(f"NOT IN({len(tf.exclude)})")
        return " ".join(parts)

    def _star_summary(self) -> str:
        return self._state.star_filter or "any"

    def _timeline_summary(self) -> str:
        tf = self._state.timeline_filter
        if not tf:
            return "—"
        if self._timeline_total:
            return f"visible: {len(tf)} of {self._timeline_total}"
        return f"visible: {len(tf)}"

    def _refresh_rows(self) -> None:
        lst = self.query_one(OptionList)
        highlighted = lst.highlighted
        lst.clear_options()
        lst.add_options(self._render_rows())
        if highlighted is not None and highlighted < lst.option_count:
            lst.highlighted = highlighted

    def _current_row_id(self) -> str | None:
        lst = self.query_one(OptionList)
        idx = lst.highlighted
        if idx is None:
            return None
        opt = lst.get_option_at_index(idx)
        return opt.id

    def action_commit(self) -> None:
        self.dismiss(self._state)

    def action_clear_column(self) -> None:
        rid = self._current_row_id()
        if rid is None or rid == self._SORT_ROW_ID:
            return
        if rid == "__tags__":
            self._state = self._state.set_tag_filter(include=set(), exclude=set())
        elif rid == "__stars__":
            self._state = self._state.set_star_filter(None)
        elif rid == "__timelines__":
            self._state = self._state.set_timeline_filter(set())
        else:
            self._state = self._state.clear_column(rid)
        self._refresh_rows()

    def action_clear_all(self) -> None:
        self._state = self._state.clear_all()
        self._refresh_rows()

    def action_toggle_sort(self) -> None:
        if self._current_row_id() != self._SORT_ROW_ID:
            return
        new_dir = "DESC" if self._state.sort.direction == "ASC" else "ASC"
        self._state = self._state.set_sort(self._state.sort.column, new_dir)
        self._refresh_rows()

    def action_activate(self) -> None:
        rid = self._current_row_id()
        if rid is None:
            return
        if rid == self._SORT_ROW_ID:
            cols = [c for c, _ in SORTABLE_COLUMNS]
            idx = cols.index(self._state.sort.column)
            next_col = cols[(idx + 1) % len(cols)]
            self._state = self._state.set_sort(next_col, self._state.sort.direction)
            self._refresh_rows()
            return
        if rid == "__tags__":
            counts = self._counts_provider("__tags__")
            initial = self._state.tag_filter
            self.app.push_screen(
                ValuePickerScreen("tags", counts, initial),
                callback=self._apply_tag_result,
            )
            return
        if rid == "__stars__":
            self.app.push_screen(
                StarFilterScreen(self._state.star_filter),
                callback=self._apply_star_result,
            )
            return
        if rid == "__timelines__":
            if self._timelines_supplier is None:
                return
            timelines = self._timelines_supplier()
            self.app.push_screen(
                TimelinePanelScreen(timelines, self._state.timeline_filter),
                callback=self._apply_timeline_result,
            )
            return
        kinds = {c[0]: c[2] for c in FILTERABLE_COLUMNS}
        kind = kinds[rid]
        if kind == FilterKind.CATEGORICAL:
            counts = self._counts_provider(rid)
            initial = self._state.categorical.get(rid, CategoricalFilter())
            self.app.push_screen(
                ValuePickerScreen(rid, counts, initial),
                callback=lambda result, col=rid: self._apply_categorical(col, result),
            )
        else:
            initial = self._state.substring.get(rid, SubstringFilter())
            self.app.push_screen(
                TextPickerScreen(rid, initial),
                callback=lambda result, col=rid: self._apply_substring(col, result),
            )

    def _apply_tag_result(self, result) -> None:
        if result is None:
            return
        self._state = self._state.set_tag_filter(
            include=result.include, exclude=result.exclude
        )
        self._refresh_rows()

    def _apply_star_result(self, result) -> None:
        self._state = self._state.set_star_filter(result)
        self._refresh_rows()

    def _apply_timeline_result(self, result) -> None:
        if result is None:
            return
        self._state = self._state.set_timeline_filter(result)
        self._refresh_rows()

    def _apply_categorical(self, col: str, result: CategoricalFilter | None) -> None:
        if result is None:
            return
        self._state = self._state.set_categorical(
            col, include=result.include, exclude=result.exclude
        )
        self._refresh_rows()

    def _apply_substring(self, col: str, result: SubstringFilter | None) -> None:
        if result is None:
            return
        self._state = self._state.set_substring(col, result.needle)
        self._refresh_rows()

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

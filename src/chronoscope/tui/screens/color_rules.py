from __future__ import annotations

from rich.markup import escape
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from ...coloring import ColorRule, ColorRules, OffHoursRule
from .off_hours_editor import OffHoursEditorScreen


class ColorRulesScreen(ModalScreen["ColorRules"]):
    """Modal listing all color rules; toggle on/off and edit each rule."""

    DEFAULT_CSS = """
    ColorRulesScreen { align: center middle; }
    ColorRulesScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 70; height: 70%;
    }
    ColorRulesScreen OptionList { height: 1fr; }
    """

    BINDINGS = [
        ("escape", "commit", "Close"),
        ("q", "commit", "Close"),
        ("space", "toggle", "Toggle"),
        Binding("enter", "edit", "Edit", priority=True),
    ]

    def __init__(self, rules: ColorRules) -> None:
        super().__init__()
        self._rules = rules

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Color rules")
            yield OptionList(*self._render_rows())
            yield Static("space: toggle  |  Enter: edit  |  Esc/q: close")

    def _render_rows(self) -> list[Option]:
        rows: list[Option] = []
        for r in self._rules.rules:
            rows.append(Option(self._row_text(r), id=r.id))
        return rows

    def _row_text(self, r: ColorRule) -> Text:
        check = "[x]" if r.enabled else "[ ]"
        summary = self._summary(r)
        line = Text()
        line.append(f"{check} ")
        line.append(escape(f"{r.name:<14} "))
        line.append(escape(summary))
        line.append("  ")
        line.append("■", style=r.color)
        line.append(escape(f" {r.color}"))
        return line

    def _summary(self, r: ColorRule) -> str:
        if isinstance(r, OffHoursRule):
            return f"{r.start_hour:02d}:00–{r.end_hour:02d}:00 UTC"
        return ""

    def _refresh_rows(self) -> None:
        lst = self.query_one(OptionList)
        highlighted = lst.highlighted
        lst.clear_options()
        lst.add_options(self._render_rows())
        if highlighted is not None and highlighted < lst.option_count:
            lst.highlighted = highlighted

    def _current_rule(self) -> ColorRule | None:
        lst = self.query_one(OptionList)
        idx = lst.highlighted
        if idx is None:
            return None
        opt = lst.get_option_at_index(idx)
        for r in self._rules.rules:
            if r.id == opt.id:
                return r
        return None

    def action_commit(self) -> None:
        self.dismiss(self._rules)

    def action_toggle(self) -> None:
        r = self._current_rule()
        if r is None:
            return
        from dataclasses import replace as dc_replace
        new = dc_replace(r, enabled=not r.enabled)
        self._rules = self._rules.with_rule(new)
        self._refresh_rows()

    def action_edit(self) -> None:
        r = self._current_rule()
        if r is None:
            return
        if isinstance(r, OffHoursRule):
            self.app.push_screen(
                OffHoursEditorScreen(r),
                callback=self._apply_off_hours,
            )

    def _apply_off_hours(self, result: OffHoursRule | None) -> None:
        if result is None:
            return
        self._rules = self._rules.with_rule(result)
        self._refresh_rows()

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

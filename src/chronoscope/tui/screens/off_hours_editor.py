from __future__ import annotations

from dataclasses import replace as dc_replace

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...coloring import OffHoursRule


class OffHoursEditorScreen(ModalScreen["OffHoursRule | None"]):
    """Edit start/end hour and color for an OffHoursRule. UTC.

    Hours are integers 0..23; start == end means the rule never matches.
    """

    DEFAULT_CSS = """
    OffHoursEditorScreen { align: center middle; }
    OffHoursEditorScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 60; height: auto;
    }
    OffHoursEditorScreen Input { margin: 0 0 1 0; }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    def __init__(self, rule: OffHoursRule) -> None:
        super().__init__()
        self._rule = rule
        self._error: str = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Off-hours rule (UTC)")
            yield Label("Start hour (0–23):")
            yield Input(value=str(self._rule.start_hour), id="start")
            yield Label("End hour (0–23, exclusive):")
            yield Input(value=str(self._rule.end_hour), id="end")
            yield Label("Color:")
            yield Input(value=self._rule.color, id="color")
            yield Static("", id="error")
            yield Static("Enter on color: save  |  Ctrl+S: save  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#start", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "color":
            self.action_save()
        else:
            order = ["start", "end", "color"]
            idx = order.index(event.input.id)
            self.query_one(f"#{order[(idx + 1) % len(order)]}", Input).focus()

    def action_save(self) -> None:
        try:
            start = int(self.query_one("#start", Input).value)
            end = int(self.query_one("#end", Input).value)
            color = self.query_one("#color", Input).value.strip() or self._rule.color
            new = dc_replace(self._rule, start_hour=start, end_hour=end, color=color)
        except ValueError as e:
            self.query_one("#error", Static).update(f"invalid: {e}")
            return
        self.dismiss(new)

    def action_cancel(self) -> None:
        self.dismiss(None)

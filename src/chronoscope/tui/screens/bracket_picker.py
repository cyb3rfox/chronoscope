from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...query.state import TimeBracket
from ...query.timestamp import parse_jump_target


def _fmt_ts_min(ts_usec: int | None) -> str:
    if ts_usec is None:
        return ""
    return datetime.fromtimestamp(
        ts_usec / 1_000_000, tz=timezone.utc
    ).strftime("%Y-%m-%d %H:%M")


class BracketPickerScreen(ModalScreen["TimeBracket | None"]):
    DEFAULT_CSS = """
    BracketPickerScreen { align: center middle; }
    BracketPickerScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 68; height: auto;
    }
    BracketPickerScreen #error { color: $error; }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        Binding("enter", "submit", "Apply", priority=True),
    ]

    def __init__(self, initial: TimeBracket, anchor_usec: int) -> None:
        super().__init__()
        self._initial = initial
        self._anchor = anchor_usec

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Time bracket")
            yield Input(
                value=_fmt_ts_min(self._initial.start_usec),
                placeholder="From (empty = unbounded)",
                id="from",
            )
            yield Input(
                value=_fmt_ts_min(self._initial.end_usec),
                placeholder="To (empty = unbounded)",
                id="to",
            )
            yield Static("", id="error", markup=False)
            yield Static(
                "ISO (2019-03-12 17:14) or relative (-5m, +1h). "
                "Empty = unbounded."
            )
            yield Static("Enter: apply  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#from", Input).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        from_text = self.query_one("#from", Input).value.strip()
        to_text = self.query_one("#to", Input).value.strip()
        try:
            start = parse_jump_target(from_text, self._anchor) if from_text else None
            end = parse_jump_target(to_text, self._anchor) if to_text else None
        except ValueError as e:
            self.query_one("#error", Static).update(str(e))
            return
        self.dismiss(TimeBracket(start, end))

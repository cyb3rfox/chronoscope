from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...query.timestamp import parse_jump_target


class JumpPickerScreen(ModalScreen["int | None"]):
    DEFAULT_CSS = """
    JumpPickerScreen {
        align: center middle;
    }
    JumpPickerScreen > Vertical {
        background: $panel;
        border: solid $primary;
        padding: 1 2;
        width: 64;
        height: auto;
    }
    JumpPickerScreen #error {
        color: $error;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
        Binding("enter", "submit", "Jump", priority=True),
    ]

    def __init__(self, anchor_usec: int) -> None:
        super().__init__()
        self._anchor = anchor_usec

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Jump to timestamp")
            yield Input(placeholder="2019-03-12 17:13   or   -5m / +1h / -7d", id="when")
            yield Static("", id="error", markup=False)
            yield Static("Enter: jump  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#when", Input).focus()

    def action_submit(self) -> None:
        text = self.query_one("#when", Input).value
        try:
            target = parse_jump_target(text, self._anchor)
        except ValueError as e:
            self.query_one("#error", Static).update(str(e))
            return
        self.dismiss(target)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Fallback: also handle Input.Submitted in case enter binding is consumed."""
        self.action_submit()

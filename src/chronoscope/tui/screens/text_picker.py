from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...query.state import SubstringFilter


class TextPickerScreen(ModalScreen["SubstringFilter | None"]):
    DEFAULT_CSS = """
    TextPickerScreen {
        align: center middle;
    }
    TextPickerScreen > Vertical {
        background: $panel;
        border: solid $primary;
        padding: 1 2;
        width: 60;
        height: auto;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(self, column: str, initial: SubstringFilter) -> None:
        super().__init__()
        self._column = column
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Filter: {self._column} (substring)")
            yield Input(value=self._initial.needle, placeholder="needle…", id="needle")
            yield Static("Enter: apply  |  Esc: cancel  |  empty Enter clears filter")

    def on_mount(self) -> None:
        self.query_one("#needle", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(SubstringFilter(event.value))

    def action_cancel(self) -> None:
        self.dismiss(None)

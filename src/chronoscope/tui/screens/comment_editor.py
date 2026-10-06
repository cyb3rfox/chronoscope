from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static, TextArea


class CommentEditorScreen(ModalScreen["str | None"]):
    DEFAULT_CSS = """
    CommentEditorScreen { align: center middle; }
    CommentEditorScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 80; height: 80%;
    }
    CommentEditorScreen TextArea { height: 1fr; }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    def __init__(self, title: str, initial_body: str) -> None:
        super().__init__()
        self._title = title
        self._initial = initial_body

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield TextArea(text=self._initial, id="body")
            yield Static("Ctrl+S: save  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#body", TextArea).focus()

    def action_save(self) -> None:
        self.dismiss(self.query_one("#body", TextArea).text)

    def action_cancel(self) -> None:
        self.dismiss(None)

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static


class StarFilterScreen(ModalScreen["str | None"]):
    DEFAULT_CSS = """
    StarFilterScreen { align: center middle; }
    StarFilterScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 48; height: auto;
    }
    """

    BINDINGS = [
        ("a", "any", "Any"),
        ("s", "only_starred", "Only starred"),
        ("u", "only_unstarred", "Only unstarred"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, initial: str | None) -> None:
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Stars filter (current: {self._initial or 'any'})")
            yield Static("a: any  |  s: only starred  |  u: only unstarred  |  Esc: cancel")

    def action_any(self) -> None:
        self.dismiss(None)

    def action_only_starred(self) -> None:
        self.dismiss("only_starred")

    def action_only_unstarred(self) -> None:
        self.dismiss("only_unstarred")

    def action_cancel(self) -> None:
        self.dismiss(None)

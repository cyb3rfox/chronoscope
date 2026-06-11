from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import LoadingIndicator, Static


class FilterLoadingScreen(ModalScreen[bool]):
    """Dim overlay with an animated spinner shown while a filter loads.

    Dismisses True when the user cancels (Esc), and is dismissed with False
    programmatically by MainScreen when the load finishes on its own."""

    DEFAULT_CSS = """
    FilterLoadingScreen { align: center middle; background: $background 60%; }
    FilterLoadingScreen > Vertical {
        width: auto; height: auto; padding: 1 2; align: center middle;
    }
    FilterLoadingScreen LoadingIndicator {
        width: auto; height: 1; color: $accent;
    }
    FilterLoadingScreen Static { text-align: center; width: auto; }
    """
    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield LoadingIndicator()
            yield Static("Loading…  (Esc to cancel)")

    def action_cancel(self) -> None:
        self.dismiss(True)

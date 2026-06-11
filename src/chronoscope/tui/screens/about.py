from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static


def _pkg_version() -> str:
    try:
        return version("chronoscope")
    except PackageNotFoundError:
        return "unknown"


class AboutScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    AboutScreen { align: center middle; }
    AboutScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 60; height: auto;
    }
    """
    BINDINGS = [("escape", "dismiss", "Close"), ("q", "dismiss", "Close")]

    def __init__(self) -> None:
        super().__init__()
        self._body = (
            f"Chronoscope {_pkg_version()}\n"
            "TUI for Plaso forensic timelines.\n\n"
            "License: TBD"
        )

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("About")
            yield Static(self._body)
            yield Static("Esc / q: close")

    def rendered_text(self) -> str:
        return self._body

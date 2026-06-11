from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual.app import App

from .bindings import KeyBinding, to_textual
from .screens.launcher import LauncherScreen
from .screens.main import MainScreen

_APP_BINDINGS: list[KeyBinding] = [
    KeyBinding("?", "help", "Help", ("always",)),
    KeyBinding("q", "quit", "Quit", ("always",)),
]


class PlasoViewerApp(App):
    TITLE = "Chronoscope"
    CSS = """
    Screen { layers: base overlay; }
    """
    BINDINGS = to_textual(_APP_BINDINGS)

    def __init__(self, case_path: Optional[Path] = None) -> None:
        super().__init__()
        self.case_path = Path(case_path) if case_path else None

    def on_mount(self) -> None:
        if self.case_path is None:
            self.push_screen(LauncherScreen())
        else:
            self.push_screen(MainScreen(self.case_path))

    def action_help(self) -> None:
        from .screens.help import HelpScreen
        from .screens.main import _MAIN_BINDINGS

        self.push_screen(HelpScreen(_APP_BINDINGS + _MAIN_BINDINGS))

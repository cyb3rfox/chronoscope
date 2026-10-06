from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static


class OpenCaseScreen(ModalScreen["Path | None"]):
    DEFAULT_CSS = """
    OpenCaseScreen { align: center middle; }
    OpenCaseScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 70; height: auto;
    }
    OpenCaseScreen #err { color: $error; }
    """
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Open"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Open case")
            yield Input(placeholder="path to case directory", id="path")
            yield Static("", id="err")
            yield Static("Enter: open  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#path", Input).focus()

    def set_path(self, path: str) -> None:
        self.query_one("#path", Input).value = path

    def error_text(self) -> str:
        return self._error

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        raw = self.query_one("#path", Input).value.strip()
        if not raw:
            self._set_error("path required")
            return
        path = Path(raw).expanduser()
        if not (path / "case.toml").exists():
            self._set_error(f"no case.toml at {path}")
            return
        self.dismiss(path.resolve())

    def _set_error(self, msg: str) -> None:
        self._error = msg
        self.query_one("#err", Static).update(msg)

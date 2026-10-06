from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...core.case import CaseExistsError, init_case


class NewCaseScreen(ModalScreen["Path | None"]):
    DEFAULT_CSS = """
    NewCaseScreen { align: center middle; }
    NewCaseScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 70; height: auto;
    }
    NewCaseScreen #err { color: $error; }
    """
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Create"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("New case")
            yield Input(placeholder="case name", id="name")
            yield Input(placeholder="target directory", id="directory")
            yield Static("", id="err")
            yield Static("Enter: create  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()

    def set_inputs(self, *, name: str, directory: str) -> None:
        self.query_one("#name", Input).value = name
        self.query_one("#directory", Input).value = directory

    def error_text(self) -> str:
        return self._error

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_submit()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        directory = self.query_one("#directory", Input).value.strip()
        if not name or not directory:
            self._set_error("name and directory are required")
            return
        path = Path(directory).expanduser()
        try:
            init_case(path, name=name)
        except CaseExistsError as exc:
            self._set_error(str(exc))
            return
        except OSError as exc:
            self._set_error(f"could not create: {exc}")
            return
        self.dismiss(path.resolve())

    def _set_error(self, msg: str) -> None:
        self._error = msg
        self.query_one("#err", Static).update(msg)

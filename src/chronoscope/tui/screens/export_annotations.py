from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...annotations.export import export_annotations


class ExportAnnotationsScreen(ModalScreen["Path | None"]):
    DEFAULT_CSS = """
    ExportAnnotationsScreen { align: center middle; }
    ExportAnnotationsScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 70; height: auto;
    }
    ExportAnnotationsScreen #err { color: $error; }
    """
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Export"),
    ]

    def __init__(self, case_path: Path) -> None:
        super().__init__()
        self._case_path = Path(case_path)
        self._error = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Export annotations")
            yield Input(placeholder="output path (.json)", id="path")
            yield Static("", id="err")
            yield Static("Enter: export  |  Esc: cancel")

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
        out = Path(raw).expanduser()
        try:
            n = export_annotations(self._case_path, out)
        except OSError as exc:
            self._set_error(str(exc))
            return
        self.app.notify(f"Exported {n} events to {out}", severity="information")
        self.dismiss(out)

    def _set_error(self, msg: str) -> None:
        self._error = msg
        self.query_one("#err", Static).update(msg)

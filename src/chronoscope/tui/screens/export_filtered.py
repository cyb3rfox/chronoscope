from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...query.csv_export import export_filtered_csv
from ...query.state import QueryState


class ExportFilteredCsvScreen(ModalScreen["Path | None"]):
    DEFAULT_CSS = """
    ExportFilteredCsvScreen { align: center middle; }
    ExportFilteredCsvScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 80; height: auto;
    }
    ExportFilteredCsvScreen #err    { color: $error; }
    ExportFilteredCsvScreen #status { color: $text-muted; }
    """
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter",  "submit", "Export"),
    ]

    class _Progress(Message):
        def __init__(self, n: int) -> None:
            super().__init__()
            self.n = n

    class _Done(Message):
        def __init__(self, out_path: Path, n: int) -> None:
            super().__init__()
            self.out_path = out_path
            self.n = n

    class _Failed(Message):
        def __init__(self, message: str) -> None:
            super().__init__()
            self.message = message

    def __init__(
        self,
        case_path: Path,
        state: QueryState,
        *,
        default_filename: str | None = None,
    ) -> None:
        super().__init__()
        self._case_path = Path(case_path)
        self._state = state
        self._default_filename = (
            default_filename
            or f"{self._case_path.name}-{datetime.now():%Y%m%d-%H%M%S}.csv"
        )
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Export filtered events to CSV")
            yield Input(
                value=str(Path.home() / self._default_filename),
                placeholder="output path (.csv)",
                id="path",
            )
            yield Static("", id="err")
            yield Static("Enter: export  |  Esc: cancel", id="status")

    def on_mount(self) -> None:
        self.query_one("#path", Input).focus()

    def set_path(self, path: str) -> None:
        self.query_one("#path", Input).value = path

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_submit()

    def action_cancel(self) -> None:
        if self._busy:
            return
        self.dismiss(None)

    def action_submit(self) -> None:
        if self._busy:
            return
        raw = self.query_one("#path", Input).value.strip()
        if not raw:
            self._set_error("path required")
            return
        out = Path(raw).expanduser()
        if out.exists():
            self._set_error("file exists; choose a different name")
            return
        self._set_error("")
        self._set_status("Exporting…")
        self._busy = True
        self._run_export(out)

    @work(thread=True, exclusive=True)
    def _run_export(self, out: Path) -> None:
        try:
            n = export_filtered_csv(
                self._case_path,
                self._state,
                out,
                progress=lambda n: self.post_message(self._Progress(n)),
            )
        except Exception as exc:
            self.post_message(self._Failed(str(exc)))
            return
        self.post_message(self._Done(out, n))

    def on_export_filtered_csv_screen__progress(
        self, message: _Progress
    ) -> None:
        self._set_status(f"Exporting… {message.n:,} rows")

    def on_export_filtered_csv_screen__done(self, message: _Done) -> None:
        self._busy = False
        self.app.notify(
            f"Exported {message.n:,} events to {message.out_path}",
            severity="information",
        )
        self.dismiss(message.out_path)

    def on_export_filtered_csv_screen__failed(
        self, message: _Failed
    ) -> None:
        self._busy = False
        self._set_status("Enter: export  |  Esc: cancel")
        self._set_error(message.message)

    def _set_error(self, msg: str) -> None:
        self.query_one("#err", Static).update(msg)

    def _set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

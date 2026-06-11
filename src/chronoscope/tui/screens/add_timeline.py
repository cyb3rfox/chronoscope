from __future__ import annotations

import sqlite3
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static
from textual.worker import Worker, get_current_worker

from ...ingest.pipeline import IngestReport, UnsupportedSourceError, ingest_file
from ...ingest.plaso_store import PlasoFormatError


_SUPPORTED_SUFFIXES = {".jsonl", ".plaso"}


class AddTimelineScreen(ModalScreen[str | None]):
    """Dismisses with the new timeline name, or ``None`` on cancel."""

    DEFAULT_CSS = """
    AddTimelineScreen { align: center middle; }
    AddTimelineScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 70; height: auto;
    }
    AddTimelineScreen #err { color: $error; }
    AddTimelineScreen #progress { color: $accent; }
    """
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Add"),
    ]

    def __init__(self, case_path: Path) -> None:
        super().__init__()
        self._case_path = Path(case_path)
        self._error = ""
        self._progress_text = ""
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Add timeline")
            yield Input(placeholder="source .jsonl or .plaso path", id="source")
            yield Input(placeholder="name (defaults to filename stem)", id="name")
            yield Static("", id="err")
            yield Static("", id="progress")
            yield Static("Enter: add  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#source", Input).focus()

    def set_inputs(self, *, source: str, name: str = "") -> None:
        self.query_one("#source", Input).value = source
        self.query_one("#name", Input).value = name

    def error_text(self) -> str:
        return self._error

    def progress_text(self) -> str:
        return self._progress_text

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_submit()

    def action_cancel(self) -> None:
        if self._busy:
            return
        self.dismiss(None)

    def action_submit(self) -> None:
        if self._busy:
            return
        raw = self.query_one("#source", Input).value.strip()
        name = self.query_one("#name", Input).value.strip()
        if not raw:
            self._set_error("source path required")
            return
        source = Path(raw).expanduser()
        if source.suffix.lower() not in _SUPPORTED_SUFFIXES:
            self._set_error("only .jsonl and .plaso are supported")
            return
        if not source.exists():
            self._set_error(f"no such file: {source}")
            return
        label = name or source.stem
        self._set_error("")
        self._set_progress("Starting…")
        self._busy = True
        self._set_inputs_disabled(True)
        self._run_ingest(source, label)

    def _run_ingest(self, source: Path, label: str) -> None:
        def task() -> None:
            worker = get_current_worker()

            def on_progress(done: int, total: int | None) -> None:
                if worker.is_cancelled:
                    return
                self.app.call_from_thread(self._update_progress, done, total)

            try:
                report = ingest_file(
                    self._case_path, source, name=label, progress=on_progress
                )
            except UnsupportedSourceError as exc:
                self.app.call_from_thread(self._fail, str(exc))
                return
            except PlasoFormatError as exc:
                self.app.call_from_thread(self._fail, str(exc))
                return
            except sqlite3.DatabaseError as exc:
                self.app.call_from_thread(
                    self._fail, f"could not read plaso file: {exc}"
                )
                return
            except OSError as exc:
                self.app.call_from_thread(self._fail, str(exc))
                return
            self.app.call_from_thread(self._succeed, label, report)

        self.run_worker(task, thread=True, exclusive=True)

    def _update_progress(self, done: int, total: int | None) -> None:
        if total is not None and total > 0:
            self._set_progress(f"Ingesting… {done:,} / {total:,}")
        else:
            self._set_progress(f"Ingesting… {done:,} events")

    def _fail(self, msg: str) -> None:
        self._busy = False
        self._set_inputs_disabled(False)
        self._set_progress("")
        self._set_error(msg)
        self.query_one("#source", Input).focus()

    def _succeed(self, label: str, report: IngestReport) -> None:
        self._busy = False
        if report.already_present:
            self.app.notify(
                "Timeline already present (sha256 match)", severity="warning"
            )
        else:
            self.app.notify(
                f"Added '{label}': {report.inserted} events",
                severity="information",
            )
        self.dismiss(label)

    def _set_error(self, msg: str) -> None:
        self._error = msg
        self.query_one("#err", Static).update(msg)

    def _set_progress(self, msg: str) -> None:
        self._progress_text = msg
        self.query_one("#progress", Static).update(msg)

    def _set_inputs_disabled(self, disabled: bool) -> None:
        self.query_one("#source", Input).disabled = disabled
        self.query_one("#name", Input).disabled = disabled

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Re-enable inputs if the worker dies for an unforeseen reason."""
        if event.state.name == "ERROR" and self._busy:
            self._fail(f"ingest worker failed: {event.worker.error}")

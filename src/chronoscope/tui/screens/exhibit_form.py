from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static, TextArea

from ...core.case import open_case
from ...core.exhibits import Exhibit, add_exhibit, update_exhibit


class ExhibitFormScreen(ModalScreen[bool]):
    """Add or edit one text-evidence exhibit. Dismisses True on save, False on
    cancel. In add mode an optional source-path field imports a file's contents
    into the body; otherwise the pasted TextArea content is used."""

    DEFAULT_CSS = """
    ExhibitFormScreen { align: center middle; }
    ExhibitFormScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 90; height: 80%;
    }
    ExhibitFormScreen #body { height: 1fr; border: solid $accent; }
    ExhibitFormScreen #err { color: $error; }
    """
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "submit", "Save"),
    ]

    def __init__(self, case_path: Path, exhibit: Exhibit | None = None) -> None:
        super().__init__()
        self._case_path = Path(case_path)
        self._exhibit = exhibit
        self._error = ""

    def compose(self) -> ComposeResult:
        editing = self._exhibit is not None
        with Vertical():
            yield Label("Edit exhibit" if editing else "Add exhibit")
            yield Input(
                value=self._exhibit.title if editing else "",
                placeholder="title (e.g. evil.ps1)", id="title",
            )
            yield Input(
                value=self._exhibit.description if editing else "",
                placeholder="description (what it is / why it matters)",
                id="description",
            )
            if not editing:
                yield Input(
                    placeholder="optional: path to a UTF-8 text file to import",
                    id="source",
                )
            yield TextArea(self._exhibit.body if editing else "", id="body")
            yield Static("", id="err")
            yield Static("Ctrl+S: save  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#title", Input).focus()

    def error_text(self) -> str:
        return self._error

    def set_fields(
        self, *, title: str = "", description: str = "",
        source: str = "", body: str = "",
    ) -> None:
        self.query_one("#title", Input).value = title
        self.query_one("#description", Input).value = description
        try:
            self.query_one("#source", Input).value = source
        except Exception:
            pass
        self.query_one("#body", TextArea).text = body

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_submit(self) -> None:
        title = self.query_one("#title", Input).value.strip()
        description = self.query_one("#description", Input).value.strip()
        body = self.query_one("#body", TextArea).text

        if self._exhibit is None:
            try:
                source = self.query_one("#source", Input).value.strip()
            except Exception:
                source = ""
            if source:
                path = Path(source).expanduser()
                if not path.exists():
                    self._set_error(f"no such file: {path}")
                    return
                try:
                    body = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    self._set_error("file is not UTF-8 text")
                    return
                except OSError as exc:
                    self._set_error(str(exc))
                    return
                if not title:
                    title = path.stem

        if not title:
            self._set_error("title required")
            return
        if not body.strip():
            self._set_error("body required (paste text or give a file path)")
            return

        with open_case(self._case_path) as c:
            if self._exhibit is None:
                add_exhibit(c.con, title=title, description=description, body=body)
            else:
                update_exhibit(
                    c.con, self._exhibit.id,
                    title=title, description=description, body=body,
                )
        self.app.notify(f"Saved exhibit '{title}'", severity="information", timeout=2)
        self.dismiss(True)

    def _set_error(self, msg: str) -> None:
        self._error = msg
        self.query_one("#err", Static).update(msg)

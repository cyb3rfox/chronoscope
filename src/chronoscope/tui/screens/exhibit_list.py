from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from ...core.case import open_case
from ...core.exhibits import get_exhibit, list_exhibits
from .exhibit_form import ExhibitFormScreen


class ExhibitListScreen(ModalScreen[None]):
    """List the case's exhibits. Selecting one opens it in the edit form."""

    DEFAULT_CSS = """
    ExhibitListScreen { align: center middle; }
    ExhibitListScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 80; height: auto; max-height: 80%;
    }
    """
    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, case_path: Path) -> None:
        super().__init__()
        self._case_path = Path(case_path)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Exhibits")
            with open_case(self._case_path) as c:
                exhibits = list_exhibits(c.con)
            if not exhibits:
                yield Static("(no exhibits — add one from the Case menu)")
            else:
                opts = [
                    Option(self._format(e.title, e.description, len(e.body)), id=str(e.id))
                    for e in exhibits
                ]
                yield OptionList(*opts, id="list")
            yield Static("Enter: edit  |  Esc: close")

    @staticmethod
    def _format(title: str, description: str, n: int) -> str:
        first = (description or "").splitlines()[0] if description else ""
        suffix = f"  —  {escape(first)}" if first else ""
        return f"{escape(title)}{suffix}  ({n} chars)"

    def on_mount(self) -> None:
        try:
            self.query_one("#list", OptionList).focus()
        except Exception:
            pass

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        if event.option.id is not None:
            self._open(int(event.option.id))

    def open_selected(self, index: int) -> None:
        """Test/help hook: open the exhibit at list index ``index`` for editing."""
        lst = self.query_one("#list", OptionList)
        oid = lst.get_option_at_index(index).id
        if oid is not None:
            self._open(int(oid))

    def _open(self, exhibit_id: int) -> None:
        with open_case(self._case_path) as c:
            exhibit = get_exhibit(c.con, exhibit_id)
        if exhibit is None:
            return
        self.app.push_screen(
            ExhibitFormScreen(self._case_path, exhibit),
            callback=lambda _saved: self._refresh(),
        )

    def _refresh(self) -> None:
        """Re-render after an edit by replacing this screen with a fresh one."""
        self.dismiss(None)
        self.app.push_screen(ExhibitListScreen(self._case_path))

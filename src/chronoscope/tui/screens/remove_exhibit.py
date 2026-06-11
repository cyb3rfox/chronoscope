from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from ...core.case import open_case
from ...core.exhibits import get_exhibit, list_exhibits, remove_exhibit
from .confirm import ConfirmScreen


class RemoveExhibitScreen(ModalScreen[bool]):
    """Dismisses True if an exhibit was removed, else False."""

    DEFAULT_CSS = """
    RemoveExhibitScreen { align: center middle; }
    RemoveExhibitScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 70; height: auto;
    }
    """
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm_and_remove", "Remove"),
    ]

    def __init__(self, case_path: Path) -> None:
        super().__init__()
        self._case_path = Path(case_path)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Remove exhibit")
            with open_case(self._case_path) as c:
                options = [
                    Option(f"{escape(e.title)}  ({len(e.body)} chars)", id=str(e.id))
                    for e in list_exhibits(c.con)
                ]
            if not options:
                yield Static("(no exhibits)")
            else:
                yield OptionList(*options, id="list")
            yield Static("Enter: remove  |  Esc: cancel")

    def on_mount(self) -> None:
        try:
            self.query_one("#list", OptionList).focus()
        except Exception:
            pass

    def select_by_id(self, exhibit_id: int) -> None:
        lst = self.query_one("#list", OptionList)
        for i in range(lst.option_count):
            if lst.get_option_at_index(i).id == str(exhibit_id):
                lst.highlighted = i
                return

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        self.action_confirm_and_remove()

    def action_confirm_and_remove(self) -> None:
        try:
            lst = self.query_one("#list", OptionList)
        except Exception:
            self.dismiss(False)
            return
        if lst.highlighted is None:
            return
        oid = lst.get_option_at_index(lst.highlighted).id
        if oid is None:
            return
        exhibit_id = int(oid)
        with open_case(self._case_path) as c:
            exhibit = get_exhibit(c.con, exhibit_id)
        title = exhibit.title if exhibit is not None else str(exhibit_id)
        self.app.push_screen(
            ConfirmScreen(f"Remove exhibit '{escape(title)}'?"),
            callback=lambda ok, eid=exhibit_id: self._maybe_remove(eid, ok),
        )

    def _maybe_remove(self, exhibit_id: int, ok: bool) -> None:
        if not ok:
            self.dismiss(False)
            return
        with open_case(self._case_path) as c:
            remove_exhibit(c.con, exhibit_id)
        self.app.notify("Exhibit removed", severity="information", timeout=2)
        self.dismiss(True)

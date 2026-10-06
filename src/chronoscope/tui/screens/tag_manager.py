from __future__ import annotations

import sqlite3

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from ...annotations import store
from .confirm import ConfirmScreen
from .tag_picker import TagPickerScreen


class TagManagerScreen(ModalScreen["tuple[str,str] | None"]):
    DEFAULT_CSS = """
    TagManagerScreen { align: center middle; }
    TagManagerScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 72; height: 80%;
    }
    TagManagerScreen OptionList { height: 1fr; }
    """

    BINDINGS = [
        ("escape", "cancel", "Close"),
        Binding("enter", "filter", "Filter to tag", priority=True),
        ("r", "rename", "Rename"),
        ("D", "delete", "Delete"),
    ]

    def __init__(self, con: sqlite3.Connection) -> None:
        super().__init__()
        self._con = con

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Tags")
            yield OptionList(*self._build_options())
            yield Static("Enter: filter  |  r: rename  |  D: delete  |  Esc: close")

    def _build_options(self) -> list[Option]:
        return [
            Option(f"{escape(t)}  ({n})", id=t)
            for t, n in store.all_tags_with_counts(self._con)
        ]

    def _refresh(self) -> None:
        lst = self.query_one(OptionList)
        saved = lst.highlighted
        lst.clear_options()
        lst.add_options(self._build_options())
        if saved is not None and saved < lst.option_count:
            lst.highlighted = saved

    def _current_tag(self) -> str | None:
        lst = self.query_one(OptionList)
        if lst.highlighted is None:
            return None
        opt = lst.get_option_at_index(lst.highlighted)
        return opt.id if opt is not None else None

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_filter(self) -> None:
        tag = self._current_tag()
        if tag is None:
            return
        self.dismiss(("filter", tag))

    def action_rename(self) -> None:
        old = self._current_tag()
        if old is None:
            return
        case_tags = store.all_tags_with_counts(self._con)
        self.app.push_screen(
            TagPickerScreen("add", set(), case_tags),
            callback=lambda new, old=old: self._do_rename(old, new),
        )

    def _do_rename(self, old: str, new: str | None) -> None:
        if new is None or new == old:
            return
        store.rename_tag(self._con, old, new)
        self._refresh()

    def action_delete(self) -> None:
        tag = self._current_tag()
        if tag is None:
            return
        self.app.push_screen(
            ConfirmScreen(f"Delete tag '{tag}' from all events?"),
            callback=lambda ok, tag=tag: self._do_delete(tag, ok),
        )

    def _do_delete(self, tag: str, ok: bool) -> None:
        if not ok:
            return
        store.delete_tag(self._con, tag)
        self._refresh()

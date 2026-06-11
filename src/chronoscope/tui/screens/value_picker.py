from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...query.state import CategoricalFilter
from ..widgets.tri_state import State, TriStateItem, TriStateOptionList


class ValuePickerScreen(ModalScreen["CategoricalFilter | None"]):
    DEFAULT_CSS = """
    ValuePickerScreen {
        align: center middle;
    }
    ValuePickerScreen > Vertical {
        background: $panel;
        border: solid $primary;
        padding: 1 2;
        width: 80;
        height: 80%;
    }
    ValuePickerScreen TriStateOptionList {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+c", "cancel", "Cancel"),
        Binding("enter", "commit", "Apply", priority=True),
        ("r", "reset", "Reset"),
    ]

    def __init__(
        self,
        column: str,
        counts: list[tuple[str, int]],
        initial: CategoricalFilter,
    ) -> None:
        super().__init__()
        self._column = column
        self._counts = counts
        self._initial = initial

    def compose(self) -> ComposeResult:
        items = [
            TriStateItem(
                value=value,
                count=count,
                state=(
                    State.INCLUDE if value in self._initial.include
                    else State.EXCLUDE if value in self._initial.exclude
                    else State.NONE
                ),
            )
            for value, count in self._counts
        ]
        with Vertical():
            yield Label(f"Filter: {self._column}")
            yield Input(placeholder="search…", id="needle")
            yield TriStateOptionList(items)
            yield Static(
                "Space: cycle  |  +: include  |  -: exclude  |  "
                "Enter: apply  |  Esc: cancel  |  r: reset"
            )

    def on_mount(self) -> None:
        self.query_one(TriStateOptionList).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.query_one(TriStateOptionList).set_filter(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_commit(self) -> None:
        include, exclude = self.query_one(TriStateOptionList).snapshot
        self.dismiss(CategoricalFilter(include=include, exclude=exclude))

    def action_reset(self) -> None:
        lst = self.query_one(TriStateOptionList)
        for item in lst.items:
            item.state = State.NONE
        lst.refresh_rows()

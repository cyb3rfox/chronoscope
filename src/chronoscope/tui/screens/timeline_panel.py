from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from ...core.case import TimelineInfo


class TimelinePanelScreen(ModalScreen["frozenset[str]"]):
    DEFAULT_CSS = """
    TimelinePanelScreen { align: center middle; }
    TimelinePanelScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 64; height: 80%;
    }
    TimelinePanelScreen OptionList { height: 1fr; }
    """

    BINDINGS = [
        ("space", "toggle", "Toggle"),
        ("a", "select_all", "All"),
        ("x", "select_none", "None"),
        Binding("enter", "commit", "Apply", priority=True),
        ("escape", "commit", "Apply & close"),
        ("q", "commit", "Apply & close"),
    ]

    def __init__(
        self,
        timelines: list[TimelineInfo],
        initial: frozenset[str],
    ) -> None:
        super().__init__()
        self._timelines = list(timelines)
        all_ids = {t.id for t in self._timelines}
        if not initial:
            self._draft: set[str] = set(all_ids)
        else:
            self._draft = set(initial) & all_ids

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Timelines")
            if not self._timelines:
                yield Static("(no timelines)")
            else:
                yield OptionList(*self._build_options(), id="timeline-list")
            yield Static(
                "Space: toggle  |  a: all  |  x: none  |  "
                "Enter/Esc: apply & close"
            )

    def _build_options(self) -> list[Option]:
        opts: list[Option] = []
        for t in self._timelines:
            checked = "✓" if t.id in self._draft else " "
            label = Text()
            label.append(f"[{checked}] ")
            label.append("█ ", style=t.color)
            label.append(f"{t.name:<20}  {t.event_count:>10,} events")
            opts.append(Option(label, id=t.id))
        return opts

    def _refresh(self) -> None:
        if not self._timelines:
            return
        lst = self.query_one("#timeline-list", OptionList)
        saved = lst.highlighted
        lst.clear_options()
        lst.add_options(self._build_options())
        if saved is not None and saved < lst.option_count:
            lst.highlighted = saved

    def on_mount(self) -> None:
        if self._timelines:
            self.query_one("#timeline-list", OptionList).focus()

    def action_toggle(self) -> None:
        if not self._timelines:
            return
        lst = self.query_one("#timeline-list", OptionList)
        idx = lst.highlighted
        if idx is None:
            return
        opt = lst.get_option_at_index(idx)
        tid = opt.id if opt is not None else None
        if tid is None:
            return
        if tid in self._draft:
            self._draft.discard(tid)
        else:
            self._draft.add(tid)
        self._refresh()

    def action_select_all(self) -> None:
        self._draft = {t.id for t in self._timelines}
        self._refresh()

    def action_select_none(self) -> None:
        self._draft = set()
        self._refresh()

    def action_commit(self) -> None:
        all_ids = {t.id for t in self._timelines}
        if self._draft == all_ids or not self._draft:
            self.dismiss(frozenset())
        else:
            self.dismiss(frozenset(self._draft))

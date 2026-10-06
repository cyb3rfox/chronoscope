from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rich.markup import escape
from textual.widgets import OptionList
from textual.widgets.option_list import Option


class State(Enum):
    NONE = " "
    INCLUDE = "+"
    EXCLUDE = "−"


@dataclass
class TriStateItem:
    value: str
    count: int
    state: State = State.NONE


class TriStateOptionList(OptionList):
    """OptionList where each row has tri-state (none / include / exclude)."""

    BINDINGS = [
        ("space", "cycle", "Cycle"),
        ("plus", "include", "Include"),
        ("minus", "exclude", "Exclude"),
    ]

    def __init__(self, items: list[TriStateItem]) -> None:
        self.items = list(items)
        self._needle = ""
        super().__init__(*self._render_options())

    def _render_options(self) -> list[Option]:
        opts: list[Option] = []
        for i, it in enumerate(self.items):
            if self._matches(it):
                value_disp = it.value if len(it.value) <= 40 else it.value[:39] + "…"
                label = escape(f"[{it.state.value}] {value_disp:<40} {it.count:>8,}")
                opts.append(Option(label, id=str(i)))
        return opts

    def _matches(self, it: TriStateItem) -> bool:
        if not self._needle:
            return True
        return self._needle.lower() in it.value.lower()

    def refresh_rows(self) -> None:
        saved = self.highlighted
        self.clear_options()
        self.add_options(self._render_options())
        if saved is not None:
            # Clamp to valid range after potential filter changes
            new_count = self.option_count
            if new_count > 0:
                self.highlighted = min(saved, new_count - 1)

    @property
    def visible_count(self) -> int:
        return sum(1 for it in self.items if self._matches(it))

    def set_filter(self, needle: str) -> None:
        self._needle = needle
        self.refresh_rows()

    def _current_item(self) -> TriStateItem | None:
        idx = self.highlighted
        if idx is None:
            return None
        option = self.get_option_at_index(idx)
        try:
            original_index = int(option.id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if 0 <= original_index < len(self.items):
            return self.items[original_index]
        return None

    def action_cycle(self) -> None:
        item = self._current_item()
        if item is None:
            return
        item.state = {
            State.NONE: State.INCLUDE,
            State.INCLUDE: State.EXCLUDE,
            State.EXCLUDE: State.NONE,
        }[item.state]
        self.refresh_rows()

    def action_include(self) -> None:
        item = self._current_item()
        if item is None:
            return
        item.state = State.INCLUDE
        self.refresh_rows()

    def action_exclude(self) -> None:
        item = self._current_item()
        if item is None:
            return
        item.state = State.EXCLUDE
        self.refresh_rows()

    @property
    def snapshot(self) -> tuple[frozenset[str], frozenset[str]]:
        include = {it.value for it in self.items if it.state == State.INCLUDE}
        exclude = {it.value for it in self.items if it.state == State.EXCLUDE}
        return frozenset(include), frozenset(exclude)

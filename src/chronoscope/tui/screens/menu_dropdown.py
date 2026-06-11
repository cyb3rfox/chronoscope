from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList
from textual.widgets.option_list import Option


@dataclass(frozen=True)
class MenuItem:
    label: str
    hotkey: str          # display-only ("M", "alt+t a", ...); empty for none
    callback: Callable[[], None]


class MenuDropdownScreen(ModalScreen[None]):
    DEFAULT_CSS = """
    MenuDropdownScreen { align: left top; }
    MenuDropdownScreen > Vertical {
        background: $panel; border: solid $primary; padding: 0 1;
        height: auto; width: auto;
    }
    MenuDropdownScreen OptionList {
        width: auto; height: auto; border: none; padding: 0;
    }
    """
    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("left",   "siblings_prev", "Prev menu"),
        ("right",  "siblings_next", "Next menu"),
    ]

    def __init__(
        self,
        title: str,
        items: list[MenuItem],
        *,
        anchor_x: int = 0,
        siblings: list[Callable[[], None]] | None = None,
        sibling_index: int = 0,
    ) -> None:
        super().__init__()
        self._title = title
        self._items = items
        self._anchor_x = anchor_x
        self._siblings = siblings or []
        self._sibling_index = sibling_index
        label_w = max((len(i.label) for i in items), default=0)
        has_hotkey = any(i.hotkey for i in items)
        self._label_pad = label_w + (2 if has_hotkey else 0)

    def compose(self) -> ComposeResult:
        with Vertical() as box:
            box.styles.offset = (self._anchor_x, 1)
            yield OptionList(*self._build_options(), id="items")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()
        screen_w = self.app.size.width
        rendered_w = self._dropdown_width()
        max_x = max(0, screen_w - rendered_w)
        if self._anchor_x > max_x:
            self.query_one(Vertical).styles.offset = (max_x, 1)

    def _dropdown_width(self) -> int:
        content = max(
            (len(self._format(i)) for i in self._items),
            default=0,
        )
        return content + 4  # border (2) + padding 0 1 (2)

    def rendered_text(self) -> str:
        return "\n".join(self._format(i) for i in self._items)

    def _build_options(self) -> list[Option]:
        return [Option(self._format(i), id=str(idx)) for idx, i in enumerate(self._items)]

    def _format(self, item: MenuItem) -> str:
        if item.hotkey:
            return f"{escape(item.label):<{self._label_pad}}{escape(item.hotkey)}"
        return escape(item.label)

    def on_click(self, event) -> None:
        if event.widget is self:
            self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = int(event.option.id) if event.option.id is not None else -1
        if 0 <= idx < len(self._items):
            cb = self._items[idx].callback
            self.dismiss(None)
            self.app.call_later(cb)

    def action_siblings_prev(self) -> None:
        self._flip_sibling(-1)

    def action_siblings_next(self) -> None:
        self._flip_sibling(+1)

    def _flip_sibling(self, delta: int) -> None:
        if not self._siblings:
            return
        new_index = (self._sibling_index + delta) % len(self._siblings)
        opener = self._siblings[new_index]
        self.dismiss(None)
        self.app.call_later(opener)

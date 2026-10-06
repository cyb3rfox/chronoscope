from __future__ import annotations

from typing import Callable

from textual.containers import Horizontal
from textual.widgets import Static

LABELS = ["File", "Case", "Timeline", "AI", "Help"]


class MenuLabel(Static):
    """One clickable label in the menubar. Click invokes its opener directly."""

    def __init__(self, label: str, opener: Callable[[], None]) -> None:
        super().__init__(label, classes="menu-label")
        self._opener = opener

    def on_click(self, event) -> None:
        event.stop()
        self._opener()


class Menubar(Horizontal):
    DEFAULT_CSS = """
    Menubar {
        dock: top;
        height: 1;
        background: $accent 20%;
    }
    Menubar > MenuLabel {
        width: auto;
        padding: 0 2;
        content-align: center middle;
    }
    Menubar > MenuLabel:hover { background: $accent 40%; }
    """

    def __init__(self, openers: dict[str, Callable[[], None]]) -> None:
        super().__init__()
        self._openers = openers

    def compose(self):
        for label in LABELS:
            yield MenuLabel(label, self._openers[label])

    def anchor_for(self, label: str) -> int:
        """Column offset where the dropdown for ``label`` should anchor."""
        offset = 0
        for li in LABELS:
            if li == label:
                return offset
            offset += len(li) + 4  # padding: 0 2 → 2 left + 2 right
        return 0

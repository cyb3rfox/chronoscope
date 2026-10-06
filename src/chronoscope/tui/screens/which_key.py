from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.keys import _character_to_key
from textual.screen import ModalScreen, Screen
from textual.widgets import Label, Static

from ..bindings import KeyBinding


def _normalise_key(key: str) -> str:
    """Return the Textual event.key name for a raw key string."""
    if len(key) == 1:
        return _character_to_key(key)
    return key


class WhichKeyScreen(ModalScreen):
    """Popup listing bindings for one prefix; dispatches action on target."""

    DEFAULT_CSS = """
    WhichKeyScreen { align: center middle; }
    WhichKeyScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 60; height: auto;
    }
    """

    def __init__(
        self,
        title: str,
        bindings: list[KeyBinding],
        target_screen: Screen,
    ) -> None:
        super().__init__()
        self._title = title
        self._key_bindings = list(bindings)
        self._target = target_screen

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield Static(self._render_body(), id="whichkey-body", markup=False)
            yield Static("Esc: cancel", id="whichkey-footer")

    def rendered_text(self) -> str:
        return self._render_body()

    def _render_body(self) -> str:
        items = [f"{b.key}  {b.label}" for b in self._key_bindings]
        lines: list[str] = []
        for i in range(0, len(items), 2):
            left = items[i]
            right = items[i + 1] if i + 1 < len(items) else ""
            lines.append(f"  {left:<26}  {right}")
        return "\n".join(lines) if lines else "(no sub-keys registered)"

    async def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "q"):
            self.dismiss()
            event.stop()
            return
        for b in self._key_bindings:
            if event.key == _normalise_key(b.key):
                self.dismiss()
                action = getattr(self._target, f"action_{b.action}", None)
                if action is not None:
                    # Run the action on the target's message pump so that any
                    # push_screen(..., callback=...) inside the action records
                    # the target as the callback requester (not this soon-to-
                    # be-dismissed WhichKeyScreen, which would silently drop
                    # the callback).
                    self._target.call_later(action)
                event.stop()
                return

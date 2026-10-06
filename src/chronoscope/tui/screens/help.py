from __future__ import annotations

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ..bindings import GROUPS, KeyBinding, bindings_in_group


class HelpScreen(ModalScreen):
    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 80; height: 80%;
    }
    HelpScreen VerticalScroll { height: 1fr; }
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def __init__(self, bindings: list[KeyBinding]) -> None:
        super().__init__()
        self._help_bindings = list(bindings)
        self._needle = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Help")
            yield Input(placeholder="filter…", id="help-needle")
            with VerticalScroll():
                yield Static(self._render_body(), id="help-body")
            yield Static("Type to filter  |  Esc / q: close")

    def on_mount(self) -> None:
        self.query_one("#help-needle", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._needle = event.value
        self.query_one("#help-body", Static).update(self._render_body())

    def rendered_text(self) -> str:
        return self._render_body()

    def _matches(self, b: KeyBinding) -> bool:
        if not self._needle:
            return True
        n = self._needle.lower()
        return n in b.key.lower() or n in b.label.lower()

    def _render_body(self) -> str:
        lines: list[str] = []
        for gid, gl in GROUPS:
            in_group = [b for b in bindings_in_group(self._help_bindings, gid) if self._matches(b)]
            if not in_group:
                continue
            lines.append(escape(gl))
            for b in in_group:
                lines.append(f"  {escape(b.key):<12} {escape(b.label)}")
            lines.append("")
        if not lines:
            return "(no matches)"
        return "\n".join(lines)

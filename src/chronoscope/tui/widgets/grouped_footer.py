from __future__ import annotations

from rich.markup import escape
from textual.widgets import Static

from ..bindings import GROUPS, KeyBinding, bindings_in_group, group_label


class GroupedFooter(Static):
    """Two-line footer:

    Line 1: always-visible bindings.
    Line 2: one cycling secondary group, prefixed by its display label.
    """

    DEFAULT_CSS = """
    GroupedFooter {
        height: 2;
        padding: 0 1;
        background: $panel;
    }
    """

    def __init__(self, bindings: list[KeyBinding]) -> None:
        super().__init__("")
        self._bindings = list(bindings)
        self._available_groups = self._compute_available_groups()
        self._sticky_index = 0
        self._current_index = 0
        self._current_group: str | None = (
            self._available_groups[0] if self._available_groups else None
        )

    def on_mount(self) -> None:
        self._refresh()

    def current_group_id(self) -> str:
        return self._current_group or ""

    def saved_sticky_group_id(self) -> str:
        if not self._available_groups:
            return ""
        return self._available_groups[self._sticky_index]

    def cycle_group(self, step: int = 1) -> None:
        if not self._available_groups:
            return
        n = len(self._available_groups)
        self._sticky_index = (self._sticky_index + step) % n
        self._current_index = self._sticky_index
        self._current_group = self._available_groups[self._current_index]
        self._refresh()

    def set_group(self, group_id: str, *, sticky: bool = True) -> None:
        if group_id not in self._available_groups:
            return
        idx = self._available_groups.index(group_id)
        self._current_index = idx
        self._current_group = group_id
        if sticky:
            self._sticky_index = idx
        self._refresh()

    def render_always_line(self) -> str:
        always_bs = bindings_in_group(self._bindings, "always")
        parts = [f"{b.key} {b.label.lower()}" for b in always_bs]
        return "  ".join(parts)

    def render_secondary_line(self) -> str:
        if self._current_group is None:
            return ""
        label = group_label(self._current_group)
        bs = bindings_in_group(self._bindings, self._current_group)
        seen = {b.key for b in bindings_in_group(self._bindings, "always")}
        items = [f"{b.key} {b.label.lower()}" for b in bs if b.key not in seen]
        body = "  ".join(items) if items else "(no extra keys)"
        suffix = "  ▸" if len(self._available_groups) > 1 else ""
        return f"{label}   {body}{suffix}"

    def _refresh(self) -> None:
        line1 = escape(self.render_always_line())
        line2 = escape(self.render_secondary_line())
        self.update(f"{line1}\n{line2}")

    def _compute_available_groups(self) -> list[str]:
        out: list[str] = []
        for gid, _ in GROUPS:
            if gid == "always":
                continue
            if bindings_in_group(self._bindings, gid):
                out.append(gid)
        return out

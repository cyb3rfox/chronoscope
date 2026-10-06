from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from ...annotations.store import tag_normalize


class TagPickerScreen(ModalScreen["str | None"]):
    DEFAULT_CSS = """
    TagPickerScreen { align: center middle; }
    TagPickerScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 60; height: 80%;
    }
    TagPickerScreen OptionList { height: 1fr; }
    TagPickerScreen #error { color: $error; }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        Binding("enter", "submit", "Apply", priority=True),
    ]

    def __init__(
        self,
        mode: str,
        initial_tags: set[str],
        case_tags: list[tuple[str, int]],
    ) -> None:
        super().__init__()
        if mode not in ("add", "remove"):
            raise ValueError(mode)
        self._mode = mode
        self._initial = set(initial_tags)
        self._case_tags = list(case_tags)

    def compose(self) -> ComposeResult:
        title = "Add tag" if self._mode == "add" else "Remove tag"
        with Vertical():
            yield Label(title)
            yield Input(placeholder="tag name…", id="needle")
            yield OptionList(*self._build_options(""), id="suggestions")
            yield Static("", id="error", markup=False)
            yield Static("Enter: apply  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#needle", Input).focus()

    def _candidate_tags(self) -> list[str]:
        if self._mode == "remove":
            return sorted(self._initial)
        return [t for t, _ in self._case_tags]

    def _build_options(self, needle: str) -> list[Option]:
        needle_l = needle.lower()
        matches = [t for t in self._candidate_tags() if needle_l in t.lower()]
        opts: list[Option] = []
        counts = {t: n for t, n in self._case_tags}
        for t in matches:
            label = f"{t}  ({counts.get(t, 0)})"
            opts.append(Option(label, id=t))
        return opts

    def on_input_changed(self, event: Input.Changed) -> None:
        lst = self.query_one("#suggestions", OptionList)
        lst.clear_options()
        lst.add_options(self._build_options(event.value))

    def action_submit(self) -> None:
        needle = self.query_one("#needle", Input).value.strip()
        if not needle:
            lst = self.query_one("#suggestions", OptionList)
            if lst.highlighted is not None:
                opt = lst.get_option_at_index(lst.highlighted)
                if opt is not None and opt.id is not None:
                    self.dismiss(opt.id)
                    return
            self.query_one("#error", Static).update("tag name required")
            return
        try:
            normalized = tag_normalize(needle)
        except ValueError as e:
            self.query_one("#error", Static).update(str(e))
            return
        if self._mode == "remove" and normalized not in self._initial:
            self.query_one("#error", Static).update(
                f"'{normalized}' is not on this event"
            )
            return
        self.dismiss(normalized)

    def action_cancel(self) -> None:
        self.dismiss(None)

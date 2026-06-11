from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option
from textual.worker import Worker, get_current_worker

from ...core.case import list_timelines, open_case
from ...core.timelines import TimelineNotFoundError, remove_timeline
from .confirm import ConfirmScreen


class RemoveTimelineScreen(ModalScreen[str | None]):
    """Dismisses with the removed timeline's name, or ``None`` on cancel."""

    DEFAULT_CSS = """
    RemoveTimelineScreen { align: center middle; }
    RemoveTimelineScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 70; height: auto;
    }
    RemoveTimelineScreen #progress { color: $accent; }
    """
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm_and_remove", "Remove"),
    ]

    def __init__(self, case_path: Path) -> None:
        super().__init__()
        self._case_path = Path(case_path)
        self._progress_text = ""
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Remove timeline")
            with open_case(self._case_path) as c:
                options = [
                    Option(f"{escape(t.name)}    {t.event_count} events", id=t.name)
                    for t in list_timelines(c.con)
                ]
            if not options:
                yield Static("(no timelines)")
            else:
                yield OptionList(*options, id="list")
            yield Static("", id="progress")
            yield Static("Enter: remove  |  Esc: cancel")

    def on_mount(self) -> None:
        try:
            self.query_one("#list", OptionList).focus()
        except Exception:
            pass

    def select_by_name(self, name: str) -> None:
        lst = self.query_one("#list", OptionList)
        for i in range(lst.option_count):
            opt = lst.get_option_at_index(i)
            if opt.id == name:
                lst.highlighted = i
                return

    def action_cancel(self) -> None:
        if self._busy:
            return
        self.dismiss(None)

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Enter/click is consumed by the OptionList, so the ("enter", ...)
        screen binding never fires — drive removal from the selection event."""
        self.action_confirm_and_remove()

    def action_confirm_and_remove(self) -> None:
        if self._busy:
            return
        try:
            lst = self.query_one("#list", OptionList)
        except Exception:
            self.dismiss(None)
            return
        if lst.highlighted is None:
            return
        name = lst.get_option_at_index(lst.highlighted).id
        if name is None:
            return
        self.app.push_screen(
            ConfirmScreen(f"Remove timeline '{name}' and its events?"),
            callback=lambda ok, n=name: self._maybe_remove(n, ok),
        )

    def _maybe_remove(self, name: str, ok: bool) -> None:
        if not ok:
            self.dismiss(None)
            return
        self._busy = True
        self._set_list_disabled(True)
        self._set_progress(f"Removing '{name}'…")
        self._run_remove(name)

    def _run_remove(self, name: str) -> None:
        def task() -> None:
            worker = get_current_worker()

            def on_progress(done: int, total: int | None) -> None:
                if worker.is_cancelled:
                    return
                self.app.call_from_thread(self._update_progress, done, total)

            try:
                remove_timeline(self._case_path, name, progress=on_progress)
            except TimelineNotFoundError:
                self.app.call_from_thread(self._not_found, name)
                return
            self.app.call_from_thread(self._succeed, name)

        self.run_worker(task, thread=True, exclusive=True)

    def _update_progress(self, done: int, total: int | None) -> None:
        if total is not None and total > 0:
            self._set_progress(f"Removing… {done:,} / {total:,}")
        else:
            self._set_progress(f"Removing… {done:,} events")

    def _not_found(self, name: str) -> None:
        self._busy = False
        self.app.notify(f"Timeline '{name}' not found", severity="error")
        self.dismiss(None)

    def _succeed(self, name: str) -> None:
        self._busy = False
        self.app.notify(f"Removed '{name}'", severity="information")
        self.dismiss(name)

    def progress_text(self) -> str:
        return self._progress_text

    def _set_progress(self, msg: str) -> None:
        self._progress_text = msg
        self.query_one("#progress", Static).update(msg)

    def _set_list_disabled(self, disabled: bool) -> None:
        try:
            self.query_one("#list", OptionList).disabled = disabled
        except Exception:
            pass

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Recover if the removal worker dies unexpectedly."""
        if event.state.name == "ERROR" and self._busy:
            self._busy = False
            self.app.notify(
                f"remove worker failed: {event.worker.error}", severity="error"
            )
            self.dismiss(None)

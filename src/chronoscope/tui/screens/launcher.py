from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from ...config import recent
from ..screens.confirm import ConfirmScreen
from ..screens.new_case import NewCaseScreen
from ..screens.open_case import OpenCaseScreen


class LauncherScreen(Screen):
    DEFAULT_CSS = """
    LauncherScreen { align: center middle; }
    LauncherScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 80; height: 80%;
    }
    LauncherScreen OptionList { height: 1fr; }
    """
    BINDINGS = [
        ("n", "new_case", "New case…"),
        ("o", "open_path", "Open by path…"),
        ("q", "quit", "Quit"),
        ("enter", "select", "Open selected"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Chronoscope")
            yield OptionList(*self._build_options(), id="recents")
            yield Static(self._actions_line(), id="actions")

    def on_mount(self) -> None:
        try:
            self.query_one(OptionList).focus()
        except Exception:
            pass

    def on_screen_resume(self) -> None:
        self.refresh(recompose=True)

    def rendered_text(self) -> str:
        entries = recent.load()
        if not entries:
            return "No recent cases — press N to create one, O to open by path."
        return "\n".join(self._format_entry(e) for e in entries)

    def _build_options(self) -> list[Option]:
        entries = recent.load()
        if not entries:
            return [Option("No recent cases — press N to create one, O to open by path.", disabled=True)]
        return [Option(self._format_entry(e), id=e.path) for e in entries]

    def _format_entry(self, e: recent.RecentEntry) -> str:
        missing = "" if Path(e.path, "case.toml").exists() else "(missing) "
        return f"{missing}{escape(e.name)}    {escape(e.path)}    {escape(e.last_opened[:10])}"

    def _actions_line(self) -> str:
        return "[N] New case…    [O] Open by path…    [Q] Quit"

    def action_new_case(self) -> None:
        self.app.push_screen(NewCaseScreen(), callback=self._after_new_or_open)

    def action_open_path(self) -> None:
        self.app.push_screen(OpenCaseScreen(), callback=self._after_new_or_open)

    def action_quit(self) -> None:
        self.app.exit()

    def action_select(self) -> None:
        opt_list = self.query_one(OptionList)
        if opt_list.highlighted is None:
            return
        opt = opt_list.get_option_at_index(opt_list.highlighted)
        self._activate_option(opt)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._activate_option(event.option)

    def _activate_option(self, opt: Option) -> None:
        if opt.id is None:
            return
        path = Path(opt.id)
        if not (path / "case.toml").exists():
            self.app.push_screen(
                ConfirmScreen(f"{path} no longer has case.toml — remove from recents?"),
                callback=lambda ok, p=path: self._maybe_drop(p, ok),
            )
            return
        self._open_path(path)

    def _maybe_drop(self, path: Path, ok: bool) -> None:
        if ok:
            recent.remove(path)
            self.refresh(recompose=True)

    def _after_new_or_open(self, path: Path | None) -> None:
        if path is None:
            return
        self._open_path(path)

    def _open_path(self, path: Path) -> None:
        from .main import MainScreen
        self.app.push_screen(MainScreen(path))

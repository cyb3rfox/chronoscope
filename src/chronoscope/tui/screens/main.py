from __future__ import annotations

import sqlite3
from pathlib import Path

from rich.markup import escape
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Static
from textual.worker import get_current_worker

from collections.abc import Iterable
from dataclasses import replace as _dc_replace
from typing import Callable

from ...ai.agent import ChatAgent
from ...ai.client import OpenAICompatibleClient
from ...ai.history import ChatLog, load_session
from ...ai.settings import (
    AISettings,
    load_ai_settings,
    resolve_api_key,
    save_ai_settings,
)
from ...ai.toolset import build_toolset
from ...annotations import store
from ...annotations.bulk import bulk_star, bulk_tag, bulk_untag
from ...coloring import ColorRules
from ...coloring.config import load_color_rules, save_color_rules
from ...core.case import Case, list_timelines, open_case
from ...core.metadata import CaseMetadata, load_metadata, save_metadata
from ...query.state import QueryState, TimeBracket
from ...ai.jobs.report import gather_report_context
from ..screens.ai_chat import AIChatScreen
from ..screens.filter_loading import FilterLoadingScreen
from ..screens.ai_report import AIReportScreen
from ..screens.ai_settings import AISettingsScreen
from ..screens.color_rules import ColorRulesScreen
from ..screens.column_picker import ColumnPickerScreen
from ..screens.metadata_editor import MetadataEditorScreen
from ..screens.comment_editor import CommentEditorScreen
from ..screens.confirm import ConfirmScreen
from ..screens.jump_picker import JumpPickerScreen
from ..screens.tag_manager import TagManagerScreen
from ..screens.tag_picker import TagPickerScreen
from ..screens.bracket_picker import BracketPickerScreen
from ..screens.overview import OverviewJump, OverviewScreen
from ..screens.timeline_panel import TimelinePanelScreen
from ..screens.which_key import WhichKeyScreen
from ...report.data import build_overview
from ..bindings import KeyBinding, bindings_with_prefix, to_textual
from ..widgets.detail_pane import DetailPane
from ..widgets.event_table import EventTable
from ..widgets.grouped_footer import GroupedFooter
from ..widgets.menubar import LABELS as _MENU_LABELS, Menubar
from .menu_dropdown import MenuDropdownScreen, MenuItem


_MAIN_BINDINGS: list[KeyBinding] = [
    KeyBinding("f",       "open_filters",             "Filter/Sort",            ("always", "filter")),
    KeyBinding("g",       "jump",                     "Jump to timestamp",      ("always", "nav")),
    KeyBinding("d",       "toggle_detail",            "Toggle detail",          ("always", "nav")),
    KeyBinding("w",       "cycle_detail_width",       "Cycle detail width",     ("nav",)),
    KeyBinding("X",       "clear_filters",            "Clear filters",          ("filter",)),
    KeyBinding("s",       "toggle_star",              "Toggle star",            ("annot",)),
    KeyBinding("t",       "add_tag",                  "Add tag",                ("annot",)),
    KeyBinding("u",       "remove_tag",               "Remove tag",             ("annot",)),
    KeyBinding("c",       "add_comment",              "Add comment",            ("annot",)),
    KeyBinding("e",       "edit_latest_comment",      "Edit latest comment",    ("annot",)),
    KeyBinding("D",       "delete_latest_comment",    "Delete latest comment",  ("annot",)),
    KeyBinding("T",       "tag_manager",              "Tag manager",            ("annot",)),
    KeyBinding("V",       "visual_enter",             "Visual mode",            ("annot", "visual")),
    KeyBinding("space",   "visual_toggle_sticky",     "Toggle sticky",          ("visual",)),
    KeyBinding("escape",  "visual_cancel",            "Cancel visual",          ("visual",)),
    KeyBinding("shift+up",       "visual_extend_up",       "Extend selection ↑",      ("always", "visual")),
    KeyBinding("shift+down",     "visual_extend_down",     "Extend selection ↓",      ("always", "visual")),
    KeyBinding("shift+pageup",   "visual_extend_pageup",   "Extend selection ↑ page", ("visual",)),
    KeyBinding("shift+pagedown", "visual_extend_pagedown", "Extend selection ↓ page", ("visual",)),
    KeyBinding("[", "bracket_set_start_from_cursor", "Bracket start ← cursor", ("always", "time")),
    KeyBinding("]", "bracket_set_end_from_cursor",   "Bracket end ← cursor",   ("always", "time")),
    KeyBinding("b", "prefix_bracket",                "Time bracket…",          ("always", "time")),
    KeyBinding("o", "bracket_open_editor",   "Open editor",        ("time",), prefix="bracket"),
    KeyBinding("c", "bracket_clear",         "Clear bracket",      ("time",), prefix="bracket"),
    KeyBinding("{", "bracket_contract",      "Contract ±1m",       ("time",), prefix="bracket"),
    KeyBinding("}", "bracket_expand",        "Expand ±1m",         ("time",), prefix="bracket"),
    KeyBinding("=", "bracket_recenter",      "Recenter on cursor", ("time",), prefix="bracket"),
    KeyBinding("z", "bracket_zoom_cursor",   "Zoom ±50 events",    ("time",), prefix="bracket"),
    KeyBinding("L", "timeline_panel",        "Timelines…",         ("always", "nav")),
    KeyBinding("O", "open_overview",         "Overview…",          ("always", "nav")),
    KeyBinding("C", "open_color_rules",      "Color rules…",       ("always",)),
    KeyBinding("a", "open_ai_chat",          "AI chat…",           ("always",)),
    KeyBinding("A", "open_ai_settings",      "AI settings…",       ("always",)),
    KeyBinding("M", "open_metadata",         "Case metadata…",     ("always",)),
    KeyBinding("R", "open_report",           "Draft report (AI)…", ("always",)),
    KeyBinding("f2",      "cycle_footer_group",       "Cycle footer group",     ("always",)),
    KeyBinding("shift+f2","cycle_footer_group_back",  "Cycle back",             ("always",)),
    KeyBinding("alt+f", "open_menu_file",     "Menu: File",     ("always",)),
    KeyBinding("alt+c", "open_menu_case",     "Menu: Case",     ("always",)),
    KeyBinding("alt+t", "open_menu_timeline", "Menu: Timeline", ("always",)),
    KeyBinding("alt+a", "open_menu_ai",       "Menu: AI",       ("always",)),
    KeyBinding("alt+h", "open_menu_help",     "Menu: Help",     ("always",)),
]


def _APP_BINDINGS_REF() -> list[KeyBinding]:
    """Deferred import to avoid circular import with app.py."""
    from ..app import _APP_BINDINGS
    return _APP_BINDINGS


_DETAIL_WIDTH_PRESETS = (25, 35, 50, 66)
_DETAIL_WIDTH_DEFAULT_INDEX = 0  # 25%

_BRACKET_STEP_USEC = 60 * 1_000_000              # 1 minute
_BRACKET_DEFAULT_SPAN_USEC = 3600 * 1_000_000    # 1 hour
_BRACKET_ZOOM_N = 50
_FILTER_SPINNER_DELAY = 0.15  # seconds before the spinner overlay appears


class MainScreen(Screen):
    DEFAULT_CSS = """
    MainScreen #status { height: 1; padding: 0 1; }
    MainScreen EventTable { width: 1fr; }
    MainScreen DetailPane { width: 25%; }
    """

    BINDINGS = to_textual(_MAIN_BINDINGS)

    def __init__(self, case_path: Path) -> None:
        super().__init__()
        self.case_path = Path(case_path)
        self._case_cm = None
        self._case: Case | None = None
        self._state = QueryState()
        self._total: int = 0
        self._counts_cache: dict[str, list[tuple[str, int]]] = {}
        self._saved_secondary: str | None = None
        self._visual_anchor: int | None = None
        self._visual_sticky: set[int] = set()
        self._detail_width_index: int = _DETAIL_WIDTH_DEFAULT_INDEX
        self._color_rules: ColorRules = ColorRules()
        self._committed_state: QueryState = QueryState()
        self._filter_seq: int = 0
        self._filter_spinner: FilterLoadingScreen | None = None
        self._filter_spinner_timer = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Menubar({
            "File":     self.action_open_menu_file,
            "Case":     self.action_open_menu_case,
            "Timeline": self.action_open_menu_timeline,
            "AI":       self.action_open_menu_ai,
            "Help":     self.action_open_menu_help,
        })
        self._case_cm = open_case(self.case_path)
        self._case = self._case_cm.__enter__()
        with Vertical(id="main"):
            yield Static("no filters", id="status", markup=False)
            with Horizontal(id="body"):
                yield EventTable(self._case.con)
                yield DetailPane(self._case.con)
        yield GroupedFooter(_APP_BINDINGS_REF() + _MAIN_BINDINGS)

    def on_mount(self) -> None:
        assert self._case is not None
        from ...config import recent as _recent
        _recent.touch(self.case_path, self._case.name)
        self.app.title = f"Chronoscope — {self._case.name}"
        self._total = self._case.con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
        self._color_rules = load_color_rules()
        table = self.query_one(EventTable)
        table.set_color_rules(self._color_rules)
        self._refresh_status()
        table.focus()
        self._begin_filter(self._state)  # async initial load

    def _counts_provider(self, column: str) -> list[tuple[str, int]]:
        if column == "__tags__":
            assert self._case is not None
            return [(t, n) for t, n in store.all_tags_with_counts(self._case.con)]
        if column in self._counts_cache:
            return self._counts_cache[column]
        assert self._case is not None
        sql = (
            f"SELECT {column}, COUNT(*) AS n FROM event "
            f"WHERE {column} IS NOT NULL "
            f"GROUP BY {column} ORDER BY n DESC"
        )
        rows = [(str(v), int(n)) for v, n in self._case.con.execute(sql)]
        self._counts_cache[column] = rows
        return rows

    def action_open_filters(self) -> None:
        assert self._case is not None
        total_timelines = self._case.con.execute(
            "SELECT COUNT(*) FROM timeline"
        ).fetchone()[0]
        self.app.push_screen(
            ColumnPickerScreen(
                self._state,
                self._counts_provider,
                timeline_total=int(total_timelines),
                timelines_supplier=lambda: list_timelines(self._case.con),
            ),
            callback=self._apply_state,
        )

    def _apply_state(self, state: QueryState | None) -> None:
        if state is None:
            return
        self._state = state
        self.query_one(EventTable).focus()
        self._begin_filter(state)

    def _begin_filter(self, state: QueryState) -> None:
        self._filter_seq += 1
        seq = self._filter_seq
        table = self.query_one(EventTable)
        db_path = self.case_path / "events.db"
        self._cancel_spinner_timer()
        self._filter_spinner_timer = self.set_timer(
            _FILTER_SPINNER_DELAY, lambda: self._show_filter_spinner(seq)
        )

        def task() -> None:
            worker = get_current_worker()
            con = sqlite3.connect(db_path)
            try:
                data = table.query_window(con, state, 0)
            finally:
                con.close()
            if not worker.is_cancelled:
                self.app.call_from_thread(self._on_filter_loaded, seq, state, data)

        self.run_worker(task, thread=True, exclusive=True, group="filter")

    def _on_filter_loaded(self, seq: int, state: QueryState, data) -> None:
        if seq != self._filter_seq:
            return
        self._cancel_spinner_timer()
        self._dismiss_filter_spinner()
        self.query_one(EventTable).populate(state, data)
        self._committed_state = state
        self._refresh_status()

    def _show_filter_spinner(self, seq: int) -> None:
        if seq != self._filter_seq or self._filter_spinner is not None:
            return
        self._filter_spinner = FilterLoadingScreen()
        self.app.push_screen(
            self._filter_spinner,
            callback=lambda cancelled, s=seq: (
                self._on_filter_cancelled(s) if cancelled else None
            ),
        )

    def _on_filter_cancelled(self, seq: int) -> None:
        self._filter_spinner = None
        if seq != self._filter_seq:
            return
        self._filter_seq += 1
        self._cancel_spinner_timer()
        self.workers.cancel_group(self, "filter")
        self._state = self._committed_state
        self._refresh_status()

    def _dismiss_filter_spinner(self) -> None:
        if self._filter_spinner is not None:
            self._filter_spinner.dismiss(False)
            self._filter_spinner = None

    def _cancel_spinner_timer(self) -> None:
        if self._filter_spinner_timer is not None:
            self._filter_spinner_timer.stop()
            self._filter_spinner_timer = None

    def action_toggle_detail(self) -> None:
        pane = self.query_one(DetailPane)
        pane.display = not pane.display

    def action_cycle_detail_width(self) -> None:
        self._detail_width_index = (self._detail_width_index + 1) % len(_DETAIL_WIDTH_PRESETS)
        percent = _DETAIL_WIDTH_PRESETS[self._detail_width_index]
        self.query_one(DetailPane).set_width_percent(percent)

    def action_clear_filters(self) -> None:
        self._apply_state(self._state.clear_all())

    def action_open_color_rules(self) -> None:
        self.app.push_screen(
            ColorRulesScreen(self._color_rules),
            callback=self._apply_color_rules,
        )

    def action_open_ai_settings(self) -> None:
        self.app.push_screen(
            AISettingsScreen(load_ai_settings()),
            callback=self._apply_ai_settings,
        )

    def _apply_ai_settings(self, settings: AISettings | None) -> None:
        if settings is None:
            return
        save_ai_settings(settings)
        self.app.notify("AI settings saved", severity="information", timeout=2)

    def action_open_ai_chat(self) -> None:
        assert self._case is not None
        settings = load_ai_settings()
        if not settings.enabled:
            self.app.notify(
                "AI is disabled. Press A to configure and enable it.",
                severity="warning",
            )
            return
        api_key = resolve_api_key(settings)
        if not api_key:
            self.app.notify(
                f"${settings.api_key_env} is not set. "
                "Export it before opening the AI chat.",
                severity="warning",
            )
            return
        try:
            client = OpenAICompatibleClient(
                base_url=settings.base_url, api_key=api_key
            )
        except RuntimeError as e:
            self.app.notify(str(e), severity="error")
            return
        log = ChatLog(self.case_path)
        agent = ChatAgent(
            client=client,
            registry=build_toolset(
                self._case,
                settings,
                apply_filters_cb=self._apply_state,
            ),
            settings=settings,
            log=log,
            metadata=load_metadata(self.case_path),
            history=load_session(log),
        )
        self.app.push_screen(
            AIChatScreen(agent, settings),
            callback=lambda _: self._refresh_after_chat(),
        )

    def _refresh_after_chat(self) -> None:
        """The agent may have mutated tags/comments/stars while the chat was
        open. Re-applying state forces the EventTable to re-render the
        annotation gutters so the user sees the updates immediately."""
        self.query_one(EventTable).apply_query(self._state)

    def action_open_report(self) -> None:
        assert self._case is not None
        settings = load_ai_settings()
        if not settings.enabled:
            self.app.notify(
                "AI is disabled. Press A to configure and enable it.",
                severity="warning",
            )
            return
        api_key = resolve_api_key(settings)
        if not api_key:
            self.app.notify(
                f"${settings.api_key_env} is not set. "
                "Export it before drafting a report.",
                severity="warning",
            )
            return
        # Confirm before spending the AI: nothing is sent to the model until
        # the user says yes — the client isn't even built until then.
        self.app.push_screen(
            ConfirmScreen(
                f"Draft an AI report now? This sends your tagged/commented "
                f"events, case metadata, and exhibits to {settings.model}."
            ),
            callback=lambda ok: self._start_report(settings, api_key) if ok else None,
        )

    def _start_report(self, settings: AISettings, api_key: str) -> None:
        assert self._case is not None
        try:
            client = OpenAICompatibleClient(
                base_url=settings.base_url, api_key=api_key
            )
        except RuntimeError as e:
            self.app.notify(str(e), severity="error")
            return
        context = gather_report_context(self._case)
        self.app.push_screen(
            AIReportScreen(
                client=client,
                settings=settings,
                context=context,
                case_path=self.case_path,
            )
        )

    def action_open_metadata(self) -> None:
        self.app.push_screen(
            MetadataEditorScreen(load_metadata(self.case_path)),
            callback=self._apply_metadata,
        )

    def _apply_metadata(self, meta: CaseMetadata | None) -> None:
        if meta is None:
            return
        save_metadata(self.case_path, meta)
        self.app.notify("Case metadata saved", severity="information", timeout=2)

    def _apply_color_rules(self, rules: ColorRules | None) -> None:
        if rules is None:
            return
        self._color_rules = rules
        save_color_rules(rules)
        self.query_one(EventTable).set_color_rules(rules)

    def action_cycle_footer_group(self) -> None:
        self.query_one(GroupedFooter).cycle_group(+1)

    def action_cycle_footer_group_back(self) -> None:
        self.query_one(GroupedFooter).cycle_group(-1)

    # --- top menu bar ---------------------------------------------------

    def _siblings(self) -> list[Callable[[], None]]:
        return [
            self.action_open_menu_file,
            self.action_open_menu_case,
            self.action_open_menu_timeline,
            self.action_open_menu_ai,
            self.action_open_menu_help,
        ]

    def _push_menu(self, label: str, items: list[MenuItem]) -> None:
        bar = self.query_one(Menubar)
        sib_idx = _MENU_LABELS.index(label)
        self.app.push_screen(
            MenuDropdownScreen(
                label,
                items,
                anchor_x=bar.anchor_for(label),
                siblings=self._siblings(),
                sibling_index=sib_idx,
            )
        )

    def action_open_menu_file(self) -> None:
        from .new_case import NewCaseScreen
        from .open_case import OpenCaseScreen
        self._push_menu("File", [
            MenuItem("New case…",   "",   lambda: self.app.push_screen(NewCaseScreen(), callback=self._after_new_or_open)),
            MenuItem("Open case…",  "",   lambda: self.app.push_screen(OpenCaseScreen(), callback=self._after_new_or_open)),
            MenuItem("Close case",  "",   self._close_case),
            MenuItem("Quit",        "",   self.app.exit),
        ])

    def _after_new_or_open(self, path) -> None:
        if path is None:
            return
        self.app.switch_screen(MainScreen(path))

    def _close_case(self) -> None:
        from .launcher import LauncherScreen
        below_main = any(
            isinstance(s, LauncherScreen) for s in self.app.screen_stack[:-1]
        )
        if below_main:
            self.app.pop_screen()
        else:
            self.app.switch_screen(LauncherScreen())

    def action_open_menu_case(self) -> None:
        from .export_annotations import ExportAnnotationsScreen
        from .export_filtered import ExportFilteredCsvScreen
        from .exhibit_form import ExhibitFormScreen
        from .exhibit_list import ExhibitListScreen
        from .remove_exhibit import RemoveExhibitScreen
        self._push_menu("Case", [
            MenuItem("Metadata…",            "M", self.action_open_metadata),
            MenuItem("Color rules…",         "C", self.action_open_color_rules),
            MenuItem("Export annotations…",  "",  lambda: self.app.push_screen(
                ExportAnnotationsScreen(self.case_path)
            )),
            MenuItem("Export filtered to CSV…", "", lambda: self.app.push_screen(
                ExportFilteredCsvScreen(self.case_path, self._state)
            )),
            MenuItem("Add exhibit…",    "", lambda: self.app.push_screen(
                ExhibitFormScreen(self.case_path)
            )),
            MenuItem("List exhibits",   "", lambda: self.app.push_screen(
                ExhibitListScreen(self.case_path)
            )),
            MenuItem("Remove exhibit…", "", lambda: self.app.push_screen(
                RemoveExhibitScreen(self.case_path)
            )),
        ])

    def action_open_menu_timeline(self) -> None:
        from .add_timeline import AddTimelineScreen
        from .remove_timeline import RemoveTimelineScreen
        self._push_menu("Timeline", [
            MenuItem("Add timeline…",   "",  lambda: self.app.push_screen(
                AddTimelineScreen(self.case_path), callback=lambda _: self._reload_after_timeline_change()
            )),
            MenuItem("List timelines",  "L", self.action_timeline_panel),
            MenuItem("Remove timeline…", "", lambda: self.app.push_screen(
                RemoveTimelineScreen(self.case_path), callback=lambda _: self._reload_after_timeline_change()
            )),
        ])

    def _reload_after_timeline_change(self) -> None:
        """After add/remove, refresh the event count + table."""
        if self._case is None:
            return
        self._total = self._case.con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
        self._counts_cache.clear()
        self.query_one(EventTable).apply_query(self._state)
        self._refresh_status()

    def action_open_menu_ai(self) -> None:
        self._push_menu("AI", [
            MenuItem("Chat",          "a", self.action_open_ai_chat),
            MenuItem("Draft report",  "R", self.action_open_report),
            MenuItem("Settings…",     "A", self.action_open_ai_settings),
        ])

    def action_open_menu_help(self) -> None:
        from .about import AboutScreen
        self._push_menu("Help", [
            MenuItem("Keybindings",  "?", self.app.action_help),
            MenuItem("About",        "",  lambda: self.app.push_screen(AboutScreen())),
        ])

    # --- single-event annotation actions -------------------------------

    def _current_hash(self) -> bytes | None:
        return self.query_one(EventTable).current_hash()

    def action_toggle_star(self) -> None:
        assert self._case is not None
        if self._visual_active():
            hashes = self._visual_selected_hashes()
            if not hashes:
                return
            bulk_star(self._case.con, hashes, on=True)
            rows = sorted(self._visual_selected_rows())
            self._visual_cancel()
            self._refresh_rows_gutter(rows)
            return
        h = self._current_hash()
        if h is None:
            return
        store.toggle_star(self._case.con, h)
        self._refresh_current_row_gutter()

    def action_add_tag(self) -> None:
        assert self._case is not None
        if self._visual_active():
            hashes = self._visual_selected_hashes()
            if not hashes:
                return
            case_tags = store.all_tags_with_counts(self._case.con)
            self.app.push_screen(
                TagPickerScreen("add", set(), case_tags),
                callback=lambda tag, hs=hashes: self._apply_bulk_tag(hs, tag),
            )
            return
        h = self._current_hash()
        if h is None:
            return
        current = set(store.tags_for(self._case.con, h))
        case_tags = store.all_tags_with_counts(self._case.con)
        self.app.push_screen(
            TagPickerScreen("add", current, case_tags),
            callback=lambda tag, h=h: self._apply_add_tag(h, tag),
        )

    def _apply_add_tag(self, h: bytes, tag: str | None) -> None:
        if tag is None or self._case is None:
            return
        store.add_tag(self._case.con, h, tag)
        self._refresh_current_row_gutter()

    def _apply_bulk_tag(self, hashes: list[bytes], tag: str | None) -> None:
        if tag is None or self._case is None:
            return
        rows = sorted(self._visual_selected_rows()) if self._visual_active() else []
        bulk_tag(self._case.con, hashes, tag)
        self._visual_cancel()
        if rows:
            self._refresh_rows_gutter(rows)
        else:
            self._refresh_current_row_gutter()

    def action_remove_tag(self) -> None:
        assert self._case is not None
        if self._visual_active():
            case_tags = store.all_tags_with_counts(self._case.con)
            hashes = self._visual_selected_hashes()
            if not hashes:
                return
            self.app.push_screen(
                TagPickerScreen("add", set(), case_tags),
                callback=lambda tag, hs=hashes: self._apply_bulk_untag(hs, tag),
            )
            return
        h = self._current_hash()
        if h is None:
            return
        current = set(store.tags_for(self._case.con, h))
        if not current:
            self.app.notify("No tags on this event", severity="warning")
            return
        case_tags = store.all_tags_with_counts(self._case.con)
        self.app.push_screen(
            TagPickerScreen("remove", current, case_tags),
            callback=lambda tag, h=h: self._apply_remove_tag(h, tag),
        )

    def _apply_remove_tag(self, h: bytes, tag: str | None) -> None:
        if tag is None or self._case is None:
            return
        store.remove_tag(self._case.con, h, tag)
        self._refresh_current_row_gutter()

    def _apply_bulk_untag(self, hashes: list[bytes], tag: str | None) -> None:
        if tag is None or self._case is None:
            return
        rows = sorted(self._visual_selected_rows()) if self._visual_active() else []
        bulk_untag(self._case.con, hashes, tag)
        self._visual_cancel()
        if rows:
            self._refresh_rows_gutter(rows)
        else:
            self._refresh_current_row_gutter()

    def action_add_comment(self) -> None:
        assert self._case is not None
        h = self._current_hash()
        if h is None:
            return
        self.app.push_screen(
            CommentEditorScreen("New comment", ""),
            callback=lambda body, h=h: self._apply_add_comment(h, body),
        )

    def _apply_add_comment(self, h: bytes, body: str | None) -> None:
        if body is None or self._case is None:
            return
        store.add_comment(self._case.con, h, body)
        self._refresh_current_row_gutter()

    def action_edit_latest_comment(self) -> None:
        assert self._case is not None
        h = self._current_hash()
        if h is None:
            return
        cid = store.latest_comment_id(self._case.con, h)
        if cid is None:
            self.app.notify("No comments on this event", severity="warning")
            return
        body = next(
            c["body"] for c in store.comments_for(self._case.con, h) if c["id"] == cid
        )
        self.app.push_screen(
            CommentEditorScreen("Edit comment", body),
            callback=lambda new_body, cid=cid: self._apply_edit_comment(cid, new_body),
        )

    def _apply_edit_comment(self, cid: int, body: str | None) -> None:
        if body is None or self._case is None:
            return
        store.update_comment(self._case.con, cid, body)
        self._refresh_current_row_gutter()

    def action_delete_latest_comment(self) -> None:
        assert self._case is not None
        h = self._current_hash()
        if h is None:
            return
        cid = store.latest_comment_id(self._case.con, h)
        if cid is None:
            self.app.notify("No comments on this event", severity="warning")
            return
        self.app.push_screen(
            ConfirmScreen("Delete the most recent comment on this event?"),
            callback=lambda ok, cid=cid: self._apply_delete_comment(cid, ok),
        )

    def _apply_delete_comment(self, cid: int, ok: bool) -> None:
        if not ok or self._case is None:
            return
        store.delete_comment(self._case.con, cid)
        self._refresh_current_row_gutter()

    def action_tag_manager(self) -> None:
        assert self._case is not None
        self.app.push_screen(
            TagManagerScreen(self._case.con),
            callback=self._apply_tag_manager_result,
        )

    def _apply_tag_manager_result(self, result) -> None:
        if result is None:
            return
        kind, tag = result
        if kind == "filter":
            self._apply_state(self._state.set_tag_filter(include={tag}, exclude=set()))

    def action_visual_enter(self) -> None:
        if not self._ensure_visual():
            return
        self.app.notify(
            "Visual mode: arrows extend, Space marks sticky, s/t/u apply, Esc cancels",
            severity="information",
            timeout=5,
        )

    def _ensure_visual(self) -> bool:
        if self._visual_active():
            return True
        table = self.query_one(EventTable)
        if table.cursor_row is None:
            return False
        self._visual_anchor = int(table.cursor_row)
        self._visual_sticky = set()
        footer = self.query_one(GroupedFooter)
        self._saved_secondary = footer.current_group_id()
        footer.set_group("visual", sticky=False)
        self._sync_visual_selection()
        return True

    def _sync_visual_selection(self) -> None:
        table = self.query_one(EventTable)
        if self._visual_active():
            table.set_selection(self._visual_selected_rows())
        else:
            table.clear_selection()

    def action_visual_extend_up(self) -> None:
        if not self._ensure_visual():
            return
        self.query_one(EventTable).action_cursor_up()
        self._sync_visual_selection()

    def action_visual_extend_down(self) -> None:
        if not self._ensure_visual():
            return
        self.query_one(EventTable).action_cursor_down()
        self._sync_visual_selection()

    def action_visual_extend_pageup(self) -> None:
        if not self._ensure_visual():
            return
        self.query_one(EventTable).action_page_up()
        self._sync_visual_selection()

    def action_visual_extend_pagedown(self) -> None:
        if not self._ensure_visual():
            return
        self.query_one(EventTable).action_page_down()
        self._sync_visual_selection()

    def _refresh_current_row_gutter(self) -> None:
        table = self.query_one(EventTable)
        if table.cursor_row is None:
            return
        table.refresh_annotation_row(int(table.cursor_row))
        row_key = table.cursor_row
        if row_key is not None and row_key < len(table._id_list):
            self.query_one(DetailPane).show_event(table._id_list[int(row_key)])

    def _visual_active(self) -> bool:
        return self._visual_anchor is not None

    def _visual_selected_rows(self) -> set[int]:
        if self._visual_anchor is None:
            return set()
        table = self.query_one(EventTable)
        cur = int(table.cursor_row) if table.cursor_row is not None else self._visual_anchor
        lo = min(self._visual_anchor, cur)
        hi = max(self._visual_anchor, cur)
        return set(range(lo, hi + 1)) | self._visual_sticky

    def _visual_cancel(self) -> None:
        self._visual_anchor = None
        self._visual_sticky = set()
        if self._saved_secondary:
            try:
                self.query_one(GroupedFooter).set_group(self._saved_secondary, sticky=True)
            except Exception:
                pass
            self._saved_secondary = None
        try:
            self.query_one(EventTable).clear_selection()
        except Exception:
            pass

    def _visual_selected_hashes(self) -> list[bytes]:
        table = self.query_one(EventTable)
        rows = sorted(self._visual_selected_rows())
        return [table._hash_list[r] for r in rows if 0 <= r < len(table._hash_list)]

    def _refresh_rows_gutter(self, rows: Iterable[int]) -> None:
        table = self.query_one(EventTable)
        for r in rows:
            table.refresh_annotation_row(r)

    def action_visual_toggle_sticky(self) -> None:
        if not self._visual_active():
            return
        table = self.query_one(EventTable)
        row = table.cursor_row
        if row is None:
            return
        if int(row) in self._visual_sticky:
            self._visual_sticky.discard(int(row))
        else:
            self._visual_sticky.add(int(row))
        self._sync_visual_selection()

    def action_visual_cancel(self) -> None:
        if not self._visual_active():
            return
        self._visual_cancel()
        self.app.notify("Visual mode cancelled", severity="information", timeout=2)

    # --- time bracket actions -------------------------------------------

    def action_prefix_bracket(self) -> None:
        subs = bindings_with_prefix(_MAIN_BINDINGS, "bracket")
        self.app.push_screen(WhichKeyScreen("bracket", subs, self))

    def action_bracket_set_start_from_cursor(self) -> None:
        ts = self.query_one(EventTable).cursor_ts_usec()
        if ts is None:
            self.app.notify("No event under cursor", severity="warning")
            return
        self._apply_state(self._state.set_bracket_start(ts))

    def action_bracket_set_end_from_cursor(self) -> None:
        ts = self.query_one(EventTable).cursor_ts_usec()
        if ts is None:
            self.app.notify("No event under cursor", severity="warning")
            return
        self._apply_state(self._state.set_bracket_end(ts))

    def action_bracket_clear(self) -> None:
        self._apply_state(self._state.clear_bracket())

    def action_bracket_open_editor(self) -> None:
        anchor = (
            self.query_one(EventTable).cursor_ts_usec()
            or self._earliest_ts()
            or 0
        )
        self.app.push_screen(
            BracketPickerScreen(self._state.bracket, anchor),
            callback=self._apply_bracket_from_editor,
        )

    def _apply_bracket_from_editor(self, bracket: TimeBracket | None) -> None:
        if bracket is None:
            return
        self._apply_state(
            self._state.set_bracket(bracket.start_usec, bracket.end_usec)
        )

    def action_bracket_contract(self) -> None:
        self._apply_state(self._bracket_step(+_BRACKET_STEP_USEC))

    def action_bracket_expand(self) -> None:
        self._apply_state(self._bracket_step(-_BRACKET_STEP_USEC))

    def _bracket_step(self, delta: int):
        b = self._state.bracket
        new_start = b.start_usec + delta if b.start_usec is not None else None
        new_end = b.end_usec - delta if b.end_usec is not None else None
        if (new_start is not None and new_end is not None
                and new_start > new_end):
            mid = (new_start + new_end) // 2
            new_start = new_end = mid
        return self._state.set_bracket(new_start, new_end)

    def action_bracket_recenter(self) -> None:
        table = self.query_one(EventTable)
        cursor_ts = table.cursor_ts_usec()
        if cursor_ts is None:
            self.app.notify("No event under cursor", severity="warning")
            return
        span = self._state.bracket.span_usec() or _BRACKET_DEFAULT_SPAN_USEC
        half = span // 2
        self._apply_state(
            self._state.set_bracket(cursor_ts - half, cursor_ts + half)
        )

    def action_bracket_zoom_cursor(self) -> None:
        table = self.query_one(EventTable)
        cursor_ts = table.cursor_ts_usec()
        if cursor_ts is None:
            self.app.notify("No event under cursor", severity="warning")
            return
        span = self._events_window_around(cursor_ts, n=_BRACKET_ZOOM_N)
        if span is None:
            return
        start, end = span
        self._apply_state(self._state.set_bracket(start, end))

    def action_timeline_panel(self) -> None:
        assert self._case is not None
        timelines = list_timelines(self._case.con)
        self.app.push_screen(
            TimelinePanelScreen(timelines, self._state.timeline_filter),
            callback=self._apply_timeline_filter,
        )

    def action_open_overview(self) -> None:
        assert self._case is not None
        data = build_overview(self._case.con, self._state)
        self.app.push_screen(
            OverviewScreen(self._state, data, con=self._case.con),
            callback=self._apply_overview_result,
        )

    def _apply_overview_result(
        self, result: QueryState | OverviewJump | None
    ) -> None:
        if result is None:
            return
        if isinstance(result, OverviewJump):
            self.query_one(EventTable).jump_to_event(result.event_id)
            return
        assert isinstance(result, QueryState)
        self._apply_state(result)

    def _apply_timeline_filter(self, draft: frozenset[str] | None) -> None:
        if draft is None:
            return
        self._apply_state(self._state.set_timeline_filter(draft))

    def _events_window_around(
        self, cursor_ts: int, *, n: int
    ) -> tuple[int, int] | None:
        assert self._case is not None
        from ...query.builder import build_sql
        state_no_bracket = _dc_replace(self._state, bracket=TimeBracket())
        where, params, _ = build_sql(state_no_bracket)
        base = "FROM event" + (f" WHERE {where}" if where else "")
        rank = int(
            self._case.con.execute(
                f"SELECT COUNT(*) {base}"
                + (" AND " if where else " WHERE ")
                + "ts_usec < ?",
                params + (cursor_ts,),
            ).fetchone()[0]
        )
        total = int(
            self._case.con.execute(
                f"SELECT COUNT(*) {base}", params
            ).fetchone()[0]
        )
        if total == 0:
            return None
        lo = max(0, rank - n)
        hi = min(total - 1, rank + n)
        fetch_sql = f"SELECT ts_usec {base} ORDER BY ts_usec ASC LIMIT 1 OFFSET ?"
        start = int(self._case.con.execute(fetch_sql, params + (lo,)).fetchone()[0])
        end = int(self._case.con.execute(fetch_sql, params + (hi,)).fetchone()[0])
        return start, end

    def action_jump(self) -> None:
        table = self.query_one(EventTable)
        if self._state.sort.column != "ts_usec":
            self.app.notify("Jump requires sort by datetime", severity="warning")
            return
        anchor = table.cursor_ts_usec() or self._earliest_ts()
        self.app.push_screen(JumpPickerScreen(anchor), callback=self._perform_jump)

    def _earliest_ts(self) -> int:
        assert self._case is not None
        row = self._case.con.execute(
            "SELECT MIN(ts_usec) FROM event"
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _perform_jump(self, target: int | None) -> None:
        if target is None:
            return
        table = self.query_one(EventTable)
        rng = table.data_ts_range()
        if not table.jump_to_ts(target):
            self.app.notify("Jump requires sort by datetime", severity="warning")
            return
        if rng is not None and (target < rng[0] or target > rng[1]):
            from datetime import datetime, timezone
            def _fmt(usec: int) -> str:
                return datetime.fromtimestamp(usec / 1_000_000, tz=timezone.utc).isoformat(
                    timespec="minutes"
                )
            where = "earliest" if target < rng[0] else "latest"
            self.app.notify(
                f"Target {_fmt(target)} outside data range "
                f"({_fmt(rng[0])} to {_fmt(rng[1])}); cursor at {where}.",
                severity="warning",
                timeout=8,
            )

    def _refresh_status(self) -> None:
        summary = escape(self._state.summary())
        table = self.query_one(EventTable)
        filtered = table.filtered_count()
        shown = table.row_count
        offset = table.window_offset
        sort = self._state.sort
        arrow = "↑" if sort.direction == "ASC" else "↓"
        counts = f"{filtered:,} / {self._total:,}"
        if shown < filtered:
            counts += f"  showing {offset + 1:,}-{offset + shown:,}"
        segments = []
        bracket_txt = self._format_bracket()
        if bracket_txt:
            segments.append(bracket_txt)
        segments.append(f"filters: {summary}")
        segments.append(f"sort: {sort.column} {arrow}")
        segments.append(counts)
        text = "  |  ".join(segments)
        self.query_one("#status", Static).update(text)

    def _format_bracket(self) -> str:
        b = self._state.bracket
        if b.is_empty():
            return ""
        def _fmt(u: int | None) -> str:
            if u is None:
                return "…"
            from datetime import datetime, timezone
            return datetime.fromtimestamp(
                u / 1_000_000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M")
        span = b.span_usec()
        span_txt = ""
        if span is not None:
            secs = span // 1_000_000
            if secs < 3600:
                span_txt = f" ({secs // 60}m)"
            elif secs < 86400:
                span_txt = f" ({secs // 3600}h)"
            else:
                span_txt = f" ({secs // 86400}d)"
        return f"⧗ bracket: {_fmt(b.start_usec)} → {_fmt(b.end_usec)}{span_txt}"

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._visual_active():
            self._sync_visual_selection()
        if event.row_key is None or event.row_key.value is None:
            return
        self.query_one(DetailPane).show_event(int(event.row_key.value))

    def on_unmount(self) -> None:
        if self._case_cm is not None:
            self._case_cm.__exit__(None, None, None)
            self._case_cm = None
            self._case = None

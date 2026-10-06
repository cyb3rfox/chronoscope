from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable

DATA = Path(__file__).parent / "data" / "sample.jsonl"

FIRST = 1552410000_000_000
LAST  = 1552411140_000_000


@pytest.mark.asyncio
async def test_bracket_start_from_cursor(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        table.move_cursor(row=5)
        await pilot.pause()
        cursor_ts = table.cursor_ts_usec()
        await pilot.press("[")
        await pilot.pause()
        screen = pilot.app.screen
        assert screen._state.bracket.start_usec == cursor_ts
        assert table.filtered_count() == 20 - 5


@pytest.mark.asyncio
async def test_bracket_end_from_cursor(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        table.move_cursor(row=5)
        await pilot.pause()
        await pilot.press("]")
        await pilot.pause()
        assert table.filtered_count() == 6  # rows 0..5 inclusive


@pytest.mark.asyncio
async def test_b_opens_whichkey(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("b")
        await pilot.pause()
        from chronoscope.tui.screens.which_key import WhichKeyScreen
        assert isinstance(pilot.app.screen, WhichKeyScreen)


@pytest.mark.asyncio
async def test_bracket_clear_via_b_c(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        screen._apply_state(screen._state.set_bracket(FIRST, FIRST))
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table.filtered_count() == 1
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        assert table.filtered_count() == 20


@pytest.mark.asyncio
async def test_bracket_open_editor_via_b_o(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        from chronoscope.tui.screens.bracket_picker import BracketPickerScreen
        assert isinstance(pilot.app.screen, BracketPickerScreen)


@pytest.mark.asyncio
async def test_status_bar_shows_bracket_indicator(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        screen._apply_state(screen._state.set_bracket(FIRST, LAST))
        await pilot.pause()
        from textual.widgets import Static
        status = pilot.app.screen.query_one("#status", Static)
        assert "⧗" in str(status.content)


@pytest.mark.asyncio
async def test_bracket_recenter_via_b_equals(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        table.move_cursor(row=10)
        await pilot.pause()
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("=")
        await pilot.pause()
        b = screen._state.bracket
        assert b.start_usec is not None and b.end_usec is not None
        mid = (b.start_usec + b.end_usec) // 2
        assert abs(mid - table._ts_list[10]) <= 1


@pytest.mark.asyncio
async def test_b_o_editor_submit_applies_bracket(case_dir):
    """Regression: submitting BracketPickerScreen from the b-leader should
    invoke MainScreen's _apply_bracket_from_editor callback and mutate state.
    Previously the callback requester was the dismissed WhichKeyScreen so the
    callback silently dropped."""
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        assert screen._state.bracket.start_usec is None
        assert screen._state.bracket.end_usec is None

        await pilot.press("b")
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        from chronoscope.tui.screens.bracket_picker import BracketPickerScreen
        assert isinstance(pilot.app.screen, BracketPickerScreen)

        from textual.widgets import Input
        pilot.app.screen.query_one("#from", Input).value = "2019-03-12 17:05"
        pilot.app.screen.query_one("#to",   Input).value = "2019-03-12 17:10"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Find MainScreen in the stack; check the bracket actually applied.
        from chronoscope.tui.screens.main import MainScreen
        main = next(s for s in pilot.app.screen_stack if isinstance(s, MainScreen))
        assert main._state.bracket.start_usec == 1552410300_000_000
        assert main._state.bracket.end_usec   == 1552410600_000_000

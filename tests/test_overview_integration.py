from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.mark.asyncio
async def test_O_opens_overview_screen(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("O")
        await pilot.pause()
        from chronoscope.tui.screens.overview import OverviewScreen
        assert isinstance(pilot.app.screen, OverviewScreen)


@pytest.mark.asyncio
async def test_O_enter_on_bucket_applies_bracket(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        before = table.filtered_count()
        assert before == 20
        await pilot.press("O")
        await pilot.pause()
        # The overview picks a cursor at the max-tagged bucket; with no tags
        # it falls back to the middle bucket.
        await pilot.press("enter")
        await pilot.pause()
        # Back on main; bracket applied so filtered count dropped.
        from chronoscope.tui.screens.main import MainScreen
        main = next(s for s in pilot.app.screen_stack if isinstance(s, MainScreen))
        assert main._state.bracket.start_usec is not None


@pytest.mark.asyncio
async def test_O_jump_to_starred_event_moves_cursor(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        # Star event at row index 7.
        store.set_star(c.con, hashes[7], True)

    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        # Move cursor somewhere else so the jump is observable.
        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        table.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("O")
        await pilot.pause()
        from chronoscope.tui.screens.overview import OverviewScreen
        from textual.widgets import OptionList
        screen = pilot.app.screen
        assert isinstance(screen, OverviewScreen)
        lst = screen.query_one("#starred-list", OptionList)
        lst.focus()
        lst.highlighted = 0
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Back on main; cursor should be on the starred event (row 7).
        table = pilot.app.screen.query_one(EventTable)
        assert table.cursor_row == 7


@pytest.mark.asyncio
async def test_O_escape_leaves_state_unchanged(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.screens.main import MainScreen
        main = next(s for s in pilot.app.screen_stack if isinstance(s, MainScreen))
        before = main._state
        await pilot.press("O")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert main._state is before  # same object → no apply happened

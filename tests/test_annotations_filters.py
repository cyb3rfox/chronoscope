from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp

DATA = Path(__file__).parent / "data" / "sample.jsonl"


async def _setup_with_annotations(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        rows = [r[0] for r in c.con.execute(
            "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
        )]
        store.set_star(c.con, rows[0], True)
        store.set_star(c.con, rows[5], True)
        store.add_tag(c.con, rows[1], "susp")
        store.add_tag(c.con, rows[2], "susp")
        store.add_tag(c.con, rows[3], "clean")


@pytest.mark.asyncio
async def test_star_filter_only_starred(case_dir):
    await _setup_with_annotations(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        screen._apply_state(screen._state.set_star_filter("only_starred"))
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = screen.query_one(EventTable)
        assert table.row_count == 2


@pytest.mark.asyncio
async def test_tag_filter_include(case_dir):
    await _setup_with_annotations(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        screen._apply_state(
            screen._state.set_tag_filter(include={"susp"}, exclude=set())
        )
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = screen.query_one(EventTable)
        assert table.row_count == 2


@pytest.mark.asyncio
async def test_column_picker_has_tags_and_stars_rows(case_dir):
    await _setup_with_annotations(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        from chronoscope.tui.screens.column_picker import ColumnPickerScreen
        from textual.widgets import OptionList
        assert isinstance(pilot.app.screen, ColumnPickerScreen)
        lst = pilot.app.screen.query_one(OptionList)
        ids = []
        for i in range(lst.option_count):
            opt = lst.get_option_at_index(i)
            ids.append(opt.id)
        assert "__tags__" in ids
        assert "__stars__" in ids

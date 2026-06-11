from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.mark.asyncio
async def test_include_filter_on_data_type(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        from chronoscope.tui.screens.column_picker import ColumnPickerScreen
        assert isinstance(pilot.app.screen, ColumnPickerScreen)
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one(OptionList)
        lst.focus()
        lst.highlighted = 1  # data_type row
        await pilot.press("enter")
        await pilot.pause()
        from chronoscope.tui.screens.value_picker import ValuePickerScreen
        assert isinstance(pilot.app.screen, ValuePickerScreen)
        from chronoscope.tui.widgets.tri_state import TriStateOptionList
        trilist = pilot.app.screen.query_one(TriStateOptionList)
        trilist.focus()
        await pilot.press("plus")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        assert table.row_count == 10


@pytest.mark.asyncio
async def test_substring_filter_on_message_via_f(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one(OptionList)
        lst.focus()
        lst.highlighted = 6  # message
        await pilot.press("enter")
        await pilot.pause()
        from chronoscope.tui.screens.text_picker import TextPickerScreen
        assert isinstance(pilot.app.screen, TextPickerScreen)
        await pilot.press(*list("EXCEL"))
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_clear_all_on_main_with_X(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one(OptionList)
        lst.focus()
        lst.highlighted = 6  # message
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press(*list("EXCEL"))
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        assert table.row_count == 1
        await pilot.press("X")
        await pilot.pause()
        assert table.row_count == 20

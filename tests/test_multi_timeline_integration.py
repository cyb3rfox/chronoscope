from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case, list_timelines, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable

DATA1 = Path(__file__).parent / "data" / "sample.jsonl"
DATA2 = Path(__file__).parent / "data" / "sample2.jsonl"


@pytest.mark.asyncio
async def test_L_opens_timeline_panel(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA1, name="alpha")
    ingest_file(case_dir, DATA2, name="beta")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("L")
        await pilot.pause()
        from chronoscope.tui.screens.timeline_panel import TimelinePanelScreen
        assert isinstance(pilot.app.screen, TimelinePanelScreen)


@pytest.mark.asyncio
async def test_timeline_filter_narrows_table(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA1, name="alpha")
    ingest_file(case_dir, DATA2, name="beta")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table.filtered_count() == 30
        with open_case(case_dir) as c:
            timelines = list_timelines(c.con)
        beta_id = next(t.id for t in timelines if t.name == "beta")
        screen = pilot.app.screen
        screen._apply_state(screen._state.set_timeline_filter({beta_id}))
        await pilot.pause()
        assert table.filtered_count() == 10


@pytest.mark.asyncio
async def test_column_picker_has_timelines_row(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA1, name="alpha")
    ingest_file(case_dir, DATA2, name="beta")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        from chronoscope.tui.screens.column_picker import ColumnPickerScreen
        from textual.widgets import OptionList
        assert isinstance(pilot.app.screen, ColumnPickerScreen)
        lst = pilot.app.screen.query_one(OptionList)
        ids: list[str | None] = []
        for i in range(lst.option_count):
            opt = lst.get_option_at_index(i)
            ids.append(opt.id)
        assert "__timelines__" in ids


@pytest.mark.asyncio
async def test_timeline_row_summary_shows_counts(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA1, name="alpha")
    ingest_file(case_dir, DATA2, name="beta")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        with open_case(case_dir) as c:
            timelines = list_timelines(c.con)
        alpha_id = next(t.id for t in timelines if t.name == "alpha")
        screen._apply_state(screen._state.set_timeline_filter({alpha_id}))
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        from chronoscope.tui.screens.column_picker import ColumnPickerScreen
        from textual.widgets import OptionList
        picker = pilot.app.screen
        assert isinstance(picker, ColumnPickerScreen)
        lst = picker.query_one(OptionList)
        for i in range(lst.option_count):
            opt = lst.get_option_at_index(i)
            if opt.id == "__timelines__":
                label = str(opt.prompt)
                assert "1 of 2" in label
                return
        pytest.fail("no timelines row found in column picker")

from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp

DATA = Path(__file__).parent / "data" / "sample.jsonl"


def test_modules_end_to_end(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="e2e")
    report = ingest_file(case, DATA, name="sample")
    assert report.inserted == 20
    # idempotent re-ingest
    report2 = ingest_file(case, DATA, name="sample")
    assert report2.already_present is True
    with open_case(case) as c:
        names = [r[0] for r in c.con.execute("SELECT name FROM timeline")]
        assert names == ["sample"]


@pytest.mark.asyncio
async def test_tui_end_to_end(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="e2e")
    ingest_file(case, DATA, name="sample")
    async with PlasoViewerApp(case).run_test() as pilot:
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
        from chronoscope.tui.widgets.detail_pane import DetailPane
        assert pilot.app.screen.query_one(EventTable).row_count == 1
        await pilot.press("down")
        await pilot.pause()
        assert "EXCEL" in pilot.app.screen.query_one(DetailPane).text
        await pilot.press("q")

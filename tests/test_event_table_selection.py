from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable

DATA = Path(__file__).parent / "data" / "sample.jsonl"


async def _setup(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")


@pytest.mark.asyncio
async def test_set_selection_marks_rows_and_clear_resets(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)

        # Selecting two rows must record those rows...
        table.set_selection({2, 4})
        assert table._selected_rows == {2, 4}

        # ...and clear_selection must drop them all.
        table.clear_selection()
        assert table._selected_rows == set()


@pytest.mark.asyncio
async def test_set_selection_drops_out_of_range_rows(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        # Sample has 20 rows; row 999 should be silently dropped rather than
        # crashing the cell-refresh path.
        table.set_selection({0, 999})
        assert table._selected_rows == {0}

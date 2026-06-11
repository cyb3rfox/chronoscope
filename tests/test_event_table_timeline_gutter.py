from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable

DATA1 = Path(__file__).parent / "data" / "sample.jsonl"
DATA2 = Path(__file__).parent / "data" / "sample2.jsonl"


@pytest.mark.asyncio
async def test_single_timeline_no_timeline_column(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA1, name="alpha")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table._show_timeline_column is False


@pytest.mark.asyncio
async def test_two_timelines_show_timeline_column(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA1, name="alpha")
    ingest_file(case_dir, DATA2, name="beta")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table._show_timeline_column is True
        assert len(table._timeline_colors) == 2
        assert table.filtered_count() == 30


@pytest.mark.asyncio
async def test_timeline_colors_resolved_via_palette(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA1, name="alpha")
    ingest_file(case_dir, DATA2, name="beta")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        colors = sorted(table._timeline_colors.values())
        assert "cyan" in colors
        assert "magenta" in colors

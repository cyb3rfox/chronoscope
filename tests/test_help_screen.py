from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.mark.asyncio
async def test_help_shows_grouped_sections(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("?")
        await pilot.pause()
        from chronoscope.tui.screens.help import HelpScreen
        screen = pilot.app.screen
        assert isinstance(screen, HelpScreen)
        rendered = screen.rendered_text()
        assert "Always" in rendered
        assert "Annotations" in rendered
        assert "s" in rendered and "Toggle star" in rendered
        assert "f" in rendered and "Filter" in rendered


@pytest.mark.asyncio
async def test_help_filter_narrows_rows(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("?")
        await pilot.pause()
        from chronoscope.tui.screens.help import HelpScreen
        screen = pilot.app.screen
        assert isinstance(screen, HelpScreen)
        from textual.widgets import Input
        needle = screen.query_one(Input)
        needle.focus()
        await pilot.press(*list("tag"))
        await pilot.pause()
        rendered = screen.rendered_text()
        assert "Tag" in rendered
        assert "Jump" not in rendered

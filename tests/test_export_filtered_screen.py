from __future__ import annotations

import csv
from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.query.state import QueryState
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.export_filtered import ExportFilteredCsvScreen

DATA = Path(__file__).parent / "data" / "sample.jsonl"


async def _open_modal(pilot, case: Path) -> ExportFilteredCsvScreen:
    pilot.app.push_screen(
        ExportFilteredCsvScreen(case, QueryState())
    )
    await pilot.pause()
    return pilot.app.screen  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_empty_path_shows_error(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="s")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        screen = await _open_modal(pilot, case)
        screen.set_path("")
        screen.action_submit()
        await pilot.pause()
        from textual.widgets import Static
        assert "path required" in str(screen.query_one("#err", Static).content)


@pytest.mark.asyncio
async def test_existing_file_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="s")
    out = tmp_path / "out.csv"
    out.write_text("preexisting\n")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        screen = await _open_modal(pilot, case)
        screen.set_path(str(out))
        screen.action_submit()
        await pilot.pause()
        from textual.widgets import Static
        err = str(screen.query_one("#err", Static).content)
        assert "file exists" in err
        assert out.read_text() == "preexisting\n"


@pytest.mark.asyncio
async def test_successful_export_writes_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="s")
    out = tmp_path / "out.csv"
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        screen = await _open_modal(pilot, case)
        screen.set_path(str(out))
        screen.action_submit()
        # Worker runs in a thread; pump the event loop until the modal closes.
        for _ in range(200):
            await pilot.pause()
            if not isinstance(pilot.app.screen, ExportFilteredCsvScreen):
                break
        assert out.exists(), "CSV file was not created"
        rows = list(csv.reader(out.open(newline="")))
        assert rows[0][0] == "id"
        assert len(rows) >= 2

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.export_annotations import ExportAnnotationsScreen

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.mark.asyncio
async def test_export_annotations_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="s")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        out = tmp_path / "annotations.json"
        pilot.app.push_screen(ExportAnnotationsScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_path(str(out))
        screen.action_submit()
        await pilot.pause()
        assert out.exists()
        doc = json.loads(out.read_text())
        assert doc["schema_version"] == 1

from __future__ import annotations

import pytest

from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.new_case import NewCaseScreen


@pytest.mark.asyncio
async def test_new_case_screen_creates_case(tmp_path):
    target = tmp_path / "case1"
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        result: dict[str, object] = {}

        def cb(path):
            result["path"] = path

        pilot.app.push_screen(NewCaseScreen(), callback=cb)
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_inputs(name="demo", directory=str(target))
        screen.action_submit()
        await pilot.pause()

        assert (target / "case.toml").exists()
        assert result["path"] == target.resolve()


@pytest.mark.asyncio
async def test_new_case_screen_rejects_non_empty_dir(tmp_path):
    target = tmp_path / "dirty"
    target.mkdir()
    (target / "x").write_text("x")
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(NewCaseScreen())
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_inputs(name="demo", directory=str(target))
        screen.action_submit()
        await pilot.pause()
        assert isinstance(pilot.app.screen, NewCaseScreen)
        assert "not empty" in screen.error_text().lower()

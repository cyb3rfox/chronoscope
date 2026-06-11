from __future__ import annotations

import pytest

from chronoscope.core.case import init_case
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.open_case import OpenCaseScreen


@pytest.mark.asyncio
async def test_open_case_screen_accepts_valid_case(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="x")
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        result: dict[str, object] = {}
        pilot.app.push_screen(OpenCaseScreen(), callback=lambda p: result.__setitem__("p", p))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_path(str(case))
        screen.action_submit()
        await pilot.pause()
        assert result["p"] == case.resolve()


@pytest.mark.asyncio
async def test_open_case_screen_rejects_missing_toml(tmp_path):
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(OpenCaseScreen())
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_path(str(tmp_path / "nope"))
        screen.action_submit()
        await pilot.pause()
        assert isinstance(pilot.app.screen, OpenCaseScreen)
        assert "case.toml" in screen.error_text().lower()


@pytest.mark.asyncio
async def test_open_case_screen_submits_on_enter_in_input(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="x")
    result: dict[str, object] = {}
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(OpenCaseScreen(), callback=lambda p: result.__setitem__("p", p))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_path(str(case))
        await pilot.press("enter")
        await pilot.pause()
        assert result.get("p") == case.resolve()

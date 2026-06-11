from __future__ import annotations

import pytest

from chronoscope.config import recent
from chronoscope.core.case import init_case
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.launcher import LauncherScreen
from chronoscope.tui.screens.main import MainScreen


@pytest.mark.asyncio
async def test_launcher_renders_with_empty_recents(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        assert isinstance(pilot.app.screen, LauncherScreen)
        assert "No recent cases" in pilot.app.screen.rendered_text()


@pytest.mark.asyncio
async def test_launcher_opens_recent_on_enter(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    recent.touch(case, "demo")
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        assert isinstance(pilot.app.screen, LauncherScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, MainScreen)


@pytest.mark.asyncio
async def test_launcher_flags_missing_recent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    missing = tmp_path / "gone"
    missing.mkdir()
    recent.touch(missing, "ghost")
    missing.rmdir()
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        assert "(missing)" in pilot.app.screen.rendered_text()


@pytest.mark.asyncio
async def test_main_screen_direct_open_touches_recents(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        entries = recent.load()
        assert any(e.path == str(case.resolve()) for e in entries)

from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.main import MainScreen
from chronoscope.tui.screens.menu_dropdown import MenuDropdownScreen, MenuItem

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.mark.asyncio
async def test_dropdown_renders_items(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    triggered: list[str] = []
    items = [
        MenuItem("New case…", "", lambda: triggered.append("new")),
        MenuItem("Open case…", "", lambda: triggered.append("open")),
    ]
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(MenuDropdownScreen("File", items, anchor_x=0))
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, MenuDropdownScreen)
        assert "New case" in screen.rendered_text()
        await pilot.press("enter")
        await pilot.pause()
        assert triggered == ["new"]


@pytest.mark.asyncio
async def test_dropdown_escape_dismisses(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(MenuDropdownScreen("File", [MenuItem("A", "", lambda: None)], anchor_x=0))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, MenuDropdownScreen)


@pytest.mark.asyncio
async def test_menubar_alt_f_opens_file_menu(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="s")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        assert isinstance(pilot.app.screen, MainScreen)
        await pilot.press("alt+f")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, MenuDropdownScreen)
        assert "New case" in screen.rendered_text()
        assert "Quit" in screen.rendered_text()


@pytest.mark.asyncio
async def test_menubar_alt_a_opens_ai_menu(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="s")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        await pilot.press("alt+a")
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, MenuDropdownScreen)
        text = screen.rendered_text()
        assert "Chat" in text and "Draft report" in text and "Settings" in text

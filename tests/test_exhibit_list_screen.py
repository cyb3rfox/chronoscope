from __future__ import annotations

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.core.exhibits import add_exhibit
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.exhibit_form import ExhibitFormScreen
from chronoscope.tui.screens.exhibit_list import ExhibitListScreen


@pytest.mark.asyncio
async def test_list_shows_exhibits(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    with open_case(case) as c:
        add_exhibit(c.con, title="alpha.ps1", description="first", body="a")
        add_exhibit(c.con, title="beta.sh", description="second", body="b")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(ExhibitListScreen(case))
        await pilot.pause()
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one("#list", OptionList)
        assert lst.option_count == 2


@pytest.mark.asyncio
async def test_selecting_exhibit_opens_edit_form(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    with open_case(case) as c:
        add_exhibit(c.con, title="alpha.ps1", description="first", body="a")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(ExhibitListScreen(case))
        await pilot.pause()
        list_screen = pilot.app.screen
        list_screen.open_selected(0)
        await pilot.pause()
        assert isinstance(pilot.app.screen, ExhibitFormScreen)
        from textual.widgets import Input
        assert pilot.app.screen.query_one("#title", Input).value == "alpha.ps1"


@pytest.mark.asyncio
async def test_empty_state_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(ExhibitListScreen(case))
        await pilot.pause()
        from textual.widgets import OptionList
        assert not pilot.app.screen.query(OptionList)


@pytest.mark.asyncio
async def test_case_menu_has_exhibit_items(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        main = pilot.app.screen
        main.action_open_menu_case()
        await pilot.pause()
        rendered = pilot.app.screen.rendered_text()
        assert "Add exhibit" in rendered
        assert "List exhibits" in rendered
        assert "Remove exhibit" in rendered

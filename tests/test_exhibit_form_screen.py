from __future__ import annotations

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.core.exhibits import add_exhibit, get_exhibit, list_exhibits
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.exhibit_form import ExhibitFormScreen


@pytest.mark.asyncio
async def test_add_exhibit_via_paste(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(ExhibitFormScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_fields(title="evil.ps1", description="dropper", body="whoami\n")
        screen.action_submit()
        await pilot.pause()
        with open_case(case) as c:
            rows = list_exhibits(c.con)
        assert len(rows) == 1 and rows[0].title == "evil.ps1" and rows[0].body == "whoami\n"


@pytest.mark.asyncio
async def test_add_exhibit_imports_file_and_defaults_title(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    script = tmp_path / "payload.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(ExhibitFormScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_fields(title="", description="from disk", source=str(script))
        screen.action_submit()
        await pilot.pause()
        with open_case(case) as c:
            rows = list_exhibits(c.con)
        assert rows[0].title == "payload"
        assert "echo hi" in rows[0].body


@pytest.mark.asyncio
async def test_add_exhibit_requires_title(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(ExhibitFormScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_fields(title="", description="", body="x")
        screen.action_submit()
        await pilot.pause()
        assert isinstance(pilot.app.screen, ExhibitFormScreen)
        assert "title" in screen.error_text().lower()


@pytest.mark.asyncio
async def test_edit_exhibit_updates(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    with open_case(case) as c:
        eid = add_exhibit(c.con, title="old", description="d", body="b")
        exhibit = get_exhibit(c.con, eid)
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(ExhibitFormScreen(case, exhibit))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_fields(title="new", description="d2", body="b2")
        screen.action_submit()
        await pilot.pause()
        with open_case(case) as c:
            after = get_exhibit(c.con, eid)
        assert (after.title, after.description, after.body) == ("new", "d2", "b2")

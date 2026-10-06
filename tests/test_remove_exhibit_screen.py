from __future__ import annotations

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.core.exhibits import add_exhibit, count_exhibits
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.remove_exhibit import RemoveExhibitScreen


@pytest.mark.asyncio
async def test_remove_exhibit_drops_selected(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    with open_case(case) as c:
        eid = add_exhibit(c.con, title="evil.ps1", description="d", body="x")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(RemoveExhibitScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.select_by_id(eid)
        screen.action_confirm_and_remove()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        with open_case(case) as c:
            assert count_exhibits(c.con) == 0

from __future__ import annotations

import pytest

from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.about import AboutScreen


@pytest.mark.asyncio
async def test_about_screen_shows_version(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    async with PlasoViewerApp(None).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(AboutScreen())
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, AboutScreen)
        assert "Chronoscope" in screen.rendered_text()
        assert "0.0.1" in screen.rendered_text()

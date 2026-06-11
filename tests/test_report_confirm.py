from __future__ import annotations

import pytest

from chronoscope.ai.settings import AISettings, save_ai_settings
from chronoscope.core.case import init_case
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.ai_report import AIReportScreen
from chronoscope.tui.screens.confirm import ConfirmScreen


@pytest.mark.asyncio
async def test_report_asks_before_using_ai(tmp_path, monkeypatch):
    """Pressing R with AI configured must pop a confirm modal first, and must
    NOT open the report screen (which would call the AI) until the user agrees."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("TESTKEY", "sk-test")
    case = tmp_path / "c"
    init_case(case, name="demo")
    save_ai_settings(AISettings(enabled=True, api_key_env="TESTKEY"))
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.screen.action_open_report()
        await pilot.pause()
        # A confirmation modal is on top — the AI report screen is NOT open yet.
        assert isinstance(pilot.app.screen, ConfirmScreen)
        assert not isinstance(pilot.app.screen, AIReportScreen)


@pytest.mark.asyncio
async def test_report_declined_does_not_open_report(tmp_path, monkeypatch):
    """Declining the confirm must leave us on the main screen with no AI call."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("TESTKEY", "sk-test")
    case = tmp_path / "c"
    init_case(case, name="demo")
    save_ai_settings(AISettings(enabled=True, api_key_env="TESTKEY"))
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.screen.action_open_report()
        await pilot.pause()
        assert isinstance(pilot.app.screen, ConfirmScreen)
        await pilot.press("n")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, AIReportScreen)


@pytest.mark.asyncio
async def test_report_skipped_when_ai_disabled(tmp_path, monkeypatch):
    """If AI is disabled, R warns and never shows the confirm modal."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    save_ai_settings(AISettings(enabled=False))
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.screen.action_open_report()
        await pilot.pause()
        assert not isinstance(pilot.app.screen, ConfirmScreen)

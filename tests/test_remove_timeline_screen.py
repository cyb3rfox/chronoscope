from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.remove_timeline import RemoveTimelineScreen

DATA = Path(__file__).parent / "data" / "sample.jsonl"


async def _wait_for_workers(pilot) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


@pytest.mark.asyncio
async def test_remove_timeline_drops_selected(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="sample")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(RemoveTimelineScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.select_by_name("sample")
        screen.action_confirm_and_remove()
        await pilot.pause()
        await pilot.press("y")
        await _wait_for_workers(pilot)
        with open_case(case) as c:
            assert c.con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_remove_timeline_via_enter_keypress(tmp_path, monkeypatch):
    """Pressing Enter on the highlighted option must trigger removal.

    Regression: the focused OptionList consumes Enter, so the screen's
    ("enter", ...) binding never fires. The screen must react to
    OptionList.OptionSelected instead.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="sample")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(RemoveTimelineScreen(case))
        await pilot.pause()
        pilot.app.screen.select_by_name("sample")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("y")
        await _wait_for_workers(pilot)
        with open_case(case) as c:
            assert c.con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_remove_timeline_shows_progress(tmp_path, monkeypatch):
    """While removal runs, the screen must update its progress line."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="sample")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(RemoveTimelineScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.select_by_name("sample")
        await pilot.pause()

        seen: list[str] = []
        original = screen._update_progress

        def spy(done, total, _orig=original):
            _orig(done, total)
            seen.append(screen.progress_text())

        screen._update_progress = spy  # type: ignore[method-assign]
        screen.action_confirm_and_remove()
        await pilot.pause()
        await pilot.press("y")
        await _wait_for_workers(pilot)

        assert seen, "progress line was never updated during removal"
        with open_case(case) as c:
            assert c.con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_remove_timeline_cancel_leaves_data_intact(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    ingest_file(case, DATA, name="sample")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(RemoveTimelineScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.select_by_name("sample")
        screen.action_confirm_and_remove()
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        with open_case(case) as c:
            assert c.con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0] == 1

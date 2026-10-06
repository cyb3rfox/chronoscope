from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.screens.add_timeline import AddTimelineScreen
from tests._plaso_fixtures import make_plaso

DATA = Path(__file__).parent / "data" / "sample.jsonl"


async def _wait_for_workers(pilot) -> None:
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


@pytest.mark.asyncio
async def test_add_timeline_ingests(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(AddTimelineScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_inputs(source=str(DATA), name="sample")
        screen.action_submit()
        await _wait_for_workers(pilot)
        with open_case(case) as c:
            assert c.con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_add_timeline_rejects_non_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    bogus = tmp_path / "x.txt"
    bogus.write_text("nope")
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(AddTimelineScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_inputs(source=str(bogus), name="x")
        screen.action_submit()
        await pilot.pause()
        assert isinstance(pilot.app.screen, AddTimelineScreen)
        assert "jsonl" in screen.error_text().lower()


@pytest.mark.asyncio
async def test_add_timeline_plaso_happy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    pl = tmp_path / "t.plaso"
    make_plaso(
        pl,
        event_data=[{"data_type": "fs:stat", "display_name": "/a",
                     "parser": "filestat", "message": "stat"}],
        events=[(1, 1_700_000_000_000_000, "mtime")],
    )
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(AddTimelineScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_inputs(source=str(pl), name="evt")
        screen.action_submit()
        await _wait_for_workers(pilot)
        with open_case(case) as c:
            kinds = [r[0] for r in c.con.execute(
                "SELECT source_kind FROM timeline"
            )]
            assert kinds == ["plaso"]


@pytest.mark.asyncio
async def test_add_timeline_rejects_legacy_zip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    bad = tmp_path / "legacy.plaso"
    bad.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        pilot.app.push_screen(AddTimelineScreen(case))
        await pilot.pause()
        screen = pilot.app.screen
        screen.set_inputs(source=str(bad), name="x")
        screen.action_submit()
        await _wait_for_workers(pilot)
        assert isinstance(pilot.app.screen, AddTimelineScreen)
        assert "jsonl" in screen.error_text().lower() or "plaso" in screen.error_text().lower()


@pytest.mark.asyncio
async def test_add_timeline_progress_updates(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    case = tmp_path / "c"
    init_case(case, name="demo")
    pl = tmp_path / "t.plaso"
    make_plaso(
        pl,
        event_data=[{"data_type": "fs:stat", "display_name": "/a"}],
        events=[(1, 1_700_000_000_000_000, "mtime")],
    )
    async with PlasoViewerApp(case).run_test() as pilot:
        await pilot.pause()
        seen: list[str] = []
        screen = AddTimelineScreen(case)
        pilot.app.push_screen(screen)
        await pilot.pause()
        original = screen._update_progress

        def spy(done, total):
            original(done, total)
            seen.append(screen.progress_text())

        screen._update_progress = spy  # type: ignore[method-assign]
        screen.set_inputs(source=str(pl), name="evt")
        screen.action_submit()
        await _wait_for_workers(pilot)
        assert seen, "progress callback was never invoked"
        assert any("1 / 1" in s or "1 events" in s for s in seen), seen

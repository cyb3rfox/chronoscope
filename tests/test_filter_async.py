from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.query.state import QueryState
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable, WindowData

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.fixture
def case_dir(tmp_path):
    d = tmp_path / "case"
    d.mkdir()
    init_case(d, name="demo")
    ingest_file(d, DATA, name="sample")
    return d


@pytest.mark.asyncio
async def test_query_window_returns_full_count_and_rows(case_dir, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(case_dir / "xdg"))
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        data = table.query_window(table.con, QueryState(), 0)
        assert isinstance(data, WindowData)
        assert data.total_filtered == 20
        assert len(data.rows) == 20
        assert data.window_offset == 0


@pytest.mark.asyncio
async def test_query_window_substring_filter_and_clamp(case_dir, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(case_dir / "xdg"))
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 5)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        empty = table.query_window(
            table.con, QueryState().set_substring("message", "zzz-nope-xyz"), 0
        )
        assert empty.total_filtered == 0
        assert empty.rows == []
        clamped = table.query_window(table.con, QueryState(), 9999)
        assert clamped.window_offset == 15
        assert len(clamped.rows) == 5


@pytest.mark.asyncio
async def test_filter_loading_screen_cancel_dismisses_true(case_dir, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(case_dir / "xdg"))
    from chronoscope.tui.screens.filter_loading import FilterLoadingScreen
    results: list[bool] = []
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        pilot.app.push_screen(FilterLoadingScreen(), callback=results.append)
        await pilot.pause()
        assert isinstance(pilot.app.screen, FilterLoadingScreen)
        await pilot.press("escape")
        await pilot.pause()
        assert results == [True]  # Esc cancels -> dismiss(True)


@pytest.mark.asyncio
async def test_apply_state_filters_after_worker_completes(case_dir, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(case_dir / "xdg"))
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        screen = pilot.app.screen
        table = screen.query_one(EventTable)
        assert table.filtered_count() == 20  # initial load went through async path
        screen._apply_state(screen._state.set_substring("message", "zzz-nope-xyz"))
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert table.filtered_count() == 0
        assert table.row_count == 0
        screen._apply_state(screen._state.clear_all())
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert table.filtered_count() == 20


@pytest.mark.asyncio
async def test_cancel_reverts_to_committed_state(case_dir, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(case_dir / "xdg"))
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        screen = pilot.app.screen
        committed = screen._committed_state
        pending = screen._state.set_substring("message", "pending-xyz")
        screen._state = pending
        seq = screen._filter_seq
        screen._on_filter_cancelled(seq)
        assert screen._state == committed
        assert screen._filter_seq == seq + 1


@pytest.mark.asyncio
async def test_stale_load_result_is_ignored(case_dir, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(case_dir / "xdg"))
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        screen = pilot.app.screen
        table = screen.query_one(EventTable)
        before = table.filtered_count()
        stale_seq = screen._filter_seq - 1
        fake = table.query_window(
            table.con, screen._state.set_substring("message", "zzz-nope-xyz"), 0
        )
        screen._on_filter_loaded(stale_seq, screen._state, fake)
        await pilot.pause()
        assert table.filtered_count() == before  # unchanged

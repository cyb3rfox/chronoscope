"""Windowed EventTable: the display is a slice over the full filtered
result; jumps and data-range helpers operate on the full set and reposition
the window when needed."""

from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable

DATA = Path(__file__).parent / "data" / "sample.jsonl"

# Sample fixture has 20 events, minute-spaced from 2019-03-12T17:00:00 → 17:19:00
FIRST_TS = 1552410000_000_000
LAST_TS = 1552411140_000_000
EXCEL_TS = 1552410840_000_000  # row 14 in ASC order


@pytest.mark.asyncio
async def test_window_loads_only_up_to_window_size(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 5)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table.row_count == 5
        assert table.filtered_count() == 20
        assert table.window_offset == 0


@pytest.mark.asyncio
async def test_jump_past_window_reloads_centered(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 5)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table.jump_to_ts(EXCEL_TS) is True
        # Rank 14, window=5: new offset = 14 - 2 = 12, window covers ranks 12..16
        assert table.window_offset == 12
        assert table.row_count == 5
        # Cursor at local index 14 - 12 = 2
        assert table.cursor_row == 2
        assert table._ts_list[2] == EXCEL_TS


@pytest.mark.asyncio
async def test_jump_within_window_does_not_reload(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 20)  # fits all
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        before_offset = table.window_offset
        assert table.jump_to_ts(EXCEL_TS) is True
        assert table.window_offset == before_offset  # no reload
        assert table.cursor_row == 14


@pytest.mark.asyncio
async def test_data_ts_range_covers_full_filtered_set(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 3)  # tiny window
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table.row_count == 3
        assert table.data_ts_range() == (FIRST_TS, LAST_TS)


@pytest.mark.asyncio
async def test_jump_past_end_clamps_to_last_across_full_set(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 5)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        # Far-future timestamp → clamp to last of full set (rank 19).
        assert table.jump_to_ts(9_999_999_999_000_000) is True
        # Natural offset would be 19 - 2 = 17, but _load_window clamps to
        # max_offset = max(0, 20 - 5) = 15 so the window stays full.
        assert table.window_offset == 15
        assert table.row_count == 5
        # Local index of rank 19 within window starting at 15: 19 - 15 = 4.
        assert table.cursor_row == 4
        assert table._ts_list[4] == LAST_TS


@pytest.mark.asyncio
async def test_jump_before_start_clamps_to_first(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 5)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        # Jump to somewhere in the middle first to move the window.
        table.jump_to_ts(EXCEL_TS)
        assert table.window_offset == 12
        # Now jump before the start.
        assert table.jump_to_ts(0) is True
        assert table.window_offset == 0
        assert table.cursor_row == 0
        assert table._ts_list[0] == FIRST_TS


@pytest.mark.asyncio
async def test_scroll_down_past_trigger_shifts_window_forward(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    # 20-event fixture; window 6, trigger 2 → shift when cursor >= 6-2 = 4
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 6)
    monkeypatch.setattr(EventTable, "PAGE_TRIGGER", 2)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table.window_offset == 0
        assert table.row_count == 6
        table.focus()
        # Move the cursor past the trigger. Starting at row 0; press down 4x → row 4.
        for _ in range(4):
            await pilot.press("down")
            await pilot.pause()
        # At row 4 (abs 4) the handler fires; re-center on cursor:
        # target_offset = 4 - 6//2 = 1, so new offset = 1, cursor local = 4-1 = 3.
        assert table.window_offset == 1
        assert table.cursor_row == 3


@pytest.mark.asyncio
async def test_scroll_up_near_top_of_shifted_window_shifts_backward(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 6)
    monkeypatch.setattr(EventTable, "PAGE_TRIGGER", 2)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        # Force a non-zero offset by jumping near the end.
        assert table.jump_to_ts(9_999_999_999_000_000) is True
        assert table.window_offset > 0
        start_offset = table.window_offset
        table.focus()
        # Scroll up enough times that cursor crosses PAGE_TRIGGER at the top.
        # row_count = min(WINDOW_SIZE, total - offset) = 6. Initial cursor lands
        # at some row ≤ row_count-1; pressing up 5 times guarantees we hit row 0/1.
        for _ in range(5):
            await pilot.press("up")
            await pilot.pause()
        # Offset should have decreased (may eventually hit 0).
        assert table.window_offset < start_offset


@pytest.mark.asyncio
async def test_no_shift_at_absolute_bottom(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 6)
    monkeypatch.setattr(EventTable, "PAGE_TRIGGER", 2)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        # Jump to very end; window sits at its max offset; cursor at last row.
        table.jump_to_ts(9_999_999_999_000_000)
        bottom_offset = table.window_offset
        table.focus()
        # Further downs at the absolute bottom should NOT shift past the end.
        for _ in range(5):
            await pilot.press("down")
            await pilot.pause()
        assert table.window_offset == bottom_offset


@pytest.mark.asyncio
async def test_no_shift_at_absolute_top(case_dir, monkeypatch):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    monkeypatch.setattr(EventTable, "WINDOW_SIZE", 6)
    monkeypatch.setattr(EventTable, "PAGE_TRIGGER", 2)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table.window_offset == 0
        table.focus()
        # Cursor already at row 0; pressing up shouldn't trigger a backward shift.
        for _ in range(5):
            await pilot.press("up")
            await pilot.pause()
        assert table.window_offset == 0

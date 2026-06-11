from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.mark.asyncio
async def test_app_starts_and_shows_case_name(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        assert "demo" in (pilot.app.title or "")


@pytest.mark.asyncio
async def test_app_quits_on_q(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        assert pilot.app.is_running
        await pilot.press("q")
        await pilot.pause()
        assert not pilot.app.is_running


@pytest.mark.asyncio
async def test_event_table_populates_from_case(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable

        table = pilot.app.screen.query_one(EventTable)
        assert table.row_count == 20


@pytest.mark.asyncio
async def test_detail_updates_on_row_move(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.detail_pane import DetailPane
        from chronoscope.tui.widgets.event_table import EventTable

        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        await pilot.press("down")
        await pilot.pause()
        detail = pilot.app.screen.query_one(DetailPane)
        assert "data_type" in detail.text
        assert detail.text.strip() != ""


@pytest.mark.asyncio
async def test_help_modal_opens_on_question_mark(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("?")
        await pilot.pause()
        from chronoscope.tui.screens.help import HelpScreen
        assert isinstance(pilot.app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_f_opens_column_picker(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("f")
        await pilot.pause()
        from chronoscope.tui.screens.column_picker import ColumnPickerScreen
        assert isinstance(pilot.app.screen, ColumnPickerScreen)


@pytest.mark.asyncio
async def test_d_toggles_detail_pane(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.detail_pane import DetailPane
        detail = pilot.app.screen.query_one(DetailPane)
        assert detail.display is True
        await pilot.press("d")
        await pilot.pause()
        assert detail.display is False
        await pilot.press("d")
        await pilot.pause()
        assert detail.display is True


@pytest.mark.asyncio
async def test_event_table_jump_to_ts_lands_on_first_at_or_after(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        target_usec = 1552410840_000_000
        ok = table.jump_to_ts(target_usec)
        assert ok is True
        assert table.cursor_row == 14


@pytest.mark.asyncio
async def test_event_table_jump_past_end_clamps_to_last(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        ok = table.jump_to_ts(9_999_999_999_000_000)
        assert ok is True
        assert table.cursor_row == table.row_count - 1


@pytest.mark.asyncio
async def test_event_table_jump_before_start_clamps_to_first(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        ok = table.jump_to_ts(0)
        assert ok is True
        assert table.cursor_row == 0


@pytest.mark.asyncio
async def test_cursor_ts_usec_returns_current_row_timestamp(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        table.move_cursor(row=0)
        assert table.cursor_ts_usec() == 1552410000_000_000


@pytest.mark.asyncio
async def test_g_opens_jump_picker(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        from chronoscope.tui.screens.jump_picker import JumpPickerScreen
        assert isinstance(pilot.app.screen, JumpPickerScreen)


@pytest.mark.asyncio
async def test_g_flow_moves_cursor(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("g")
        await pilot.pause()
        await pilot.press(*list("2019-03-12 17:14"))
        await pilot.press("enter")
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        assert table.cursor_row == 14


@pytest.mark.asyncio
async def test_detail_pane_shows_tags_and_comments(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    from chronoscope.annotations import store
    from chronoscope.core.case import open_case
    with open_case(case_dir) as c:
        h = c.con.execute(
            "SELECT event_hash FROM event ORDER BY id LIMIT 1"
        ).fetchone()[0]
        store.add_tag(c.con, h, "susp")
        store.add_tag(c.con, h, "review")
        store.add_comment(c.con, h, "first")
        store.add_comment(c.con, h, "second\nwith newline")

    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.detail_pane import DetailPane
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        table.move_cursor(row=0)
        await pilot.pause()
        detail = pilot.app.screen.query_one(DetailPane)
        assert "tags" in detail.text
        assert "susp" in detail.text
        assert "review" in detail.text
        assert "comments" in detail.text
        assert "first" in detail.text
        assert "second" in detail.text
        assert "with newline" in detail.text


@pytest.mark.asyncio
async def test_f2_cycles_footer_group(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.grouped_footer import GroupedFooter
        footer = pilot.app.screen.query_one(GroupedFooter)
        first = footer.current_group_id()
        await pilot.press("f2")
        await pilot.pause()
        assert footer.current_group_id() != first


@pytest.mark.asyncio
async def test_w_cycles_detail_width(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.detail_pane import DetailPane
        pane = pilot.app.screen.query_one(DetailPane)
        seen = [str(pane.styles.width)]
        for _ in range(4):
            await pilot.press("w")
            await pilot.pause()
            seen.append(str(pane.styles.width))
        # Pressing 4 times returns to the original (wrap). At least 3 distinct values along the way.
        assert len(set(seen)) >= 3
        assert seen[0] == seen[-1]


@pytest.mark.asyncio
async def test_w_unhides_pane_if_hidden(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.detail_pane import DetailPane
        pane = pilot.app.screen.query_one(DetailPane)
        await pilot.press("d")  # hide
        await pilot.pause()
        assert pane.display is False
        await pilot.press("w")  # should unhide + set next width
        await pilot.pause()
        assert pane.display is True

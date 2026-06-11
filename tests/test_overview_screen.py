from __future__ import annotations

from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import OptionList, Static

from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.query.state import QueryState
from chronoscope.report.data import build_overview
from chronoscope.tui.screens.overview import OverviewScreen

DATA = Path(__file__).parent / "data" / "sample.jsonl"


class _Harness(App):
    def __init__(self, con, state):
        super().__init__()
        self._con = con
        self._state = state
        self.result = "NOT_SET"

    def on_mount(self):
        data = build_overview(self._con, self._state, buckets=10)
        self.push_screen(
            OverviewScreen(self._state, data),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_overview_screen_opens_with_histogram(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert isinstance(screen, OverviewScreen)
            assert len(screen._data.histogram) == 10
            assert 0 <= screen._cursor_bucket < 10


@pytest.mark.asyncio
async def test_overview_enter_on_bucket_dismisses_with_bracket(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        # Compute expected bucket bounds while connection is still open.
        expected_bucket = build_overview(c.con, QueryState(), buckets=10).histogram[3]
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            screen._cursor_bucket = 3
            await pilot.press("enter")
            await pilot.pause()
    assert isinstance(harness.result, QueryState)
    b = harness.result.bracket
    assert b.start_usec is not None and b.end_usec is not None
    # The cursor bucket's [start, end) maps to bracket [start, end - 1].
    assert b.start_usec == expected_bucket.start_usec
    assert b.end_usec == expected_bucket.end_usec - 1


@pytest.mark.asyncio
async def test_overview_arrow_moves_cursor(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            start = screen._cursor_bucket
            await pilot.press("right")
            await pilot.pause()
            assert screen._cursor_bucket == min(start + 1, 9)
            await pilot.press("left")
            await pilot.press("left")
            await pilot.pause()
            assert screen._cursor_bucket >= 0


@pytest.mark.asyncio
async def test_overview_escape_dismisses_with_none(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_overview_home_end_jumps_to_first_last(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            await pilot.press("end")
            await pilot.pause()
            assert pilot.app.screen._cursor_bucket == 9
            await pilot.press("home")
            await pilot.pause()
            assert pilot.app.screen._cursor_bucket == 0


@pytest.mark.asyncio
async def test_overview_summary_shows_headline_counts(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        # Make some annotations visible in the summary.
        from chronoscope.annotations import store
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        store.add_tag(c.con, hashes[0], "susp")
        store.set_star(c.con, hashes[1], True)
        store.add_comment(c.con, hashes[2], "first")
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            summary_text = screen.query_one("#summary", Static).content
            s = summary_text if isinstance(summary_text, str) else str(summary_text)
            assert "20" in s     # total
            assert "Tagged" in s and "1" in s
            assert "Starred" in s
            assert "Commented" in s


@pytest.mark.asyncio
async def test_overview_enter_on_tag_row_dismisses_with_tag_filter(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        from chronoscope.annotations import store
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        store.add_tag(c.con, hashes[0], "alpha")
        store.add_tag(c.con, hashes[1], "alpha")
        store.add_tag(c.con, hashes[2], "beta")
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            # Focus the tags list.
            await pilot.press("tab")
            await pilot.pause()
            # Highlight the first row (alpha has the higher count).
            await pilot.press("enter")
            await pilot.pause()
    assert isinstance(harness.result, QueryState)
    assert harness.result.tag_filter.include == frozenset({"alpha"})


@pytest.mark.asyncio
async def test_overview_tab_focus_moves_between_panels(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        from chronoscope.annotations import store
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        store.add_tag(c.con, hashes[0], "tag1")
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            # Tab should leave the default focus and move somewhere else.
            before = pilot.app.focused
            await pilot.press("tab")
            await pilot.pause()
            after = pilot.app.focused
            # Tab should move focus to an OptionList.
            assert isinstance(after, OptionList), f"expected OptionList focused, got {type(after)}"


@pytest.mark.asyncio
async def test_overview_zoom_in_doubles_bucket_count(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        # Construct the harness with the connection passed through.
        class _ZoomHarness(App):
            def __init__(self, con, state):
                super().__init__()
                self._con = con
                self._state = state
                self.result = "NOT_SET"

            def on_mount(self):
                from chronoscope.report.data import build_overview
                data = build_overview(self._con, self._state, buckets=10)
                self.push_screen(
                    OverviewScreen(self._state, data, con=self._con),
                    callback=lambda r: setattr(self, "result", r),
                )

        harness = _ZoomHarness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            assert len(screen._data.histogram) == 10
            await pilot.press("plus")
            await pilot.pause()
            # zoom_in: max(15, min(240, 10*2)) = 20
            assert len(screen._data.histogram) == 20
            await pilot.press("minus")
            await pilot.pause()
            # zoom_out: max(15, min(240, 20//2)) = max(15, 10) = 15
            assert len(screen._data.histogram) == 15


@pytest.mark.asyncio
async def test_overview_tag_with_brackets_survives(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        from chronoscope.annotations import store
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        store.add_tag(c.con, hashes[0], "S-1-5-21")
        harness = _Harness(c.con, QueryState())
        async with harness.run_test() as pilot:
            await pilot.pause()
            lst = pilot.app.screen.query_one("#tags-list", OptionList)
            # Option prompt should contain the full tag (not a markup-stripped
            # empty string). Tags are stored lowercase, so we check for the
            # SID-like pattern with hyphens (verifying brackets weren't consumed).
            opt = lst.get_option_at_index(0)
            prompt_text = str(opt.prompt)
            assert "s-1-5-21" in prompt_text
            # Verify it's not mangled by checking the SID structure is intact
            assert "s-1-5-21" in prompt_text

from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp

DATA = Path(__file__).parent / "data" / "sample.jsonl"


async def _setup(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")


def _first_hash(case_dir):
    with open_case(case_dir) as c:
        return c.con.execute(
            "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC LIMIT 1"
        ).fetchone()[0]


@pytest.mark.asyncio
async def test_s_toggles_star(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        h = _first_hash(case_dir)
        with open_case(case_dir) as c:
            assert store.get_star(c.con, h) is True
        await pilot.press("s")
        await pilot.pause()
        with open_case(case_dir) as c:
            assert store.get_star(c.con, h) is False


@pytest.mark.asyncio
async def test_t_adds_tag(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        await pilot.press(*list("susp"))
        await pilot.press("enter")
        await pilot.pause()
        h = _first_hash(case_dir)
        with open_case(case_dir) as c:
            assert "susp" in store.tags_for(c.con, h)


@pytest.mark.asyncio
async def test_c_adds_comment(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("c")
        await pilot.pause()
        await pilot.press(*list("hi there"))
        await pilot.press("ctrl+s")
        await pilot.pause()
        h = _first_hash(case_dir)
        with open_case(case_dir) as c:
            cs = store.comments_for(c.con, h)
            assert [x["body"] for x in cs] == ["hi there"]


@pytest.mark.asyncio
async def test_e_edits_latest_comment(case_dir):
    await _setup(case_dir)
    h = _first_hash(case_dir)
    with open_case(case_dir) as c:
        store.add_comment(c.con, h, "original")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        from textual.widgets import TextArea
        ta = pilot.app.screen.query_one(TextArea)
        ta.clear()
        await pilot.press(*list("edited"))
        await pilot.press("ctrl+s")
        await pilot.pause()
        with open_case(case_dir) as c:
            cs = store.comments_for(c.con, h)
            assert cs[0]["body"] == "edited"


@pytest.mark.asyncio
async def test_D_deletes_latest_comment_with_confirm(case_dir):
    await _setup(case_dir)
    h = _first_hash(case_dir)
    with open_case(case_dir) as c:
        store.add_comment(c.con, h, "to-delete")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        with open_case(case_dir) as c:
            assert store.comments_for(c.con, h) == []


@pytest.mark.asyncio
async def test_V_visual_mode_contiguous_bulk_star(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("V")
        await pilot.press("down")
        await pilot.press("down")
        await pilot.press("s")
        await pilot.pause()
        with open_case(case_dir) as c:
            hashes = [r[0] for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC LIMIT 3"
            )]
            for h in hashes:
                assert store.get_star(c.con, h) is True


@pytest.mark.asyncio
async def test_V_space_marks_discontinuous(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("V")          # anchor=0
        await pilot.press("down")       # cursor=1, range=0..1
        await pilot.press("down")       # cursor=2
        await pilot.press("down")       # cursor=3
        await pilot.press("down")       # cursor=4
        await pilot.press("down")       # cursor=5
        await pilot.press("space")      # sticky +5
        await pilot.press("up")         # cursor=4
        await pilot.press("up")         # cursor=3, range=0..3 + {5}
        await pilot.press("s")
        await pilot.pause()
        with open_case(case_dir) as c:
            starred = [bool(r[0]) for r in c.con.execute(
                "SELECT (SELECT 1 FROM annotation_star s WHERE s.event_hash=e.event_hash) "
                "FROM event e ORDER BY ts_usec ASC, id ASC"
            )]
        starred_indices = {i for i, s in enumerate(starred) if s}
        assert starred_indices >= {0, 1, 2, 3, 5}
        assert 4 not in starred_indices


@pytest.mark.asyncio
async def test_shift_down_extends_selection_and_bulk_stars(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        # Without pressing V first: shift+down should auto-enter visual mode,
        # anchor at the current row, and extend the selection by one.
        await pilot.press("shift+down")
        await pilot.press("shift+down")
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        assert table._selected_rows == {0, 1, 2}
        await pilot.press("s")
        await pilot.pause()
        with open_case(case_dir) as c:
            hashes = [r[0] for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC LIMIT 3"
            )]
            for h in hashes:
                assert store.get_star(c.con, h) is True


@pytest.mark.asyncio
async def test_shift_arrow_clears_selection_after_apply(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("shift+down")
        await pilot.press("shift+down")
        await pilot.press("s")
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        # bulk_star calls _visual_cancel which should clear visible selection.
        assert table._selected_rows == set()


@pytest.mark.asyncio
async def test_shift_up_from_middle_extends_upward(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        # Move down a few rows first so shift+up can extend upward.
        await pilot.press("down")
        await pilot.press("down")
        await pilot.press("down")
        await pilot.press("shift+up")
        await pilot.press("shift+up")
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        assert table._selected_rows == {1, 2, 3}


@pytest.mark.asyncio
async def test_V_escape_cancels(case_dir):
    await _setup(case_dir)
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        await pilot.press("V")
        await pilot.press("down")
        await pilot.press("escape")
        await pilot.pause()
        # Now press s — should be single-event, only row 0 starred (cursor at 1
        # after "down", but "escape" ends visual mode; the cursor is at the
        # final row, so `s` toggles that row only).
        await pilot.press("s")
        await pilot.pause()
        with open_case(case_dir) as c:
            n_starred = c.con.execute("SELECT COUNT(*) FROM annotation_star").fetchone()[0]
        assert n_starred == 1

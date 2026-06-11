from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable

DATA = Path(__file__).parent / "data" / "sample.jsonl"


def _hashes_in_order(case_dir):
    with open_case(case_dir) as c:
        return [r[0] for r in c.con.execute(
            "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
        )]


@pytest.mark.asyncio
async def test_gutter_reflects_star_and_tag_and_comment_counts(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    hashes = _hashes_in_order(case_dir)
    with open_case(case_dir) as c:
        store.set_star(c.con, hashes[0], True)
        store.add_tag(c.con, hashes[1], "susp")
        store.add_tag(c.con, hashes[1], "review")
        store.add_comment(c.con, hashes[2], "first note")
        store.add_comment(c.con, hashes[2], "second note")

    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        star0, cmt0, tag0 = table._annot_for_row(0)
        assert (star0, cmt0, tag0) == (True, 0, 0)
        s1, c1, t1 = table._annot_for_row(1)
        assert (s1, c1, t1) == (False, 0, 2)
        s2, c2, t2 = table._annot_for_row(2)
        assert (s2, c2, t2) == (False, 2, 0)
        assert table._annot_for_row(3) == (False, 0, 0)


@pytest.mark.asyncio
async def test_refresh_annotation_row_picks_up_changes(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table._annot_for_row(0) == (False, 0, 0)
        # Mutate directly via the store
        h = table._hash_list[0]
        store.set_star(table.con, h, True)
        store.add_tag(table.con, h, "x")
        table.refresh_annotation_row(0)
        assert table._annot_for_row(0) == (True, 0, 1)

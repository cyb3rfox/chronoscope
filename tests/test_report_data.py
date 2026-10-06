from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.query.state import QueryState
from chronoscope.report.data import (
    HistogramBucket,
    OverviewData,
    StarredOrCommentedEvent,
    TagStat,
    build_histogram,
    build_overview,
)

DATA = Path(__file__).parent / "data" / "sample.jsonl"

# 20 events, minute-spaced from 1552410000_000_000 to 1552411140_000_000
FIRST = 1552410000_000_000
LAST  = 1552411140_000_000


def _ingested_con(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    return case_dir


def test_build_histogram_default_buckets(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        h = build_histogram(c.con, QueryState(), buckets=60)
    assert len(h) == 60
    # Heights sum to total events.
    assert sum(b.total for b in h) == 20


def test_histogram_bucket_boundaries_are_contiguous(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        h = build_histogram(c.con, QueryState(), buckets=10)
    assert len(h) == 10
    # Contiguous: each bucket's end_usec >= the next bucket's start_usec (equal means no gap).
    for a, b in zip(h, h[1:]):
        assert a.end_usec == b.start_usec


def test_histogram_tagged_and_starred_counts_isolated(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        # Tag the first event, star the second (disjoint).
        store.add_tag(c.con, hashes[0], "susp")
        store.set_star(c.con, hashes[1], True)
        h = build_histogram(c.con, QueryState(), buckets=60)
    assert sum(b.tagged for b in h) == 1
    assert sum(b.starred for b in h) == 1


def test_histogram_empty_filtered_set_returns_empty_list(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        # Filter with an impossible substring — should match no rows.
        s = QueryState().set_substring("message", "ZZZZZZZZZZZ")
        h = build_histogram(c.con, s, buckets=60)
    assert h == []


def test_histogram_respects_bracket_filter(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        # Restrict to rows 5..9 (5 events).
        s = QueryState().set_bracket(
            FIRST + 5 * 60_000_000, FIRST + 9 * 60_000_000 + 1
        )
        h = build_histogram(c.con, s, buckets=10)
    assert sum(b.total for b in h) == 5


def test_histogram_respects_active_tag_filter(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        store.add_tag(c.con, hashes[0], "keep")
        store.add_tag(c.con, hashes[1], "keep")
        store.add_tag(c.con, hashes[2], "drop")
        s = QueryState().set_tag_filter(include={"keep"}, exclude=set())
        h = build_histogram(c.con, s, buckets=10)
    # Only the 2 "keep"-tagged events should show in the filtered histogram totals.
    assert sum(b.total for b in h) == 2
    # Both of them are also tagged — tagged sum equals total here.
    assert sum(b.tagged for b in h) == 2


def test_histogram_buckets_one_returns_single_bucket_covering_all_events(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        h = build_histogram(c.con, QueryState(), buckets=1)
    assert len(h) == 1
    assert h[0].total == 20


def test_overview_counts_match_sql(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        store.add_tag(c.con, hashes[0], "susp")
        store.add_tag(c.con, hashes[1], "susp")
        store.add_tag(c.con, hashes[2], "clean")
        store.set_star(c.con, hashes[0], True)
        store.add_comment(c.con, hashes[5], "hello")
        data = build_overview(c.con, QueryState(), buckets=12)
    assert data.total == 20
    assert data.tagged == 3
    assert data.starred == 1
    assert data.commented == 1
    assert data.first_usec == FIRST
    assert data.last_usec == LAST


def test_overview_per_tag_sorted_by_count_desc(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        store.add_tag(c.con, hashes[0], "a")
        store.add_tag(c.con, hashes[1], "a")
        store.add_tag(c.con, hashes[2], "a")
        store.add_tag(c.con, hashes[3], "b")
        store.add_tag(c.con, hashes[4], "c")
        store.add_tag(c.con, hashes[5], "c")
        data = build_overview(c.con, QueryState())
    names = [t.tag for t in data.per_tag]
    assert names == ["a", "c", "b"]
    assert [t.count for t in data.per_tag] == [3, 2, 1]


def test_overview_empty_case_has_none_time_and_empty_lists(case_dir):
    init_case(case_dir, name="demo")
    with open_case(case_dir) as c:
        data = build_overview(c.con, QueryState())
    assert data.total == 0
    assert data.first_usec is None
    assert data.last_usec is None
    assert data.per_tag == []
    assert data.histogram == []


def test_overview_starred_events_capped_at_ten(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        for h in hashes[:15]:
            store.set_star(c.con, h, True)
        data = build_overview(c.con, QueryState())
    assert len(data.starred_events) == 10
    assert all(isinstance(e, StarredOrCommentedEvent) for e in data.starred_events)


def test_overview_filter_summary_echoes_state(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        s = QueryState().set_substring("message", "evil")
        data = build_overview(c.con, s)
    assert data.filter_summary == s.summary()


def test_overview_with_active_tag_filter_qualifies_correctly(case_dir):
    _ingested_con(case_dir)
    with open_case(case_dir) as c:
        hashes = [
            r[0]
            for r in c.con.execute(
                "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
            )
        ]
        store.add_tag(c.con, hashes[0], "keep")
        store.add_tag(c.con, hashes[1], "keep")
        store.add_tag(c.con, hashes[2], "keep")
        store.set_star(c.con, hashes[0], True)
        store.add_comment(c.con, hashes[1], "note")
        s = QueryState().set_tag_filter(include={"keep"}, exclude=set())
        data = build_overview(c.con, s)
    assert data.total == 3
    assert data.tagged == 3
    assert data.starred == 1
    assert data.commented == 1
    assert len(data.per_tag) == 1
    assert data.per_tag[0].tag == "keep"

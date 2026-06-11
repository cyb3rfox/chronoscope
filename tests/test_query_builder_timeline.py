from __future__ import annotations

from chronoscope.query.builder import build_sql
from chronoscope.query.state import QueryState


def test_empty_timeline_filter_emits_no_clause():
    s = QueryState()
    where, _, _ = build_sql(s)
    assert "timeline_id" not in where


def test_single_timeline_filter_emits_in_clause():
    s = QueryState().set_timeline_filter({"tl_1"})
    where, params, _ = build_sql(s)
    assert "timeline_id IN (?)" in where
    assert params == ("tl_1",)


def test_multi_timeline_filter_sorted_params():
    s = QueryState().set_timeline_filter({"tl_b", "tl_a", "tl_c"})
    where, params, _ = build_sql(s)
    assert "timeline_id IN (?, ?, ?)" in where
    assert list(params) == ["tl_a", "tl_b", "tl_c"]


def test_timeline_filter_composes_with_categorical():
    s = (
        QueryState()
        .set_timeline_filter({"tl_1"})
        .set_categorical("data_type", include={"dt"}, exclude=set())
    )
    where, params, _ = build_sql(s)
    assert " AND " in where
    assert "timeline_id IN (?)" in where
    assert "data_type IN (?)" in where
    assert where.count("?") == len(params)

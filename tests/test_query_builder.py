from __future__ import annotations

import pytest

from chronoscope.query.builder import build_sql
from chronoscope.query.state import QueryState, Sort


def test_empty_state_produces_no_where():
    where, params, order_by = build_sql(QueryState())
    assert where == ""
    assert params == ()
    assert order_by == "ts_usec ASC, id ASC"


def test_categorical_include_only():
    s = QueryState().set_categorical("data_type", include={"a", "b"}, exclude=set())
    where, params, _ = build_sql(s)
    assert where == "data_type IN (?, ?)"
    assert sorted(params) == ["a", "b"]


def test_categorical_exclude_only():
    s = QueryState().set_categorical("data_type", include=set(), exclude={"c"})
    where, params, _ = build_sql(s)
    assert where == "data_type NOT IN (?)"
    assert params == ("c",)


def test_categorical_include_and_exclude_both_applied():
    s = QueryState().set_categorical("data_type", include={"a"}, exclude={"b"})
    where, params, _ = build_sql(s)
    assert "data_type IN (?)" in where
    assert "data_type NOT IN (?)" in where
    assert "AND" in where
    assert sorted(params) == ["a", "b"]


def test_substring_uses_lower_like_lower():
    s = QueryState().set_substring("message", "EVIL")
    where, params, _ = build_sql(s)
    assert where == "LOWER(message) LIKE LOWER(?)"
    assert params == ("%EVIL%",)


def test_extra_text_substring_filter_compiles():
    s = QueryState().set_substring("extra_text", "google.com")
    where, params, _ = build_sql(s)
    assert where == "LOWER(extra_text) LIKE LOWER(?)"
    assert params == ("%google.com%",)


def test_multiple_columns_anded():
    s = (
        QueryState()
        .set_categorical("data_type", include={"a"}, exclude=set())
        .set_substring("message", "foo")
    )
    where, params, _ = build_sql(s)
    assert " AND " in where
    assert "data_type IN (?)" in where
    assert "LOWER(message) LIKE LOWER(?)" in where
    assert len(params) == 2


def test_sort_direction_descending():
    s = QueryState().set_sort("data_type", "DESC")
    _, _, order_by = build_sql(s)
    assert order_by == "data_type DESC, id ASC"


def test_unknown_sort_column_via_bypass_raises():
    from dataclasses import replace
    bad = replace(QueryState(), sort=Sort(column="not_whitelisted", direction="ASC"))
    with pytest.raises(ValueError):
        build_sql(bad)


def test_placeholder_count_matches_params():
    s = (
        QueryState()
        .set_categorical("data_type", include={"a", "b", "c"}, exclude={"d", "e"})
        .set_categorical("parser", include={"x"}, exclude=set())
        .set_substring("message", "foo")
        .set_substring("display_name", "bar")
    )
    where, params, _ = build_sql(s)
    assert where.count("?") == len(params)

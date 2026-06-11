from __future__ import annotations

from chronoscope.query.builder import build_sql
from chronoscope.query.state import QueryState


def test_bracket_start_only_clause():
    s = QueryState().set_bracket_start(100)
    where, params, _ = build_sql(s)
    assert "ts_usec >= ?" in where
    assert "ts_usec <= ?" not in where
    assert params == (100,)


def test_bracket_end_only_clause():
    s = QueryState().set_bracket_end(400)
    where, params, _ = build_sql(s)
    assert "ts_usec <= ?" in where
    assert "ts_usec >= ?" not in where
    assert params == (400,)


def test_bracket_both_sides_anded():
    s = QueryState().set_bracket(100, 400)
    where, params, _ = build_sql(s)
    assert "ts_usec >= ?" in where
    assert "ts_usec <= ?" in where
    assert " AND " in where
    assert list(params) == [100, 400]


def test_empty_bracket_emits_no_clause():
    s = QueryState()
    where, params, _ = build_sql(s)
    assert "ts_usec" not in where
    assert params == ()


def test_bracket_composes_with_other_filters():
    s = (
        QueryState()
        .set_bracket(100, 400)
        .set_categorical("data_type", include={"dt"}, exclude=set())
        .set_substring("message", "foo")
    )
    where, params, _ = build_sql(s)
    assert where.count("?") == len(params)
    assert "ts_usec >= ?" in where
    assert "ts_usec <= ?" in where
    assert "data_type IN (?)" in where
    assert "LOWER(message) LIKE LOWER(?)" in where

from __future__ import annotations

from chronoscope.query.builder import build_sql
from chronoscope.query.state import QueryState


def test_only_starred_filter():
    s = QueryState().set_star_filter("only_starred")
    where, params, _ = build_sql(s)
    assert "event_hash IN (SELECT event_hash FROM annotation_star)" in where
    assert params == ()


def test_only_unstarred_filter():
    s = QueryState().set_star_filter("only_unstarred")
    where, _, _ = build_sql(s)
    assert "event_hash NOT IN (SELECT event_hash FROM annotation_star)" in where


def test_tag_include_filter():
    s = QueryState().set_tag_filter(include={"a", "b"}, exclude=set())
    where, params, _ = build_sql(s)
    assert "event_hash IN (SELECT event_hash FROM annotation_tag WHERE tag IN (?, ?))" in where
    assert sorted(params) == ["a", "b"]


def test_tag_exclude_filter():
    s = QueryState().set_tag_filter(include=set(), exclude={"x"})
    where, params, _ = build_sql(s)
    assert "event_hash NOT IN (SELECT event_hash FROM annotation_tag WHERE tag IN (?))" in where
    assert params == ("x",)


def test_mixed_with_categorical_and_substring():
    s = (QueryState()
         .set_categorical("data_type", include={"dt"}, exclude=set())
         .set_substring("message", "foo")
         .set_tag_filter(include={"a"}, exclude=set())
         .set_star_filter("only_starred"))
    where, params, _ = build_sql(s)
    assert where.count(" AND ") == 3
    assert where.count("?") == len(params)

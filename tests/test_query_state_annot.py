from __future__ import annotations

from chronoscope.query.state import CategoricalFilter, QueryState


def test_default_tag_filter_is_empty():
    s = QueryState()
    assert s.tag_filter.is_empty()
    assert s.star_filter is None
    assert s.active_filter_count() == 0


def test_set_tag_filter_updates_state():
    s = QueryState().set_tag_filter(include={"susp"}, exclude=set())
    assert s.tag_filter.include == frozenset({"susp"})
    assert s.active_filter_count() == 1


def test_set_tag_filter_empty_clears():
    s = QueryState().set_tag_filter(include={"x"}, exclude=set())
    s = s.set_tag_filter(include=set(), exclude=set())
    assert s.tag_filter.is_empty()
    assert s.active_filter_count() == 0


def test_set_star_filter():
    s = QueryState().set_star_filter("only_starred")
    assert s.star_filter == "only_starred"
    assert s.active_filter_count() == 1
    s2 = s.set_star_filter(None)
    assert s2.star_filter is None
    assert s2.active_filter_count() == 0


def test_set_star_filter_rejects_invalid():
    import pytest
    with pytest.raises(ValueError):
        QueryState().set_star_filter("bogus")


def test_clear_all_resets_tag_and_star():
    s = (QueryState()
         .set_tag_filter(include={"x"}, exclude=set())
         .set_star_filter("only_starred"))
    s = s.clear_all()
    assert s.active_filter_count() == 0
    assert s.tag_filter.is_empty()
    assert s.star_filter is None


def test_summary_mentions_tag_and_star_filters():
    s = (QueryState()
         .set_tag_filter(include={"a", "b"}, exclude={"c"})
         .set_star_filter("only_starred"))
    out = s.summary()
    assert "tags" in out and "IN 2" in out and "NOT 1" in out
    assert "stars" in out and "only_starred" in out

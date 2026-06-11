from __future__ import annotations

from chronoscope.query.state import QueryState


def test_default_timeline_filter_is_empty():
    s = QueryState()
    assert s.timeline_filter == frozenset()
    assert s.active_filter_count() == 0


def test_set_timeline_filter_returns_new_state():
    s0 = QueryState()
    s1 = s0.set_timeline_filter({"a", "b"})
    assert s0.timeline_filter == frozenset()
    assert s1.timeline_filter == frozenset({"a", "b"})
    assert s1.active_filter_count() == 1


def test_set_timeline_filter_empty_clears():
    s = QueryState().set_timeline_filter({"a"}).set_timeline_filter(set())
    assert s.timeline_filter == frozenset()
    assert s.active_filter_count() == 0


def test_clear_all_resets_timeline_filter():
    s = QueryState().set_timeline_filter({"a"}).clear_all()
    assert s.timeline_filter == frozenset()

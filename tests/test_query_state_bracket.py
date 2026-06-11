from __future__ import annotations

from chronoscope.query.state import QueryState, TimeBracket


def test_time_bracket_empty_default():
    tb = TimeBracket()
    assert tb.is_empty() is True
    assert tb.start_usec is None and tb.end_usec is None
    assert tb.span_usec() is None


def test_time_bracket_span_when_both_set():
    tb = TimeBracket(100, 400)
    assert tb.span_usec() == 300
    assert tb.is_empty() is False


def test_time_bracket_span_none_when_half_set():
    assert TimeBracket(100, None).span_usec() is None
    assert TimeBracket(None, 400).span_usec() is None


def test_default_query_state_bracket_is_empty():
    s = QueryState()
    assert s.bracket.is_empty() is True
    assert s.active_filter_count() == 0


def test_set_bracket_start_returns_new_state():
    s0 = QueryState()
    s1 = s0.set_bracket_start(100)
    assert s0.bracket.is_empty() is True
    assert s1.bracket.start_usec == 100
    assert s1.bracket.end_usec is None
    assert s1.active_filter_count() == 1


def test_set_bracket_end_returns_new_state():
    s = QueryState().set_bracket_end(400)
    assert s.bracket.end_usec == 400
    assert s.bracket.start_usec is None
    assert s.active_filter_count() == 1


def test_set_bracket_both():
    s = QueryState().set_bracket(100, 400)
    assert s.bracket.start_usec == 100
    assert s.bracket.end_usec == 400


def test_set_bracket_none_none_clears():
    s = QueryState().set_bracket(100, 400).set_bracket(None, None)
    assert s.bracket.is_empty()
    assert s.active_filter_count() == 0


def test_clear_bracket():
    s0 = QueryState().set_bracket(100, 400)
    s1 = s0.clear_bracket()
    assert s1.bracket.is_empty()
    assert s0.bracket.is_empty() is False


def test_clear_all_resets_bracket():
    s = (
        QueryState()
        .set_bracket(100, 400)
        .set_categorical("data_type", include={"a"}, exclude=set())
    )
    cleared = s.clear_all()
    assert cleared.bracket.is_empty()
    assert cleared.active_filter_count() == 0


def test_summary_does_not_mention_bracket():
    s = QueryState().set_bracket(100, 400)
    assert "⧗" not in s.summary()
    assert "bracket" not in s.summary().lower()

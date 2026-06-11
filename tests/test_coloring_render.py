from __future__ import annotations

from chronoscope.coloring.render import colorize_timestamp


def test_no_colors_returns_plain_text():
    t = colorize_timestamp("2026-05-08T22:30:00+00:00", ())
    assert t.plain == "2026-05-08T22:30:00+00:00"
    assert t.spans == []


def test_single_color_styles_whole_string():
    t = colorize_timestamp("2026-05-08T22:30:00+00:00", ("red",))
    assert t.plain == "2026-05-08T22:30:00+00:00"
    assert t.style == "red"


def test_multiple_colors_split_into_segments():
    text = "2026-05-08T22:30:00+00:00"
    t = colorize_timestamp(text, ("red", "blue", "green"))
    # The plain text is preserved exactly...
    assert t.plain == text
    # ...and split into three contiguous, non-overlapping styled spans that
    # together cover the whole string.
    spans = sorted(t.spans, key=lambda s: s.start)
    assert len(spans) == 3
    assert spans[0].start == 0
    assert spans[-1].end == len(text)
    for a, b in zip(spans, spans[1:]):
        assert a.end == b.start
    assert [s.style for s in spans] == ["red", "blue", "green"]

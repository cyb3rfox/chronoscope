from __future__ import annotations

from chronoscope.tui.bindings import (
    KeyBinding,
    bindings_with_prefix,
    to_textual,
)


def _mixed() -> list[KeyBinding]:
    return [
        KeyBinding("b", "prefix_bracket", "Bracket…",   ("time",)),
        KeyBinding("f", "open_filters",   "Filter",     ("always", "filter")),
        KeyBinding("o", "bracket_open",   "Open editor", ("time",), prefix="bracket"),
        KeyBinding("c", "bracket_clear",  "Clear",       ("time",), prefix="bracket"),
    ]


def test_to_textual_skips_prefixed_bindings():
    out = to_textual(_mixed())
    keys = [k for (k, _, _) in out]
    assert "b" in keys
    assert "f" in keys
    assert "o" not in keys
    assert "c" not in keys


def test_to_textual_preserves_label_and_action_for_non_prefixed():
    out = to_textual(_mixed())
    assert ("f", "open_filters", "Filter") in out
    assert ("b", "prefix_bracket", "Bracket…") in out


def test_bindings_with_prefix_matches_only_named_prefix():
    found = bindings_with_prefix(_mixed(), "bracket")
    assert [b.key for b in found] == ["o", "c"]


def test_bindings_with_prefix_empty_when_no_match():
    assert bindings_with_prefix(_mixed(), "ghost") == []

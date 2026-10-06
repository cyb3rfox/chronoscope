from __future__ import annotations

from chronoscope.core.timeline_colors import PALETTE, resolve_color


def test_palette_non_empty_six_colors():
    assert len(PALETTE) == 6
    assert PALETTE == ("cyan", "magenta", "yellow", "green", "blue", "red")


def test_resolve_color_stored_overrides_palette():
    assert resolve_color("#ff00aa", 0) == "#ff00aa"
    assert resolve_color("banana", 3) == "banana"


def test_resolve_color_cycles_palette_when_none():
    assert resolve_color(None, 0) == "cyan"
    assert resolve_color(None, 1) == "magenta"
    assert resolve_color(None, 5) == "red"
    assert resolve_color(None, 6) == "cyan"
    assert resolve_color(None, 13) == "magenta"


def test_resolve_color_empty_string_uses_palette():
    assert resolve_color("", 0) == "cyan"

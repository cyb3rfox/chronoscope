from __future__ import annotations

import pytest

from chronoscope.tui.bindings import (
    GROUPS,
    GROUP_IDS,
    KeyBinding,
    bindings_in_group,
    groups_of,
    to_textual,
    validate,
)


def _sample():
    return [
        KeyBinding("f", "open_filters", "Filter/Sort", ("always", "filter")),
        KeyBinding("s", "toggle_star",  "Toggle star", ("annot",)),
        KeyBinding("?", "help",         "Help",        ("always",)),
    ]


def test_groups_registry_has_expected_ids():
    expected = {"always", "nav", "annot", "filter", "visual", "time"}
    assert expected <= GROUP_IDS


def test_validate_rejects_empty_groups():
    with pytest.raises(ValueError):
        validate(KeyBinding("x", "act", "Label", ()))


def test_validate_rejects_unknown_group():
    with pytest.raises(ValueError):
        validate(KeyBinding("x", "act", "Label", ("bogus",)))


def test_validate_accepts_valid():
    validate(KeyBinding("x", "act", "Label", ("always", "nav")))


def test_to_textual_strips_metadata():
    out = to_textual(_sample())
    assert out == [
        ("f", "open_filters", "Filter/Sort"),
        ("s", "toggle_star",  "Toggle star"),
        ("?", "help",         "Help"),
    ]


def test_bindings_in_group_filters():
    bs = _sample()
    always = bindings_in_group(bs, "always")
    assert {b.key for b in always} == {"f", "?"}
    annot = bindings_in_group(bs, "annot")
    assert [b.key for b in annot] == ["s"]


def test_bindings_in_group_unknown_returns_empty():
    assert bindings_in_group(_sample(), "nonexistent") == []


def test_groups_of_known_key():
    assert groups_of(_sample(), "f") == ("always", "filter")


def test_groups_of_unknown_key_returns_empty():
    assert groups_of(_sample(), "z") == ()


def test_keybinding_prefix_defaults_to_none():
    b = KeyBinding("b", "prefix_bracket", "Time bracket", ("time",))
    assert b.prefix is None

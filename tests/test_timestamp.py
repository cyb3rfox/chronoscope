from __future__ import annotations

import pytest

from chronoscope.query.timestamp import parse_jump_target


# Anchor: 2019-03-12 17:14:00 UTC in microseconds
ANCHOR = 1552410840_000_000


def test_iso_with_z():
    assert parse_jump_target("2019-03-12T17:13:42Z", ANCHOR) == 1552410822_000_000


def test_iso_with_space_and_seconds():
    assert parse_jump_target("2019-03-12 17:13:42", ANCHOR) == 1552410822_000_000


def test_iso_without_seconds():
    assert parse_jump_target("2019-03-12 17:13", ANCHOR) == 1552410780_000_000


def test_iso_date_only_is_midnight_utc():
    assert parse_jump_target("2019-03-12", ANCHOR) == 1552348800_000_000


def test_relative_minus_minutes():
    assert parse_jump_target("-5m", ANCHOR) == ANCHOR - 5 * 60 * 1_000_000


def test_relative_plus_hours():
    assert parse_jump_target("+2h", ANCHOR) == ANCHOR + 2 * 3600 * 1_000_000


def test_relative_minus_days():
    assert parse_jump_target("-7d", ANCHOR) == ANCHOR - 7 * 86400 * 1_000_000


def test_relative_seconds_and_weeks():
    assert parse_jump_target("-30s", ANCHOR) == ANCHOR - 30 * 1_000_000
    assert parse_jump_target("+1w", ANCHOR) == ANCHOR + 7 * 86400 * 1_000_000


def test_relative_without_sign_rejected():
    with pytest.raises(ValueError):
        parse_jump_target("5m", ANCHOR)


def test_invalid_format_raises():
    with pytest.raises(ValueError):
        parse_jump_target("tomorrow", ANCHOR)
    with pytest.raises(ValueError):
        parse_jump_target("", ANCHOR)
    with pytest.raises(ValueError):
        parse_jump_target("2019-13-45", ANCHOR)

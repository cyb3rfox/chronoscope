from __future__ import annotations

import pytest

from chronoscope.coloring.rules import (
    ColorRules,
    OffHoursRule,
    default_rules,
)


def _ts_at_hour(hour: int) -> int:
    """ts_usec at HH:30:00 on 1970-01-01 UTC, so we exercise mid-hour math."""
    return (hour * 3600 + 30 * 60) * 1_000_000


def test_off_hours_simple_window_inclusive_start_exclusive_end():
    r = OffHoursRule(id="x", name="x", enabled=True, color="red",
                     start_hour=9, end_hour=17)
    assert r.matches(_ts_at_hour(9))
    assert r.matches(_ts_at_hour(16))
    assert not r.matches(_ts_at_hour(17))
    assert not r.matches(_ts_at_hour(8))


def test_off_hours_wrap_around_midnight():
    r = OffHoursRule(id="x", name="x", enabled=True, color="red",
                     start_hour=22, end_hour=4)
    assert r.matches(_ts_at_hour(22))
    assert r.matches(_ts_at_hour(23))
    assert r.matches(_ts_at_hour(0))
    assert r.matches(_ts_at_hour(3))
    assert not r.matches(_ts_at_hour(4))
    assert not r.matches(_ts_at_hour(12))


def test_off_hours_empty_window_never_matches():
    r = OffHoursRule(id="x", name="x", enabled=True, color="red",
                     start_hour=5, end_hour=5)
    for h in range(24):
        assert not r.matches(_ts_at_hour(h))


def test_off_hours_zero_or_negative_ts_does_not_match():
    r = OffHoursRule(id="x", name="x", enabled=True, color="red",
                     start_hour=0, end_hour=24 - 1)
    # ts_usec == 0 is a sentinel for "no timestamp" in this app.
    assert not r.matches(0)
    assert not r.matches(-1)


def test_off_hours_rejects_out_of_range_hours():
    with pytest.raises(ValueError):
        OffHoursRule(id="x", name="x", enabled=True, color="red",
                     start_hour=24, end_hour=0)
    with pytest.raises(ValueError):
        OffHoursRule(id="x", name="x", enabled=True, color="red",
                     start_hour=0, end_hour=-1)


def test_color_rules_matching_skips_disabled_and_keeps_order():
    r1 = OffHoursRule(id="a", name="A", enabled=True,  color="red",
                     start_hour=22, end_hour=4)
    r2 = OffHoursRule(id="b", name="B", enabled=False, color="blue",
                     start_hour=22, end_hour=4)
    r3 = OffHoursRule(id="c", name="C", enabled=True,  color="green",
                     start_hour=0,  end_hour=12)
    rules = ColorRules(rules=(r1, r2, r3))
    matches = rules.matching(_ts_at_hour(2))
    assert [r.id for r in matches] == ["a", "c"]


def test_color_rules_with_rule_replaces_in_place():
    r1 = OffHoursRule(id="a", name="A", enabled=True,  color="red",
                     start_hour=22, end_hour=4)
    rules = ColorRules(rules=(r1,))
    new = OffHoursRule(id="a", name="A renamed", enabled=False, color="blue",
                      start_hour=22, end_hour=4)
    rules2 = rules.with_rule(new)
    assert len(rules2.rules) == 1
    assert rules2.rules[0].name == "A renamed"
    assert rules2.rules[0].enabled is False


def test_color_rules_with_rule_appends_when_id_missing():
    rules = ColorRules(rules=())
    r = OffHoursRule(id="x", name="x", enabled=True, color="red",
                    start_hour=0, end_hour=1)
    assert rules.with_rule(r).rules == (r,)


def test_default_rules_seeds_off_hours_disabled():
    rules = default_rules()
    assert len(rules.rules) == 1
    only = rules.rules[0]
    assert only.id == "off_hours"
    assert only.enabled is False
    assert only.start_hour == 22
    assert only.end_hour == 4

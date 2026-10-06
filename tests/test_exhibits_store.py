from __future__ import annotations

import sqlite3

import pytest

from chronoscope.core.exhibits import (
    Exhibit,
    add_exhibit,
    count_exhibits,
    get_exhibit,
    list_exhibits,
    remove_exhibit,
    update_exhibit,
)
from chronoscope.core.schema import migrate


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    migrate(c)
    yield c
    c.close()


def test_add_and_get_round_trip(con):
    eid = add_exhibit(con, title="evil.ps1", description="dropper", body="whoami\n")
    e = get_exhibit(con, eid)
    assert isinstance(e, Exhibit)
    assert e.title == "evil.ps1"
    assert e.description == "dropper"
    assert e.body == "whoami\n"
    assert e.created_at and e.updated_at


def test_add_strips_title_and_requires_nonempty(con):
    eid = add_exhibit(con, title="  spaced  ", description="", body="x")
    assert get_exhibit(con, eid).title == "spaced"
    with pytest.raises(ValueError):
        add_exhibit(con, title="   ", description="", body="x")
    with pytest.raises(ValueError):
        add_exhibit(con, title="t", description="", body="")


def test_list_is_ordered_by_id(con):
    a = add_exhibit(con, title="a", description="", body="1")
    b = add_exhibit(con, title="b", description="", body="2")
    ids = [e.id for e in list_exhibits(con)]
    assert ids == [a, b]


def test_get_missing_returns_none(con):
    assert get_exhibit(con, 999) is None


def test_update_changes_fields_and_bumps_updated_at(con):
    eid = add_exhibit(con, title="t", description="d", body="b")
    before = get_exhibit(con, eid)
    update_exhibit(con, eid, title="t2", description="d2", body="b2")
    after = get_exhibit(con, eid)
    assert (after.title, after.description, after.body) == ("t2", "d2", "b2")
    assert after.created_at == before.created_at
    assert after.updated_at >= before.updated_at


def test_update_rejects_empty(con):
    eid = add_exhibit(con, title="t", description="d", body="b")
    with pytest.raises(ValueError):
        update_exhibit(con, eid, title="", description="d", body="b")
    with pytest.raises(ValueError):
        update_exhibit(con, eid, title="t", description="d", body="")


def test_remove_and_count(con):
    a = add_exhibit(con, title="a", description="", body="1")
    add_exhibit(con, title="b", description="", body="2")
    assert count_exhibits(con) == 2
    remove_exhibit(con, a)
    assert count_exhibits(con) == 1
    assert get_exhibit(con, a) is None

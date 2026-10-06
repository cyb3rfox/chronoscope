from __future__ import annotations

import sqlite3

import pytest

from chronoscope.annotations.bulk import bulk_star, bulk_tag, bulk_untag
from chronoscope.annotations.store import get_star, tags_for
from chronoscope.core.schema import migrate


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    migrate(c)
    yield c
    c.close()


def _h(i: int) -> bytes:
    return bytes([i]) * 32


def test_bulk_star_on(con):
    hashes = [_h(1), _h(2), _h(3)]
    bulk_star(con, hashes, on=True)
    for h in hashes:
        assert get_star(con, h) is True


def test_bulk_star_off(con):
    hashes = [_h(1), _h(2)]
    bulk_star(con, hashes, on=True)
    bulk_star(con, hashes, on=False)
    for h in hashes:
        assert get_star(con, h) is False


def test_bulk_tag_applies_to_all(con):
    hashes = [_h(1), _h(2), _h(3)]
    bulk_tag(con, hashes, "susp")
    for h in hashes:
        assert "susp" in tags_for(con, h)


def test_bulk_untag(con):
    hashes = [_h(1), _h(2)]
    bulk_tag(con, hashes, "x")
    bulk_untag(con, hashes, "x")
    for h in hashes:
        assert tags_for(con, h) == []


def test_bulk_tag_rolls_back_on_invalid_tag(con):
    hashes = [_h(1), _h(2)]
    with pytest.raises(ValueError):
        bulk_tag(con, hashes, "   ")
    for h in hashes:
        assert tags_for(con, h) == []


def test_bulk_star_empty_iterable_is_noop(con):
    bulk_star(con, [], on=True)
    n = con.execute("SELECT COUNT(*) FROM annotation_star").fetchone()[0]
    assert n == 0

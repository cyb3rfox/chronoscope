from __future__ import annotations

import sqlite3

import pytest

from chronoscope.annotations.store import (
    add_comment,
    add_tag,
    all_tags_with_counts,
    comments_for,
    delete_comment,
    delete_tag,
    get_star,
    latest_comment_id,
    remove_tag,
    rename_tag,
    set_star,
    tag_normalize,
    tags_for,
    toggle_star,
    update_comment,
)
from chronoscope.core.schema import migrate

HASH_A = b"\x01" * 32
HASH_B = b"\x02" * 32


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    migrate(c)
    yield c
    c.close()


def test_tag_normalize_lowercases_and_trims():
    assert tag_normalize("  Foo  ") == "foo"


def test_tag_normalize_collapses_whitespace_to_dash():
    assert tag_normalize("lateral movement") == "lateral-movement"
    assert tag_normalize("a\t  b\nc") == "a-b-c"


def test_tag_normalize_idempotent():
    once = tag_normalize("Some Tag")
    assert tag_normalize(once) == once


def test_tag_normalize_empty_raises():
    with pytest.raises(ValueError):
        tag_normalize("")
    with pytest.raises(ValueError):
        tag_normalize("   ")


def test_star_roundtrip(con):
    assert get_star(con, HASH_A) is False
    set_star(con, HASH_A, True)
    assert get_star(con, HASH_A) is True
    set_star(con, HASH_A, True)
    assert get_star(con, HASH_A) is True
    set_star(con, HASH_A, False)
    assert get_star(con, HASH_A) is False


def test_toggle_star_returns_new_state(con):
    assert toggle_star(con, HASH_A) is True
    assert toggle_star(con, HASH_A) is False


def test_add_tag_normalizes(con):
    add_tag(con, HASH_A, " Suspicious ")
    assert tags_for(con, HASH_A) == ["suspicious"]


def test_add_tag_idempotent(con):
    add_tag(con, HASH_A, "foo")
    add_tag(con, HASH_A, "foo")
    assert tags_for(con, HASH_A) == ["foo"]


def test_remove_tag(con):
    add_tag(con, HASH_A, "foo")
    add_tag(con, HASH_A, "bar")
    remove_tag(con, HASH_A, "foo")
    assert tags_for(con, HASH_A) == ["bar"]


def test_all_tags_with_counts(con):
    add_tag(con, HASH_A, "x")
    add_tag(con, HASH_B, "x")
    add_tag(con, HASH_A, "y")
    assert all_tags_with_counts(con) == [("x", 2), ("y", 1)]


def test_rename_tag_merges_on_collision(con):
    add_tag(con, HASH_A, "old")
    add_tag(con, HASH_B, "old")
    add_tag(con, HASH_A, "new")
    rename_tag(con, "old", "new")
    assert tags_for(con, HASH_A) == ["new"]
    assert tags_for(con, HASH_B) == ["new"]
    assert all_tags_with_counts(con) == [("new", 2)]


def test_delete_tag(con):
    add_tag(con, HASH_A, "x")
    add_tag(con, HASH_B, "x")
    add_tag(con, HASH_B, "y")
    removed = delete_tag(con, "x")
    assert removed == 2
    assert all_tags_with_counts(con) == [("y", 1)]


def test_add_and_list_comments(con):
    id1 = add_comment(con, HASH_A, "first")
    id2 = add_comment(con, HASH_A, "second")
    cs = comments_for(con, HASH_A)
    assert [c["id"] for c in cs] == [id1, id2]
    assert [c["body"] for c in cs] == ["first", "second"]


def test_update_comment_changes_body_and_updated_at(con):
    cid = add_comment(con, HASH_A, "x")
    update_comment(con, cid, "y")
    cs = comments_for(con, HASH_A)
    assert cs[0]["body"] == "y"
    assert cs[0]["updated_at"] >= cs[0]["created_at"]


def test_delete_comment(con):
    cid = add_comment(con, HASH_A, "x")
    delete_comment(con, cid)
    assert comments_for(con, HASH_A) == []


def test_latest_comment_id(con):
    assert latest_comment_id(con, HASH_A) is None
    id1 = add_comment(con, HASH_A, "x")
    id2 = add_comment(con, HASH_A, "y")
    assert latest_comment_id(con, HASH_A) == id2

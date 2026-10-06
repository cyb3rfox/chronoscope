from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronoscope.ai.settings import AISettings
from chronoscope.ai.toolset import build_toolset
from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.query.state import QueryState

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.fixture
def case_with_data(case_dir):
    init_case(case_dir, name="t")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        yield c


def _call(reg, name, args):
    return json.loads(reg.call(name, json.dumps(args)))


def _first_event_id(con) -> int:
    return int(con.execute(
        "SELECT id FROM event ORDER BY ts_usec ASC, id ASC LIMIT 1"
    ).fetchone()[0])


def _hash_of(con, event_id: int) -> bytes:
    return bytes(con.execute(
        "SELECT event_hash FROM event WHERE id = ?", (event_id,)
    ).fetchone()[0])


def test_tag_event_persists_through_store(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    eid = _first_event_id(case_with_data.con)
    out = _call(reg, "tag_event", {"event_id": eid, "tag": "lateral-movement"})
    assert out["ok"] is True
    h = _hash_of(case_with_data.con, eid)
    assert "lateral-movement" in store.tags_for(case_with_data.con, h)


def test_untag_event_drops_the_tag(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    eid = _first_event_id(case_with_data.con)
    _call(reg, "tag_event", {"event_id": eid, "tag": "x"})
    _call(reg, "untag_event", {"event_id": eid, "tag": "x"})
    h = _hash_of(case_with_data.con, eid)
    assert "x" not in store.tags_for(case_with_data.con, h)


def test_tag_event_unknown_id_returns_error(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "tag_event", {"event_id": 99999, "tag": "x"})
    assert "no event with id" in out["error"]


def test_tag_event_blank_tag_returns_error(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    eid = _first_event_id(case_with_data.con)
    out = _call(reg, "tag_event", {"event_id": eid, "tag": "   "})
    assert "non-empty" in out["error"]


def test_add_event_comment_writes_to_store(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    eid = _first_event_id(case_with_data.con)
    out = _call(reg, "add_event_comment",
                {"event_id": eid, "body": "looks suspicious"})
    assert out["ok"] is True
    h = _hash_of(case_with_data.con, eid)
    bodies = [c["body"] for c in store.comments_for(case_with_data.con, h)]
    assert "looks suspicious" in bodies


def test_add_event_comment_blank_body_returns_error(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    eid = _first_event_id(case_with_data.con)
    out = _call(reg, "add_event_comment", {"event_id": eid, "body": "   "})
    assert "non-empty" in out["error"]


def test_apply_filters_routes_through_callback(case_with_data):
    captured: list[QueryState] = []
    reg = build_toolset(
        case_with_data, AISettings(),
        apply_filters_cb=lambda s: captured.append(s),
    )
    out = _call(reg, "apply_filters",
                {"filters": {"data_type_in": ["chrome:history:page_visited"]}})
    assert out["ok"] is True
    assert out["active_filter_count"] == 1
    assert len(captured) == 1
    cf = captured[0].categorical["data_type"]
    assert "chrome:history:page_visited" in cf.include


def test_clear_filters_passes_empty_state_to_callback(case_with_data):
    captured: list[QueryState] = []
    reg = build_toolset(
        case_with_data, AISettings(),
        apply_filters_cb=lambda s: captured.append(s),
    )
    _call(reg, "clear_filters", {})
    assert len(captured) == 1
    assert captured[0].active_filter_count() == 0


def test_apply_filters_without_callback_returns_helpful_error(case_with_data):
    reg = build_toolset(case_with_data, AISettings())  # no callback
    out = _call(reg, "apply_filters", {"filters": {}})
    assert "no UI" in out["error"]


def test_apply_filters_unknown_field_returns_error(case_with_data):
    reg = build_toolset(
        case_with_data, AISettings(),
        apply_filters_cb=lambda s: None,
    )
    out = _call(reg, "apply_filters", {"filters": {"bogus": [1]}})
    assert "unknown filter fields" in out["error"]

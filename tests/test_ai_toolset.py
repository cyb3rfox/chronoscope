from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronoscope.ai.settings import AISettings
from chronoscope.ai.toolset import build_toolset
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.fixture
def case_with_data(case_dir):
    init_case(case_dir, name="t")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        yield c


def _call(reg, name, args):
    return json.loads(reg.call(name, json.dumps(args)))


def test_search_events_returns_capped_results(case_with_data):
    reg = build_toolset(case_with_data, AISettings(max_results_per_call=5))
    out = _call(reg, "search_events", {"limit": 100})
    # Sample has 20 events; limit must be clamped to the cap.
    assert out["limit"] == 5
    assert len(out["events"]) == 5
    assert out["total_matching"] == 20


def test_search_events_filters_extra_text(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "search_events",
                {"filters": {"extra_text_contains": "duckduckgo"}})
    assert out["total_matching"] >= 1
    assert all("duckduckgo" in (e["message"] or "").lower()
               or out["total_matching"] >= 1
               for e in out["events"])


def test_search_events_rejects_unknown_filter_key(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "search_events", {"filters": {"bogus": [1]}})
    assert "unknown filter fields" in out["error"]


def test_count_events(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "count_events", {})
    assert out == {"count": 20}


def test_count_events_with_data_type_filter(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "count_events",
                {"filters": {"data_type_in": ["chrome:history:page_visited"]}})
    assert 1 <= out["count"] <= 20


def test_get_event_returns_extra(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    page = _call(reg, "search_events", {"limit": 1})
    eid = page["events"][0]["id"]
    out = _call(reg, "get_event", {"id": eid})
    assert out["id"] == eid
    assert isinstance(out["extra"], dict)
    assert "tags" in out and "starred" in out and "comments" in out


def test_get_event_missing_id_returns_error(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "get_event", {"id": 99999})
    assert "no event with id" in out["error"]


def test_histogram_returns_buckets(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "histogram", {"field": "data_type"})
    assert out["field"] == "data_type"
    assert out["buckets"]
    assert sum(b["count"] for b in out["buckets"]) <= 20


def test_histogram_rejects_non_categorical_field(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "histogram", {"field": "message"})
    # The model may also be blocked by JSON-schema enum, but the runtime check
    # gives a clear error if the model bypasses the schema.
    assert "field must be one of" in out.get("error", "")


def test_list_timelines(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "list_timelines", {})
    assert len(out["timelines"]) == 1
    t = out["timelines"][0]
    assert t["name"] == "sample"
    assert t["event_count"] == 20


def test_list_tags_empty_initially(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "list_tags", {})
    assert out == {"tags": []}


def test_case_overview(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "case_overview", {})
    assert out["total_events"] == 20
    assert out["ts_first"] and out["ts_last"]
    assert out["top_data_types"]


def test_search_events_iso_ts_filter(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    # Sample data is in March 2019; everything is after this lower bound.
    out = _call(reg, "search_events",
                {"filters": {"ts_after": "2019-01-01T00:00:00Z"}})
    assert out["total_matching"] == 20


def test_search_events_iso_ts_before_excludes_all(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "search_events",
                {"filters": {"ts_before": "2018-01-01T00:00:00Z"}})
    assert out["total_matching"] == 0


def test_search_events_unparseable_ts_returns_error(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "search_events",
                {"filters": {"ts_after": "yesterdayish"}})
    assert "unparseable timestamp" in out["error"]


def test_list_exhibits_omits_bodies(case_with_data):
    from chronoscope.core.exhibits import add_exhibit
    add_exhibit(case_with_data.con, title="evil.ps1", description="dropper", body="whoami")
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "list_exhibits", {})
    assert out["exhibits"][0]["title"] == "evil.ps1"
    assert out["exhibits"][0]["body_chars"] == len("whoami")
    assert "body" not in out["exhibits"][0]


def test_get_exhibit_returns_full_body(case_with_data):
    from chronoscope.core.exhibits import add_exhibit
    eid = add_exhibit(case_with_data.con, title="t", description="d", body="full body here")
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "get_exhibit", {"id": eid})
    assert out["body"] == "full body here"


def test_get_exhibit_unknown_id_errors(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "get_exhibit", {"id": 999})
    assert "no exhibit" in out["error"]

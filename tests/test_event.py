from __future__ import annotations

from chronoscope.core.event import Event, canonical_json, event_hash


def test_canonical_json_sorts_keys():
    a = {"b": 1, "a": 2, "c": [3, 2, 1]}
    b = {"a": 2, "c": [3, 2, 1], "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_canonical_json_normalizes_floats():
    a = {"x": 1.0}
    b = {"x": 1.000000}
    assert canonical_json(a) == canonical_json(b)


def test_event_hash_stable():
    e = {"datetime": "2019-03-12T17:13:42+00:00", "message": "hi", "data_type": "t"}
    assert event_hash(e) == event_hash(dict(e))


def test_event_hash_changes_on_message_change():
    e1 = {"datetime": "2019-03-12T17:13:42+00:00", "message": "hi", "data_type": "t"}
    e2 = {"datetime": "2019-03-12T17:13:42+00:00", "message": "bye", "data_type": "t"}
    assert event_hash(e1) != event_hash(e2)


def test_event_from_jsonl_dict_extracts_core_and_extra():
    raw = {
        "datetime": "2019-03-12T17:13:42.002825+00:00",
        "timestamp": 1552410822002825,
        "timestamp_desc": "Last Visited Time",
        "data_type": "chrome:history:page_visited",
        "parser": "sqlite/chrome_27_history",
        "source_short": "WEBHIST",
        "source_long": "Chrome History",
        "display_name": "TSK:/Users/u/AppData/\u2026/History",
        "message": "https://example.com/ (Example)",
        "url": "https://example.com/",
        "title": "Example",
        "tag": [],
    }
    ev = Event.from_dict(raw)
    assert ev.ts_usec == 1552410822002825
    assert ev.ts_desc == "Last Visited Time"
    assert ev.data_type == "chrome:history:page_visited"
    assert ev.parser == "sqlite/chrome_27_history"
    assert ev.source_short == "WEBHIST"
    assert ev.source_long == "Chrome History"
    assert ev.display_name == "TSK:/Users/u/AppData/\u2026/History"
    assert ev.message == "https://example.com/ (Example)"
    assert ev.extra == {"url": "https://example.com/", "title": "Example", "tag": []}


def test_event_from_dict_missing_timestamp_uses_zero():
    ev = Event.from_dict({"message": "m", "data_type": "t", "timestamp_desc": "T"})
    assert ev.ts_usec == 0

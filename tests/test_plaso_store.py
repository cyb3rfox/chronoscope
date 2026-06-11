from __future__ import annotations

import pytest

from chronoscope.ingest.plaso_store import (
    PlasoFormatError,
    event_count,
    iter_events,
)
from tests._plaso_fixtures import make_plaso


def test_iter_events_zlib_roundtrip(tmp_path):
    path = tmp_path / "a.plaso"
    make_plaso(
        path,
        event_data=[
            {"data_type": "fs:stat", "display_name": "/etc/hosts", "parser": "filestat"},
            {"data_type": "evtx:record", "display_name": "Security.evtx", "parser": "winevtx"},
        ],
        events=[
            (1, 1_700_000_000_000_000, "Modification time"),
            (2, 1_700_000_001_000_000, "Creation time"),
        ],
    )
    rows = list(iter_events(path))
    assert len(rows) == 2
    assert rows[0]["timestamp"] == 1_700_000_000_000_000
    assert rows[0]["timestamp_desc"] == "Modification time"
    assert rows[0]["data_type"] == "fs:stat"
    assert rows[0]["display_name"] == "/etc/hosts"
    assert rows[1]["data_type"] == "evtx:record"


def test_iter_events_uncompressed(tmp_path):
    path = tmp_path / "u.plaso"
    make_plaso(
        path,
        compression="none",
        event_data=[{"data_type": "fs:stat", "display_name": "x"}],
        events=[(1, 1_700_000_000_000_000, "mtime")],
    )
    rows = list(iter_events(path))
    assert rows[0]["data_type"] == "fs:stat"


def test_iter_events_fan_out(tmp_path):
    path = tmp_path / "fo.plaso"
    make_plaso(
        path,
        event_data=[{"data_type": "fs:stat", "display_name": "/x"}],
        events=[
            (1, 1_700_000_000_000_000, "atime"),
            (1, 1_700_000_001_000_000, "mtime"),
            (1, 1_700_000_002_000_000, "ctime"),
        ],
    )
    rows = list(iter_events(path))
    assert len(rows) == 3
    assert {r["timestamp_desc"] for r in rows} == {"atime", "mtime", "ctime"}
    assert all(r["display_name"] == "/x" for r in rows)


def test_iter_events_strips_container_metadata(tmp_path):
    path = tmp_path / "m.plaso"
    make_plaso(
        path,
        event_data=[{
            "__type__": "AttributeContainer",
            "__container_type__": "event_data",
            "data_type": "fs:stat",
            "display_name": "/y",
        }],
        events=[(1, 1, "mtime")],
    )
    row = list(iter_events(path))[0]
    assert "__type__" not in row
    assert "__container_type__" not in row
    assert row["data_type"] == "fs:stat"


def test_iter_events_rejects_old_format(tmp_path):
    path = tmp_path / "old.plaso"
    make_plaso(path, version=20180101, event_data=[], events=[])
    with pytest.raises(PlasoFormatError, match="too old"):
        list(iter_events(path))


def test_iter_events_rejects_non_json_serializer(tmp_path):
    path = tmp_path / "cbor.plaso"
    make_plaso(path, serialization="cbor", event_data=[], events=[])
    with pytest.raises(PlasoFormatError, match="serialization"):
        list(iter_events(path))


def test_iter_events_results_are_chronological(tmp_path):
    path = tmp_path / "sorted.plaso"
    make_plaso(
        path,
        event_data=[{"data_type": "fs:stat", "display_name": "/x"}],
        events=[
            (1, 3_000_000_000_000_000, "third"),
            (1, 1_000_000_000_000_000, "first"),
            (1, 2_000_000_000_000_000, "second"),
        ],
    )
    rows = list(iter_events(path))
    assert [r["timestamp"] for r in rows] == [
        1_000_000_000_000_000, 2_000_000_000_000_000, 3_000_000_000_000_000,
    ]


def test_iter_events_preserves_explicit_message(tmp_path):
    path = tmp_path / "msg.plaso"
    make_plaso(
        path,
        event_data=[{"data_type": "fs:stat", "display_name": "/x",
                     "message": "explicit message"}],
        events=[(1, 1, "mtime")],
    )
    row = list(iter_events(path))[0]
    assert row["message"] == "explicit message"


def test_iter_events_synthesizes_message_from_display_name(tmp_path):
    path = tmp_path / "synth.plaso"
    make_plaso(
        path,
        event_data=[{"data_type": "fs:stat", "display_name": "/etc/hosts"}],
        events=[(1, 1, "mtime")],
    )
    row = list(iter_events(path))[0]
    assert row["message"] == "/etc/hosts"


def test_iter_events_synthesizes_message_prefers_text_over_display_name(tmp_path):
    path = tmp_path / "synth2.plaso"
    make_plaso(
        path,
        event_data=[{
            "data_type": "browser:bookmark",
            "display_name": "/Users/x/Library/Bookmarks",
            "text": "Hacker News",
            "url": "https://news.ycombinator.com",
        }],
        events=[(1, 1, "mtime")],
    )
    row = list(iter_events(path))[0]
    assert row["message"] == "Hacker News"


def test_iter_events_message_falls_back_to_data_type(tmp_path):
    path = tmp_path / "empty.plaso"
    make_plaso(
        path,
        event_data=[{"data_type": "weird:event"}],
        events=[(1, 1, "mtime")],
    )
    row = list(iter_events(path))[0]
    assert row["message"] == "weird:event"


def test_iter_events_message_truncated_when_huge(tmp_path):
    path = tmp_path / "long.plaso"
    huge = "X" * 1000
    make_plaso(
        path,
        event_data=[{"data_type": "x:y", "text": huge}],
        events=[(1, 1, "mtime")],
    )
    row = list(iter_events(path))[0]
    assert len(row["message"]) <= 501  # 500 chars + ellipsis
    assert row["message"].endswith("…")


def test_event_count_returns_total_rows(tmp_path):
    path = tmp_path / "cnt.plaso"
    make_plaso(
        path,
        event_data=[{"data_type": "fs:stat", "display_name": "/a"}],
        events=[(1, i, "mtime") for i in range(7)],
    )
    assert event_count(path) == 7

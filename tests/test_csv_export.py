from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import cbor2
import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.query.csv_export import export_filtered_csv
from chronoscope.query.state import QueryState

EXPECTED_HEADER = [
    "id", "event_hash", "timeline_id", "timeline_name",
    "datetime_utc", "ts_usec", "ts_desc",
    "data_type", "parser", "source_short", "source_long",
    "display_name", "message",
    "starred", "tags", "comments", "extras",
]


def _seed(case_path: Path) -> None:
    """Insert two timelines and six events with assorted shapes."""
    init_case(case_path, name="csvtest")
    with open_case(case_path) as c:
        con = c.con
        con.executemany(
            "INSERT INTO timeline(id, name, source_path, source_kind, "
            "source_sha256, event_count, ingested_at, color) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [
                ("tl-a", "Alpha", "/tmp/a.jsonl", "jsonl",
                 "a" * 64, 0, "2026-06-02T00:00:00+00:00", None),
                ("tl-b", "Beta", "/tmp/b.jsonl", "jsonl",
                 "b" * 64, 0, "2026-06-02T00:00:00+00:00", None),
            ],
        )
        rows = [
            ("tl-a", b"\x01", 1_000_000_000_000, "Creation Time", "fs:stat",
             "filestat", "FILE", "File Stat", "/etc/hosts",
             "first event line one\nline two", {"sha1": "deadbeef"}),
            ("tl-a", b"\x02", 2_000_000_000_000, "Modification Time",
             "windows:registry:key", "winreg", "REG", "Registry Key",
             "HKLM\\Run", "registry change", {"key": "value"}),
            ("tl-b", b"\x03", 3_000_000_000_000, "Last Access",
             "windows:evtx:record", "winevtx", "EVTX", "Event Log",
             "logon", "user logged on", {"user": "alice", "sid": "S-1-5"}),
            ("tl-b", b"\x04", 4_000_000_000_000, "Creation Time",
             "fs:stat", "filestat", "FILE", "File Stat", "/var/log",
             "fourth event", {}),
            ("tl-a", b"\x05", 5_000_000_000_000, "Creation Time",
             "fs:stat", "filestat", "FILE", "File Stat", "/home",
             "fifth event", {"a": 1}),
            ("tl-b", b"\x06", 0, "Creation Time",
             "fs:stat", "filestat", "FILE", "File Stat", "/zero",
             "zero-time event", {}),
        ]
        for tl, h, ts, td, dt, p, ss, sl, dn, msg, ex in rows:
            event_hash = (h * 32)[:32]
            con.execute(
                "INSERT INTO event(timeline_id, event_hash, ts_usec, ts_desc, "
                "data_type, parser, source_short, source_long, display_name, "
                "message, extra, extra_text) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (tl, event_hash, ts, td, dt, p, ss, sl, dn, msg,
                 cbor2.dumps(ex), ""),
            )
        con.commit()


def test_export_happy_path_writes_all_rows(tmp_path):
    case = tmp_path / "case"
    _seed(case)

    out = tmp_path / "out.csv"
    n = export_filtered_csv(case, QueryState(), out)

    assert n == 6
    with out.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        body = list(reader)

    assert header == EXPECTED_HEADER
    assert len(body) == 6
    assert body[0][5] == "0"
    assert body[0][4] == ""
    assert body[-1][5] == "5000000000000"
    expected_dt = datetime.fromtimestamp(
        5_000_000_000_000 / 1_000_000, tz=timezone.utc
    ).isoformat(timespec="seconds")
    assert body[-1][4] == expected_dt


def test_export_respects_substring_filter(tmp_path):
    case = tmp_path / "case"
    _seed(case)
    state = QueryState().set_substring("message", "registry")
    out = tmp_path / "out.csv"
    n = export_filtered_csv(case, state, out)
    assert n == 1
    body = list(csv.reader(out.open(newline="")))[1:]
    assert body[0][12] == "registry change"


def test_export_respects_categorical_filter(tmp_path):
    case = tmp_path / "case"
    _seed(case)
    state = QueryState().set_categorical(
        "data_type", include=["fs:stat"], exclude=[]
    )
    out = tmp_path / "out.csv"
    n = export_filtered_csv(case, state, out)
    assert n == 4
    body = list(csv.reader(out.open(newline="")))[1:]
    assert all(r[7] == "fs:stat" for r in body)


def test_export_respects_bracket(tmp_path):
    case = tmp_path / "case"
    _seed(case)
    state = QueryState().set_bracket(
        2_000_000_000_000, 4_000_000_000_000
    )
    out = tmp_path / "out.csv"
    n = export_filtered_csv(case, state, out)
    assert n == 3
    body = list(csv.reader(out.open(newline="")))[1:]
    ts_values = [int(r[5]) for r in body]
    assert ts_values == sorted(ts_values)
    assert min(ts_values) >= 2_000_000_000_000
    assert max(ts_values) <= 4_000_000_000_000


def test_export_respects_sort_desc(tmp_path):
    case = tmp_path / "case"
    _seed(case)
    state = QueryState().set_sort("ts_usec", "DESC")
    out = tmp_path / "out.csv"
    n = export_filtered_csv(case, state, out)
    assert n == 6
    body = list(csv.reader(out.open(newline="")))[1:]
    ts_values = [int(r[5]) for r in body]
    assert ts_values == sorted(ts_values, reverse=True)


def test_export_empty_result_writes_header_only(tmp_path):
    case = tmp_path / "case"
    _seed(case)
    state = QueryState().set_substring("message", "no-such-needle-xyz")
    out = tmp_path / "out.csv"
    n = export_filtered_csv(case, state, out)
    assert n == 0
    rows = list(csv.reader(out.open(newline="")))
    assert rows == [EXPECTED_HEADER]


def test_export_renders_annotations(tmp_path):
    case = tmp_path / "case"
    _seed(case)
    from chronoscope.annotations import store

    with open_case(case) as c:
        registry_hash = c.con.execute(
            "SELECT event_hash FROM event WHERE data_type = ?",
            ("windows:registry:key",),
        ).fetchone()[0]
        evtx_hash = c.con.execute(
            "SELECT event_hash FROM event WHERE data_type = ?",
            ("windows:evtx:record",),
        ).fetchone()[0]
        store.add_tag(c.con, registry_hash, "lateral")
        store.add_tag(c.con, registry_hash, "auth")
        store.add_comment(c.con, registry_hash, "first comment\nsecond line")
        store.add_comment(c.con, registry_hash, "another comment")
        store.set_star(c.con, evtx_hash, True)
        c.con.commit()

    out = tmp_path / "out.csv"
    export_filtered_csv(case, QueryState(), out)
    body = {
        r[7]: r for r in csv.reader(out.open(newline=""))
        if r[0] != "id"
    }

    reg = body["windows:registry:key"]
    assert reg[13] == "false"
    assert reg[14] == "auth;lateral"
    assert reg[15] == (
        "first comment second line | another comment"
    )

    evtx = body["windows:evtx:record"]
    assert evtx[13] == "true"


def test_export_round_trips_extras_as_json(tmp_path):
    case = tmp_path / "case"
    _seed(case)
    out = tmp_path / "out.csv"
    export_filtered_csv(case, QueryState(), out)
    body = list(csv.reader(out.open(newline="")))[1:]
    evtx_row = next(r for r in body if r[7] == "windows:evtx:record")
    assert json.loads(evtx_row[16]) == {"user": "alice", "sid": "S-1-5"}
    empty_row = next(r for r in body if r[11] == "/var/log")
    assert json.loads(empty_row[16]) == {}


def test_export_refuses_existing_file(tmp_path):
    case = tmp_path / "case"
    _seed(case)
    out = tmp_path / "out.csv"
    out.write_text("existing content\n")
    with pytest.raises(FileExistsError):
        export_filtered_csv(case, QueryState(), out)
    assert out.read_text() == "existing content\n"


def test_export_cleans_up_tmp_on_failure(tmp_path, monkeypatch):
    case = tmp_path / "case"
    _seed(case)
    out = tmp_path / "out.csv"

    class _Boom(RuntimeError):
        pass

    import chronoscope.query.csv_export as mod
    real_format = mod._format_row
    calls = {"n": 0}

    def _explode(row):
        calls["n"] += 1
        if calls["n"] >= 3:
            raise _Boom("synthetic mid-stream failure")
        return real_format(row)

    monkeypatch.setattr(mod, "_format_row", _explode)
    with pytest.raises(_Boom):
        export_filtered_csv(case, QueryState(), out)
    tmp = out.with_suffix(out.suffix + ".tmp")
    assert not tmp.exists()
    assert not out.exists()


def test_export_progress_callback_invoked(tmp_path, monkeypatch):
    case = tmp_path / "case"
    _seed(case)
    out = tmp_path / "out.csv"

    import chronoscope.query.csv_export as mod
    monkeypatch.setattr(mod, "_PROGRESS_INTERVAL", 2)
    seen: list[int] = []
    export_filtered_csv(case, QueryState(), out, progress=seen.append)
    # 6 rows, interval=2 → callbacks at 2, 4, 6, plus final-flush at 6.
    assert 2 in seen and 4 in seen and 6 in seen
    assert seen[-1] == 6

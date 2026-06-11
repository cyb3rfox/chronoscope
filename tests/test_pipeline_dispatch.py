from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import (
    UnsupportedSourceError,
    ingest_file,
)
from tests._plaso_fixtures import make_plaso

JSONL_DATA = Path(__file__).parent / "data" / "sample.jsonl"


def test_ingest_jsonl_marks_source_kind_jsonl(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="x")
    report = ingest_file(case, JSONL_DATA, name="jl")
    assert report.inserted > 0
    with open_case(case) as c:
        kinds = [r[0] for r in c.con.execute("SELECT source_kind FROM timeline")]
        assert kinds == ["jsonl"]


def test_ingest_plaso_round_trip(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="x")
    pl = tmp_path / "t.plaso"
    make_plaso(
        pl,
        event_data=[
            {"data_type": "fs:stat", "display_name": "/a", "parser": "filestat",
             "message": "stat /a"},
            {"data_type": "fs:stat", "display_name": "/b", "parser": "filestat",
             "message": "stat /b"},
        ],
        events=[
            (1, 1_700_000_000_000_000, "mtime"),
            (2, 1_700_000_001_000_000, "mtime"),
        ],
    )
    report = ingest_file(case, pl, name="evt")
    assert report.inserted == 2
    with open_case(case) as c:
        rows = list(c.con.execute(
            "SELECT source_kind, event_count FROM timeline"
        ))
        assert rows == [("plaso", 2)]
        types = [r[0] for r in c.con.execute(
            "SELECT data_type FROM event ORDER BY ts_usec"
        )]
        assert types == ["fs:stat", "fs:stat"]


def test_ingest_unsupported_raises(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="x")
    bad = tmp_path / "legacy.plaso"
    bad.write_bytes(b"PK\x03\x04" + b"\x00" * 32)
    with pytest.raises(UnsupportedSourceError):
        ingest_file(case, bad, name="bad")


def test_ingest_dedup_works_for_plaso(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="x")
    pl = tmp_path / "dup.plaso"
    make_plaso(
        pl,
        event_data=[{"data_type": "fs:stat", "display_name": "/a"}],
        events=[(1, 1_700_000_000_000_000, "mtime")],
    )
    first = ingest_file(case, pl, name="evt")
    assert first.already_present is False
    second = ingest_file(case, pl, name="evt")
    assert second.already_present is True


def test_progress_callback_invoked_for_plaso(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="x")
    pl = tmp_path / "p.plaso"
    make_plaso(
        pl,
        event_data=[{"data_type": "fs:stat", "display_name": "/a"}],
        events=[(1, i, "mtime") for i in range(3)],
    )
    calls: list[tuple[int, int | None]] = []
    ingest_file(case, pl, name="evt", progress=lambda d, t: calls.append((d, t)))
    assert calls, "expected at least one progress call"
    # plaso knows the total upfront, so every call should include total=3
    assert all(t == 3 for _, t in calls)
    # final call reports the full count
    assert calls[-1][0] == 3


def test_progress_callback_invoked_for_jsonl(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="x")
    calls: list[tuple[int, int | None]] = []
    ingest_file(case, JSONL_DATA, name="jl",
                progress=lambda d, t: calls.append((d, t)))
    assert calls, "expected at least one progress call"
    # JSONL doesn't know total upfront
    assert all(t is None for _, t in calls)
    # final call's done count matches what was actually inserted
    with open_case(case) as c:
        n = c.con.execute("SELECT event_count FROM timeline").fetchone()[0]
    assert calls[-1][0] == n

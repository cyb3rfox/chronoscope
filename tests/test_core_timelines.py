from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.core.timelines import (
    TimelineNotFoundError,
    remove_timeline,
)
from chronoscope.ingest.pipeline import ingest_file

DATA = Path(__file__).parent / "data" / "sample.jsonl"


def test_remove_timeline_drops_events_and_row(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="t")
    ingest_file(case, DATA, name="sample")
    remove_timeline(case, "sample")
    with open_case(case) as c:
        assert c.con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0] == 0
        assert c.con.execute("SELECT COUNT(*) FROM event").fetchone()[0] == 0


def test_remove_timeline_unknown_raises(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="t")
    with pytest.raises(TimelineNotFoundError):
        remove_timeline(case, "nope")


def test_remove_timeline_reports_progress(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="t")
    ingest_file(case, DATA, name="sample")
    seen: list[tuple[int, int | None]] = []
    remove_timeline(case, "sample", progress=lambda d, t: seen.append((d, t)))
    assert seen, "progress callback was never invoked"
    assert seen[0] == (0, 20)  # starts at 0 of the known total
    assert seen[-1][0] == 20  # ends having deleted every event
    counts = [d for d, _ in seen]
    assert counts == sorted(counts)  # monotonically non-decreasing
    assert all(t == 20 for _, t in seen)  # total stays constant
    with open_case(case) as c:
        assert c.con.execute("SELECT COUNT(*) FROM event").fetchone()[0] == 0


def test_remove_timeline_deletes_in_batches(tmp_path, monkeypatch):
    import chronoscope.core.timelines as tl

    monkeypatch.setattr(tl, "BATCH", 5)
    case = tmp_path / "c"
    init_case(case, name="t")
    ingest_file(case, DATA, name="sample")
    counts: list[int] = []
    remove_timeline(case, "sample", progress=lambda d, _t: counts.append(d))
    # 20 events in batches of 5 -> a callback after each batch, plus the 0 start
    assert counts == [0, 5, 10, 15, 20]
    with open_case(case) as c:
        assert c.con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0] == 0
        assert c.con.execute("SELECT COUNT(*) FROM event").fetchone()[0] == 0

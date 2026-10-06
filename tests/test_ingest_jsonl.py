from __future__ import annotations

import io

from chronoscope.ingest.jsonl import iter_events


SAMPLE = b"""\
{"datetime":"2019-03-12T17:13:42+00:00","timestamp":1552410822002825,"timestamp_desc":"Last Visited Time","data_type":"chrome:history:page_visited","message":"m1"}
{"datetime":"2019-03-12T17:14:01+00:00","timestamp":1552410841000000,"timestamp_desc":"Recorded Time","data_type":"windows:prefetch:execution","message":"m2"}
"""


def test_iter_events_reads_lines():
    events = list(iter_events(io.BytesIO(SAMPLE)))
    assert len(events) == 2
    assert events[0].message == "m1"
    assert events[1].data_type == "windows:prefetch:execution"


def test_iter_events_skips_malformed_line_and_reports():
    bad = SAMPLE.splitlines(keepends=True)
    bad.insert(1, b"not json\n")
    buf = io.BytesIO(b"".join(bad))
    skipped: list[tuple[int, str]] = []
    events = list(iter_events(buf, on_error=lambda lineno, reason: skipped.append((lineno, reason))))
    assert len(events) == 2
    assert skipped and skipped[0][0] == 2


def test_iter_events_ignores_blank_lines():
    buf = io.BytesIO(b"\n" + SAMPLE + b"\n\n")
    assert len(list(iter_events(buf))) == 2


from pathlib import Path

from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file


DATA = Path(__file__).parent / "data" / "sample.jsonl"


def test_ingest_writes_events_and_timeline(case_dir):
    init_case(case_dir, name="t")
    report = ingest_file(case_dir, DATA, name="sample")
    assert report.inserted == 20
    assert report.skipped == 0
    with open_case(case_dir) as c:
        counts = c.con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
        assert counts == 20
        tl = c.con.execute("SELECT name, event_count FROM timeline").fetchone()
        assert tl == ("sample", 20)


def test_ingest_is_idempotent_on_resame_source(case_dir):
    init_case(case_dir, name="t")
    ingest_file(case_dir, DATA, name="sample")
    r2 = ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        counts = c.con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
        assert counts == 20
    assert r2.inserted == 0
    assert r2.already_present is True


def test_ingest_populates_extra_text_for_extra_field_search(case_dir):
    init_case(case_dir, name="t")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        # sample.jsonl has "url"/"title"/"visit_count" as extra fields, none of
        # which appear as their own column. A single substring against
        # extra_text should reach values across all extra keys.
        hits = c.con.execute(
            "SELECT COUNT(*) FROM event WHERE LOWER(extra_text) LIKE LOWER(?)",
            ("%hacker news%",),
        ).fetchone()[0]
        assert hits >= 1

        # And it should also match keys that don't exist in the core columns.
        hits = c.con.execute(
            "SELECT COUNT(*) FROM event WHERE LOWER(extra_text) LIKE LOWER(?)",
            ("%duckduckgo%",),
        ).fetchone()[0]
        assert hits >= 1

        # Every event row must have a non-empty extra_text since every sample
        # event carries at least one extra field.
        empty = c.con.execute(
            "SELECT COUNT(*) FROM event WHERE extra_text = ''"
        ).fetchone()[0]
        assert empty == 0

from __future__ import annotations

import json
from pathlib import Path

from chronoscope.annotations import store
from chronoscope.annotations.export import export_annotations
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file

DATA = Path(__file__).parent / "data" / "sample.jsonl"


def test_export_annotations_writes_json(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="e")
    ingest_file(case, DATA, name="s")
    with open_case(case) as c:
        hashes = [r[0] for r in c.con.execute(
            "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC"
        )]
        store.set_star(c.con, hashes[0], True)
        store.add_tag(c.con, hashes[0], "susp")
        store.add_comment(c.con, hashes[1], "hi")

    out = tmp_path / "out.json"
    n = export_annotations(case, out)
    assert n == 2

    doc = json.loads(out.read_text())
    assert doc["schema_version"] == 1
    assert "exported_at" in doc
    events = {e["event_hash"]: e for e in doc["events"]}
    assert len(events) == 2
    e0 = next(e for e in doc["events"] if e["star"])
    assert e0["star"] is True
    assert "susp" in e0["tags"]
    e1 = next(e for e in doc["events"] if e["comments"])
    assert e1["comments"][0]["body"] == "hi"


def test_export_annotations_empty_case_writes_empty_events(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="e")
    ingest_file(case, DATA, name="s")
    out = tmp_path / "out.json"
    n = export_annotations(case, out)
    assert n == 0
    doc = json.loads(out.read_text())
    assert doc["events"] == []

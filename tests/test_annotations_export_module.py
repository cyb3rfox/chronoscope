from __future__ import annotations

import json
from pathlib import Path

from chronoscope.annotations import store
from chronoscope.annotations.export import export_annotations
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file

DATA = Path(__file__).parent / "data" / "sample.jsonl"


def test_export_writes_annotated_events(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="e")
    ingest_file(case, DATA, name="s")
    with open_case(case) as c:
        h = c.con.execute(
            "SELECT event_hash FROM event ORDER BY ts_usec, id LIMIT 1"
        ).fetchone()[0]
        store.set_star(c.con, h, True)
        store.add_tag(c.con, h, "susp")

    out = tmp_path / "out.json"
    n = export_annotations(case, out)

    assert n == 1
    doc = json.loads(out.read_text())
    assert doc["schema_version"] == 1
    assert "exported_at" in doc
    assert len(doc["events"]) == 1
    assert doc["events"][0]["star"] is True
    assert "susp" in doc["events"][0]["tags"]


def test_export_empty_case_writes_empty_events(tmp_path):
    case = tmp_path / "c"
    init_case(case, name="e")
    ingest_file(case, DATA, name="s")
    out = tmp_path / "out.json"
    n = export_annotations(case, out)
    assert n == 0
    assert json.loads(out.read_text())["events"] == []

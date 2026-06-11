from __future__ import annotations

from pathlib import Path

from chronoscope.core.case import init_case, list_timelines, open_case
from chronoscope.ingest.pipeline import ingest_file

DATA = Path(__file__).parent / "data" / "sample.jsonl"


def test_list_timelines_empty_case(case_dir):
    init_case(case_dir, name="demo")
    with open_case(case_dir) as c:
        assert list_timelines(c.con) == []


def test_list_timelines_one(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="alpha")
    with open_case(case_dir) as c:
        out = list_timelines(c.con)
    assert len(out) == 1
    t = out[0]
    assert t.name == "alpha"
    assert t.event_count == 20
    assert t.order_index == 0
    assert t.color == "cyan"


def test_list_timelines_two_sorted_by_ingest_time(case_dir, tmp_path):
    import shutil
    fixture2 = tmp_path / "sample_copy.jsonl"
    shutil.copy(DATA, fixture2)
    with fixture2.open("a") as f:
        f.write("\n")
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="alpha")
    ingest_file(case_dir, fixture2, name="beta")
    with open_case(case_dir) as c:
        out = list_timelines(c.con)
    assert [t.name for t in out] == ["alpha", "beta"]
    assert out[0].order_index == 0 and out[0].color == "cyan"
    assert out[1].order_index == 1 and out[1].color == "magenta"

from __future__ import annotations

from chronoscope.ingest.detect import detect_format


def test_detect_plaso_by_sqlite_magic(tmp_path):
    p = tmp_path / "x.plaso"
    p.write_bytes(b"SQLite format 3\x00" + b"junkjunkjunk")
    assert detect_format(p) == "plaso"


def test_detect_jsonl_by_opening_brace(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_bytes(b'{"timestamp": 0, "data_type": "x"}\n')
    assert detect_format(p) == "jsonl"


def test_detect_jsonl_tolerates_leading_whitespace(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_bytes(b'\n  {"timestamp": 0}\n')
    assert detect_format(p) == "jsonl"


def test_detect_unsupported_for_zip(tmp_path):
    p = tmp_path / "legacy.plaso"
    p.write_bytes(b"PK\x03\x04somelegacystuff")
    assert detect_format(p) == "unsupported"


def test_detect_unsupported_for_empty_file(tmp_path):
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    assert detect_format(p) == "unsupported"


def test_detect_unsupported_for_random_binary(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"\xff\xfe\xfd\xfc\xfb\xfa\xf9\xf8")
    assert detect_format(p) == "unsupported"

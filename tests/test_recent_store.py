from __future__ import annotations

import json

from chronoscope.config import recent


def test_load_returns_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert recent.load() == []


def test_load_returns_empty_on_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tmp_path / "chronoscope" / "recent.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert recent.load() == []


def test_load_returns_entries_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tmp_path / "chronoscope" / "recent.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([
        {"path": "/a", "name": "A", "last_opened": "2026-01-01T00:00:00+00:00"},
        {"path": "/b", "name": "B", "last_opened": "2026-05-01T00:00:00+00:00"},
    ]))
    entries = recent.load()
    assert [e.path for e in entries] == ["/b", "/a"]


def test_touch_creates_file_and_upserts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    case = tmp_path / "c"
    case.mkdir()
    recent.touch(case, "demo")
    entries = recent.load()
    assert len(entries) == 1
    assert entries[0].path == str(case.resolve())
    assert entries[0].name == "demo"

    recent.touch(case, "demo")  # second touch must not duplicate
    assert len(recent.load()) == 1


def test_remove_drops_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    case = tmp_path / "c"
    case.mkdir()
    recent.touch(case, "demo")
    recent.remove(case)
    assert recent.load() == []


def test_touch_caps_at_max_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for i in range(recent.MAX_ENTRIES + 5):
        d = tmp_path / f"case-{i}"
        d.mkdir()
        recent.touch(d, f"c{i}")
    assert len(recent.load()) == recent.MAX_ENTRIES

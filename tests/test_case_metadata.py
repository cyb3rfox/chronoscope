from __future__ import annotations

from pathlib import Path

import pytest

from chronoscope.core.case import init_case, open_case
from chronoscope.core.metadata import (
    CaseMetadata,
    format_briefing,
    load_metadata,
    save_metadata,
)


def test_load_returns_empty_for_fresh_case(case_dir):
    init_case(case_dir, name="t")
    meta = load_metadata(case_dir)
    assert meta == CaseMetadata()
    assert meta.is_empty() is True


def test_save_then_load_round_trip(case_dir):
    init_case(case_dir, name="t")
    custom = CaseMetadata(
        company="ACME",
        incident="ransomware on PC01",
        notes="multi-line\nnotes",
        compromised_accounts=("alice", "bob"),
        compromised_machines=("WIN-PC01",),
        known_iocs=("192.0.2.1", "evil.example.com"),
    )
    save_metadata(case_dir, custom)
    assert load_metadata(case_dir) == custom


def test_save_metadata_preserves_other_manifest_keys(case_dir):
    init_case(case_dir, name="acme-case")
    save_metadata(case_dir, CaseMetadata(company="ACME"))
    # The standard case lifecycle must keep working — name and the timeline
    # array set by init_case must survive a metadata write.
    with open_case(case_dir) as c:
        assert c.name == "acme-case"


def test_with_added_is_idempotent_and_skips_blank():
    m = CaseMetadata().with_added("compromised_accounts", "alice")
    m = m.with_added("compromised_accounts", "alice")  # duplicate
    m = m.with_added("compromised_accounts", "  ")     # blank
    assert m.compromised_accounts == ("alice",)


def test_with_removed_drops_value():
    m = CaseMetadata(compromised_accounts=("alice", "bob"))
    m = m.with_removed("compromised_accounts", "alice")
    assert m.compromised_accounts == ("bob",)
    # Removing a missing value is a no-op.
    m = m.with_removed("compromised_accounts", "ghost")
    assert m.compromised_accounts == ("bob",)


def test_with_list_dedupes_and_strips():
    m = CaseMetadata().with_list(
        "known_iocs", ["1.1.1.1", "  2.2.2.2  ", "1.1.1.1", ""]
    )
    assert m.known_iocs == ("1.1.1.1", "2.2.2.2")


def test_unknown_field_or_category_raises():
    with pytest.raises(ValueError):
        CaseMetadata().with_scalar("not_a_field", "x")
    with pytest.raises(ValueError):
        CaseMetadata().with_added("not_a_category", "x")


def test_format_briefing_omits_empty_fields():
    assert format_briefing(CaseMetadata()) == ""
    text = format_briefing(CaseMetadata(company="ACME"))
    assert "ACME" in text
    assert "Incident" not in text
    assert "Known compromised" not in text


def test_format_briefing_includes_all_populated_fields():
    meta = CaseMetadata(
        company="ACME",
        incident="ransomware",
        compromised_accounts=("alice",),
        compromised_machines=("PC01",),
        known_iocs=("evil.example.com",),
        notes="brief notes",
    )
    text = format_briefing(meta)
    for needle in ("ACME", "ransomware", "alice", "PC01", "evil.example.com", "brief notes"):
        assert needle in text


def test_load_metadata_for_case_without_metadata_section(case_dir: Path):
    # Pre-existing case.toml from before the metadata section was added.
    init_case(case_dir, name="legacy")
    # Manifest already exists; a newer chronoscope reading it should see
    # an empty CaseMetadata rather than crash.
    assert load_metadata(case_dir) == CaseMetadata()

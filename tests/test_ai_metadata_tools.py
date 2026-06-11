from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronoscope.ai.agent import build_system_prompt
from chronoscope.ai.settings import AISettings
from chronoscope.ai.toolset import build_toolset
from chronoscope.core.case import init_case, open_case
from chronoscope.core.metadata import (
    CaseMetadata,
    load_metadata,
    save_metadata,
)
from chronoscope.ingest.pipeline import ingest_file

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.fixture
def case_with_data(case_dir):
    init_case(case_dir, name="t")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        yield c


def _call(reg, name, args):
    return json.loads(reg.call(name, json.dumps(args)))


def test_read_case_metadata_returns_empty_initially(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "read_case_metadata", {})
    assert out["company"] == ""
    assert out["compromised_accounts"] == []


def test_set_case_metadata_field_persists_to_disk(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "set_case_metadata_field",
                {"field": "company", "value": "ACME"})
    assert out["ok"] is True
    assert out["metadata"]["company"] == "ACME"
    # Round-trip from disk to confirm we actually wrote.
    assert load_metadata(case_with_data.path).company == "ACME"


def test_set_case_metadata_field_rejects_unknown_field(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "set_case_metadata_field",
                {"field": "made_up", "value": "x"})
    assert "field must be one of" in out["error"]


def test_add_metadata_entry_is_idempotent_and_persisted(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    _call(reg, "add_metadata_entry",
          {"category": "compromised_accounts", "value": "alice"})
    _call(reg, "add_metadata_entry",
          {"category": "compromised_accounts", "value": "alice"})
    out = _call(reg, "read_case_metadata", {})
    assert out["compromised_accounts"] == ["alice"]
    assert load_metadata(case_with_data.path).compromised_accounts == ("alice",)


def test_add_metadata_entry_rejects_blank(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "add_metadata_entry",
                {"category": "known_iocs", "value": "   "})
    assert "non-empty" in out["error"]


def test_remove_metadata_entry_drops_value(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    _call(reg, "add_metadata_entry",
          {"category": "known_iocs", "value": "192.0.2.1"})
    _call(reg, "add_metadata_entry",
          {"category": "known_iocs", "value": "evil.example.com"})
    _call(reg, "remove_metadata_entry",
          {"category": "known_iocs", "value": "192.0.2.1"})
    out = _call(reg, "read_case_metadata", {})
    assert out["known_iocs"] == ["evil.example.com"]


def test_remove_metadata_entry_unknown_category(case_with_data):
    reg = build_toolset(case_with_data, AISettings())
    out = _call(reg, "remove_metadata_entry",
                {"category": "fake", "value": "x"})
    assert "category must be one of" in out["error"]


def test_metadata_writes_dont_clobber_existing_metadata(case_with_data):
    """A model writing to one field must preserve everything else the user
    has already curated."""
    save_metadata(
        case_with_data.path,
        CaseMetadata(
            company="ACME",
            incident="ransomware",
            compromised_accounts=("alice",),
        ),
    )
    reg = build_toolset(case_with_data, AISettings())
    _call(reg, "add_metadata_entry",
          {"category": "compromised_machines", "value": "PC01"})
    after = load_metadata(case_with_data.path)
    assert after.company == "ACME"
    assert after.incident == "ransomware"
    assert after.compromised_accounts == ("alice",)
    assert after.compromised_machines == ("PC01",)


def test_build_system_prompt_inlines_briefing_when_metadata_present():
    meta = CaseMetadata(company="ACME", incident="ransomware")
    prompt = build_system_prompt(meta)
    assert "Case context" in prompt
    assert "ACME" in prompt
    assert "ransomware" in prompt


def test_build_system_prompt_skips_briefing_when_metadata_empty():
    prompt = build_system_prompt(CaseMetadata())
    assert "Case context" not in prompt


def test_build_system_prompt_handles_none():
    prompt = build_system_prompt(None)
    assert "Case context" not in prompt

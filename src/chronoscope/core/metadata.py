from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

import tomli_w

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore[no-redef]

SCALAR_FIELDS = (
    "company",
    "incident",
    "incident_started",
    "incident_discovered",
    "notes",
)
LIST_FIELDS = (
    "compromised_accounts",
    "compromised_machines",
    "known_iocs",
)


@dataclass(frozen=True, slots=True)
class CaseMetadata:
    """Investigator-curated context that travels with the case.

    Headline scalars describe the engagement; the three lists capture the
    indicators-of-interest the analyst already knows about. Designed to grow
    — per-item structure (status, type, etc.) can be added later without
    breaking existing case.toml files because tomllib silently drops unknown
    nested keys."""
    company: str = ""
    incident: str = ""
    incident_started: str = ""
    incident_discovered: str = ""
    notes: str = ""
    compromised_accounts: tuple[str, ...] = field(default_factory=tuple)
    compromised_machines: tuple[str, ...] = field(default_factory=tuple)
    known_iocs: tuple[str, ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return self == CaseMetadata()

    def with_scalar(self, name: str, value: str) -> "CaseMetadata":
        if name not in SCALAR_FIELDS:
            raise ValueError(f"unknown scalar field: {name}")
        return replace(self, **{name: str(value)})

    def with_added(self, category: str, value: str) -> "CaseMetadata":
        if category not in LIST_FIELDS:
            raise ValueError(f"unknown list category: {category}")
        v = str(value).strip()
        if not v:
            return self
        current: tuple[str, ...] = getattr(self, category)
        if v in current:
            return self
        return replace(self, **{category: current + (v,)})

    def with_removed(self, category: str, value: str) -> "CaseMetadata":
        if category not in LIST_FIELDS:
            raise ValueError(f"unknown list category: {category}")
        current: tuple[str, ...] = getattr(self, category)
        return replace(
            self,
            **{category: tuple(x for x in current if x != value)},
        )

    def with_list(self, category: str, values: list[str]) -> "CaseMetadata":
        if category not in LIST_FIELDS:
            raise ValueError(f"unknown list category: {category}")
        cleaned: list[str] = []
        seen: set[str] = set()
        for v in values:
            s = str(v).strip()
            if s and s not in seen:
                cleaned.append(s)
                seen.add(s)
        return replace(self, **{category: tuple(cleaned)})


def load_metadata(case_path: Path) -> CaseMetadata:
    p = _manifest_path(case_path)
    if not p.exists():
        return CaseMetadata()
    with p.open("rb") as f:
        doc = tomllib.load(f)
    return _decode(doc.get("metadata") or {})


def save_metadata(case_path: Path, meta: CaseMetadata) -> None:
    """Persist metadata into the case.toml manifest, preserving every other
    key the manifest already has (schema_version, name, created, timeline,
    plus anything future versions add)."""
    p = _manifest_path(case_path)
    if p.exists():
        with p.open("rb") as f:
            doc = tomllib.load(f)
    else:
        doc = {}
    doc["metadata"] = _encode(meta)
    with p.open("wb") as f:
        tomli_w.dump(doc, f)


def format_briefing(meta: CaseMetadata) -> str:
    """Return a markdown briefing of the metadata suitable for prepending to
    the agent's system prompt. Empty fields are omitted so a fresh case
    produces a small briefing rather than a sea of blanks."""
    if meta.is_empty():
        return ""
    parts: list[str] = []
    if meta.company:
        parts.append(f"**Company:** {meta.company}")
    if meta.incident:
        parts.append(f"**Incident:** {meta.incident}")
    if meta.incident_started:
        parts.append(f"**Incident started:** {meta.incident_started}")
    if meta.incident_discovered:
        parts.append(f"**Incident discovered:** {meta.incident_discovered}")
    if meta.compromised_accounts:
        parts.append(
            "**Known compromised accounts:** "
            + ", ".join(meta.compromised_accounts)
        )
    if meta.compromised_machines:
        parts.append(
            "**Known compromised machines:** "
            + ", ".join(meta.compromised_machines)
        )
    if meta.known_iocs:
        parts.append("**Known IOCs:** " + ", ".join(meta.known_iocs))
    if meta.notes:
        parts.append(f"\n**Notes:**\n\n{meta.notes}")
    return "\n".join(parts)


def _manifest_path(case_path: Path) -> Path:
    return Path(case_path) / "case.toml"


def _encode(meta: CaseMetadata) -> dict:
    return {
        "company": meta.company,
        "incident": meta.incident,
        "incident_started": meta.incident_started,
        "incident_discovered": meta.incident_discovered,
        "notes": meta.notes,
        "compromised_accounts": list(meta.compromised_accounts),
        "compromised_machines": list(meta.compromised_machines),
        "known_iocs": list(meta.known_iocs),
    }


def _decode(section: dict) -> CaseMetadata:
    def _list(key: str) -> tuple[str, ...]:
        raw = section.get(key) or []
        if not isinstance(raw, list):
            return ()
        return tuple(str(x) for x in raw if str(x).strip())

    return CaseMetadata(
        company=str(section.get("company", "")),
        incident=str(section.get("incident", "")),
        incident_started=str(section.get("incident_started", "")),
        incident_discovered=str(section.get("incident_discovered", "")),
        notes=str(section.get("notes", "")),
        compromised_accounts=_list("compromised_accounts"),
        compromised_machines=_list("compromised_machines"),
        known_iocs=_list("known_iocs"),
    )

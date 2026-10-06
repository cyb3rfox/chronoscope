from __future__ import annotations

import json
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ...core.case import Case
from ...core.exhibits import Exhibit, list_exhibits
from ...core.metadata import CaseMetadata, load_metadata
from ..client import ChatMessage, LLMClient
from ..settings import AISettings


REPORT_SYSTEM_PROMPT = (
    "You are a forensic incident reporter. Generate a concise, factual "
    "markdown report of the investigation captured below. Cite events by "
    "their numeric id and ISO timestamp where helpful, and use only facts "
    "the analyst has already established (tags, comments, and case metadata). "
    "Do not invent IOCs, accounts, or events that aren't in the input.\n\n"
    "Use the following sections in this order; OMIT a section entirely if "
    "the input has nothing to put under it:\n"
    "  1. # Executive Summary — 2-4 sentences for an exec audience.\n"
    "  2. ## Incident Timeline — bulleted timeline of the marked events.\n"
    "  3. ## Indicators of Compromise (IOCs) — every IOC from metadata + "
    "any extracted from tagged events / commented evidence.\n"
    "  4. ## Compromised Credentials — every known compromised account.\n"
    "  5. ## Affected Systems — every known compromised machine, plus any "
    "additional systems referenced in tagged events.\n"
    "  6. ## Key Events — short list of the most important tagged/commented "
    "events with their analyst notes.\n"
    "  7. ## Analyst Notes — free-form notes from the case metadata.\n\n"
    "Be concise. No filler. No conclusions beyond what the evidence shows. "
    "If something is uncertain, say so."
    "\n\nThe analyst may attach EXHIBITS — supporting text artifacts (scripts, "
    "file contents) that are not timeline events. Reference relevant exhibits by "
    "their title in your narrative (e.g. \"see Exhibit 2 — evil.ps1\"). Do NOT "
    "reproduce an exhibit's body or write your own '## Exhibits' section: the full "
    "verbatim text is appended automatically after your report."
)


EXHIBIT_PROMPT_BODY_CAP = 4000


def _exhibit_excerpt(body: str) -> str:
    if len(body) <= EXHIBIT_PROMPT_BODY_CAP:
        return body
    return (
        body[:EXHIBIT_PROMPT_BODY_CAP]
        + "… [truncated; full text in the Exhibits appendix]"
    )


@dataclass(frozen=True, slots=True)
class ReportEvent:
    id: int
    ts: str
    data_type: str
    parser: str
    source_short: str
    display_name: str
    message: str
    timeline_id: str
    tags: tuple[str, ...] = ()
    comments: tuple[str, ...] = ()
    starred: bool = False


@dataclass(frozen=True, slots=True)
class ReportContext:
    """Everything the report agent sees. Built once at draft time; not
    mutated. Designed to serialise cleanly into the user message."""
    case_name: str
    generated_at: str
    metadata: CaseMetadata = field(default_factory=CaseMetadata)
    tagged_events: tuple[ReportEvent, ...] = field(default_factory=tuple)
    commented_events: tuple[ReportEvent, ...] = field(default_factory=tuple)
    starred_events: tuple[ReportEvent, ...] = field(default_factory=tuple)
    exhibits: tuple[Exhibit, ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return (
            self.metadata.is_empty()
            and not self.tagged_events
            and not self.commented_events
            and not self.starred_events
            and not self.exhibits
        )

    def to_prompt(self) -> str:
        """Render the context as a markdown-flavoured user message. The LLM
        sees stable JSON for the events plus a markdown briefing for the
        metadata — easy to parse, hard to misread."""
        meta_dict = {
            "company": self.metadata.company,
            "incident": self.metadata.incident,
            "incident_started": self.metadata.incident_started,
            "incident_discovered": self.metadata.incident_discovered,
            "notes": self.metadata.notes,
            "compromised_accounts": list(self.metadata.compromised_accounts),
            "compromised_machines": list(self.metadata.compromised_machines),
            "known_iocs": list(self.metadata.known_iocs),
        }
        payload: dict[str, Any] = {
            "case": self.case_name,
            "generated_at": self.generated_at,
            "metadata": meta_dict,
            "tagged_events": [asdict(e) for e in self.tagged_events],
            "commented_events": [asdict(e) for e in self.commented_events],
            "starred_events": [asdict(e) for e in self.starred_events],
            "exhibits": [
                {
                    "id": e.id,
                    "title": e.title,
                    "description": e.description,
                    "body_excerpt": _exhibit_excerpt(e.body),
                }
                for e in self.exhibits
            ],
        }
        return (
            "Draft a forensic report from the following case data. Tagged "
            "and commented events represent the analyst's manual triage — "
            "treat them as the load-bearing evidence. Starred events are "
            "secondary leads.\n\n"
            "```json\n"
            + json.dumps(payload, indent=2, default=str)
            + "\n```"
        )


def gather_report_context(case: Case) -> ReportContext:
    """Collect every fact the analyst has manually established: metadata,
    plus the tagged / commented / starred events."""
    con = case.con
    tagged = _events_with_annotations(con, kind="tagged")
    commented = _events_with_annotations(con, kind="commented")
    starred = _events_with_annotations(con, kind="starred")
    return ReportContext(
        case_name=case.name,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        metadata=load_metadata(case.path),
        tagged_events=tagged,
        commented_events=commented,
        starred_events=starred,
        exhibits=tuple(list_exhibits(con)),
    )


def _events_with_annotations(
    con: sqlite3.Connection, *, kind: str,
) -> tuple[ReportEvent, ...]:
    """Return events that have at least one annotation of the given kind,
    each annotated with their tags and comments so the model can attribute
    evidence to the analyst."""
    if kind == "tagged":
        where_join = (
            "JOIN annotation_tag a ON a.event_hash = e.event_hash"
        )
    elif kind == "commented":
        where_join = (
            "JOIN annotation_comment a ON a.event_hash = e.event_hash"
        )
    elif kind == "starred":
        where_join = (
            "JOIN annotation_star a ON a.event_hash = e.event_hash"
        )
    else:
        raise ValueError(f"unknown kind: {kind}")

    sql = (
        "SELECT DISTINCT e.id, e.ts_usec, e.data_type, e.parser, e.source_short, "
        "e.display_name, e.message, e.timeline_id, e.event_hash "
        f"FROM event e {where_join} "
        "ORDER BY e.ts_usec ASC, e.id ASC"
    )
    out: list[ReportEvent] = []
    for row in con.execute(sql):
        eid, ts, dt, parser, ss, dn, msg, tid, ehash = row
        tags = tuple(t for (t,) in con.execute(
            "SELECT tag FROM annotation_tag WHERE event_hash=? ORDER BY tag",
            (bytes(ehash),),
        ))
        comments = tuple(c for (c,) in con.execute(
            "SELECT body FROM annotation_comment WHERE event_hash=? "
            "ORDER BY created_at ASC",
            (bytes(ehash),),
        ))
        starred = bool(con.execute(
            "SELECT 1 FROM annotation_star WHERE event_hash=?", (bytes(ehash),)
        ).fetchone())
        out.append(ReportEvent(
            id=int(eid),
            ts=_format_ts(int(ts)),
            data_type=str(dt or ""),
            parser=str(parser or ""),
            source_short=str(ss or ""),
            display_name=str(dn or ""),
            message=str(msg or "")[:1000],
            timeline_id=str(tid or ""),
            tags=tags,
            comments=comments,
            starred=starred,
        ))
    return tuple(out)


def _format_ts(ts_usec: int) -> str:
    if ts_usec <= 0:
        return ""
    return datetime.fromtimestamp(ts_usec / 1_000_000, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _fence_for(body: str) -> str:
    """A backtick run one longer than the longest run in ``body``, min 3, so
    code-fence content can never break out of the fenced block."""
    longest = run = 0
    for ch in body:
        if ch == "`":
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return "`" * max(3, longest + 1)


def render_exhibits_appendix(context: "ReportContext") -> str:
    """Deterministic verbatim '## Exhibits' section. Empty when no exhibits.
    Generated by us — not the model — so the bodies are byte-faithful."""
    if not context.exhibits:
        return ""
    parts = ["\n\n## Exhibits\n"]
    for i, e in enumerate(context.exhibits, start=1):
        parts.append(f"\n### Exhibit {i} — {e.title}\n")
        if e.description:
            parts.append(f"\n{e.description}\n")
        fence = _fence_for(e.body)
        parts.append(f"\n{fence}\n{e.body}\n{fence}\n")
    return "".join(parts)


async def generate_report(
    *,
    client: LLMClient,
    settings: AISettings,
    context: ReportContext,
    on_text: Callable[[str], Awaitable[None] | None] | None = None,
) -> str:
    """Stream a markdown report. Emits each text chunk to on_text as it
    arrives so the UI can render the answer typing in. Returns the
    complete markdown when the stream ends."""
    messages = [
        ChatMessage(role="system", content=REPORT_SYSTEM_PROMPT),
        ChatMessage(role="user", content=context.to_prompt()),
    ]
    buffer = ""
    async for sev in client.chat_stream(messages, tools=[], model=settings.model):
        if sev.kind == "text" and sev.text:
            buffer += sev.text
            if on_text is not None:
                res = on_text(sev.text)
                if hasattr(res, "__await__"):
                    await res  # type: ignore[func-returns-value]
        elif sev.kind == "done":
            break
    appendix = render_exhibits_appendix(context)
    if appendix:
        buffer += appendix
        if on_text is not None:
            res = on_text(appendix)
            if hasattr(res, "__await__"):
                await res  # type: ignore[func-returns-value]
    return buffer

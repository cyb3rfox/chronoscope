from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from chronoscope.ai.client import AssistantReply, StreamEvent
from chronoscope.ai.jobs.report import (
    ReportContext,
    gather_report_context,
    generate_report,
)
from chronoscope.ai.settings import AISettings
from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.core.exhibits import Exhibit, add_exhibit
from chronoscope.core.metadata import CaseMetadata, save_metadata
from chronoscope.ingest.pipeline import ingest_file

DATA = Path(__file__).parent / "data" / "sample.jsonl"


class _StreamingStub:
    """Replays scripted AssistantReply objects as a text stream so the
    generator's streaming path is exercised."""

    def __init__(self, replies: list[AssistantReply], *, chunk_size: int = 0) -> None:
        self._replies = list(replies)
        self._chunk_size = chunk_size

    def chat_stream(self, messages, tools, *, model) -> AsyncIterator[StreamEvent]:
        return self._iter(self._replies.pop(0), messages)

    async def _iter(self, reply, messages):
        self.last_messages = list(messages)
        if reply.content:
            if self._chunk_size > 0:
                for i in range(0, len(reply.content), self._chunk_size):
                    yield StreamEvent(
                        kind="text",
                        text=reply.content[i : i + self._chunk_size],
                    )
            else:
                yield StreamEvent(kind="text", text=reply.content)
        yield StreamEvent(kind="done", finish_reason="stop")


@pytest.fixture
def case_with_annotations(case_dir):
    init_case(case_dir, name="acme-case")
    ingest_file(case_dir, DATA, name="sample")
    save_metadata(
        case_dir,
        CaseMetadata(
            company="ACME",
            incident="Suspected RAT infection",
            compromised_accounts=("alice",),
            compromised_machines=("PC01",),
            known_iocs=("evil.example.com",),
        ),
    )
    with open_case(case_dir) as c:
        # Tag and comment two events so the report has something to chew on.
        rows = c.con.execute(
            "SELECT id, event_hash FROM event ORDER BY ts_usec ASC LIMIT 2"
        ).fetchall()
        for _, h in rows:
            store.add_tag(c.con, bytes(h), "lateral-movement")
            store.add_comment(c.con, bytes(h), "looks suspicious")
            store.set_star(c.con, bytes(h), True)
        c.con.commit()
        yield c


def test_gather_report_context_collects_metadata_and_annotations(
    case_with_annotations,
):
    ctx = gather_report_context(case_with_annotations)
    assert ctx.case_name == "acme-case"
    assert ctx.metadata.company == "ACME"
    assert len(ctx.tagged_events) == 2
    assert len(ctx.commented_events) == 2
    assert len(ctx.starred_events) == 2
    # Each tagged event must carry its tags and analyst comment.
    for ev in ctx.tagged_events:
        assert "lateral-movement" in ev.tags
        assert "looks suspicious" in ev.comments


def test_report_context_is_empty_when_nothing_marked(case_dir):
    init_case(case_dir, name="empty")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        ctx = gather_report_context(c)
    assert ctx.is_empty()


def test_report_context_to_prompt_includes_facts():
    ctx = ReportContext(
        case_name="case-1",
        generated_at="2026-05-11T00:00:00+00:00",
        metadata=CaseMetadata(
            company="ACME",
            compromised_accounts=("alice",),
            known_iocs=("evil.example.com",),
        ),
    )
    prompt = ctx.to_prompt()
    assert "case-1" in prompt
    assert "ACME" in prompt
    assert "alice" in prompt
    assert "evil.example.com" in prompt
    # JSON block is parseable so the model gets stable structured input.
    body = prompt.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    payload = json.loads(body)
    assert payload["metadata"]["company"] == "ACME"


@pytest.mark.asyncio
async def test_generate_report_streams_chunks_to_callback(case_with_annotations):
    ctx = gather_report_context(case_with_annotations)
    chunks: list[str] = []
    client = _StreamingStub(
        [AssistantReply(content="# Report\n\nbody", tool_calls=())],
        chunk_size=4,
    )
    final = await generate_report(
        client=client,
        settings=AISettings(),
        context=ctx,
        on_text=lambda s: chunks.append(s),
    )
    assert final == "# Report\n\nbody"
    # Stream actually chunked, not delivered in one shot.
    assert len(chunks) > 1
    assert "".join(chunks) == final


@pytest.mark.asyncio
async def test_generate_report_sends_system_and_user_messages():
    ctx = ReportContext(case_name="x", generated_at="t")
    client = _StreamingStub(
        [AssistantReply(content="ok", tool_calls=())]
    )
    await generate_report(
        client=client, settings=AISettings(), context=ctx,
    )
    roles = [m.role for m in client.last_messages]
    assert roles == ["system", "user"]
    # The user message must carry the JSON context block for the model.
    assert "```json" in client.last_messages[1].content


# ---------------------------------------------------------------------------
# Task 3: Report context carries exhibits
# ---------------------------------------------------------------------------

def test_gather_report_context_collects_exhibits(case_with_annotations):
    add_exhibit(
        case_with_annotations.con,
        title="evil.ps1", description="dropper", body="whoami\n",
    )
    ctx = gather_report_context(case_with_annotations)
    assert len(ctx.exhibits) == 1
    assert ctx.exhibits[0].title == "evil.ps1"


def test_report_context_not_empty_with_only_exhibits():
    ctx = ReportContext(
        case_name="c", generated_at="t",
        exhibits=(Exhibit(1, "s.sh", "d", "echo hi", "t", "t"),),
    )
    assert not ctx.is_empty()


def test_to_prompt_includes_exhibit_title_and_excerpt():
    ctx = ReportContext(
        case_name="c", generated_at="t",
        exhibits=(Exhibit(1, "evil.ps1", "dropper", "whoami", "t", "t"),),
    )
    prompt = ctx.to_prompt()
    assert "evil.ps1" in prompt
    body = prompt.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    import json as _json
    payload = _json.loads(body)
    assert payload["exhibits"][0]["title"] == "evil.ps1"
    assert payload["exhibits"][0]["body_excerpt"] == "whoami"


def test_to_prompt_caps_long_exhibit_body():
    from chronoscope.ai.jobs.report import EXHIBIT_PROMPT_BODY_CAP
    big = "A" * (EXHIBIT_PROMPT_BODY_CAP + 500)
    ctx = ReportContext(
        case_name="c", generated_at="t",
        exhibits=(Exhibit(1, "big.txt", "", big, "t", "t"),),
    )
    body = ctx.to_prompt().split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    import json as _json
    excerpt = _json.loads(body)["exhibits"][0]["body_excerpt"]
    assert len(excerpt) < len(big)
    assert "truncated" in excerpt


# ---------------------------------------------------------------------------
# Task 4: Verbatim exhibits appendix
# ---------------------------------------------------------------------------

def test_render_exhibits_appendix_reproduces_body_verbatim():
    from chronoscope.ai.jobs.report import render_exhibits_appendix
    body = "Get-Process | Stop-Process\nwhoami /all\n"
    ctx = ReportContext(
        case_name="c", generated_at="t",
        exhibits=(Exhibit(1, "evil.ps1", "dropper", body, "t", "t"),),
    )
    md = render_exhibits_appendix(ctx)
    assert "## Exhibits" in md
    assert "Exhibit 1 — evil.ps1" in md
    assert "dropper" in md
    assert body in md


def test_render_exhibits_appendix_fences_safely_around_backticks():
    from chronoscope.ai.jobs.report import render_exhibits_appendix
    body = "text with ```triple backticks``` inside"
    ctx = ReportContext(
        case_name="c", generated_at="t",
        exhibits=(Exhibit(1, "x.md", "", body, "t", "t"),),
    )
    md = render_exhibits_appendix(ctx)
    assert body in md
    assert "````" in md


def test_render_exhibits_appendix_empty_when_no_exhibits():
    ctx = ReportContext(case_name="c", generated_at="t")
    from chronoscope.ai.jobs.report import render_exhibits_appendix
    assert render_exhibits_appendix(ctx) == ""


@pytest.mark.asyncio
async def test_generate_report_appends_verbatim_appendix():
    body = "echo pwned\n"
    ctx = ReportContext(
        case_name="c", generated_at="t",
        exhibits=(Exhibit(1, "evil.sh", "dropper", body, "t", "t"),),
    )
    chunks: list[str] = []
    client = _StreamingStub([AssistantReply(content="# Report\n\nSee Exhibit 1.", tool_calls=())])
    final = await generate_report(
        client=client, settings=AISettings(), context=ctx,
        on_text=lambda s: chunks.append(s),
    )
    assert "## Exhibits" in final
    assert body in final
    assert "## Exhibits" in "".join(chunks)


# ---------------------------------------------------------------------------
# Task 5: Report prompt mentions exhibits
# ---------------------------------------------------------------------------

def test_system_prompt_mentions_exhibits():
    from chronoscope.ai.jobs.report import REPORT_SYSTEM_PROMPT
    low = REPORT_SYSTEM_PROMPT.lower()
    assert "exhibit" in low
    assert "appended" in low or "do not" in low

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from textual.app import App
from textual.containers import VerticalScroll
from textual.widgets import Static

from chronoscope.ai.client import AssistantReply, StreamEvent
from chronoscope.ai.jobs.report import ReportContext, gather_report_context
from chronoscope.ai.settings import AISettings
from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.core.metadata import CaseMetadata, save_metadata
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.screens.ai_report import AIReportScreen

DATA = Path(__file__).parent / "data" / "sample.jsonl"


class _StreamingStub:
    def __init__(self, replies: list[AssistantReply]) -> None:
        self._replies = list(replies)

    def chat_stream(self, messages, tools, *, model) -> AsyncIterator[StreamEvent]:
        return self._iter(self._replies.pop(0))

    async def _iter(self, reply):
        if reply.content:
            for ch in reply.content:
                yield StreamEvent(kind="text", text=ch)
        yield StreamEvent(kind="done", finish_reason="stop")


class _Harness(App):
    def __init__(
        self,
        *,
        client,
        context: ReportContext,
        case_path: Path,
    ) -> None:
        super().__init__()
        self._client = client
        # NB: not ``self._context`` — that shadows Textual's
        # ``App._context`` context-manager and hangs ``run_test()``.
        self._report_ctx = context
        self._case_path = case_path

    def on_mount(self):
        self.push_screen(AIReportScreen(
            client=self._client,
            settings=AISettings(),
            context=self._report_ctx,
            case_path=self._case_path,
        ))


def _seed_case(case_dir: Path):
    init_case(case_dir, name="acme")
    ingest_file(case_dir, DATA, name="sample")
    save_metadata(case_dir, CaseMetadata(company="ACME"))
    with open_case(case_dir) as c:
        row = c.con.execute(
            "SELECT event_hash FROM event ORDER BY ts_usec ASC LIMIT 1"
        ).fetchone()
        store.add_tag(c.con, bytes(row[0]), "test")
        c.con.commit()


@pytest.mark.asyncio
async def test_report_screen_renders_streaming_markdown(case_dir):
    _seed_case(case_dir)
    with open_case(case_dir) as c:
        ctx = gather_report_context(c)
    client = _StreamingStub([
        AssistantReply(content="# Title\n\nbody", tool_calls=()),
    ])
    harness = _Harness(client=client, context=ctx, case_path=case_dir)
    async with harness.run_test() as pilot:
        # Let the worker run to completion.
        for _ in range(8):
            await pilot.pause()
        status = pilot.app.screen.query_one("#status", Static)
        assert "ready" in str(status.render()).lower()


@pytest.mark.asyncio
async def test_report_screen_save_writes_file_in_case_dir(case_dir):
    _seed_case(case_dir)
    with open_case(case_dir) as c:
        ctx = gather_report_context(c)
    client = _StreamingStub([
        AssistantReply(content="# Drafted\n\nbody", tool_calls=()),
    ])
    harness = _Harness(client=client, context=ctx, case_path=case_dir)
    async with harness.run_test() as pilot:
        for _ in range(8):
            await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        screen = pilot.app.screen
        assert screen.saved_path is not None
        assert screen.saved_path.parent == case_dir
        assert screen.saved_path.name.startswith("report-")
        assert screen.saved_path.suffix == ".md"
        assert screen.saved_path.read_text(encoding="utf-8") == "# Drafted\n\nbody"


@pytest.mark.asyncio
async def test_report_screen_empty_context_shows_helpful_notice(case_dir):
    """If the analyst hits R before tagging anything, the screen should
    explain why there's nothing to draft instead of calling the model."""
    init_case(case_dir, name="empty")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        ctx = gather_report_context(c)
    # No client should be called — provide one that would explode if invoked.

    class _Boom:
        def chat_stream(self, *a, **kw):
            raise AssertionError("client must not be called for empty context")

    harness = _Harness(client=_Boom(), context=ctx, case_path=case_dir)
    async with harness.run_test() as pilot:
        await pilot.pause()
        scroll = pilot.app.screen.query_one("#body-scroll", VerticalScroll)
        rendered = "\n".join(
            str(getattr(child.render(), "plain", child.render()))
            for child in scroll.children
        )
        assert "No content to report on" in rendered

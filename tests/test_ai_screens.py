from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from textual.app import App
from textual.containers import VerticalScroll
from textual.widgets import Input

from chronoscope.ai.agent import ChatAgent
from chronoscope.ai.client import AssistantReply, ChatMessage, StreamEvent, ToolCall
from chronoscope.ai.history import ChatLog
from chronoscope.ai.settings import AISettings
from chronoscope.ai.tools import Tool, ToolRegistry
from chronoscope.tui.screens.ai_chat import AIChatScreen
from chronoscope.tui.screens.ai_settings import AISettingsScreen


class _StubClient:
    def __init__(
        self,
        replies: list[AssistantReply],
        *,
        chunk_size: int = 0,
        delay: float = 0.0,
    ) -> None:
        self._replies = list(replies)
        self._chunk_size = chunk_size
        # Seconds to await before each text chunk. With delay > 0 the turn
        # genuinely spans several event-loop iterations, like a real LLM —
        # which is what makes the spinner/streaming behaviour observable.
        self._delay = delay

    def chat_stream(self, messages, tools, *, model) -> AsyncIterator[StreamEvent]:
        reply = self._replies.pop(0)
        return self._iter(reply)

    async def _iter(self, reply: AssistantReply) -> AsyncIterator[StreamEvent]:
        if reply.content:
            if self._chunk_size > 0:
                for i in range(0, len(reply.content), self._chunk_size):
                    if self._delay:
                        await asyncio.sleep(self._delay)
                    yield StreamEvent(
                        kind="text",
                        text=reply.content[i : i + self._chunk_size],
                    )
            else:
                if self._delay:
                    await asyncio.sleep(self._delay)
                yield StreamEvent(kind="text", text=reply.content)
        for tc in reply.tool_calls:
            yield StreamEvent(kind="tool_call", tool_call=tc)
        yield StreamEvent(kind="done", finish_reason="stop")


def _make_agent(
    tmp_path: Path,
    replies: list[AssistantReply],
    *,
    chunk_size: int = 0,
    delay: float = 0.0,
) -> ChatAgent:
    reg = ToolRegistry()
    reg.register(Tool("echo", "echo", {"type": "object"},
                      lambda a: {"echoed": a}))
    return ChatAgent(
        client=_StubClient(replies, chunk_size=chunk_size, delay=delay),
        registry=reg,
        settings=AISettings(),
        log=ChatLog(tmp_path),
    )


async def _send_prompt(pilot, text: str) -> None:
    """Type ``text`` into the chat input, submit it, and wait for the agent
    turn (which runs in a worker, off the message pump) to finish — then
    flush the resulting mounts/updates so the transcript is stable to
    assert against."""
    prompt = pilot.app.screen.query_one("#prompt", Input)
    prompt.value = text
    await prompt.action_submit()
    # Let on_input_submitted run so the worker exists, then wait it out.
    await pilot.pause()
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()


class _ChatHarness(App):
    def __init__(self, agent: ChatAgent) -> None:
        super().__init__()
        self._agent = agent

    def on_mount(self):
        self.push_screen(AIChatScreen(self._agent, AISettings()))


def _transcript_text(pilot) -> str:
    scroll = pilot.app.screen.query_one("#transcript", VerticalScroll)
    chunks: list[str] = []
    for child in scroll.children:
        try:
            rendered = child.render()
        except Exception:
            continue
        # Static.render() returns the renderable directly (rich.Content for
        # markup-styled lines) or wraps Rich renderables in a RichVisual
        # whose ._renderable points at the original (e.g. Markdown).
        inner = getattr(rendered, "_renderable", rendered)
        text = (
            getattr(inner, "markup", None)
            or getattr(inner, "plain", None)
            or str(inner)
        )
        chunks.append(text)
    return "\n".join(chunks)


@pytest.mark.asyncio
async def test_chat_screen_renders_user_and_assistant_turns(tmp_path):
    agent = _make_agent(
        tmp_path,
        [AssistantReply(content="hello back", tool_calls=())],
    )
    harness = _ChatHarness(agent)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await _send_prompt(pilot, "hi")
        rendered = _transcript_text(pilot)
        assert "hi" in rendered
        assert "hello back" in rendered


@pytest.mark.asyncio
async def test_chat_screen_streams_assistant_text(tmp_path):
    """Streaming chunks must accumulate into a single assistant line — not
    one separate line per delta."""
    agent = _make_agent(
        tmp_path,
        [AssistantReply(content="streaming reply text", tool_calls=())],
        chunk_size=4,
    )
    harness = _ChatHarness(agent)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await _send_prompt(pilot, "go")
        scroll = pilot.app.screen.query_one("#transcript", VerticalScroll)
        # Tool-info banner + user line + assistant role label + ONE assistant
        # markdown body. If streaming mounted a new Static per delta we'd
        # have many more children.
        assert len(scroll.children) == 4
        rendered = _transcript_text(pilot)
        assert "streaming reply text" in rendered


@pytest.mark.asyncio
async def test_chat_screen_replays_loaded_history_on_open(tmp_path):
    """Opening a chat must show the prior conversation the agent loaded
    from disk, otherwise the user thinks history was lost even though the
    agent has it."""
    from chronoscope.ai.client import ChatMessage as CM, ToolCall as TC

    # Hand-built agent with pre-loaded history (no LLM call needed).
    reg = ToolRegistry()
    reg.register(Tool("echo", "echo", {"type": "object"}, lambda a: a))
    history = [
        CM(role="user", content="earlier question"),
        CM(role="assistant", content="earlier answer", tool_calls=()),
        CM(role="user", content="and a follow-up"),
        CM(
            role="assistant",
            content=None,
            tool_calls=(TC(id="c1", name="echo", arguments="{}"),),
        ),
        CM(role="tool", content='{"echoed":1}', tool_call_id="c1", name="echo"),
        CM(role="assistant", content="follow-up answer", tool_calls=()),
    ]
    agent = ChatAgent(
        client=_StubClient([]),
        registry=reg,
        settings=AISettings(),
        log=ChatLog(tmp_path),
        history=history,
    )
    harness = _ChatHarness(agent)
    async with harness.run_test() as pilot:
        await pilot.pause()
        rendered = _transcript_text(pilot)
        for needle in (
            "earlier question",
            "earlier answer",
            "and a follow-up",
            "echo",
            "follow-up answer",
        ):
            assert needle in rendered, f"history line missing: {needle}"


@pytest.mark.asyncio
async def test_chat_screen_renders_assistant_text_as_markdown(tmp_path):
    """Models reply in markdown. The assistant body Static must hold a
    rich.markdown.Markdown renderable so bullets, code, headings format —
    not a raw string showing literal **stars** and `# hashes`."""
    from rich.markdown import Markdown
    md_source = "# Heading\n\n- one\n- two\n\n**bold** and `code`"
    agent = _make_agent(
        tmp_path,
        [AssistantReply(content=md_source, tool_calls=())],
    )
    harness = _ChatHarness(agent)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await _send_prompt(pilot, "summarize")
        scroll = pilot.app.screen.query_one("#transcript", VerticalScroll)
        # Last child is the assistant body that should hold a Markdown
        # (Textual wraps Rich renderables in a RichVisual whose
        # ._renderable points at the original).
        body = scroll.children[-1]
        rendered = body.render()
        inner = getattr(rendered, "_renderable", rendered)
        assert isinstance(inner, Markdown)
        assert inner.markup == md_source


@pytest.mark.asyncio
async def test_chat_screen_shows_tool_calls(tmp_path):
    tc = ToolCall(id="c1", name="echo", arguments=json.dumps({"x": 1}))
    agent = _make_agent(tmp_path, [
        AssistantReply(content=None, tool_calls=(tc,)),
        AssistantReply(content="done", tool_calls=()),
    ])
    harness = _ChatHarness(agent)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await _send_prompt(pilot, "go")
        rendered = _transcript_text(pilot)
        assert "echo" in rendered
        assert "done" in rendered


@pytest.mark.asyncio
async def test_chat_screen_spinner_appears_during_thinking_and_clears_at_end(tmp_path):
    """The user must see *something* moving as soon as they hit enter, and
    that something must go away when the turn ends so they know it's their
    turn again.

    Mechanically: the agent turn runs in a worker, so on_input_submitted
    returns immediately and the screen's message pump stays free — that's
    what lets the spinner mount/animate and streamed text repaint while
    the model is responding. Awaiting the turn inline (the old bug) froze
    the screen until the turn was over: no spinner, no streaming.
    """
    from textual.worker import WorkerState

    from chronoscope.tui.screens.ai_chat import _SpinnerLine

    # Slow stream: the turn genuinely spans many event-loop iterations,
    # like a real LLM, so its in-flight state is observable.
    agent = _make_agent(
        tmp_path,
        [AssistantReply(content="hello there friend", tool_calls=())],
        chunk_size=3,
        delay=0.1,
    )
    harness = _ChatHarness(agent)
    async with harness.run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        # Idle: no spinner mounted.
        assert not list(screen.query(_SpinnerLine))

        prompt = screen.query_one("#prompt", Input)
        prompt.value = "hi"
        await prompt.action_submit()
        await pilot.pause()

        # on_input_submitted returned immediately, leaving the turn running
        # in a worker — it did NOT block the handler for the whole turn.
        turn_workers = [w for w in pilot.app.workers if w.name == "chat-turn"]
        assert turn_workers, "the agent turn must run in a worker, not inline"
        assert turn_workers[0].state in (WorkerState.PENDING, WorkerState.RUNNING)

        # While the model is mid-stream, the spinner is mounted and visible.
        await pilot.pause(0.03)
        await pilot.pause()
        assert list(screen.query(_SpinnerLine)), \
            "spinner must be visible while the turn is in flight"

        # Turn done: spinner gone, and the streamed chunks accumulated into
        # a single assistant line.
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert not list(screen.query(_SpinnerLine))
        assert "hello there friend" in _transcript_text(pilot)


@pytest.mark.asyncio
async def test_chat_screen_thinking_event_mounts_spinner(tmp_path):
    """Driving the thinking event directly proves the spinner mounts and
    that subsequent text_delta removes it — without relying on real timing
    against an in-flight LLM call."""
    from chronoscope.ai.agent import AgentEvent
    from chronoscope.tui.screens.ai_chat import _SpinnerLine

    agent = _make_agent(
        tmp_path,
        [AssistantReply(content="(unused)", tool_calls=())],
    )
    harness = _ChatHarness(agent)
    async with harness.run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen

        screen._on_event(AgentEvent(kind="user", text="hi"))
        screen._on_event(AgentEvent(kind="thinking"))
        await pilot.pause()
        assert list(screen.query(_SpinnerLine)), \
            "spinner must mount on thinking so the user sees activity"

        screen._on_event(AgentEvent(kind="text_delta", text="hello"))
        await pilot.pause()
        assert not list(screen.query(_SpinnerLine)), \
            "spinner must come down once text starts streaming"


@pytest.mark.asyncio
async def test_chat_screen_tool_call_swaps_spinner_label(tmp_path):
    """Between tool_call and tool_result the spinner label must change so
    the analyst can tell the agent is running a tool, not just waiting on
    the model."""
    from chronoscope.ai.agent import AgentEvent
    from chronoscope.tui.screens.ai_chat import _SpinnerLine

    agent = _make_agent(
        tmp_path,
        [AssistantReply(content="(unused)", tool_calls=())],
    )
    harness = _ChatHarness(agent)
    async with harness.run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        screen._on_event(AgentEvent(kind="user", text="hi"))
        screen._on_event(AgentEvent(
            kind="tool_call", name="search_events", text="{}",
        ))
        await pilot.pause()
        spinners = list(screen.query(_SpinnerLine))
        assert spinners
        assert "search_events" in spinners[0]._label


class _SettingsHarness(App):
    def __init__(self, initial: AISettings) -> None:
        super().__init__()
        self._initial = initial
        self.result: AISettings | None = None

    def on_mount(self):
        self.push_screen(
            AISettingsScreen(self._initial), callback=self._on_result
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_ai_settings_screen_save_returns_updated():
    harness = _SettingsHarness(AISettings(model="initial"))
    async with harness.run_test() as pilot:
        await pilot.pause()
        pilot.app.screen.query_one("#model", Input).value = "deepseek-chat"
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.model == "deepseek-chat"


@pytest.mark.asyncio
async def test_ai_settings_screen_cancel_returns_none():
    harness = _SettingsHarness(AISettings())
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_ai_settings_screen_rejects_invalid_limits():
    harness = _SettingsHarness(AISettings())
    async with harness.run_test() as pilot:
        await pilot.pause()
        pilot.app.screen.query_one("#max_iters", Input).value = "0"
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(pilot.app.screen, AISettingsScreen)
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from chronoscope.ai.agent import AgentEvent, ChatAgent
from chronoscope.ai.client import AssistantReply, ChatMessage, StreamEvent, ToolCall
from chronoscope.ai.history import ChatLog
from chronoscope.ai.settings import AISettings
from chronoscope.ai.tools import Tool, ToolError, ToolRegistry


class _StubClient:
    """Plays back a scripted sequence of replies as streaming chat output so
    the agent loop can be tested without touching the network. Each AssistantReply
    becomes one stream: zero or more text events, then any tool_call events,
    then a done event."""

    def __init__(self, replies: list[AssistantReply], *, chunk_size: int = 0) -> None:
        self._replies = list(replies)
        self._chunk_size = chunk_size
        self.received: list[list[ChatMessage]] = []

    def chat_stream(self, messages, tools, *, model) -> AsyncIterator[StreamEvent]:
        self.received.append(list(messages))
        if not self._replies:
            raise AssertionError("StubClient ran out of scripted replies")
        reply = self._replies.pop(0)
        return self._iter(reply)

    async def _iter(self, reply: AssistantReply) -> AsyncIterator[StreamEvent]:
        if reply.content:
            if self._chunk_size > 0:
                # Split into chunks so tests can observe streaming behavior.
                text = reply.content
                for i in range(0, len(text), self._chunk_size):
                    yield StreamEvent(kind="text", text=text[i : i + self._chunk_size])
            else:
                yield StreamEvent(kind="text", text=reply.content)
        for tc in reply.tool_calls:
            yield StreamEvent(kind="tool_call", tool_call=tc)
        yield StreamEvent(kind="done", finish_reason="stop")


def _registry_with_echo() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool(
        name="echo",
        description="echo",
        parameters_schema={"type": "object",
                           "properties": {"x": {"type": "integer"}}},
        fn=lambda args: {"echoed": args.get("x")},
    ))
    return reg


@pytest.mark.asyncio
async def test_agent_returns_text_when_no_tool_call(tmp_path: Path):
    client = _StubClient([AssistantReply(content="all clear", tool_calls=())])
    agent = ChatAgent(
        client=client,
        registry=_registry_with_echo(),
        settings=AISettings(),
        log=ChatLog(tmp_path),
    )
    out = await agent.send("how does it look?")
    assert out == "all clear"


@pytest.mark.asyncio
async def test_agent_dispatches_tool_then_returns_text(tmp_path: Path):
    tc = ToolCall(id="c1", name="echo", arguments=json.dumps({"x": 7}))
    client = _StubClient([
        AssistantReply(content=None, tool_calls=(tc,)),
        AssistantReply(content="x was 7", tool_calls=()),
    ])
    log = ChatLog(tmp_path)
    agent = ChatAgent(
        client=client,
        registry=_registry_with_echo(),
        settings=AISettings(),
        log=log,
    )
    out = await agent.send("call echo with 7")
    assert out == "x was 7"
    second_call_msgs = client.received[1]
    tool_msg = next(m for m in second_call_msgs if m.role == "tool")
    assert tool_msg.tool_call_id == "c1"
    assert json.loads(tool_msg.content)["echoed"] == 7
    kinds = [e["kind"] for e in log.read_all()]
    # The assistant entry that emits the tool call is logged so future
    # sessions can rebuild the message sequence.
    assert kinds == ["user", "assistant", "tool_call", "tool_result", "assistant"]


@pytest.mark.asyncio
async def test_agent_emits_streaming_events(tmp_path: Path):
    """Streaming reply must surface text_delta + thinking + assistant_complete
    so the UI can render typing-style output."""
    client = _StubClient(
        [AssistantReply(content="hello world", tool_calls=())],
        chunk_size=3,  # "hel"/"lo "/"wor"/"ld"
    )
    agent = ChatAgent(
        client=client,
        registry=_registry_with_echo(),
        settings=AISettings(),
        log=ChatLog(tmp_path),
    )
    events: list[AgentEvent] = []
    final = await agent.send("hi", on_event=lambda e: events.append(e))

    assert final == "hello world"
    kinds = [e.kind for e in events]
    # Expect: user, thinking, several text_delta, assistant_complete, stop.
    assert kinds[0] == "user"
    assert kinds[1] == "thinking"
    deltas = [e.text for e in events if e.kind == "text_delta"]
    assert "".join(deltas) == "hello world"
    assert len(deltas) > 1  # actually streamed in chunks
    assert any(e.kind == "assistant_complete" and e.text == "hello world"
               for e in events)
    assert kinds[-1] == "stop"


@pytest.mark.asyncio
async def test_agent_emits_thinking_after_tool_result(tmp_path: Path):
    """When the model uses a tool, the UI must see a 'thinking' event after
    the tool result so the spinner reappears while the second LLM call runs."""
    tc = ToolCall(id="c1", name="echo", arguments=json.dumps({"x": 1}))
    client = _StubClient([
        AssistantReply(content=None, tool_calls=(tc,)),
        AssistantReply(content="done", tool_calls=()),
    ])
    agent = ChatAgent(
        client=client,
        registry=_registry_with_echo(),
        settings=AISettings(),
        log=ChatLog(tmp_path),
    )
    events: list[AgentEvent] = []
    await agent.send("hi", on_event=lambda e: events.append(e))
    kinds = [e.kind for e in events]
    # Two thinking events: before each LLM call.
    assert kinds.count("thinking") == 2
    # Order: user, thinking, tool_call, tool_result, thinking, text_delta..., assistant_complete, stop.
    assert kinds.index("tool_result") < kinds.index("text_delta")


@pytest.mark.asyncio
async def test_agent_iteration_cap_prevents_runaway(tmp_path: Path):
    looping_call = ToolCall(id="c", name="echo", arguments="{}")
    replies = [AssistantReply(content=None, tool_calls=(looping_call,))] * 5
    client = _StubClient(replies)
    agent = ChatAgent(
        client=client,
        registry=_registry_with_echo(),
        settings=AISettings(max_tool_iterations=3),
        log=ChatLog(tmp_path),
    )
    out = await agent.send("loop forever")
    assert "Tool-loop limit reached" in out
    assert len(client.received) == 3


@pytest.mark.asyncio
async def test_agent_surfaces_llm_errors_as_text(tmp_path: Path):
    class _Boom:
        def chat_stream(self, messages, tools, *, model):
            async def gen():
                raise RuntimeError("network down")
                yield  # pragma: no cover - unreachable
            return gen()

    agent = ChatAgent(
        client=_Boom(),
        registry=_registry_with_echo(),
        settings=AISettings(),
        log=ChatLog(tmp_path),
    )
    out = await agent.send("hi")
    assert "network down" in out


@pytest.mark.asyncio
async def test_agent_logs_assistant_with_tool_calls(tmp_path: Path):
    """The assistant turn that emits tool calls must be persisted with the
    full tool_calls structure so load_session can reconstruct it."""
    tc = ToolCall(id="c1", name="echo", arguments="{}")
    client = _StubClient([
        AssistantReply(content=None, tool_calls=(tc,)),
        AssistantReply(content="done", tool_calls=()),
    ])
    log = ChatLog(tmp_path)
    agent = ChatAgent(
        client=client,
        registry=_registry_with_echo(),
        settings=AISettings(),
        log=log,
    )
    await agent.send("go")
    entries = [e for e in log.read_all() if e["kind"] == "assistant"]
    # Two assistant entries: one with tool_calls (no text), one with text.
    assert len(entries) == 2
    assert entries[0]["text"] == ""
    assert entries[0]["tool_calls"][0]["name"] == "echo"
    assert entries[1]["text"] == "done"
    assert entries[1]["tool_calls"] == []


@pytest.mark.asyncio
async def test_agent_resumes_from_loaded_history(tmp_path: Path):
    """Constructing a ChatAgent with prior history must include those
    messages in the next LLM call so the model has context."""
    from chronoscope.ai.history import load_session

    # Drive a first session that produces some history.
    log = ChatLog(tmp_path)
    first = ChatAgent(
        client=_StubClient([AssistantReply(content="hello", tool_calls=())]),
        registry=_registry_with_echo(),
        settings=AISettings(),
        log=log,
    )
    await first.send("first turn")

    # Second session resumes from disk.
    second_client = _StubClient([
        AssistantReply(content="continuing", tool_calls=()),
    ])
    second = ChatAgent(
        client=second_client,
        registry=_registry_with_echo(),
        settings=AISettings(),
        log=log,
        history=load_session(log),
    )
    await second.send("second turn")

    # The LLM call from the second session must have seen the prior turns.
    sent_messages = second_client.received[0]
    roles = [m.role for m in sent_messages]
    contents = [m.content for m in sent_messages]
    assert roles[0] == "system"
    assert "first turn" in contents
    assert "hello" in contents
    assert "second turn" in contents


@pytest.mark.asyncio
async def test_tool_error_is_recoverable(tmp_path: Path):
    """A failing tool returns an error string the model can read; the loop
    must keep going so the model can correct itself."""
    reg = ToolRegistry()
    reg.register(Tool("boom", "boom", {"type": "object"},
                      lambda a: (_ for _ in ()).throw(ToolError("bad input"))))
    bad = ToolCall(id="c1", name="boom", arguments="{}")
    client = _StubClient([
        AssistantReply(content=None, tool_calls=(bad,)),
        AssistantReply(content="ok I gave up on that tool", tool_calls=()),
    ])
    agent = ChatAgent(client=client, registry=reg, settings=AISettings(),
                      log=ChatLog(tmp_path))
    out = await agent.send("try it")
    assert out == "ok I gave up on that tool"
    second_msgs = client.received[1]
    tool_msg = next(m for m in second_msgs if m.role == "tool")
    assert json.loads(tool_msg.content) == {"error": "bad input"}


@pytest.mark.asyncio
async def test_unexpected_tool_exception_still_yields_tool_result(tmp_path: Path):
    """A tool raising a *non*-ToolError (e.g. bad model args -> ValueError, or a
    DB error) must still produce a tool result so the assistant tool_calls turn
    stays valid. Otherwise the turn aborts mid-tool, leaving a dangling
    tool_call in memory and chat.log that 400s the next request with "an
    assistant message with tool calls must be followed by tool message"."""
    reg = ToolRegistry()
    reg.register(Tool(
        "kaboom", "kaboom", {"type": "object"},
        lambda a: (_ for _ in ()).throw(ValueError("invalid literal for int()")),
    ))
    bad = ToolCall(id="c1", name="kaboom", arguments="{}")
    client = _StubClient([
        AssistantReply(content=None, tool_calls=(bad,)),
        AssistantReply(content="recovered", tool_calls=()),
    ])
    log = ChatLog(tmp_path)
    agent = ChatAgent(client=client, registry=reg, settings=AISettings(), log=log)
    out = await agent.send("try it")
    assert out == "recovered"
    # The second LLM call must include a tool result for c1.
    second_msgs = client.received[1]
    tool_msg = next(m for m in second_msgs if m.role == "tool")
    assert tool_msg.tool_call_id == "c1"
    assert "error" in json.loads(tool_msg.content)
    # And it must be persisted so a reload stays API-valid.
    kinds = [e["kind"] for e in log.read_all()]
    assert kinds == ["user", "assistant", "tool_call", "tool_result", "assistant"]

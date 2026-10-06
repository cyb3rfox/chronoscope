from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string as emitted by the model


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    tool_call_id: str | None = None  # role=="tool"
    name: str | None = None          # role=="tool"

    def to_openai(self) -> dict:
        msg: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        return msg


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One thing the model emitted during a streaming chat call.

    "text"       — content token; aggregate text equals the assistant's reply.
    "tool_call"  — a fully reassembled tool call (we buffer partial deltas).
    "done"       — end of the stream; finish_reason mirrors OpenAI's.
    """
    kind: str
    text: str = ""
    tool_call: ToolCall | None = None
    finish_reason: str = ""


@dataclass(frozen=True, slots=True)
class AssistantReply:
    """Non-streaming projection used by tests and the legacy code path."""
    content: str | None
    tool_calls: tuple[ToolCall, ...]


class LLMClient(Protocol):
    """Streaming chat surface. Swap implementations to retarget the same agent
    at any OpenAI-compatible endpoint, or at a non-OpenAI provider by
    implementing this Protocol."""

    def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict],
        *,
        model: str,
    ) -> AsyncIterator[StreamEvent]: ...


class OpenAICompatibleClient:
    """Targets any OpenAI Chat Completions-compatible endpoint (DeepSeek,
    OpenAI, OpenRouter, vLLM, etc.). The `openai` package is imported lazily
    so the rest of the app keeps working when the dependency is absent."""

    def __init__(self, *, base_url: str, api_key: str) -> None:
        try:
            from openai import AsyncOpenAI  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - dep optional at install
            raise RuntimeError(
                "openai package not installed; pip install openai"
            ) from e
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: list[dict],
        *,
        model: str,
    ) -> AsyncIterator[StreamEvent]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [m.to_openai() for m in messages],
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        stream = await self._client.chat.completions.create(**kwargs)

        # OpenAI delivers tool calls in deltas indexed by position; buffer
        # until the stream finishes so callers see a fully-assembled ToolCall.
        buffers: dict[int, dict[str, str]] = {}
        finish_reason: str = ""
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta and getattr(delta, "content", None):
                yield StreamEvent(kind="text", text=delta.content)
            for tc_delta in (getattr(delta, "tool_calls", None) or []):
                idx = getattr(tc_delta, "index", 0) or 0
                buf = buffers.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if getattr(tc_delta, "id", None):
                    buf["id"] = tc_delta.id
                fn = getattr(tc_delta, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        buf["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        buf["arguments"] += fn.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        for buf in buffers.values():
            yield StreamEvent(
                kind="tool_call",
                tool_call=ToolCall(
                    id=buf["id"], name=buf["name"], arguments=buf["arguments"],
                ),
            )
        yield StreamEvent(kind="done", finish_reason=finish_reason or "stop")

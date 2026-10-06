from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..core.metadata import CaseMetadata, format_briefing
from .client import ChatMessage, LLMClient, ToolCall
from .history import ChatLog
from .settings import AISettings
from .tools import ToolRegistry

DEFAULT_SYSTEM_PROMPT = (
    "You are a forensic timeline analyst embedded in Chronoscope. The user is "
    "investigating a Plaso super-timeline that has been ingested into a case. "
    "Use the provided tools to look up real data — never invent events. "
    "Prefer narrow filters over loading large pages, and cite specific events "
    "by id when you make a claim. When you find something noteworthy, point "
    "out the timeline_id, timestamp, and why it matters. Be concise.\n\n"
    "You can also read and update the case metadata (company, incident "
    "summary, known compromised accounts/machines, IOCs). When you confirm "
    "a new lead with the user, persist it via the metadata write tools so "
    "future sessions inherit the context."
)


def build_system_prompt(meta: CaseMetadata | None) -> str:
    """The agent's initial system message. Includes a markdown briefing of
    the current case metadata so the model starts every conversation with
    investigator context. The briefing is a snapshot at construction; the
    read_case_metadata tool refreshes it if it changes mid-session."""
    if meta is None or meta.is_empty():
        return DEFAULT_SYSTEM_PROMPT
    briefing = format_briefing(meta)
    return f"{DEFAULT_SYSTEM_PROMPT}\n\n# Case context\n\n{briefing}"


@dataclass
class AgentEvent:
    """One observable thing the agent did, surfaced to the UI for live status.

    Event kinds:
        user                — the user's prompt was accepted
        thinking            — about to call the LLM (UI: show spinner)
        text_delta          — partial assistant content (stream as it arrives)
        tool_call           — a tool is about to run (text holds args JSON)
        tool_result         — a tool returned (text holds result JSON)
        assistant_complete  — final assistant text for this turn (text == full)
        stop                — turn ended cleanly
        error               — non-recoverable failure; text holds the message
    """
    kind: str
    text: str = ""
    name: str = ""
    tool_call_id: str = ""


class ChatAgent:
    """Owns one chat session: the running message list, the tool registry,
    the LLM client, and the audit log. The UI calls send(prompt, on_event)
    and observes events as the loop progresses."""

    def __init__(
        self,
        *,
        client: LLMClient,
        registry: ToolRegistry,
        settings: AISettings,
        log: ChatLog,
        system_prompt: str | None = None,
        metadata: CaseMetadata | None = None,
        history: list[ChatMessage] | None = None,
    ) -> None:
        self._client = client
        self._registry = registry
        self._settings = settings
        self._log = log
        prompt = system_prompt if system_prompt is not None else build_system_prompt(metadata)
        # System prompt is rebuilt fresh every session so updated case
        # metadata is reflected; conversation history is loaded from disk.
        self._messages: list[ChatMessage] = [ChatMessage(role="system", content=prompt)]
        if history:
            self._messages.extend(history)

    @property
    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    async def send(
        self,
        prompt: str,
        on_event: Callable[[AgentEvent], Awaitable[None] | None] | None = None,
    ) -> str:
        """Submit a user prompt, drive the tool loop, return the final
        assistant text. on_event is fired for every loop step so a UI can
        stream partial progress."""
        await _emit(on_event, AgentEvent(kind="user", text=prompt))
        self._log.append("user", text=prompt)
        self._messages.append(ChatMessage(role="user", content=prompt))

        tools_schema = self._registry.openai_schema()
        max_iters = max(1, int(self._settings.max_tool_iterations))

        for _ in range(max_iters):
            await _emit(on_event, AgentEvent(kind="thinking"))
            text_buffer = ""
            tool_calls: list[ToolCall] = []
            try:
                async for sev in self._client.chat_stream(
                    self._messages, tools_schema, model=self._settings.model
                ):
                    if sev.kind == "text":
                        text_buffer += sev.text
                        await _emit(
                            on_event, AgentEvent(kind="text_delta", text=sev.text)
                        )
                    elif sev.kind == "tool_call" and sev.tool_call is not None:
                        tool_calls.append(sev.tool_call)
                    elif sev.kind == "done":
                        break
            except Exception as e:
                err = f"LLM error: {e}"
                self._log.append("error", text=err)
                await _emit(on_event, AgentEvent(kind="error", text=err))
                return err

            self._messages.append(
                ChatMessage(
                    role="assistant",
                    content=text_buffer or None,
                    tool_calls=tuple(tool_calls),
                )
            )

            # Persist every assistant turn with its tool_calls so the next
            # session can reconstruct the OpenAI message sequence verbatim
            # (assistant → tool → assistant → …).
            self._log.append(
                "assistant",
                text=text_buffer,
                tool_calls=[
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in tool_calls
                ],
            )

            if not tool_calls:
                await _emit(
                    on_event,
                    AgentEvent(kind="assistant_complete", text=text_buffer),
                )
                await _emit(on_event, AgentEvent(kind="stop"))
                return text_buffer

            for call in tool_calls:
                await self._dispatch_tool(call, on_event)

        msg = (
            f"Tool-loop limit reached ({max_iters}). Stopping. Increase "
            "max_tool_iterations in AI settings if the agent legitimately "
            "needs more steps."
        )
        self._log.append("error", text=msg)
        await _emit(on_event, AgentEvent(kind="error", text=msg))
        return msg

    async def _dispatch_tool(
        self,
        call: ToolCall,
        on_event: Callable[[AgentEvent], Awaitable[None] | None] | None,
    ) -> None:
        self._log.append(
            "tool_call", name=call.name, arguments=call.arguments, id=call.id
        )
        await _emit(
            on_event,
            AgentEvent(kind="tool_call", name=call.name, text=call.arguments,
                       tool_call_id=call.id),
        )
        try:
            result = self._registry.call(call.name, call.arguments)
        except Exception as e:  # noqa: BLE001
            # A tool failing for any reason must still produce a result: the
            # assistant message that requested this call is already in the
            # message list and log, and the OpenAI API requires every such
            # tool_call to be answered by a tool message. Aborting here would
            # leave a dangling tool_call that 400s the next request. Surface
            # the error to the model so it can recover.
            result = json.dumps({"error": f"tool {call.name!r} failed: {e}"})
        self._log.append("tool_result", name=call.name, result=result, id=call.id)
        await _emit(
            on_event,
            AgentEvent(kind="tool_result", name=call.name, text=result,
                       tool_call_id=call.id),
        )
        self._messages.append(
            ChatMessage(
                role="tool",
                content=result,
                tool_call_id=call.id,
                name=call.name,
            )
        )


async def _emit(
    sink: Callable[[AgentEvent], Awaitable[None] | None] | None,
    event: AgentEvent,
) -> None:
    if sink is None:
        return
    res = sink(event)
    if hasattr(res, "__await__"):
        await res  # type: ignore[func-returns-value]

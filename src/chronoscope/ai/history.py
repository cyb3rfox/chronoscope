from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import ChatMessage, ToolCall

LOG_FILENAME = "chat.log"
DEFAULT_MAX_HISTORY_MESSAGES = 50


class ChatLog:
    """Append-only JSONL log of every chat exchange in a case directory.

    One line per event (user prompt, assistant reply, tool call, tool result,
    or error) so the entire forensic interaction is reconstructable from the
    case alone. Doubles as the persistent transcript: opening a case re-shows
    the latest session.
    """

    def __init__(self, case_dir: Path) -> None:
        self._path = Path(case_dir) / LOG_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def append(self, kind: str, **payload: Any) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            **payload,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str))
            f.write("\n")

    def read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        out: list[dict] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out


def load_session(
    log: ChatLog,
    *,
    max_messages: int = DEFAULT_MAX_HISTORY_MESSAGES,
) -> list[ChatMessage]:
    """Reconstruct the OpenAI-shaped message sequence from a chat.log so a
    new ChatAgent can resume the prior conversation.

    Reconstruction rules:
        user      → role=user
        assistant → role=assistant; tool_calls populated from the entry
        tool_result → role=tool with tool_call_id+name
        tool_call → skipped (its data lives inside the assistant entry)
        error     → skipped (not part of the conversation seen by the model)

    Truncation: if the rebuilt list is longer than max_messages, keep only
    the tail and align the start to the next "user" message so we never
    begin with a stray tool/assistant turn that has no matching parent.
    """
    msgs: list[ChatMessage] = []
    for entry in log.read_all():
        kind = entry.get("kind")
        if kind == "user":
            msgs.append(ChatMessage(role="user", content=str(entry.get("text") or "")))
        elif kind == "assistant":
            tool_calls = tuple(
                ToolCall(
                    id=str(tc.get("id", "")),
                    name=str(tc.get("name", "")),
                    arguments=str(tc.get("arguments", "")),
                )
                for tc in (entry.get("tool_calls") or [])
            )
            text = entry.get("text")
            msgs.append(ChatMessage(
                role="assistant",
                content=text if text else None,
                tool_calls=tool_calls,
            ))
        elif kind == "tool_result":
            msgs.append(ChatMessage(
                role="tool",
                content=str(entry.get("result") or ""),
                tool_call_id=str(entry.get("id") or ""),
                name=str(entry.get("name") or ""),
            ))
        # tool_call and error entries are intentionally skipped.

    if max_messages and len(msgs) > max_messages:
        msgs = msgs[-max_messages:]
        for i, m in enumerate(msgs):
            if m.role == "user":
                msgs = msgs[i:]
                break
        else:
            # No user boundary in the tail — drop everything to be safe.
            msgs = []
    return _strip_incomplete_tool_turns(msgs)


def _strip_incomplete_tool_turns(msgs: list[ChatMessage]) -> list[ChatMessage]:
    """Guarantee the OpenAI invariant: every assistant message carrying
    ``tool_calls`` is immediately followed by a ``tool`` message for *each*
    call id. A prior session interrupted mid-tool (crash, app close, or an
    unexpected tool error) leaves a dangling assistant tool-call turn in the
    log; replaying it verbatim makes the next request 400 with "an assistant
    message with tool calls must be followed by tool message".

    We repair by dropping any assistant tool-call turn whose results are
    incomplete (all-or-nothing) and any orphan ``tool`` message with no owning
    turn. We never fabricate tool output.
    """
    out: list[ChatMessage] = []
    i = 0
    n = len(msgs)
    while i < n:
        m = msgs[i]
        if m.role == "assistant" and m.tool_calls:
            # Collect the contiguous run of tool results that follow this turn.
            j = i + 1
            results: dict[str, ChatMessage] = {}
            while j < n and msgs[j].role == "tool":
                results[str(msgs[j].tool_call_id)] = msgs[j]
                j += 1
            need = [tc.id for tc in m.tool_calls]
            if all(tid in results for tid in need):
                out.append(m)
                out.extend(results[tid] for tid in need)
            # else: incomplete turn — drop the assistant message and its
            # partial results entirely.
            i = j
        elif m.role == "tool":
            # Orphan tool result (no preceding assistant tool-call) — drop.
            i += 1
        else:
            out.append(m)
            i += 1
    return out

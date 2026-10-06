from __future__ import annotations

from pathlib import Path

from chronoscope.ai.history import ChatLog, load_session


def test_append_and_read_roundtrip(tmp_path: Path):
    log = ChatLog(tmp_path)
    log.append("user", text="hello")
    log.append("assistant", text="hi there")
    log.append("tool_call", name="search_events", arguments='{"a":1}')
    entries = log.read_all()
    assert len(entries) == 3
    assert entries[0]["kind"] == "user"
    assert entries[0]["text"] == "hello"
    assert entries[2]["name"] == "search_events"
    # Every entry has a timestamp the audit log relies on.
    assert all("ts" in e for e in entries)


def test_read_empty_when_no_log(tmp_path: Path):
    log = ChatLog(tmp_path)
    assert log.read_all() == []


def test_read_skips_corrupted_lines(tmp_path: Path):
    log = ChatLog(tmp_path)
    log.append("user", text="ok")
    # Simulate partial write: append a malformed line.
    with log.path.open("a") as f:
        f.write("not-json\n")
    log.append("assistant", text="recovered")
    kinds = [e["kind"] for e in log.read_all()]
    assert kinds == ["user", "assistant"]


def test_load_session_empty_log(tmp_path: Path):
    assert load_session(ChatLog(tmp_path)) == []


def test_load_session_text_only_round_trip(tmp_path: Path):
    log = ChatLog(tmp_path)
    log.append("user", text="hi")
    log.append("assistant", text="hello", tool_calls=[])
    log.append("user", text="more")
    log.append("assistant", text="ok", tool_calls=[])
    msgs = load_session(log)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "hi"),
        ("assistant", "hello"),
        ("user", "more"),
        ("assistant", "ok"),
    ]


def test_load_session_reconstructs_tool_calls(tmp_path: Path):
    log = ChatLog(tmp_path)
    log.append("user", text="search")
    log.append(
        "assistant",
        text="",
        tool_calls=[{"id": "c1", "name": "search_events", "arguments": "{}"}],
    )
    log.append("tool_call", name="search_events", arguments="{}", id="c1")
    log.append("tool_result", name="search_events", result='{"x":1}', id="c1")
    log.append("assistant", text="here you go", tool_calls=[])
    msgs = load_session(log)
    # tool_call entries are absorbed into the assistant entry, so the rebuilt
    # sequence is user → assistant(tool_calls) → tool → assistant(text).
    assert [(m.role, m.tool_call_id, m.name) for m in msgs] == [
        ("user", None, None),
        ("assistant", None, None),
        ("tool", "c1", "search_events"),
        ("assistant", None, None),
    ]
    assert msgs[1].tool_calls[0].name == "search_events"
    assert msgs[2].content == '{"x":1}'


def test_load_session_skips_error_entries(tmp_path: Path):
    log = ChatLog(tmp_path)
    log.append("user", text="hi")
    log.append("error", text="LLM 503")
    log.append("user", text="retry")
    log.append("assistant", text="ok", tool_calls=[])
    msgs = load_session(log)
    assert [m.role for m in msgs] == ["user", "user", "assistant"]


def test_load_session_drops_interrupted_tool_turn(tmp_path: Path):
    # Prior session was interrupted after the model requested a tool but
    # before the result was persisted (crash / app close / unexpected error).
    log = ChatLog(tmp_path)
    log.append("user", text="search")
    log.append(
        "assistant",
        text="",
        tool_calls=[{"id": "c1", "name": "search_events", "arguments": "{}"}],
    )
    msgs = load_session(log)
    # The dangling assistant(tool_calls) must be dropped so the next prompt
    # doesn't send an assistant tool_calls turn with no matching tool result.
    assert [m.role for m in msgs] == ["user"]


def test_load_session_drops_partial_multi_tool_turn(tmp_path: Path):
    # Model requested two tools; only one result was persisted.
    log = ChatLog(tmp_path)
    log.append("user", text="two things")
    log.append(
        "assistant",
        text="",
        tool_calls=[
            {"id": "c1", "name": "search_events", "arguments": "{}"},
            {"id": "c2", "name": "get_event", "arguments": "{}"},
        ],
    )
    log.append("tool_result", name="search_events", result="{}", id="c1")
    msgs = load_session(log)
    # All-or-nothing: an assistant turn keeps its tool results only if every
    # tool_call id is satisfied, otherwise the whole turn is dropped.
    assert [m.role for m in msgs] == ["user"]


def test_load_session_drops_dangling_turn_but_keeps_later_turn(tmp_path: Path):
    log = ChatLog(tmp_path)
    log.append("user", text="q1")
    log.append(
        "assistant",
        text="",
        tool_calls=[{"id": "c1", "name": "search_events", "arguments": "{}"}],
    )  # interrupted, no result
    log.append("user", text="q2")
    log.append("assistant", text="answer", tool_calls=[])
    msgs = load_session(log)
    assert [(m.role, m.content) for m in msgs] == [
        ("user", "q1"),
        ("user", "q2"),
        ("assistant", "answer"),
    ]


def test_load_session_drops_orphan_tool_result(tmp_path: Path):
    # A tool result with no owning assistant tool_call (e.g. log head was lost).
    log = ChatLog(tmp_path)
    log.append("tool_result", name="search_events", result="{}", id="c1")
    log.append("user", text="hi")
    msgs = load_session(log)
    assert [m.role for m in msgs] == ["user"]


def test_load_session_truncates_to_user_boundary(tmp_path: Path):
    log = ChatLog(tmp_path)
    # Many turns; only the tail should survive truncation.
    for i in range(20):
        log.append("user", text=f"q{i}")
        log.append("assistant", text=f"a{i}", tool_calls=[])
    msgs = load_session(log, max_messages=5)
    # max_messages=5 keeps the last 5; truncation realigns to a "user" so we
    # don't begin with an orphan assistant.
    assert msgs[0].role == "user"
    assert len(msgs) <= 5
    # Tail content reflects the most recent turns.
    assert msgs[-1].content.startswith("a")

from __future__ import annotations

import json

import pytest

from chronoscope.ai.tools import Tool, ToolError, ToolRegistry


def test_tool_to_openai_shape():
    t = Tool(
        name="echo",
        description="echo back",
        parameters_schema={"type": "object"},
        fn=lambda args: args,
    )
    out = t.to_openai()
    assert out["type"] == "function"
    assert out["function"]["name"] == "echo"
    assert out["function"]["parameters"] == {"type": "object"}


def test_registry_register_and_schema_export():
    reg = ToolRegistry()
    reg.register(Tool("a", "a", {"type": "object"}, lambda a: a))
    reg.register(Tool("b", "b", {"type": "object"}, lambda a: a))
    schema = reg.openai_schema()
    assert {s["function"]["name"] for s in schema} == {"a", "b"}


def test_registry_rejects_duplicate_names():
    reg = ToolRegistry()
    reg.register(Tool("a", "a", {"type": "object"}, lambda a: a))
    with pytest.raises(ValueError):
        reg.register(Tool("a", "a", {"type": "object"}, lambda a: a))


def test_registry_call_returns_jsonable_string():
    reg = ToolRegistry()
    reg.register(Tool("identity", "id", {"type": "object"},
                      lambda a: {"got": a, "n": 3}))
    out = reg.call("identity", json.dumps({"x": 1}))
    decoded = json.loads(out)
    assert decoded == {"got": {"x": 1}, "n": 3}


def test_registry_call_unknown_tool_returns_error():
    reg = ToolRegistry()
    out = json.loads(reg.call("missing", "{}"))
    assert "unknown tool" in out["error"]


def test_registry_call_invalid_json_returns_error():
    reg = ToolRegistry()
    reg.register(Tool("a", "a", {"type": "object"}, lambda a: a))
    out = json.loads(reg.call("a", "{not json"))
    assert "invalid arguments JSON" in out["error"]


def test_registry_call_non_object_arguments_returns_error():
    reg = ToolRegistry()
    reg.register(Tool("a", "a", {"type": "object"}, lambda a: a))
    out = json.loads(reg.call("a", "[1, 2]"))
    assert "must be an object" in out["error"]


def test_tool_error_is_serialized_for_model():
    reg = ToolRegistry()
    def boom(_args):
        raise ToolError("nope")
    reg.register(Tool("a", "a", {"type": "object"}, boom))
    out = json.loads(reg.call("a", "{}"))
    assert out == {"error": "nope"}


def test_registry_handles_bytes_in_results():
    reg = ToolRegistry()
    reg.register(Tool("hex", "hex", {"type": "object"},
                      lambda a: {"blob": b"\xde\xad"}))
    out = json.loads(reg.call("hex", "{}"))
    assert out == {"blob": "dead"}

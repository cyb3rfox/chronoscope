from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class ToolError(Exception):
    """Raised by a tool implementation to surface a deterministic error to the
    model. The string becomes the tool result so the model can recover."""


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters_schema: dict
    fn: Callable[[dict], Any]

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


@dataclass(slots=True)
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def openai_schema(self) -> list[dict]:
        return [t.to_openai() for t in self._tools.values()]

    def call(self, name: str, arguments_json: str) -> str:
        """Dispatch a tool call. Returns a JSON string the model will read.

        Tool errors are stringified rather than raised so the model can react
        to them inside the tool loop. Truly programmer-level bugs (KeyError on
        a missing tool name) still raise.
        """
        if name not in self._tools:
            return json.dumps({"error": f"unknown tool: {name}"})
        try:
            args = json.loads(arguments_json) if arguments_json else {}
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"invalid arguments JSON: {e}"})
        if not isinstance(args, dict):
            return json.dumps({"error": "arguments must be an object"})
        try:
            result = self._tools[name].fn(args)
        except ToolError as e:
            return json.dumps({"error": str(e)})
        return json.dumps(_jsonable(result), default=str)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return str(value)

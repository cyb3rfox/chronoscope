from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import BinaryIO

import orjson

from ..core.event import Event

ErrorHandler = Callable[[int, str], None]


def iter_events(stream: BinaryIO, *, on_error: ErrorHandler | None = None) -> Iterator[Event]:
    """Yield Event objects from a JSONL byte stream; skip malformed lines."""
    for lineno, raw in enumerate(stream, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = orjson.loads(line)
        except orjson.JSONDecodeError as e:
            if on_error is not None:
                on_error(lineno, str(e))
            continue
        if not isinstance(obj, dict):
            if on_error is not None:
                on_error(lineno, "not a JSON object")
            continue
        yield Event.from_dict(obj)

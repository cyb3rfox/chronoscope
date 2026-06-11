from __future__ import annotations

from typing import Any

import cbor2


def dump_extra(d: dict[str, Any]) -> bytes:
    return cbor2.dumps(d)


def load_extra(blob: bytes) -> dict[str, Any]:
    value = cbor2.loads(blob)
    if not isinstance(value, dict):
        raise ValueError(f"expected dict, got {type(value).__name__}")
    return value


_FLATTEN_SEP = " \x1f "


def flatten_extra(d: dict[str, Any]) -> str:
    """Flatten an extra-fields dict into a single searchable string.

    Includes both keys and stringified leaf values so a substring filter can
    match either. Nested dicts and lists are walked recursively. None is
    rendered as the empty string. The output is intended for case-insensitive
    LIKE matching, not for display.
    """
    parts: list[str] = []
    _walk(d, parts)
    return _FLATTEN_SEP.join(parts)


def _walk(value: Any, out: list[str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            out.append(str(k))
            _walk(v, out)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _walk(item, out)
    elif isinstance(value, bytes):
        out.append(value.hex())
    elif value is None:
        out.append("")
    else:
        out.append(str(value))

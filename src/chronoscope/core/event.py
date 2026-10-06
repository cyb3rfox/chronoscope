from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import blake3
import orjson

CORE_KEYS = frozenset({
    "datetime", "timestamp", "timestamp_desc",
    "data_type", "parser",
    "source_short", "source_long",
    "display_name", "message",
})


def canonical_json(obj: Any) -> bytes:
    """Deterministic JSON bytes for hashing: sorted keys, normalized floats."""
    return orjson.dumps(_normalize(obj), option=orjson.OPT_SORT_KEYS)


def _normalize(obj: Any) -> Any:
    if isinstance(obj, float):
        return float(f"{obj:.6g}")
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    return obj


def event_hash(raw: dict[str, Any]) -> bytes:
    """32-byte blake3 digest of canonical JSON."""
    return blake3.blake3(canonical_json(raw)).digest()


@dataclass(slots=True)
class Event:
    ts_usec: int
    ts_desc: str
    data_type: str
    parser: str | None
    source_short: str | None
    source_long: str | None
    display_name: str | None
    message: str
    extra: dict[str, Any] = field(default_factory=dict)
    event_hash: bytes = b""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Event":
        extra = {k: v for k, v in raw.items() if k not in CORE_KEYS}
        ev = cls(
            ts_usec=int(raw.get("timestamp") or 0),
            ts_desc=str(raw.get("timestamp_desc") or ""),
            data_type=str(raw.get("data_type") or ""),
            parser=raw.get("parser"),
            source_short=raw.get("source_short"),
            source_long=raw.get("source_long"),
            display_name=raw.get("display_name"),
            message=str(raw.get("message") or ""),
            extra=extra,
        )
        ev.event_hash = event_hash(raw)
        return ev

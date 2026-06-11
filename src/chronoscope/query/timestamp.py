from __future__ import annotations

import re
from datetime import datetime, timezone

_RELATIVE_RE = re.compile(r"^([+-])(\d+)([smhdw])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 86400 * 7}


def parse_jump_target(text: str, anchor_usec: int) -> int:
    """Parse an ISO absolute or signed-relative timestamp into microseconds UTC.

    ISO forms: "YYYY-MM-DDTHH:MM:SSZ", "YYYY-MM-DD HH:MM:SS",
               "YYYY-MM-DD HH:MM", "YYYY-MM-DD".
    Relative forms (sign required): "-5m", "+2h", "-7d", "-30s", "+1w".
    Relative values are resolved against anchor_usec.
    """
    text = text.strip()
    if not text:
        raise ValueError("empty timestamp")

    m = _RELATIVE_RE.match(text)
    if m is not None:
        sign, num, unit = m.groups()
        delta_usec = int(num) * _UNIT_SECONDS[unit] * 1_000_000
        return anchor_usec + delta_usec if sign == "+" else anchor_usec - delta_usec

    normalized = text.replace(" ", "T")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000)
    raise ValueError(f"unparseable timestamp: {text!r}")

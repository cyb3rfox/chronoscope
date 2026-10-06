from __future__ import annotations

from pathlib import Path
from typing import Literal

Format = Literal["jsonl", "plaso", "unsupported"]

_SQLITE_MAGIC = b"SQLite format 3\x00"


def detect_format(path: Path) -> Format:
    """Classify ``path`` as ``"jsonl"`` / ``"plaso"`` / ``"unsupported"``.

    Reads only the first 16 bytes of the file.
    """
    try:
        with Path(path).open("rb") as f:
            head = f.read(16)
    except OSError:
        return "unsupported"
    if head.startswith(_SQLITE_MAGIC):
        return "plaso"
    if head.lstrip()[:1] == b"{":
        return "jsonl"
    return "unsupported"

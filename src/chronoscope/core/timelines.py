from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .case import open_case

#: Number of event rows deleted per batch, so progress can be reported and the
#: UI stays responsive while a large timeline is removed.
BATCH = 10_000

ProgressCallback = Callable[[int, "int | None"], None]


class TimelineNotFoundError(Exception):
    pass


def remove_timeline(
    case_path: Path,
    name: str,
    *,
    progress: ProgressCallback | None = None,
) -> None:
    """Delete a timeline and all its events.

    Events are removed in batches of :data:`BATCH`. When ``progress`` is given
    it is called with ``(deleted_so_far, total)`` once before any deletion and
    again after each batch, where ``total`` is the timeline's stored
    ``event_count``. The whole removal is one transaction: it commits only
    after the last batch, so an interrupted delete leaves the timeline intact.
    """
    with open_case(case_path) as c:
        row = c.con.execute(
            "SELECT id, event_count FROM timeline WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            raise TimelineNotFoundError(name)
        timeline_id, total = row[0], int(row[1])
        if progress is not None:
            progress(0, total)
        deleted = 0
        while True:
            cur = c.con.execute(
                "DELETE FROM event WHERE id IN ("
                "  SELECT id FROM event WHERE timeline_id=? LIMIT ?"
                ")",
                (timeline_id, BATCH),
            )
            if cur.rowcount <= 0:
                break
            deleted += cur.rowcount
            if progress is not None:
                progress(deleted, total)
        c.con.execute("DELETE FROM timeline WHERE id=?", (timeline_id,))
        c.con.commit()

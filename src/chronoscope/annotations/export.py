from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..core.case import open_case
from . import store


def export_annotations(case_path: Path, out_path: Path) -> int:
    """Write annotated events + their annotations to ``out_path``.

    Returns the number of events written.
    """
    with open_case(case_path) as c:
        rows = c.con.execute("""
            SELECT e.event_hash, e.ts_usec, e.data_type, e.display_name
            FROM event e
            WHERE e.event_hash IN (
              SELECT event_hash FROM annotation_star
              UNION
              SELECT event_hash FROM annotation_tag
              UNION
              SELECT event_hash FROM annotation_comment
            )
            ORDER BY e.ts_usec ASC, e.id ASC
        """).fetchall()
        events: list[dict] = []
        seen: set[bytes] = set()
        for event_hash, ts_usec, data_type, display_name in rows:
            h = bytes(event_hash)
            if h in seen:
                continue
            seen.add(h)
            events.append({
                "event_hash": h.hex(),
                "ts_usec": int(ts_usec),
                "data_type": data_type,
                "display_name": display_name,
                "star": store.get_star(c.con, h),
                "tags": store.tags_for(c.con, h),
                "comments": [
                    {
                        "body": cm["body"],
                        "created_at": cm["created_at"],
                        "updated_at": cm["updated_at"],
                    }
                    for cm in store.comments_for(c.con, h)
                ],
            })
        doc = {
            "schema_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "events": events,
        }
    Path(out_path).write_text(json.dumps(doc, indent=2, sort_keys=True))
    return len(events)

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from ..annotations import store
from ..core.case import Case, list_timelines
from ..core.exhibits import get_exhibit, list_exhibits
from ..core.extra import load_extra
from ..core.metadata import (
    LIST_FIELDS,
    SCALAR_FIELDS,
    CaseMetadata,
    load_metadata,
    save_metadata,
)
from ..query.builder import build_sql
from ..query.state import FILTERABLE_COLUMNS, FilterKind, QueryState
from ..query.timestamp import parse_jump_target
from .settings import AISettings
from .tools import Tool, ToolError, ToolRegistry

DEFAULT_LIMIT = 50

_CATEGORICAL = {c[0] for c in FILTERABLE_COLUMNS if c[2] == FilterKind.CATEGORICAL}
_SUBSTRING = {c[0] for c in FILTERABLE_COLUMNS if c[2] == FilterKind.SUBSTRING}

_FILTERS_SCHEMA = {
    "type": "object",
    "description": "Filter the timeline. Every field is optional; combine freely.",
    "properties": {
        "data_type_in": {"type": "array", "items": {"type": "string"}},
        "parser_in": {"type": "array", "items": {"type": "string"}},
        "source_short_in": {"type": "array", "items": {"type": "string"}},
        "source_long_in": {"type": "array", "items": {"type": "string"}},
        "ts_desc_in": {"type": "array", "items": {"type": "string"}},
        "message_contains": {"type": "string"},
        "display_name_contains": {"type": "string"},
        "extra_text_contains": {
            "type": "string",
            "description": (
                "Substring search across every event's extra fields. Use this to "
                "find values that aren't in any core column (URLs, usernames, "
                "process names, etc.)."
            ),
        },
        "ts_after": {
            "type": "string",
            "description": "Inclusive lower bound; ISO-8601 UTC, e.g. 2024-01-01T00:00:00Z",
        },
        "ts_before": {
            "type": "string",
            "description": "Inclusive upper bound; ISO-8601 UTC, e.g. 2024-01-01T00:00:00Z",
        },
        "tags_in":     {"type": "array", "items": {"type": "string"}},
        "tags_not_in": {"type": "array", "items": {"type": "string"}},
        "starred":     {"type": "boolean"},
        "timeline_ids":{"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": False,
}


FilterApplier = "Callable[[QueryState], None]"


def build_toolset(
    case: Case,
    settings: AISettings,
    *,
    apply_filters_cb=None,
) -> ToolRegistry:
    """Tool registry the agent uses to interrogate, annotate, and steer the
    case. Read tools respect ``settings.max_results_per_call`` so the model
    can never page the whole DB into context.

    ``apply_filters_cb`` is a sync callable invoked by the apply_filters
    tool to push a new QueryState into the active UI. It is None when no UI
    is attached (e.g. from a CLI or test agent run); the apply_filters and
    clear_filters tools then return an explanatory error string."""
    reg = ToolRegistry()
    cap = max(1, int(settings.max_results_per_call))
    con = case.con
    case_path = case.path

    reg.register(Tool(
        name="search_events",
        description=(
            "Return a page of events matching the given filters, ordered by "
            "timestamp. Result is capped to max_results_per_call from settings."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "filters": _FILTERS_SCHEMA,
                "sort": {
                    "type": "string",
                    "enum": ["ts_asc", "ts_desc"],
                    "default": "ts_asc",
                },
                "limit": {"type": "integer", "minimum": 1},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "additionalProperties": False,
        },
        fn=lambda args: _search_events(con, args, cap),
    ))

    reg.register(Tool(
        name="get_event",
        description="Return one event by id with all extra fields.",
        parameters_schema={
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        fn=lambda args: _get_event(con, args),
    ))

    reg.register(Tool(
        name="count_events",
        description="Count events matching filters.",
        parameters_schema={
            "type": "object",
            "properties": {"filters": _FILTERS_SCHEMA},
            "additionalProperties": False,
        },
        fn=lambda args: _count_events(con, args),
    ))

    reg.register(Tool(
        name="histogram",
        description=(
            "Return value-frequency pairs for one categorical column under "
            "the given filters, sorted by count descending."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": sorted(_CATEGORICAL)},
                "filters": _FILTERS_SCHEMA,
                "limit": {"type": "integer", "minimum": 1, "default": 50},
            },
            "required": ["field"],
            "additionalProperties": False,
        },
        fn=lambda args: _histogram(con, args, cap),
    ))

    reg.register(Tool(
        name="list_timelines",
        description="List ingested timelines (id, name, source path, event count).",
        parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        fn=lambda args: _list_timelines(con),
    ))

    reg.register(Tool(
        name="list_tags",
        description="List all tags currently used in the case with usage counts.",
        parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        fn=lambda args: _list_tags(con),
    ))

    reg.register(Tool(
        name="case_overview",
        description=(
            "High-level summary of the case: total events, time range, top "
            "data types and parsers."
        ),
        parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        fn=lambda args: _case_overview(con),
    ))

    reg.register(Tool(
        name="read_case_metadata",
        description=(
            "Return the investigator-curated metadata for this case "
            "(company, incident summary, known compromised accounts and "
            "machines, IOCs, free-form notes). Use this if the user mentions "
            "context the system prompt didn't include or to refresh after an "
            "update."
        ),
        parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        fn=lambda args: _read_metadata(case_path),
    ))

    reg.register(Tool(
        name="set_case_metadata_field",
        description=(
            "Overwrite a scalar metadata field. Confirm with the user before "
            "replacing existing content."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": list(SCALAR_FIELDS)},
                "value": {"type": "string"},
            },
            "required": ["field", "value"],
            "additionalProperties": False,
        },
        fn=lambda args: _set_metadata_field(case_path, args),
    ))

    reg.register(Tool(
        name="add_metadata_entry",
        description=(
            "Append an entry to one of the metadata lists (compromised "
            "accounts, compromised machines, known IOCs). Idempotent."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(LIST_FIELDS)},
                "value": {"type": "string"},
            },
            "required": ["category", "value"],
            "additionalProperties": False,
        },
        fn=lambda args: _add_metadata_entry(case_path, args),
    ))

    reg.register(Tool(
        name="remove_metadata_entry",
        description="Remove an entry from one of the metadata lists.",
        parameters_schema={
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(LIST_FIELDS)},
                "value": {"type": "string"},
            },
            "required": ["category", "value"],
            "additionalProperties": False,
        },
        fn=lambda args: _remove_metadata_entry(case_path, args),
    ))

    reg.register(Tool(
        name="tag_event",
        description=(
            "Attach a tag to one event. Use to mark events of interest "
            "(e.g. 'persistence', 'lateral-movement', 'beacon')."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "tag": {"type": "string"},
            },
            "required": ["event_id", "tag"],
            "additionalProperties": False,
        },
        fn=lambda args: _tag_event(con, args),
    ))

    reg.register(Tool(
        name="untag_event",
        description="Remove a tag from one event.",
        parameters_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "tag": {"type": "string"},
            },
            "required": ["event_id", "tag"],
            "additionalProperties": False,
        },
        fn=lambda args: _untag_event(con, args),
    ))

    reg.register(Tool(
        name="add_event_comment",
        description=(
            "Attach a free-form comment to one event so the analyst sees "
            "your reasoning when they review the event later."
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "body": {"type": "string"},
            },
            "required": ["event_id", "body"],
            "additionalProperties": False,
        },
        fn=lambda args: _add_event_comment(con, args),
    ))

    reg.register(Tool(
        name="apply_filters",
        description=(
            "Replace the analyst's current event-table filters with the "
            "given filters so they immediately see the same slice you're "
            "looking at. Same filter shape as search_events. Pass an empty "
            "filters object to clear filters."
        ),
        parameters_schema={
            "type": "object",
            "properties": {"filters": _FILTERS_SCHEMA},
            "additionalProperties": False,
        },
        fn=lambda args: _apply_filters(args, apply_filters_cb),
    ))

    reg.register(Tool(
        name="clear_filters",
        description="Clear all active filters in the analyst's event table.",
        parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        fn=lambda args: _apply_filters({"filters": {}}, apply_filters_cb),
    ))

    reg.register(Tool(
        name="list_exhibits",
        description=(
            "List the text-evidence exhibits attached to the case (scripts, "
            "file contents, etc.): id, title, description, and body size. "
            "Bodies are omitted; call get_exhibit to read one in full."
        ),
        parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        fn=lambda args: _list_exhibits(con),
    ))

    reg.register(Tool(
        name="get_exhibit",
        description="Return one exhibit by id, including its full text body.",
        parameters_schema={
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
            "additionalProperties": False,
        },
        fn=lambda args: _get_exhibit(con, args),
    ))

    return reg


# --- helpers ----------------------------------------------------------------


def _state_from_filters(filters: dict | None) -> QueryState:
    """Translate the agent-facing filter dict into a QueryState.

    Unknown keys raise ToolError so the model gets a deterministic correction
    rather than silent drift."""
    s = QueryState()
    if not filters:
        return s
    if not isinstance(filters, dict):
        raise ToolError("filters must be an object")
    cat_keys = {
        "data_type_in":   "data_type",
        "parser_in":      "parser",
        "source_short_in":"source_short",
        "source_long_in": "source_long",
        "ts_desc_in":     "ts_desc",
    }
    sub_keys = {
        "message_contains":      "message",
        "display_name_contains": "display_name",
        "extra_text_contains":   "extra_text",
    }
    valid = (
        set(cat_keys) | set(sub_keys)
        | {"ts_after", "ts_before", "tags_in", "tags_not_in", "starred", "timeline_ids"}
    )
    unknown = set(filters) - valid
    if unknown:
        raise ToolError(f"unknown filter fields: {sorted(unknown)}")

    for key, col in cat_keys.items():
        if key in filters:
            vals = filters[key] or []
            if not isinstance(vals, list):
                raise ToolError(f"{key} must be a list")
            s = s.set_categorical(col, include=set(vals), exclude=set())
    for key, col in sub_keys.items():
        if key in filters and filters[key]:
            s = s.set_substring(col, str(filters[key]))
    if filters.get("ts_after"):
        s = s.set_bracket_start(_parse_ts_arg(filters["ts_after"]))
    if filters.get("ts_before"):
        s = s.set_bracket_end(_parse_ts_arg(filters["ts_before"]))
    if filters.get("tags_in") or filters.get("tags_not_in"):
        s = s.set_tag_filter(
            include=set(filters.get("tags_in") or []),
            exclude=set(filters.get("tags_not_in") or []),
        )
    if "starred" in filters:
        s = s.set_star_filter(
            "only_starred" if filters["starred"] else "only_unstarred"
        )
    if filters.get("timeline_ids"):
        s = s.set_timeline_filter(set(filters["timeline_ids"]))
    return s


def _parse_ts_arg(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        raise ToolError(f"timestamp must be a string or number, got {type(value).__name__}")
    try:
        return parse_jump_target(value, anchor_usec=0)
    except ValueError as e:
        raise ToolError(f"unparseable timestamp {value!r}: {e}")


def _format_ts(ts_usec: int) -> str:
    if ts_usec <= 0:
        return ""
    return datetime.fromtimestamp(ts_usec / 1_000_000, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _search_events(con: sqlite3.Connection, args: dict, cap: int) -> dict:
    state = _state_from_filters(args.get("filters"))
    sort = args.get("sort", "ts_asc")
    direction = "DESC" if sort == "ts_desc" else "ASC"
    state = state.set_sort("ts_usec", direction)
    requested = int(args.get("limit") or DEFAULT_LIMIT)
    limit = max(1, min(requested, cap))
    offset = max(0, int(args.get("offset") or 0))

    where, params, order_by = build_sql(state)
    base = "FROM event" + (f" WHERE {where}" if where else "")
    total = int(con.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0])
    rows = list(con.execute(
        f"SELECT id, ts_usec, ts_desc, data_type, parser, source_short, "
        f"display_name, message, timeline_id "
        f"{base} ORDER BY {order_by} LIMIT ? OFFSET ?",
        params + (limit, offset),
    ))
    out: list[dict] = []
    for r in rows:
        eid, ts, td, dt, parser, ss, dn, msg, tid = r
        out.append({
            "id": int(eid),
            "ts": _format_ts(int(ts)),
            "ts_desc": td or "",
            "data_type": dt or "",
            "parser": parser or "",
            "source_short": ss or "",
            "display_name": dn or "",
            "message": (msg or "")[:500],
            "timeline_id": tid,
        })
    return {
        "total_matching": total,
        "returned": len(out),
        "limit": limit,
        "offset": offset,
        "events": out,
    }


def _get_event(con: sqlite3.Connection, args: dict) -> dict:
    eid = int(args["id"])
    row = con.execute(
        "SELECT id, ts_usec, ts_desc, data_type, parser, source_short, "
        "source_long, display_name, message, extra, event_hash, timeline_id "
        "FROM event WHERE id = ?",
        (eid,),
    ).fetchone()
    if row is None:
        raise ToolError(f"no event with id {eid}")
    (id_, ts, td, dt, parser, ss, sl, dn, msg, extra_blob, ehash, tid) = row
    extra: dict = {}
    if extra_blob:
        try:
            extra = load_extra(bytes(extra_blob))
        except Exception:
            extra = {"_decode_error": True}
    tags = list(store.tags_for(con, bytes(ehash)))
    starred = store.get_star(con, bytes(ehash))
    comments = [c["body"] for c in store.comments_for(con, bytes(ehash))]
    return {
        "id": int(id_),
        "ts": _format_ts(int(ts)),
        "ts_desc": td or "",
        "data_type": dt or "",
        "parser": parser or "",
        "source_short": ss or "",
        "source_long": sl or "",
        "display_name": dn or "",
        "message": msg or "",
        "extra": extra,
        "tags": tags,
        "starred": bool(starred),
        "comments": comments,
        "timeline_id": tid,
    }


def _count_events(con: sqlite3.Connection, args: dict) -> dict:
    state = _state_from_filters(args.get("filters"))
    where, params, _ = build_sql(state)
    base = "FROM event" + (f" WHERE {where}" if where else "")
    n = int(con.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0])
    return {"count": n}


def _histogram(con: sqlite3.Connection, args: dict, cap: int) -> dict:
    field = str(args["field"])
    if field not in _CATEGORICAL:
        raise ToolError(f"field must be one of {sorted(_CATEGORICAL)}")
    state = _state_from_filters(args.get("filters"))
    requested = int(args.get("limit") or 50)
    limit = max(1, min(requested, cap))
    where, params, _ = build_sql(state)
    base = "FROM event" + (f" WHERE {where}" if where else "")
    rows = con.execute(
        f"SELECT {field}, COUNT(*) AS n {base} "
        f"GROUP BY {field} ORDER BY n DESC LIMIT ?",
        params + (limit,),
    ).fetchall()
    return {
        "field": field,
        "buckets": [{"value": v, "count": int(n)} for v, n in rows],
    }


def _list_timelines(con: sqlite3.Connection) -> dict:
    return {
        "timelines": [
            {
                "id": t.id,
                "name": t.name,
                "source_path": t.source_path,
                "event_count": t.event_count,
            }
            for t in list_timelines(con)
        ]
    }


def _list_exhibits(con: sqlite3.Connection) -> dict:
    return {
        "exhibits": [
            {
                "id": e.id,
                "title": e.title,
                "description": e.description,
                "body_chars": len(e.body),
            }
            for e in list_exhibits(con)
        ]
    }


def _get_exhibit(con: sqlite3.Connection, args: dict) -> dict:
    eid = int(args["id"])
    e = get_exhibit(con, eid)
    if e is None:
        raise ToolError(f"no exhibit with id {eid}")
    return {
        "id": e.id,
        "title": e.title,
        "description": e.description,
        "body": e.body,
    }


def _list_tags(con: sqlite3.Connection) -> dict:
    return {
        "tags": [
            {"tag": t, "count": int(n)}
            for t, n in store.all_tags_with_counts(con)
        ]
    }


def _hash_for_event_id(con: sqlite3.Connection, event_id: int) -> bytes:
    row = con.execute(
        "SELECT event_hash FROM event WHERE id = ?", (event_id,)
    ).fetchone()
    if row is None:
        raise ToolError(f"no event with id {event_id}")
    return bytes(row[0])


def _tag_event(con: sqlite3.Connection, args: dict) -> dict:
    event_id = int(args["event_id"])
    tag = str(args.get("tag", "")).strip()
    if not tag:
        raise ToolError("tag must be a non-empty string")
    h = _hash_for_event_id(con, event_id)
    store.add_tag(con, h, tag)
    con.commit()
    return {"ok": True, "event_id": event_id, "tag": tag}


def _untag_event(con: sqlite3.Connection, args: dict) -> dict:
    event_id = int(args["event_id"])
    tag = str(args.get("tag", "")).strip()
    if not tag:
        raise ToolError("tag must be a non-empty string")
    h = _hash_for_event_id(con, event_id)
    store.remove_tag(con, h, tag)
    con.commit()
    return {"ok": True, "event_id": event_id, "tag": tag}


def _add_event_comment(con: sqlite3.Connection, args: dict) -> dict:
    event_id = int(args["event_id"])
    body = str(args.get("body", "")).strip()
    if not body:
        raise ToolError("body must be a non-empty string")
    h = _hash_for_event_id(con, event_id)
    cid = store.add_comment(con, h, body)
    con.commit()
    return {"ok": True, "event_id": event_id, "comment_id": cid}


def _apply_filters(args: dict, callback) -> dict:
    if callback is None:
        raise ToolError(
            "apply_filters has no UI to update in this session. The model is "
            "running outside an interactive chat — nothing was changed."
        )
    state = _state_from_filters(args.get("filters"))
    callback(state)
    return {"ok": True, "active_filter_count": state.active_filter_count()}


def _metadata_to_dict(meta: CaseMetadata) -> dict:
    return {
        "company": meta.company,
        "incident": meta.incident,
        "incident_started": meta.incident_started,
        "incident_discovered": meta.incident_discovered,
        "notes": meta.notes,
        "compromised_accounts": list(meta.compromised_accounts),
        "compromised_machines": list(meta.compromised_machines),
        "known_iocs": list(meta.known_iocs),
    }


def _read_metadata(case_path) -> dict:
    return _metadata_to_dict(load_metadata(case_path))


def _set_metadata_field(case_path, args: dict) -> dict:
    field = str(args.get("field", ""))
    value = str(args.get("value", ""))
    if field not in SCALAR_FIELDS:
        raise ToolError(f"field must be one of {list(SCALAR_FIELDS)}")
    meta = load_metadata(case_path).with_scalar(field, value)
    save_metadata(case_path, meta)
    return {"ok": True, "metadata": _metadata_to_dict(meta)}


def _add_metadata_entry(case_path, args: dict) -> dict:
    category = str(args.get("category", ""))
    value = str(args.get("value", "")).strip()
    if category not in LIST_FIELDS:
        raise ToolError(f"category must be one of {list(LIST_FIELDS)}")
    if not value:
        raise ToolError("value must be a non-empty string")
    meta = load_metadata(case_path).with_added(category, value)
    save_metadata(case_path, meta)
    return {"ok": True, "metadata": _metadata_to_dict(meta)}


def _remove_metadata_entry(case_path, args: dict) -> dict:
    category = str(args.get("category", ""))
    value = str(args.get("value", ""))
    if category not in LIST_FIELDS:
        raise ToolError(f"category must be one of {list(LIST_FIELDS)}")
    meta = load_metadata(case_path).with_removed(category, value)
    save_metadata(case_path, meta)
    return {"ok": True, "metadata": _metadata_to_dict(meta)}


def _case_overview(con: sqlite3.Connection) -> dict:
    total = int(con.execute("SELECT COUNT(*) FROM event").fetchone()[0])
    rng = con.execute("SELECT MIN(ts_usec), MAX(ts_usec) FROM event").fetchone()
    first = _format_ts(int(rng[0])) if rng[0] is not None else None
    last = _format_ts(int(rng[1])) if rng[1] is not None else None
    top_dt = con.execute(
        "SELECT data_type, COUNT(*) FROM event GROUP BY data_type "
        "ORDER BY 2 DESC LIMIT 10"
    ).fetchall()
    top_parser = con.execute(
        "SELECT parser, COUNT(*) FROM event WHERE parser IS NOT NULL "
        "GROUP BY parser ORDER BY 2 DESC LIMIT 10"
    ).fetchall()
    return {
        "total_events": total,
        "ts_first": first,
        "ts_last": last,
        "top_data_types": [{"value": v, "count": int(n)} for v, n in top_dt],
        "top_parsers": [{"value": v, "count": int(n)} for v, n in top_parser],
    }

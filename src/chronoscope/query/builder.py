from __future__ import annotations

from .state import QueryState, SORTABLE_COLUMNS

_SORTABLE = {c[0] for c in SORTABLE_COLUMNS}


def build_sql(state: QueryState) -> tuple[str, tuple, str]:
    """Compile a QueryState into (where_sql, params, order_by_sql).

    where_sql is '' when there are no filters; params are positional ('?'
    placeholders); order_by_sql always has a secondary 'id ASC' for stability.
    """
    if state.sort.column not in _SORTABLE:
        raise ValueError(f"sort column not whitelisted: {state.sort.column}")
    if state.sort.direction not in ("ASC", "DESC"):
        raise ValueError(f"sort direction invalid: {state.sort.direction}")

    clauses: list[str] = []
    params: list = []

    for col, cf in sorted(state.categorical.items()):
        if cf.include:
            placeholders = ", ".join("?" * len(cf.include))
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(cf.include)
        if cf.exclude:
            placeholders = ", ".join("?" * len(cf.exclude))
            clauses.append(f"{col} NOT IN ({placeholders})")
            params.extend(cf.exclude)

    for col, sf in sorted(state.substring.items()):
        if sf.needle:
            clauses.append(f"LOWER({col}) LIKE LOWER(?)")
            params.append(f"%{sf.needle}%")

    tf = state.tag_filter
    if tf.include:
        placeholders = ", ".join("?" * len(tf.include))
        clauses.append(
            f"event_hash IN (SELECT event_hash FROM annotation_tag WHERE tag IN ({placeholders}))"
        )
        params.extend(tf.include)
    if tf.exclude:
        placeholders = ", ".join("?" * len(tf.exclude))
        clauses.append(
            f"event_hash NOT IN (SELECT event_hash FROM annotation_tag WHERE tag IN ({placeholders}))"
        )
        params.extend(tf.exclude)

    if state.star_filter == "only_starred":
        clauses.append("event_hash IN (SELECT event_hash FROM annotation_star)")
    elif state.star_filter == "only_unstarred":
        clauses.append("event_hash NOT IN (SELECT event_hash FROM annotation_star)")

    if state.timeline_filter:
        placeholders = ", ".join("?" * len(state.timeline_filter))
        clauses.append(f"timeline_id IN ({placeholders})")
        params.extend(sorted(state.timeline_filter))

    if state.bracket.start_usec is not None:
        clauses.append("ts_usec >= ?")
        params.append(state.bracket.start_usec)
    if state.bracket.end_usec is not None:
        clauses.append("ts_usec <= ?")
        params.append(state.bracket.end_usec)

    where_sql = " AND ".join(clauses)
    order_by = f"{state.sort.column} {state.sort.direction}, id ASC"
    return where_sql, tuple(params), order_by

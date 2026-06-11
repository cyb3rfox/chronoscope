from __future__ import annotations

from chronoscope.query.state import (
    FILTERABLE_COLUMNS,
    SORTABLE_COLUMNS,
    CategoricalFilter,
    FilterKind,
    QueryState,
    Sort,
    SubstringFilter,
)


def test_empty_state_is_empty():
    s = QueryState()
    assert s.active_filter_count() == 0
    assert s.summary() == "no filters"
    assert s.sort == Sort(column="ts_usec", direction="ASC")


def test_set_categorical_returns_new_state():
    s0 = QueryState()
    s1 = s0.set_categorical("data_type", include={"a", "b"}, exclude={"c"})
    assert "data_type" not in s0.categorical  # s0 unchanged
    cf = s1.categorical["data_type"]
    assert cf.include == frozenset({"a", "b"})
    assert cf.exclude == frozenset({"c"})
    assert s1.active_filter_count() == 1


def test_set_substring_returns_new_state():
    s0 = QueryState()
    s1 = s0.set_substring("message", "foo")
    assert "message" not in s0.substring
    assert s1.substring["message"].needle == "foo"
    assert s1.active_filter_count() == 1


def test_set_substring_empty_clears_column():
    s = QueryState().set_substring("message", "foo").set_substring("message", "")
    assert "message" not in s.substring
    assert s.active_filter_count() == 0


def test_set_categorical_empty_both_sides_clears_column():
    s = (
        QueryState()
        .set_categorical("data_type", include={"a"}, exclude=set())
        .set_categorical("data_type", include=set(), exclude=set())
    )
    assert "data_type" not in s.categorical


def test_set_sort_changes_sort_only():
    s = QueryState().set_sort("data_type", "DESC")
    assert s.sort == Sort("data_type", "DESC")
    assert s.active_filter_count() == 0


def test_set_sort_rejects_unknown_column():
    import pytest
    with pytest.raises(ValueError):
        QueryState().set_sort("nonexistent_column", "ASC")


def test_set_sort_rejects_unknown_direction():
    import pytest
    with pytest.raises(ValueError):
        QueryState().set_sort("ts_usec", "SIDEWAYS")


def test_clear_column_removes_filters():
    s = (
        QueryState()
        .set_categorical("data_type", include={"a"}, exclude=set())
        .set_substring("message", "foo")
        .clear_column("data_type")
    )
    assert "data_type" not in s.categorical
    assert "message" in s.substring


def test_clear_all_preserves_sort():
    s0 = (
        QueryState()
        .set_sort("data_type", "DESC")
        .set_categorical("data_type", include={"a"}, exclude=set())
        .set_substring("message", "foo")
    )
    s1 = s0.clear_all()
    assert s1.active_filter_count() == 0
    assert s1.sort == Sort("data_type", "DESC")


def test_summary_formats_filters():
    s = (
        QueryState()
        .set_categorical("data_type", include={"a", "b", "c"}, exclude={"d"})
        .set_substring("message", "foo")
    )
    summary = s.summary()
    assert "data_type" in summary
    assert "IN 3" in summary
    assert "NOT 1" in summary
    assert "message" in summary
    assert "*foo*" in summary


def test_filterable_columns_registry_has_expected_shape():
    names = [c[0] for c in FILTERABLE_COLUMNS]
    assert names == [
        "ts_desc", "data_type", "parser",
        "source_short", "source_long",
        "display_name", "message", "extra_text",
    ]
    kinds = {c[0]: c[2] for c in FILTERABLE_COLUMNS}
    assert kinds["data_type"] == FilterKind.CATEGORICAL
    assert kinds["message"] == FilterKind.SUBSTRING
    assert kinds["extra_text"] == FilterKind.SUBSTRING


def test_extra_text_substring_round_trips_through_state():
    s = QueryState().set_substring("extra_text", "google.com")
    assert s.substring["extra_text"].needle == "google.com"
    assert s.active_filter_count() == 1


def test_sortable_columns_registry():
    names = [c[0] for c in SORTABLE_COLUMNS]
    assert "ts_usec" in names
    assert "data_type" in names

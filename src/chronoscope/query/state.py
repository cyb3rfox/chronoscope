from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable


class FilterKind(Enum):
    CATEGORICAL = "categorical"
    SUBSTRING = "substring"


FILTERABLE_COLUMNS: list[tuple[str, str, FilterKind]] = [
    ("ts_desc",      "Timestamp desc", FilterKind.CATEGORICAL),
    ("data_type",    "Data type",      FilterKind.CATEGORICAL),
    ("parser",       "Parser",         FilterKind.CATEGORICAL),
    ("source_short", "Source (short)", FilterKind.CATEGORICAL),
    ("source_long",  "Source (long)",  FilterKind.CATEGORICAL),
    ("display_name", "Display name",   FilterKind.SUBSTRING),
    ("message",      "Message",        FilterKind.SUBSTRING),
    ("extra_text",   "Extra fields",   FilterKind.SUBSTRING),
]

SORTABLE_COLUMNS: list[tuple[str, str]] = [
    ("ts_usec",   "Datetime"),
    ("ts_desc",   "Timestamp desc"),
    ("data_type", "Data type"),
    ("parser",    "Parser"),
]

_FILTERABLE = {c[0] for c in FILTERABLE_COLUMNS}
_SORTABLE = {c[0] for c in SORTABLE_COLUMNS}
_DIRECTIONS = {"ASC", "DESC"}


@dataclass(frozen=True, slots=True)
class CategoricalFilter:
    include: frozenset[str] = frozenset()
    exclude: frozenset[str] = frozenset()

    def is_empty(self) -> bool:
        return not self.include and not self.exclude


@dataclass(frozen=True, slots=True)
class SubstringFilter:
    needle: str = ""

    def is_empty(self) -> bool:
        return self.needle == ""


@dataclass(frozen=True, slots=True)
class Sort:
    column: str = "ts_usec"
    direction: str = "ASC"


@dataclass(frozen=True, slots=True)
class TimeBracket:
    start_usec: int | None = None
    end_usec: int | None = None

    def is_empty(self) -> bool:
        return self.start_usec is None and self.end_usec is None

    def span_usec(self) -> int | None:
        if self.start_usec is None or self.end_usec is None:
            return None
        return self.end_usec - self.start_usec


@dataclass(frozen=True, slots=True)
class QueryState:
    categorical: dict[str, CategoricalFilter] = field(default_factory=dict)
    substring: dict[str, SubstringFilter] = field(default_factory=dict)
    tag_filter: CategoricalFilter = field(default_factory=CategoricalFilter)
    star_filter: str | None = None
    timeline_filter: frozenset[str] = field(default_factory=frozenset)
    bracket: TimeBracket = field(default_factory=TimeBracket)
    sort: Sort = field(default_factory=Sort)

    def set_categorical(
        self, col: str, *, include: Iterable[str], exclude: Iterable[str]
    ) -> "QueryState":
        _require_filterable(col, FilterKind.CATEGORICAL)
        cf = CategoricalFilter(frozenset(include), frozenset(exclude))
        new_cat = dict(self.categorical)
        if cf.is_empty():
            new_cat.pop(col, None)
        else:
            new_cat[col] = cf
        return replace(self, categorical=new_cat)

    def set_substring(self, col: str, needle: str) -> "QueryState":
        _require_filterable(col, FilterKind.SUBSTRING)
        new_sub = dict(self.substring)
        if needle == "":
            new_sub.pop(col, None)
        else:
            new_sub[col] = SubstringFilter(needle)
        return replace(self, substring=new_sub)

    def set_tag_filter(
        self, *, include: Iterable[str], exclude: Iterable[str]
    ) -> "QueryState":
        cf = CategoricalFilter(frozenset(include), frozenset(exclude))
        return replace(self, tag_filter=cf)

    def set_star_filter(self, mode: str | None) -> "QueryState":
        if mode not in (None, "only_starred", "only_unstarred"):
            raise ValueError(f"unknown star_filter: {mode!r}")
        return replace(self, star_filter=mode)

    def set_timeline_filter(self, include) -> "QueryState":
        return replace(self, timeline_filter=frozenset(include))

    def set_bracket_start(self, ts: int | None) -> "QueryState":
        return replace(self, bracket=TimeBracket(ts, self.bracket.end_usec))

    def set_bracket_end(self, ts: int | None) -> "QueryState":
        return replace(self, bracket=TimeBracket(self.bracket.start_usec, ts))

    def set_bracket(self, start: int | None, end: int | None) -> "QueryState":
        return replace(self, bracket=TimeBracket(start, end))

    def clear_bracket(self) -> "QueryState":
        return replace(self, bracket=TimeBracket())

    def set_sort(self, column: str, direction: str) -> "QueryState":
        if column not in _SORTABLE:
            raise ValueError(f"unknown sort column: {column}")
        if direction not in _DIRECTIONS:
            raise ValueError(f"unknown sort direction: {direction}")
        return replace(self, sort=Sort(column, direction))

    def clear_column(self, col: str) -> "QueryState":
        new_cat = {k: v for k, v in self.categorical.items() if k != col}
        new_sub = {k: v for k, v in self.substring.items() if k != col}
        return replace(self, categorical=new_cat, substring=new_sub)

    def clear_all(self) -> "QueryState":
        return replace(
            self,
            categorical={},
            substring={},
            tag_filter=CategoricalFilter(),
            star_filter=None,
            bracket=TimeBracket(),
            timeline_filter=frozenset(),
        )

    def active_filter_count(self) -> int:
        n = len(self.categorical) + len(self.substring)
        if not self.tag_filter.is_empty():
            n += 1
        if self.star_filter is not None:
            n += 1
        if not self.bracket.is_empty():
            n += 1
        if self.timeline_filter:
            n += 1
        return n

    def summary(self) -> str:
        if self.active_filter_count() == 0:
            return "no filters"
        parts: list[str] = []
        for col, cf in self.categorical.items():
            bits = []
            if cf.include:
                bits.append(f"IN {len(cf.include)}")
            if cf.exclude:
                bits.append(f"NOT {len(cf.exclude)}")
            parts.append(f"{col}({' '.join(bits)})")
        for col, sf in self.substring.items():
            parts.append(f"{col}(*{sf.needle}*)")
        if not self.tag_filter.is_empty():
            bits = []
            if self.tag_filter.include:
                bits.append(f"IN {len(self.tag_filter.include)}")
            if self.tag_filter.exclude:
                bits.append(f"NOT {len(self.tag_filter.exclude)}")
            parts.append(f"tags({' '.join(bits)})")
        if self.star_filter is not None:
            parts.append(f"stars({self.star_filter})")
        return "  ".join(parts)


def _require_filterable(col: str, expected_kind: FilterKind) -> None:
    if col not in _FILTERABLE:
        raise ValueError(f"unknown filterable column: {col}")
    kinds = {c[0]: c[2] for c in FILTERABLE_COLUMNS}
    if kinds[col] != expected_kind:
        raise ValueError(
            f"column {col} is {kinds[col].value}, expected {expected_kind.value}"
        )

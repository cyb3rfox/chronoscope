from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

DEFAULT_OFF_HOURS_COLOR = "red"


@dataclass(frozen=True, slots=True)
class ColorRule:
    """Common fields shared by every rule type. Concrete subclasses add their
    own match parameters."""
    id: str
    name: str
    enabled: bool
    color: str

    def matches(self, ts_usec: int) -> bool:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class OffHoursRule(ColorRule):
    """Matches events whose UTC hour falls in [start_hour, end_hour).

    When end_hour < start_hour the window wraps midnight, so an off-hours rule
    of 22→4 matches 22:00:00 through 03:59:59 inclusive. start_hour == end_hour
    means the rule never matches (an empty window).
    """
    start_hour: int = 22
    end_hour: int = 4

    def __post_init__(self) -> None:
        if not 0 <= self.start_hour <= 23:
            raise ValueError(f"start_hour out of range: {self.start_hour}")
        if not 0 <= self.end_hour <= 23:
            raise ValueError(f"end_hour out of range: {self.end_hour}")

    def matches(self, ts_usec: int) -> bool:
        if ts_usec <= 0:
            return False
        hour = (ts_usec // 1_000_000 // 3600) % 24
        if self.start_hour == self.end_hour:
            return False
        if self.start_hour < self.end_hour:
            return self.start_hour <= hour < self.end_hour
        return hour >= self.start_hour or hour < self.end_hour


@dataclass(frozen=True, slots=True)
class ColorRules:
    rules: tuple[ColorRule, ...] = field(default_factory=tuple)

    def enabled(self) -> tuple[ColorRule, ...]:
        return tuple(r for r in self.rules if r.enabled)

    def matching(self, ts_usec: int) -> tuple[ColorRule, ...]:
        return tuple(r for r in self.rules if r.enabled and r.matches(ts_usec))

    def with_rule(self, rule: ColorRule) -> "ColorRules":
        existing = {r.id: r for r in self.rules}
        existing[rule.id] = rule
        ordered = []
        seen: set[str] = set()
        for r in self.rules:
            if r.id == rule.id:
                ordered.append(rule)
                seen.add(r.id)
            else:
                ordered.append(r)
                seen.add(r.id)
        if rule.id not in seen:
            ordered.append(rule)
        return replace(self, rules=tuple(ordered))

    def with_replaced(self, rules: Iterable[ColorRule]) -> "ColorRules":
        return replace(self, rules=tuple(rules))


def default_rules() -> ColorRules:
    """The factory rule set seeded into a fresh tool-wide config."""
    return ColorRules(
        rules=(
            OffHoursRule(
                id="off_hours",
                name="Off-hours",
                enabled=False,
                color=DEFAULT_OFF_HOURS_COLOR,
                start_hour=22,
                end_hour=4,
            ),
        )
    )

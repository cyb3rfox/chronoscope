from __future__ import annotations

from dataclasses import dataclass

GROUPS: list[tuple[str, str]] = [
    ("always", "Always"),
    ("nav",    "Navigation"),
    ("annot",  "Annotations"),
    ("filter", "Filters & Sort"),
    ("visual", "Visual mode"),
    ("time",   "Time"),
]
GROUP_IDS: frozenset[str] = frozenset(gid for gid, _ in GROUPS)


@dataclass(frozen=True)
class KeyBinding:
    key: str
    action: str
    label: str
    groups: tuple[str, ...]
    prefix: str | None = None


def validate(binding: KeyBinding) -> None:
    if not binding.groups:
        raise ValueError(f"binding {binding.key!r}: at least one group required")
    for g in binding.groups:
        if g not in GROUP_IDS:
            raise ValueError(f"binding {binding.key!r}: unknown group {g!r}")


def to_textual(bindings: list[KeyBinding]) -> list[tuple[str, str, str]]:
    """Produce Textual-compatible (key, action, description) tuples.
    Skip bindings with a non-None ``prefix`` — those live inside
    WhichKeyScreen, not at screen level."""
    out: list[tuple[str, str, str]] = []
    for b in bindings:
        validate(b)
        if b.prefix is not None:
            continue
        out.append((b.key, b.action, b.label))
    return out


def bindings_in_group(bindings: list[KeyBinding], group_id: str) -> list[KeyBinding]:
    return [b for b in bindings if group_id in b.groups]


def groups_of(bindings: list[KeyBinding], key: str) -> tuple[str, ...]:
    for b in bindings:
        if b.key == key:
            return b.groups
    return ()


def group_label(group_id: str) -> str:
    for gid, label in GROUPS:
        if gid == group_id:
            return label
    raise KeyError(group_id)


def bindings_with_prefix(
    bindings: list[KeyBinding], prefix_name: str
) -> list[KeyBinding]:
    return [b for b in bindings if b.prefix == prefix_name]

from __future__ import annotations

PALETTE: tuple[str, ...] = (
    "cyan", "magenta", "yellow", "green", "blue", "red",
)


def resolve_color(stored: str | None, order_index: int) -> str:
    """Explicit --color wins; otherwise cycle through PALETTE by add-order."""
    if stored:
        return stored
    return PALETTE[order_index % len(PALETTE)]

from __future__ import annotations

from rich.text import Text


def colorize_timestamp(ts_text: str, colors: tuple[str, ...]) -> Text:
    """Return a Rich Text where ts_text is split into len(colors) roughly
    equal segments, each styled with the corresponding color.

    With no colors, returns a plain Text. With one color, the whole string
    takes that color.
    """
    if not colors:
        return Text(ts_text)
    if len(colors) == 1:
        return Text(ts_text, style=colors[0])
    n = len(colors)
    length = len(ts_text)
    out = Text()
    for i, color in enumerate(colors):
        start = (length * i) // n
        end = (length * (i + 1)) // n
        out.append(ts_text[start:end], style=color)
    return out

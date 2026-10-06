from __future__ import annotations

from datetime import datetime, timezone

from textual.containers import Container, Horizontal
from textual.widgets import Static


def _fmt_ts(ts_usec: int | None) -> str:
    if ts_usec is None or ts_usec <= 0:
        return "—"
    return datetime.fromtimestamp(
        ts_usec / 1_000_000, tz=timezone.utc
    ).isoformat(timespec="seconds")


def _dash(v) -> str:
    if v is None or v == "":
        return "—"
    return str(v)


class Card(Container):
    """Bordered container for one detail-pane section."""

    def __init__(self, title: str, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.border_title = title
        self.add_class("card")
        self._body = Static("", markup=False)

    def compose(self):
        yield self._body

    def body_text(self) -> str:
        r = self._body.content
        return r if isinstance(r, str) else str(r)

    def _set_body(self, text: str) -> None:
        self._body.update(text)


class EventBasicsCard(Card):
    def __init__(self) -> None:
        super().__init__("event", id="card-event")

    def update_from(
        self,
        ts_usec: int | None,
        ts_desc: str | None,
        data_type: str | None,
        timeline_name: str | None,
    ) -> None:
        lines = [
            f"{'datetime':12} {_fmt_ts(ts_usec)}",
            f"{'ts_desc':12} {_dash(ts_desc)}",
            f"{'data_type':12} {_dash(data_type)}",
            f"{'timeline':12} {_dash(timeline_name)}",
        ]
        self._set_body("\n".join(lines))
        self.display = True


class SourceCard(Card):
    def __init__(self) -> None:
        super().__init__("source", id="card-source")

    def update_from(
        self,
        parser: str | None,
        source_short: str | None,
        source_long: str | None,
        display_name: str | None,
    ) -> None:
        src_joined = " · ".join(s for s in (source_short, source_long) if s)
        src_joined = src_joined if src_joined else "—"
        lines = [
            f"{'parser':12} {_dash(parser)}",
            f"{'source':12} {src_joined}",
            f"{'display':12} {_dash(display_name)}",
        ]
        self._set_body("\n".join(lines))
        self.display = True


class MessageCard(Card):
    def __init__(self) -> None:
        super().__init__("message", id="card-message")

    def update_from(self, message: str) -> None:
        if not message:
            self._set_body("")
            self.display = False
            return
        self._set_body(message)
        self.display = True


class ExtraCard(Card):
    def __init__(self) -> None:
        super().__init__("extra (0)", id="card-extra")

    def update_from(self, extra: dict) -> None:
        if not extra:
            self._set_body("")
            self.border_title = "extra (0)"
            self.display = False
            return
        lines = []
        for k in sorted(extra):
            v = extra[k]
            s = "" if v is None else str(v)
            lines.append(f"{k:12} {s}")
        self._set_body("\n".join(lines))
        self.border_title = f"extra ({len(extra)})"
        self.display = True


def _fmt_iso_to_minutes(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso or ""


class CommentsCard(Card):
    def __init__(self) -> None:
        super().__init__("comments (0)", id="card-comments")

    def update_from(self, comments: list[dict]) -> None:
        if not comments:
            self._set_body("")
            self.border_title = "comments (0)"
            self.display = False
            return
        chunks: list[str] = []
        for c in comments:
            when = _fmt_iso_to_minutes(c.get("created_at", ""))
            body = c.get("body", "")
            body_lines = body.splitlines() or [""]
            indented = "\n".join(f"  {line}" for line in body_lines)
            chunks.append(f"{when}\n{indented}")
        self._set_body("\n\n".join(chunks))
        self.border_title = f"comments ({len(comments)})"
        self.display = True


class TagsCard(Card):
    def __init__(self) -> None:
        super().__init__("tags", id="card-tags")
        self._body = None  # disable base body; we render children directly
        self._chip_row = Horizontal(classes="chips")

    def compose(self):
        yield self._chip_row

    def body_text(self) -> str:
        chips = list(self.query(".chip"))
        out = []
        for c in chips:
            r = c.content
            out.append(r if isinstance(r, str) else str(r))
        return "  ".join(out)

    def update_from(self, tags: list[str], *, starred: bool) -> None:
        for child in list(self._chip_row.children):
            child.remove()
        for tag in tags:
            chip = Static(tag, markup=False, classes="chip")
            self._chip_row.mount(chip)
        title = "tags"
        if starred:
            title += " · ★ starred"
            self.add_class("is-starred")
        else:
            self.remove_class("is-starred")
        self.border_title = title
        self.display = bool(tags) or starred

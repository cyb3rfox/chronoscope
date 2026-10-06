from __future__ import annotations

import sqlite3

from textual.containers import VerticalScroll

from ...annotations import store
from ...core.extra import load_extra
from .detail_cards import (
    CommentsCard,
    EventBasicsCard,
    ExtraCard,
    MessageCard,
    SourceCard,
    TagsCard,
)


class DetailPane(VerticalScroll):
    DEFAULT_CSS = """
    DetailPane {
        border: none; padding: 0 1; width: 50%;
    }

    DetailPane .card {
        border: round $panel-lighten-1;
        border-title-color: $secondary;
        border-title-style: bold;
        padding: 0 1;
        margin: 0 0 1 0;
        height: auto;
        overflow-x: hidden;
    }
    DetailPane .card Static { color: $text; }

    DetailPane MessageCard { height: auto; max-height: 14; overflow-y: auto; }
    DetailPane ExtraCard   { max-height: 12; overflow-y: auto; }

    DetailPane TagsCard { height: auto; }
    DetailPane TagsCard .chips {
        layout: horizontal; height: 1; width: 100%;
    }
    DetailPane TagsCard .chip {
        background: $accent 20%;
        color: $text;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    DetailPane TagsCard.is-starred {
        border-title-color: $warning;
    }

    DetailPane CommentsCard .comment-date {
        color: $warning; text-style: bold; padding: 1 0 0 0;
    }
    DetailPane CommentsCard .comment-body {
        color: $text; padding: 0 0 0 2;
    }
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        super().__init__()
        self.con = con

    def set_width_percent(self, percent: int) -> None:
        """Set the pane width to the given percent of its parent; unhide if hidden."""
        self.styles.width = f"{percent}%"
        self.display = True

    def compose(self):
        yield EventBasicsCard()
        yield SourceCard()
        yield MessageCard()
        yield ExtraCard()
        yield TagsCard()
        yield CommentsCard()

    @property
    def text(self) -> str:
        """Back-compat accessor used by tests; concatenates visible cards."""
        parts: list[str] = []
        for card in self.query(".card"):
            if getattr(card, "display", True):
                title = getattr(card, "border_title", "") or ""
                body = card.body_text() if hasattr(card, "body_text") else ""
                section = "\n".join(x for x in (title, body) if x)
                if section:
                    parts.append(section)
        return "\n\n".join(parts)

    def show_event(self, event_id: int) -> None:
        row = self.con.execute(
            "SELECT e.ts_usec, e.ts_desc, e.data_type, e.parser, e.source_short, "
            "e.source_long, e.display_name, e.message, e.extra, e.event_hash, "
            "t.name FROM event e JOIN timeline t ON t.id = e.timeline_id "
            "WHERE e.id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            for card in self.query(".card"):
                card.display = False
            return
        (ts_usec, ts_desc, data_type, parser, src_s, src_l,
         disp, msg, extra_blob, event_hash, timeline_name) = row
        try:
            extra = load_extra(extra_blob) if extra_blob else {}
        except Exception:
            extra = {}
        h = bytes(event_hash)
        tags = store.tags_for(self.con, h)
        comments = store.comments_for(self.con, h)
        starred = store.get_star(self.con, h)

        self.query_one(EventBasicsCard).update_from(ts_usec, ts_desc, data_type, timeline_name)
        self.query_one(SourceCard).update_from(parser, src_s, src_l, disp)
        self.query_one(MessageCard).update_from(msg or "")
        self.query_one(ExtraCard).update_from(extra)
        self.query_one(TagsCard).update_from(tags, starred=starred)
        self.query_one(CommentsCard).update_from(comments)

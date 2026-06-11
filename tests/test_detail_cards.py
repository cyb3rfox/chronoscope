from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from chronoscope.tui.widgets.detail_cards import (
    EventBasicsCard,
    MessageCard,
    SourceCard,
)


class _Harness(App):
    def compose(self) -> ComposeResult:
        yield EventBasicsCard()
        yield SourceCard()
        yield MessageCard()


@pytest.mark.asyncio
async def test_event_basics_card_renders_fields():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(EventBasicsCard)
        card.update_from(
            ts_usec=1552410822_000_000,
            ts_desc="Last Visited Time",
            data_type="chrome:history:page_visited",
            timeline_name="web01",
        )
        text = card.body_text()
        assert "2019-03-12T17:13:42+00:00" in text
        assert "Last Visited Time" in text
        assert "chrome:history:page_visited" in text
        assert "web01" in text


@pytest.mark.asyncio
async def test_event_basics_card_dash_when_timeline_missing():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(EventBasicsCard)
        card.update_from(1, "desc", "dt", None)
        assert "—" in card.body_text()


@pytest.mark.asyncio
async def test_source_card_joins_short_and_long_with_middot():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(SourceCard)
        card.update_from(
            parser="sqlite/chrome_27_history",
            source_short="WEBHIST",
            source_long="Chrome History",
            display_name="TSK:/x",
        )
        text = card.body_text()
        assert "sqlite/chrome_27_history" in text
        assert "WEBHIST · Chrome History" in text
        assert "TSK:/x" in text


@pytest.mark.asyncio
async def test_source_card_handles_missing_source_fields():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(SourceCard)
        card.update_from("p", None, None, None)
        text = card.body_text()
        assert "p" in text


@pytest.mark.asyncio
async def test_message_card_shows_message_when_nonempty():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(MessageCard)
        card.update_from("hello world")
        assert card.display is True
        assert "hello world" in card.body_text()


@pytest.mark.asyncio
async def test_message_card_hidden_when_empty():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(MessageCard)
        card.update_from("")
        assert card.display is False


@pytest.mark.asyncio
async def test_card_base_sets_border_title_and_class():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        basics = pilot.app.query_one(EventBasicsCard)
        assert basics.border_title == "event"
        assert basics.has_class("card")


@pytest.mark.asyncio
async def test_message_card_with_brackets_does_not_crash():
    # Regression for the EVTX pattern that crashed Textual's markup parser.
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(MessageCard)
        card.update_from(
            "['OU=Starfield', 'O=\"Starfield Technologies, Inc.\", C=US']"
        )
        await pilot.pause()
        assert card.display is True


from chronoscope.tui.widgets.detail_cards import CommentsCard, ExtraCard


class _ExtraHarness(App):
    def compose(self) -> ComposeResult:
        yield ExtraCard()


class _CommentsHarness(App):
    def compose(self) -> ComposeResult:
        yield CommentsCard()


@pytest.mark.asyncio
async def test_extra_card_shows_sorted_keys_with_count_in_title():
    async with _ExtraHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(ExtraCard)
        card.update_from({"url": "https://x/", "count": 3, "title": "T"})
        assert card.display is True
        assert card.border_title == "extra (3)"
        text = card.body_text()
        pos_count = text.index("count")
        pos_title = text.index("title")
        pos_url = text.index("url")
        assert pos_count < pos_title < pos_url


@pytest.mark.asyncio
async def test_extra_card_hidden_when_empty():
    async with _ExtraHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(ExtraCard)
        card.update_from({})
        assert card.display is False


@pytest.mark.asyncio
async def test_extra_card_bracket_values_do_not_crash():
    async with _ExtraHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(ExtraCard)
        card.update_from({"payload": "[key='value', other=\"inner\"]"})
        await pilot.pause()
        assert card.display is True
        assert "payload" in card.body_text()


@pytest.mark.asyncio
async def test_comments_card_shows_each_comment_with_date():
    async with _CommentsHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(CommentsCard)
        card.update_from([
            {"id": 1, "body": "first", "created_at": "2026-04-20T14:02:00+00:00",
             "updated_at": "2026-04-20T14:02:00+00:00"},
            {"id": 2, "body": "second\nwith newline",
             "created_at": "2026-04-20T14:15:00+00:00",
             "updated_at": "2026-04-20T14:15:00+00:00"},
        ])
        assert card.display is True
        assert card.border_title == "comments (2)"
        text = card.body_text()
        assert "2026-04-20 14:02" in text
        assert "first" in text
        assert "second" in text
        assert "with newline" in text


@pytest.mark.asyncio
async def test_comments_card_hidden_when_empty():
    async with _CommentsHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(CommentsCard)
        card.update_from([])
        assert card.display is False


from chronoscope.tui.widgets.detail_cards import TagsCard


class _TagsHarness(App):
    def compose(self) -> ComposeResult:
        yield TagsCard()


@pytest.mark.asyncio
async def test_tags_card_hidden_when_no_tags_and_not_starred():
    async with _TagsHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(TagsCard)
        card.update_from([], starred=False)
        assert card.display is False


@pytest.mark.asyncio
async def test_tags_card_visible_when_starred_alone():
    async with _TagsHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(TagsCard)
        card.update_from([], starred=True)
        assert card.display is True
        assert card.has_class("is-starred")
        assert "starred" in card.border_title


@pytest.mark.asyncio
async def test_tags_card_renders_one_static_chip_per_tag():
    async with _TagsHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(TagsCard)
        card.update_from(["suspicious", "lateral-movement"], starred=False)
        await pilot.pause()
        chips = list(card.query(".chip"))
        assert len(chips) == 2
        chip_texts = set()
        for c in chips:
            r = c.content
            chip_texts.add(r if isinstance(r, str) else str(r))
        assert chip_texts == {"suspicious", "lateral-movement"}


@pytest.mark.asyncio
async def test_tags_card_title_and_class_toggle_on_star_change():
    async with _TagsHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(TagsCard)
        card.update_from(["a"], starred=True)
        assert card.has_class("is-starred")
        assert "starred" in card.border_title
        card.update_from(["a"], starred=False)
        assert not card.has_class("is-starred")
        assert "starred" not in card.border_title


@pytest.mark.asyncio
async def test_tags_card_chip_contents_survive_brackets():
    # Tags go through tag_normalize so they shouldn't contain [, but guard anyway.
    async with _TagsHarness().run_test() as pilot:
        await pilot.pause()
        card = pilot.app.query_one(TagsCard)
        card.update_from(["weird[tag]"], starred=False)
        await pilot.pause()
        chips = list(card.query(".chip"))
        assert len(chips) == 1


from pathlib import Path

from chronoscope.annotations import store
from chronoscope.core.case import init_case, open_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.detail_pane import DetailPane

DATA = Path(__file__).parent / "data" / "sample.jsonl"


@pytest.mark.asyncio
async def test_detail_pane_mounts_all_six_cards(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        pane = pilot.app.screen.query_one(DetailPane)
        assert len(pane.query(".card")) == 6


@pytest.mark.asyncio
async def test_detail_pane_hides_empty_sections_for_bare_event(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        table.move_cursor(row=0)
        await pilot.pause()
        pane = pilot.app.screen.query_one(DetailPane)
        from chronoscope.tui.widgets.detail_cards import (
            EventBasicsCard, SourceCard, TagsCard, CommentsCard,
        )
        assert pane.query_one(EventBasicsCard).display is True
        assert pane.query_one(SourceCard).display is True
        assert pane.query_one(TagsCard).display is False
        assert pane.query_one(CommentsCard).display is False


@pytest.mark.asyncio
async def test_detail_pane_exposes_combined_text_property(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        table.move_cursor(row=0)
        await pilot.pause()
        pane = pilot.app.screen.query_one(DetailPane)
        text = pane.text
        assert "data_type" in text
        assert "chrome:history" in text


@pytest.mark.asyncio
async def test_detail_pane_tags_and_comments_flow(case_dir):
    init_case(case_dir, name="demo")
    ingest_file(case_dir, DATA, name="sample")
    with open_case(case_dir) as c:
        h = c.con.execute(
            "SELECT event_hash FROM event ORDER BY ts_usec ASC, id ASC LIMIT 1"
        ).fetchone()[0]
        store.set_star(c.con, h, True)
        store.add_tag(c.con, h, "susp")
        store.add_comment(c.con, h, "first")

    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.detail_cards import CommentsCard, TagsCard
        from chronoscope.tui.widgets.event_table import EventTable
        table = pilot.app.screen.query_one(EventTable)
        table.focus()
        table.move_cursor(row=0)
        await pilot.pause()
        pane = pilot.app.screen.query_one(DetailPane)
        tags_card = pane.query_one(TagsCard)
        assert tags_card.display is True
        assert tags_card.has_class("is-starred")
        assert "susp" in tags_card.body_text()
        cm_card = pane.query_one(CommentsCard)
        assert cm_card.display is True
        assert "first" in cm_card.body_text()

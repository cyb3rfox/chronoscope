from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from chronoscope.tui.bindings import KeyBinding
from chronoscope.tui.widgets.grouped_footer import GroupedFooter


def _bindings() -> list[KeyBinding]:
    return [
        KeyBinding("f", "open_filters", "Filter/Sort", ("always", "filter")),
        KeyBinding("g", "jump",         "Jump",        ("always", "nav")),
        KeyBinding("?", "help",         "Help",        ("always",)),
        KeyBinding("s", "toggle_star",  "Star",        ("annot",)),
        KeyBinding("t", "add_tag",      "Tag",         ("annot",)),
        KeyBinding("R", "clear_filters", "Clear",      ("filter",)),
        KeyBinding("V", "visual_enter", "Visual",      ("annot", "visual")),
        KeyBinding("space", "visual_toggle_sticky", "Sticky", ("visual",)),
    ]


class _Harness(App):
    def compose(self) -> ComposeResult:
        yield GroupedFooter(_bindings())


@pytest.mark.asyncio
async def test_footer_starts_on_first_non_always_group_with_bindings():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        footer = pilot.app.query_one(GroupedFooter)
        assert footer.current_group_id() == "nav"


@pytest.mark.asyncio
async def test_cycle_group_forward():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        footer = pilot.app.query_one(GroupedFooter)
        assert footer.current_group_id() == "nav"
        footer.cycle_group(+1)
        assert footer.current_group_id() == "annot"
        footer.cycle_group(+1)
        assert footer.current_group_id() == "filter"
        footer.cycle_group(+1)
        assert footer.current_group_id() == "visual"
        footer.cycle_group(+1)
        assert footer.current_group_id() == "nav"


@pytest.mark.asyncio
async def test_cycle_group_backward():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        footer = pilot.app.query_one(GroupedFooter)
        footer.cycle_group(-1)
        assert footer.current_group_id() == "visual"


@pytest.mark.asyncio
async def test_set_group_sticky():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        footer = pilot.app.query_one(GroupedFooter)
        footer.set_group("annot", sticky=True)
        assert footer.current_group_id() == "annot"


@pytest.mark.asyncio
async def test_set_group_non_sticky_restores_previous():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        footer = pilot.app.query_one(GroupedFooter)
        footer.set_group("annot", sticky=True)
        assert footer.saved_sticky_group_id() == "annot"
        footer.set_group("visual", sticky=False)
        assert footer.current_group_id() == "visual"
        assert footer.saved_sticky_group_id() == "annot"
        footer.set_group(footer.saved_sticky_group_id(), sticky=True)
        assert footer.current_group_id() == "annot"


@pytest.mark.asyncio
async def test_footer_shows_always_line_content():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        footer = pilot.app.query_one(GroupedFooter)
        always = footer.render_always_line()
        assert "f" in always and "Filter/Sort".lower() in always
        assert "g" in always and "jump" in always
        assert "?" in always and "help" in always
        assert "Star" not in always and "star" not in always

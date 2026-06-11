from __future__ import annotations

import sqlite3

import pytest
from textual.app import App

from chronoscope.annotations import store
from chronoscope.core.schema import migrate
from chronoscope.tui.screens.tag_manager import TagManagerScreen


class _Harness(App):
    def __init__(self, con):
        super().__init__()
        self._con = con
        self.result = "NOT_SET"

    def on_mount(self):
        self.push_screen(TagManagerScreen(self._con), callback=self._on_result)

    def _on_result(self, result):
        self.result = result


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    migrate(c)
    store.add_tag(c, b"\x01" * 32, "susp")
    store.add_tag(c, b"\x02" * 32, "susp")
    store.add_tag(c, b"\x02" * 32, "review")
    yield c
    c.close()


@pytest.mark.asyncio
async def test_tag_manager_lists_tags_with_counts(con):
    harness = _Harness(con)
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one(OptionList)
        assert lst.option_count == 2
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_tag_manager_enter_returns_filter_tuple(con):
    harness = _Harness(con)
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one(OptionList)
        lst.focus()
        lst.highlighted = 0
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == ("filter", "susp")


@pytest.mark.asyncio
async def test_tag_manager_delete_removes_tag(con):
    harness = _Harness(con)
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one(OptionList)
        lst.focus()
        lst.highlighted = 1
        await pilot.press("D")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        lst2 = pilot.app.screen.query_one(OptionList)
        assert lst2.option_count == 1
        await pilot.press("escape")
        await pilot.pause()

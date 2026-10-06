from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.tui.widgets.tri_state import State, TriStateItem, TriStateOptionList


class _Harness(App):
    def __init__(self, items):
        super().__init__()
        self._items = items

    def compose(self):
        yield TriStateOptionList(self._items)


def _items():
    return [
        TriStateItem("alpha", 100, State.NONE),
        TriStateItem("beta", 50, State.NONE),
        TriStateItem("gamma", 25, State.NONE),
    ]


@pytest.mark.asyncio
async def test_cycle_transitions():
    async with _Harness(_items()).run_test() as pilot:
        await pilot.pause()
        lst = pilot.app.query_one(TriStateOptionList)
        lst.focus()
        await pilot.press("space")
        await pilot.pause()
        assert lst.items[0].state == State.INCLUDE
        await pilot.press("space")
        await pilot.pause()
        assert lst.items[0].state == State.EXCLUDE
        await pilot.press("space")
        await pilot.pause()
        assert lst.items[0].state == State.NONE


@pytest.mark.asyncio
async def test_plus_and_minus_set_states_directly():
    async with _Harness(_items()).run_test() as pilot:
        await pilot.pause()
        lst = pilot.app.query_one(TriStateOptionList)
        lst.focus()
        await pilot.press("plus")
        await pilot.pause()
        assert lst.items[0].state == State.INCLUDE
        await pilot.press("down")
        await pilot.press("minus")
        await pilot.pause()
        assert lst.items[1].state == State.EXCLUDE


@pytest.mark.asyncio
async def test_snapshot_returns_include_exclude_sets():
    async with _Harness(_items()).run_test() as pilot:
        await pilot.pause()
        lst = pilot.app.query_one(TriStateOptionList)
        lst.focus()
        lst.items[0].state = State.INCLUDE
        lst.items[2].state = State.EXCLUDE
        lst.refresh_rows()
        inc, exc = lst.snapshot
        assert inc == frozenset({"alpha"})
        assert exc == frozenset({"gamma"})


@pytest.mark.asyncio
async def test_set_filter_hides_non_matching_rows():
    async with _Harness(_items()).run_test() as pilot:
        await pilot.pause()
        lst = pilot.app.query_one(TriStateOptionList)
        lst.set_filter("bet")
        await pilot.pause()
        assert lst.visible_count == 1
        lst.set_filter("")
        await pilot.pause()
        assert lst.visible_count == 3

from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.query.state import CategoricalFilter
from chronoscope.tui.screens.value_picker import ValuePickerScreen


class _Harness(App):
    def __init__(self, col: str, counts, initial: CategoricalFilter):
        super().__init__()
        self._col = col
        self._counts = counts
        self._initial = initial
        self.result: CategoricalFilter | None = None

    def on_mount(self):
        self.push_screen(
            ValuePickerScreen(self._col, self._counts, self._initial),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


COUNTS = [("chrome:history:page_visited", 10),
          ("chrome:history:file_downloaded", 3),
          ("windows:prefetch:execution", 7)]


@pytest.mark.asyncio
async def test_value_picker_selects_include():
    harness = _Harness("data_type", COUNTS, CategoricalFilter())
    async with harness.run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.tri_state import TriStateOptionList
        lst = pilot.app.screen.query_one(TriStateOptionList)
        lst.focus()
        await pilot.press("plus")      # first row → INCLUDE
        await pilot.press("enter")     # commit
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.include == frozenset({"chrome:history:page_visited"})
    assert harness.result.exclude == frozenset()


@pytest.mark.asyncio
async def test_value_picker_exclude_via_space_cycle():
    harness = _Harness("data_type", COUNTS, CategoricalFilter())
    async with harness.run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.tri_state import TriStateOptionList
        lst = pilot.app.screen.query_one(TriStateOptionList)
        lst.focus()
        await pilot.press("space")  # NONE → INCLUDE
        await pilot.press("space")  # INCLUDE → EXCLUDE
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.include == frozenset()
    assert harness.result.exclude == frozenset({"chrome:history:page_visited"})


@pytest.mark.asyncio
async def test_value_picker_escape_cancels():
    harness = _Harness("data_type", COUNTS, CategoricalFilter())
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_value_picker_seeds_from_initial():
    initial = CategoricalFilter(
        include=frozenset({"chrome:history:page_visited"}),
        exclude=frozenset({"windows:prefetch:execution"}),
    )
    harness = _Harness("data_type", COUNTS, initial)
    async with harness.run_test() as pilot:
        await pilot.pause()
        from chronoscope.tui.widgets.tri_state import TriStateOptionList, State
        lst = pilot.app.screen.query_one(TriStateOptionList)
        by_value = {it.value: it.state for it in lst.items}
        assert by_value["chrome:history:page_visited"] == State.INCLUDE
        assert by_value["windows:prefetch:execution"] == State.EXCLUDE

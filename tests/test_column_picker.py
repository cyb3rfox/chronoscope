from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.query.state import QueryState
from chronoscope.tui.screens.column_picker import ColumnPickerScreen


def _counts_provider(column: str) -> list[tuple[str, int]]:
    if column == "data_type":
        return [("chrome:history:page_visited", 10),
                ("chrome:history:file_downloaded", 3),
                ("windows:prefetch:execution", 7)]
    if column == "parser":
        return [("sqlite/chrome_27_history", 13),
                ("winprefetch", 7)]
    if column == "ts_desc":
        return [("Last Visited Time", 10),
                ("File Downloaded", 3),
                ("Recorded Time", 7)]
    if column == "source_short":
        return [("WEBHIST", 13), ("LOG", 7)]
    if column == "source_long":
        return [("Chrome History", 13), ("Prefetch", 7)]
    return []


class _Harness(App):
    def __init__(self, initial: QueryState):
        super().__init__()
        self._initial = initial
        self.result: QueryState | None = None

    def on_mount(self):
        self.push_screen(
            ColumnPickerScreen(self._initial, _counts_provider),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_column_picker_opens_and_lists_columns():
    harness = _Harness(QueryState())
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one(OptionList)
        # 8 filterable columns + 2 annotation rows (Tags, Stars) + 1 timelines row + 1 sort row
        # separators are rendered but are not Options.
        assert lst.option_count == 12
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result == QueryState()


@pytest.mark.asyncio
async def test_column_picker_sort_direction_toggle():
    harness = _Harness(QueryState())
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList
        lst = pilot.app.screen.query_one(OptionList)
        lst.focus()
        lst.highlighted = lst.option_count - 1  # sort row is last
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.sort.direction == "DESC"


@pytest.mark.asyncio
async def test_column_picker_clear_all_R():
    initial = (
        QueryState()
        .set_categorical("data_type", include={"x"}, exclude=set())
        .set_substring("message", "foo")
    )
    harness = _Harness(initial)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("R")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.active_filter_count() == 0
    assert harness.result.sort == initial.sort

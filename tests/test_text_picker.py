from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.query.state import SubstringFilter
from chronoscope.tui.screens.text_picker import TextPickerScreen


class _Harness(App):
    def __init__(self, col: str, initial: SubstringFilter):
        super().__init__()
        self._col = col
        self._initial = initial
        self.result: SubstringFilter | None = None

    def on_mount(self):
        self.push_screen(
            TextPickerScreen(self._col, self._initial),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_text_picker_apply_sets_needle():
    harness = _Harness("message", SubstringFilter(""))
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press(*list("evil"))
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == SubstringFilter("evil")


@pytest.mark.asyncio
async def test_text_picker_empty_enter_clears():
    harness = _Harness("message", SubstringFilter("old"))
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+u")
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == SubstringFilter("")


@pytest.mark.asyncio
async def test_text_picker_escape_returns_none():
    harness = _Harness("message", SubstringFilter("keep"))
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None

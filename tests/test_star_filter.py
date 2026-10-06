from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.tui.screens.star_filter import StarFilterScreen


class _Harness(App):
    def __init__(self, initial):
        super().__init__()
        self._initial = initial
        self.result = "NOT_SET"

    def on_mount(self):
        self.push_screen(StarFilterScreen(self._initial), callback=self._on_result)

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_star_filter_any_returns_none():
    harness = _Harness(None)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_star_filter_only_starred():
    harness = _Harness(None)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
    assert harness.result == "only_starred"


@pytest.mark.asyncio
async def test_star_filter_only_unstarred():
    harness = _Harness(None)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("u")
        await pilot.pause()
    assert harness.result == "only_unstarred"

from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.tui.screens.confirm import ConfirmScreen


class _Harness(App):
    def __init__(self, prompt):
        super().__init__()
        self.prompt = prompt
        self.result = None

    def on_mount(self):
        self.push_screen(ConfirmScreen(self.prompt), callback=self._on_result)

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_confirm_y_returns_true():
    harness = _Harness("delete?")
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
    assert harness.result is True


@pytest.mark.asyncio
async def test_confirm_n_returns_false():
    harness = _Harness("delete?")
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
    assert harness.result is False


@pytest.mark.asyncio
async def test_confirm_escape_returns_false():
    harness = _Harness("delete?")
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is False

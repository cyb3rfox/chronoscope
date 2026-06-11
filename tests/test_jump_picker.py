from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.tui.screens.jump_picker import JumpPickerScreen


class _Harness(App):
    def __init__(self, anchor_usec: int):
        super().__init__()
        self._anchor = anchor_usec
        self.result: int | None = None

    def on_mount(self):
        self.push_screen(
            JumpPickerScreen(self._anchor),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_jump_picker_applies_iso():
    harness = _Harness(anchor_usec=1552410840_000_000)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press(*list("2019-03-12 17:13"))
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == 1552410780_000_000


@pytest.mark.asyncio
async def test_jump_picker_applies_relative():
    anchor = 1552410840_000_000
    harness = _Harness(anchor_usec=anchor)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press(*list("-5m"))
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == anchor - 5 * 60 * 1_000_000


@pytest.mark.asyncio
async def test_jump_picker_escape_returns_none():
    harness = _Harness(anchor_usec=1552410840_000_000)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_jump_picker_invalid_input_stays_open():
    harness = _Harness(anchor_usec=1552410840_000_000)
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press(*list("garbage"))
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, JumpPickerScreen)
        from textual.widgets import Static
        msg = pilot.app.screen.query_one("#error", Static)
        # Content should be non-empty string (adapted: .renderable not available in this Textual version).
        assert msg.content != ""

from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.tui.screens.tag_picker import TagPickerScreen


class _Harness(App):
    def __init__(self, mode, initial, case_tags):
        super().__init__()
        self.mode = mode
        self.initial = initial
        self.case_tags = case_tags
        self.result = None

    def on_mount(self):
        self.push_screen(
            TagPickerScreen(self.mode, self.initial, self.case_tags),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_tag_picker_add_returns_normalized_tag():
    harness = _Harness("add", set(), [("susp", 3)])
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press(*list("Lateral Movement"))
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == "lateral-movement"


@pytest.mark.asyncio
async def test_tag_picker_escape_cancels():
    harness = _Harness("add", set(), [])
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_tag_picker_empty_submission_shows_error():
    harness = _Harness("add", set(), [])
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        from chronoscope.tui.screens.tag_picker import TagPickerScreen
        assert isinstance(pilot.app.screen, TagPickerScreen)

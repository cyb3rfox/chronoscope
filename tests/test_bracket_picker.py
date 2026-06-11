from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.query.state import TimeBracket
from chronoscope.tui.screens.bracket_picker import BracketPickerScreen


ANCHOR = 1552410840_000_000   # 2019-03-12T17:14:00Z


class _Harness(App):
    def __init__(self, initial: TimeBracket):
        super().__init__()
        self._initial = initial
        self.result = "NOT_SET"

    def on_mount(self):
        self.push_screen(
            BracketPickerScreen(self._initial, ANCHOR),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_bracket_picker_empty_applies_unbounded():
    harness = _Harness(TimeBracket())
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == TimeBracket(None, None)


@pytest.mark.asyncio
async def test_bracket_picker_iso_on_both():
    harness = _Harness(TimeBracket())
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Input
        from_input = pilot.app.screen.query_one("#from", Input)
        to_input = pilot.app.screen.query_one("#to", Input)
        from_input.value = "2019-03-12 17:00"
        to_input.value = "2019-03-12 17:19"
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.start_usec == 1552410000_000_000
    assert harness.result.end_usec == 1552411140_000_000


@pytest.mark.asyncio
async def test_bracket_picker_relative_anchored_to_cursor():
    harness = _Harness(TimeBracket())
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Input
        pilot.app.screen.query_one("#from", Input).value = "-5m"
        pilot.app.screen.query_one("#to",   Input).value = "+5m"
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.start_usec == ANCHOR - 5 * 60 * 1_000_000
    assert harness.result.end_usec   == ANCHOR + 5 * 60 * 1_000_000


@pytest.mark.asyncio
async def test_bracket_picker_escape_returns_none():
    harness = _Harness(TimeBracket(100, 400))
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_bracket_picker_invalid_stays_open_and_shows_error():
    harness = _Harness(TimeBracket())
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Input, Static
        pilot.app.screen.query_one("#from", Input).value = "garbage"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(pilot.app.screen, BracketPickerScreen)
        err = pilot.app.screen.query_one("#error", Static)
        assert str(err.content) != ""

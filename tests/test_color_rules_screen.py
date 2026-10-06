from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import OptionList

from chronoscope.coloring.rules import ColorRules, OffHoursRule
from chronoscope.tui.screens.color_rules import ColorRulesScreen


class _Harness(App):
    def __init__(self, initial: ColorRules):
        super().__init__()
        self._initial = initial
        self.result: ColorRules | None = None

    def on_mount(self):
        self.push_screen(
            ColorRulesScreen(self._initial),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


def _seed() -> ColorRules:
    return ColorRules(
        rules=(
            OffHoursRule(
                id="off_hours", name="Off-hours", enabled=False, color="red",
                start_hour=22, end_hour=4,
            ),
        )
    )


@pytest.mark.asyncio
async def test_color_rules_screen_lists_rule():
    harness = _Harness(_seed())
    async with harness.run_test() as pilot:
        await pilot.pause()
        lst = pilot.app.screen.query_one(OptionList)
        assert lst.option_count == 1
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result == _seed()


@pytest.mark.asyncio
async def test_color_rules_screen_toggles_with_space():
    harness = _Harness(_seed())
    async with harness.run_test() as pilot:
        await pilot.pause()
        lst = pilot.app.screen.query_one(OptionList)
        lst.focus()
        lst.highlighted = 0
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.rules[0].enabled is True

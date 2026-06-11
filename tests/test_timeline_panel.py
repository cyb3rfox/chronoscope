from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.core.case import TimelineInfo
from chronoscope.tui.screens.timeline_panel import TimelinePanelScreen


def _sample_timelines() -> list[TimelineInfo]:
    return [
        TimelineInfo("tl_a", "web01",  "/a.jsonl", 12401, "cyan",    0),
        TimelineInfo("tl_b", "dc01",   "/b.jsonl", 47318, "magenta", 1),
        TimelineInfo("tl_c", "laptop", "/c.jsonl",  8722, "yellow",  2),
    ]


class _Harness(App):
    def __init__(self, timelines, initial):
        super().__init__()
        self._timelines = timelines
        self._initial = initial
        self.result = "NOT_SET"

    def on_mount(self):
        self.push_screen(
            TimelinePanelScreen(self._timelines, self._initial),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_empty_initial_means_all_checked():
    async with _Harness(_sample_timelines(), frozenset()).run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, TimelinePanelScreen)
        assert screen._draft == {"tl_a", "tl_b", "tl_c"}


@pytest.mark.asyncio
async def test_space_toggles_highlighted_row():
    harness = _Harness(_sample_timelines(), frozenset())
    async with harness.run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        from textual.widgets import OptionList
        lst = screen.query_one("#timeline-list", OptionList)
        lst.focus()
        lst.highlighted = 1  # dc01
        await pilot.press("space")
        await pilot.pause()
        assert "tl_b" not in screen._draft


@pytest.mark.asyncio
async def test_a_selects_all_x_selects_none():
    harness = _Harness(_sample_timelines(), frozenset({"tl_a"}))
    async with harness.run_test() as pilot:
        await pilot.pause()
        screen = pilot.app.screen
        await pilot.press("x")
        await pilot.pause()
        assert screen._draft == set()
        await pilot.press("a")
        await pilot.pause()
        assert screen._draft == {"tl_a", "tl_b", "tl_c"}


@pytest.mark.asyncio
async def test_enter_all_selected_dismisses_empty_frozenset():
    harness = _Harness(_sample_timelines(), frozenset())
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == frozenset()


@pytest.mark.asyncio
async def test_enter_none_selected_also_dismisses_empty_frozenset():
    harness = _Harness(_sample_timelines(), frozenset())
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == frozenset()


@pytest.mark.asyncio
async def test_enter_partial_dismisses_with_that_subset():
    harness = _Harness(_sample_timelines(), frozenset({"tl_a"}))
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == frozenset({"tl_a"})


@pytest.mark.asyncio
async def test_empty_timelines_dismisses_cleanly():
    harness = _Harness([], frozenset())
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert harness.result == frozenset()

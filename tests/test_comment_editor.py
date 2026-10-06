from __future__ import annotations

import pytest
from textual.app import App

from chronoscope.tui.screens.comment_editor import CommentEditorScreen


class _Harness(App):
    def __init__(self, initial):
        super().__init__()
        self._initial = initial
        self.result = None

    def on_mount(self):
        self.push_screen(
            CommentEditorScreen("Comment", self._initial),
            callback=self._on_result,
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_comment_editor_ctrl_s_saves():
    harness = _Harness("")
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press(*list("hello"))
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert harness.result == "hello"


@pytest.mark.asyncio
async def test_comment_editor_escape_cancels():
    harness = _Harness("initial")
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_comment_editor_seeds_initial():
    harness = _Harness("seeded body")
    async with harness.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import TextArea
        ta = pilot.app.screen.query_one(TextArea)
        assert ta.text == "seeded body"
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert harness.result == "seeded body"

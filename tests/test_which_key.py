from __future__ import annotations

import pytest
from textual.app import App
from textual.screen import Screen

from chronoscope.tui.bindings import KeyBinding
from chronoscope.tui.screens.which_key import WhichKeyScreen


class _Target(Screen):
    """Caller screen exposing action_*s that WhichKeyScreen dispatches."""

    def __init__(self) -> None:
        super().__init__()
        self.invoked: list[str] = []

    def action_do_open(self) -> None: self.invoked.append("open")
    def action_do_clear(self) -> None: self.invoked.append("clear")


class _Harness(App):
    def on_mount(self) -> None:
        self.target = _Target()
        self.push_screen(self.target)

    def show_whichkey(self) -> None:
        bindings = [
            KeyBinding("o", "do_open",  "Open",  ("time",), prefix="bracket"),
            KeyBinding("c", "do_clear", "Clear", ("time",), prefix="bracket"),
        ]
        self.push_screen(WhichKeyScreen("bracket", bindings, self.target))


@pytest.mark.asyncio
async def test_whichkey_dispatches_subkey_to_target():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        pilot.app.show_whichkey()
        await pilot.pause()
        assert isinstance(pilot.app.screen, WhichKeyScreen)
        await pilot.press("o")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, WhichKeyScreen)
        assert pilot.app.target.invoked == ["open"]


@pytest.mark.asyncio
async def test_whichkey_escape_does_not_dispatch():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        pilot.app.show_whichkey()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, WhichKeyScreen)
        assert pilot.app.target.invoked == []


@pytest.mark.asyncio
async def test_whichkey_unknown_key_ignored():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        pilot.app.show_whichkey()
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        assert isinstance(pilot.app.screen, WhichKeyScreen)
        assert pilot.app.target.invoked == []


@pytest.mark.asyncio
async def test_whichkey_renders_both_subkeys():
    async with _Harness().run_test() as pilot:
        await pilot.pause()
        pilot.app.show_whichkey()
        await pilot.pause()
        screen = pilot.app.screen
        assert isinstance(screen, WhichKeyScreen)
        body = screen.rendered_text()
        assert "o" in body and "Open" in body
        assert "c" in body and "Clear" in body

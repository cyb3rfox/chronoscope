from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Input, TextArea

from chronoscope.core.metadata import CaseMetadata
from chronoscope.tui.screens.metadata_editor import MetadataEditorScreen


class _Harness(App):
    def __init__(self, initial: CaseMetadata) -> None:
        super().__init__()
        self._initial = initial
        self.result: CaseMetadata | None = None

    def on_mount(self):
        self.push_screen(
            MetadataEditorScreen(self._initial), callback=self._on_result
        )

    def _on_result(self, result):
        self.result = result


@pytest.mark.asyncio
async def test_editor_save_returns_updated_metadata():
    harness = _Harness(CaseMetadata())
    async with harness.run_test() as pilot:
        await pilot.pause()
        pilot.app.screen.query_one("#company", Input).value = "ACME"
        pilot.app.screen.query_one("#incident", Input).value = "RAT"
        pilot.app.screen.query_one(
            "#compromised_accounts", TextArea
        ).text = "alice\nbob\n"
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.company == "ACME"
    assert harness.result.incident == "RAT"
    # TextArea lines must be parsed into list entries with blanks dropped.
    assert harness.result.compromised_accounts == ("alice", "bob")


@pytest.mark.asyncio
async def test_editor_cancel_returns_none():
    harness = _Harness(CaseMetadata(company="should-not-leak"))
    async with harness.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert harness.result is None


@pytest.mark.asyncio
async def test_editor_dedupes_list_entries():
    harness = _Harness(CaseMetadata())
    async with harness.run_test() as pilot:
        await pilot.pause()
        pilot.app.screen.query_one(
            "#known_iocs", TextArea
        ).text = "1.1.1.1\n  2.2.2.2  \n1.1.1.1\n"
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert harness.result is not None
    assert harness.result.known_iocs == ("1.1.1.1", "2.2.2.2")

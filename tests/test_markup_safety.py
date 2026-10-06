"""Regression tests: events whose fields contain Rich-markup-like brackets must
not crash the TUI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chronoscope.core.case import init_case
from chronoscope.ingest.pipeline import ingest_file
from chronoscope.tui.app import PlasoViewerApp
from chronoscope.tui.widgets.event_table import EventTable


def _make_fixture(path: Path) -> None:
    """Write a JSONL fixture with events that contain bracket-heavy strings
    (the kind Plaso emits for EVTX, CloudTrail, etc.)."""
    events = [
        {
            "datetime": "2019-03-12T17:00:00+00:00",
            "timestamp": 1552410000_000_000,
            "timestamp_desc": "Recorded Time",
            "data_type": "windows:evtx:record",
            "parser": "winevtx",
            "source_short": "EVT",
            "source_long": "Windows EVTX",
            "display_name": "Security.evtx",
            "message": '[EventID=4624] [ServiceName="foo"] user logged on',
        },
        {
            "datetime": "2019-03-12T17:01:00+00:00",
            "timestamp": 1552410060_000_000,
            "timestamp_desc": "Recorded Time",
            "data_type": "windows:evtx:record",
            "parser": "winevtx",
            "source_short": "EVT",
            "source_long": "Windows EVTX",
            "display_name": "Security.evtx",
            "message": 'PSAP_CODES="NOI DEV PSA PSD IVA IVD OTP OUR OTR IND OTC"',
        },
        {
            "datetime": "2019-03-12T17:02:00+00:00",
            "timestamp": 1552410120_000_000,
            "timestamp_desc": "Recorded Time",
            "data_type": "fs:stat",
            "parser": "filestat",
            "source_short": "FILE",
            "source_long": "File entry",
            "display_name": "/path/[weird name].txt",
            "message": "[just a bracket at the start]",
        },
        {
            # Pattern that crashed in the wild on real plaso EVTX output:
            # nested quotes inside a bracketed list-literal. Rich's
            # markup.escape() does NOT make this safe for Textual's markup
            # parser; the fix is Static(markup=False).
            "datetime": "2019-03-12T17:03:00+00:00",
            "timestamp": 1552410180_000_000,
            "timestamp_desc": "Recorded Time",
            "data_type": "windows:evtx:record",
            "parser": "winevtx",
            "source_short": "EVT",
            "source_long": "Windows EVTX",
            "display_name": "Security.evtx",
            "message": (
                "['OU=Starfield Class 2 Certification Authority', "
                "'O=\"Starfield Technologies, Inc.\", C=US', "
                "'AD7E1C28B064EF8F6003402014C3D0E3370EB58A'] "
                "Computer Name: SRVWADERNBU.unimed.local Record Number: 756335"
            ),
        },
    ]
    with path.open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


@pytest.mark.asyncio
async def test_bracket_heavy_events_render_without_crash(case_dir, tmp_path):
    fixture = tmp_path / "brackets.jsonl"
    _make_fixture(fixture)
    init_case(case_dir, name="demo")
    ingest_file(case_dir, fixture, name="brackets")

    async with PlasoViewerApp(case_dir).run_test() as pilot:
        await pilot.pause()
        table = pilot.app.screen.query_one(EventTable)
        assert table.row_count == 4
        # Select each row to render the detail pane — used to blow up on markup.
        table.focus()
        for _ in range(4):
            await pilot.press("down")
            await pilot.pause()
        # If we got here without MarkupError, markup=False on Static worked.

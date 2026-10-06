"""Build minimal .plaso-format SQLite files for tests.

Matches the schema and on-disk format used by plaso >= 20230327:
- metadata(key, value)
- event(_identifier, _event_data_identifier, timestamp, timestamp_desc)
- event_data(_identifier, _data)  -- _data is (optionally zlib-compressed) JSON

This is a deliberately minimal subset of plaso's actual schema; we only
include the tables our ingestor reads. See:
``docs/superpowers/specs/2026-05-14-plaso-ingest-design.md``.
"""
from __future__ import annotations

import sqlite3
import zlib
from pathlib import Path

import orjson


def make_plaso(
    path: Path,
    *,
    version: int = 20230327,
    serialization: str = "json",
    compression: str = "zlib",
    event_data: list[dict] | None = None,
    events: list[tuple[int, int, str]] | None = None,
) -> Path:
    """Write a minimal plaso-format SQLite file at ``path``.

    Parameters
    ----------
    version : int
        Value to write into ``metadata.format_version``.
    serialization : str
        Value to write into ``metadata.serialization_format``.
    compression : str
        ``"zlib"`` or ``"none"``; controls how ``event_data._data`` is encoded.
    event_data : list of dict
        Payload dicts. Each becomes one ``event_data`` row.
    events : list of (event_data_index, timestamp_usec, timestamp_desc)
        One ``event`` row per tuple. ``event_data_index`` is 1-based and points
        at the corresponding ``event_data._identifier``. Allows fan-out
        (multiple events per event_data row) by repeating the index.
    """
    event_data = event_data or []
    events = events or []
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE metadata (key TEXT, value TEXT);
            CREATE TABLE event (
                _identifier INTEGER PRIMARY KEY,
                _event_data_identifier TEXT,
                timestamp BIGINT,
                timestamp_desc TEXT
            );
            CREATE TABLE event_data (
                _identifier INTEGER PRIMARY KEY,
                _data BLOB
            );
            """
        )
        con.execute(
            "INSERT INTO metadata VALUES('format_version', ?)", (str(version),)
        )
        con.execute(
            "INSERT INTO metadata VALUES('serialization_format', ?)",
            (serialization,),
        )
        con.execute(
            "INSERT INTO metadata VALUES('compression_format', ?)",
            (compression,),
        )
        for i, payload in enumerate(event_data, start=1):
            blob = orjson.dumps(payload)
            if compression == "zlib":
                blob = zlib.compress(blob)
            con.execute(
                "INSERT INTO event_data VALUES(?, ?)", (i, blob)
            )
        for eid, (ed_idx, ts_usec, ts_desc) in enumerate(events, start=1):
            con.execute(
                "INSERT INTO event VALUES(?, ?, ?, ?)",
                (eid, f"event_data.{ed_idx}", ts_usec, ts_desc),
            )
        con.commit()
    finally:
        con.close()
    return path

import sqlite3

from chronoscope.core.extra import dump_extra
from chronoscope.core.schema import CURRENT_VERSION, migrate


def test_migrate_fresh_db_sets_version():
    con = sqlite3.connect(":memory:")
    migrate(con)
    cur = con.execute("SELECT version FROM schema_version")
    assert cur.fetchone()[0] == CURRENT_VERSION


def test_migrate_creates_tables():
    con = sqlite3.connect(":memory:")
    migrate(con)
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in rows}
    assert {"timeline", "event", "schema_version"} <= names


def test_migrate_is_idempotent():
    con = sqlite3.connect(":memory:")
    migrate(con)
    migrate(con)
    cur = con.execute("SELECT version FROM schema_version")
    assert cur.fetchone()[0] == CURRENT_VERSION


def test_event_table_has_unique_timeline_hash():
    con = sqlite3.connect(":memory:")
    migrate(con)
    con.execute("INSERT INTO timeline VALUES('t1','a','/x','jsonl','s1',0,'now',NULL)")
    con.execute(
        "INSERT INTO event(timeline_id,event_hash,ts_usec,ts_desc,data_type,parser,"
        "source_short,source_long,display_name,message,extra) "
        "VALUES('t1',x'01',1,'T','dt',NULL,NULL,NULL,NULL,'m',x'')"
    )
    # Inserting the same (timeline_id, event_hash) with INSERT OR IGNORE must not error.
    con.execute(
        "INSERT OR IGNORE INTO event(timeline_id,event_hash,ts_usec,ts_desc,data_type,parser,"
        "source_short,source_long,display_name,message,extra) "
        "VALUES('t1',x'01',1,'T','dt',NULL,NULL,NULL,NULL,'m',x'')"
    )
    count = con.execute("SELECT COUNT(*) FROM event").fetchone()[0]
    assert count == 1


def test_migrate_to_v2_creates_annotation_tables():
    con = sqlite3.connect(":memory:")
    migrate(con)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "annotation_tag" in tables
    assert "annotation_star" in tables
    assert "annotation_comment" in tables


def test_migrate_from_v1_upgrades_to_current():
    con = sqlite3.connect(":memory:")
    migrate(con)
    con.execute("UPDATE schema_version SET version = 1")
    con.commit()
    migrate(con)
    v = con.execute("SELECT version FROM schema_version").fetchone()[0]
    assert v == CURRENT_VERSION
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "annotation_tag" in tables


def test_migrate_is_idempotent_across_calls():
    con = sqlite3.connect(":memory:")
    migrate(con)
    migrate(con)
    migrate(con)
    v = con.execute("SELECT version FROM schema_version").fetchone()[0]
    assert v == CURRENT_VERSION


def test_migrate_v3_adds_extra_text_column_on_fresh_db():
    con = sqlite3.connect(":memory:")
    migrate(con)
    cols = {r[1] for r in con.execute("PRAGMA table_info(event)")}
    assert "extra_text" in cols


def test_migrate_v3_backfills_extra_text_from_existing_blobs():
    con = sqlite3.connect(":memory:")
    migrate(con)
    con.execute("INSERT INTO timeline VALUES('t1','a','/x','jsonl','s1',0,'now',NULL)")
    con.execute(
        "INSERT INTO event(timeline_id,event_hash,ts_usec,ts_desc,data_type,parser,"
        "source_short,source_long,display_name,message,extra,extra_text) "
        "VALUES('t1',?,1,'T','dt',NULL,NULL,NULL,NULL,'m',?,'')",
        (b"\x01", dump_extra({"url": "https://example.com/", "n": 7})),
    )
    con.execute("UPDATE schema_version SET version = 2")
    con.commit()

    migrate(con)

    text = con.execute(
        "SELECT extra_text FROM event WHERE event_hash=?", (b"\x01",)
    ).fetchone()[0]
    assert "https://example.com/" in text
    assert "url" in text
    assert "7" in text
    assert con.execute("SELECT version FROM schema_version").fetchone()[0] == CURRENT_VERSION


def test_migrate_v3_idempotent_does_not_overwrite_populated_text():
    con = sqlite3.connect(":memory:")
    migrate(con)
    con.execute("INSERT INTO timeline VALUES('t1','a','/x','jsonl','s1',0,'now',NULL)")
    con.execute(
        "INSERT INTO event(timeline_id,event_hash,ts_usec,ts_desc,data_type,parser,"
        "source_short,source_long,display_name,message,extra,extra_text) "
        "VALUES('t1',?,1,'T','dt',NULL,NULL,NULL,NULL,'m',?,?)",
        (b"\x02", dump_extra({"k": "v"}), "preexisting"),
    )
    con.commit()
    migrate(con)
    text = con.execute(
        "SELECT extra_text FROM event WHERE event_hash=?", (b"\x02",)
    ).fetchone()[0]
    assert text == "preexisting"


def test_annotation_tag_pk_dedupes():
    con = sqlite3.connect(":memory:")
    migrate(con)
    con.execute("INSERT INTO annotation_tag VALUES(x'01','a','now')")
    con.execute(
        "INSERT OR IGNORE INTO annotation_tag VALUES(x'01','a','now')"
    )
    assert con.execute("SELECT COUNT(*) FROM annotation_tag").fetchone()[0] == 1


def test_migrate_v4_creates_exhibit_table_on_fresh_db():
    con = sqlite3.connect(":memory:")
    migrate(con)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "exhibit" in tables
    cols = {r[1] for r in con.execute("PRAGMA table_info(exhibit)")}
    assert {"id", "title", "description", "body", "created_at", "updated_at"} <= cols


def test_migrate_from_v3_adds_exhibit_table_keeping_data():
    con = sqlite3.connect(":memory:")
    migrate(con)
    con.execute("INSERT INTO timeline VALUES('t1','a','/x','jsonl','s1',0,'now',NULL)")
    con.commit()
    con.execute("UPDATE schema_version SET version = 3")
    con.commit()
    migrate(con)
    assert con.execute("SELECT version FROM schema_version").fetchone()[0] == CURRENT_VERSION
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "exhibit" in tables
    cols = {r[1] for r in con.execute("PRAGMA table_info(exhibit)")}
    assert {"id", "title", "description", "body", "created_at", "updated_at"} <= cols
    assert con.execute("SELECT COUNT(*) FROM timeline").fetchone()[0] == 1

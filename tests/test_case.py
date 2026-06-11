import pytest

from chronoscope.core.case import (
    Case,
    CaseExistsError,
    CaseNotFoundError,
    init_case,
    open_case,
)


def test_init_case_creates_layout(case_dir):
    init_case(case_dir, name="acme")
    assert (case_dir / "case.toml").exists()
    assert (case_dir / "events.db").exists()
    assert (case_dir / "tmp").is_dir()


def test_init_case_refuses_non_empty(case_dir):
    (case_dir / "stuff.txt").write_text("x")
    with pytest.raises(CaseExistsError):
        init_case(case_dir, name="acme")


def test_open_case_returns_case_object(case_dir):
    init_case(case_dir, name="acme")
    with open_case(case_dir) as c:
        assert isinstance(c, Case)
        assert c.name == "acme"
        assert c.path == case_dir


def test_open_case_missing_raises(case_dir):
    with pytest.raises(CaseNotFoundError):
        with open_case(case_dir):
            pass

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_xdg_config(tmp_path, monkeypatch):
    """Point tool-wide config at a per-test tmp dir so a TUI test that ends up
    saving (e.g. via the color rules modal) never writes into the developer's
    real $HOME / $XDG_CONFIG_HOME."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def case_dir(tmp_path):
    d = tmp_path / "case"
    d.mkdir()
    return d

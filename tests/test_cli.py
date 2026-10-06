from __future__ import annotations

from typer.testing import CliRunner

from chronoscope.cli import app


def test_cli_help_exits_clean():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Chronoscope" in result.stdout

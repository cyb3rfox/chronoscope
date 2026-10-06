from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .tui.app import PlasoViewerApp

app = typer.Typer(
    add_completion=False,
    help="Chronoscope — TUI for Plaso forensic timelines",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    case: Optional[str] = typer.Argument(
        None, help="Optional path to a case directory. Omit to open the launcher."
    ),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    if case is not None:
        path = Path(case)
        if not (path / "case.toml").exists():
            typer.echo(
                f"Error: no case at {path}. Run `chronoscope` and use File → New case…",
                err=True,
            )
            raise typer.Exit(code=2)
        PlasoViewerApp(path).run()
        return
    PlasoViewerApp(None).run()

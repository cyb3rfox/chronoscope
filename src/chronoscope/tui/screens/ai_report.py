from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rich.markdown import Markdown
from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from ...ai.client import LLMClient
from ...ai.jobs.report import ReportContext, generate_report
from ...ai.settings import AISettings
from .ai_chat import _SpinnerLine


class AIReportScreen(ModalScreen[None]):
    """Generates a draft incident report from the case metadata + the
    analyst's tags/comments/stars. Streams the markdown into a Static and
    lets the user save it as a versioned ``report-<ts>.md`` in the case
    directory."""

    DEFAULT_CSS = """
    AIReportScreen { align: center middle; }
    AIReportScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 90%; height: 90%;
    }
    AIReportScreen #body-scroll {
        height: 1fr; border: solid $accent; padding: 0 1;
    }
    AIReportScreen #status { height: 1; color: $text-muted; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("ctrl+c", "close", "Close", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
    ]

    def __init__(
        self,
        *,
        client: LLMClient,
        settings: AISettings,
        context: ReportContext,
        case_path: Path,
    ) -> None:
        super().__init__()
        self._client = client
        self._settings = settings
        # NB: not ``self._context`` — that name shadows Textual's
        # ``MessagePump._context`` context-manager and breaks the screen.
        self._report_ctx = context
        self._case_path = case_path
        self._buffer: str = ""
        self._body: Static | None = None
        self._spinner: _SpinnerLine | None = None
        self._busy: bool = False
        self._done: bool = False
        self._saved_path: Path | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Draft report — {self._settings.model}")
            yield VerticalScroll(id="body-scroll")
            yield Static("idle", id="status")
            yield Static(
                "Ctrl+S: save  |  Esc: close  (saves to <case>/report-<ts>.md)"
            )

    async def on_mount(self) -> None:
        scroll = self.query_one("#body-scroll", VerticalScroll)
        if self._report_ctx.is_empty():
            scroll.mount(Static(
                "[bold red]No content to report on.[/bold red] "
                "Tag or comment events, or fill in case metadata (M), "
                "then try again.",
                markup=True,
            ))
            self.query_one("#status", Static).update("nothing to do")
            return
        self._spinner = _SpinnerLine("drafting…")
        scroll.mount(self._spinner)
        self._body = Static(classes="ai-body")
        scroll.mount(self._body)
        self._busy = True
        self.query_one("#status", Static).update("drafting…")
        # Run the streaming draft as a background task so on_mount doesn't
        # block the rest of Textual's mount pipeline.
        self.app.call_later(self._start_draft)

    def _start_draft(self) -> None:
        import asyncio
        asyncio.create_task(self._draft())

    async def _draft(self) -> None:
        try:
            self._buffer = await generate_report(
                client=self._client,
                settings=self._settings,
                context=self._report_ctx,
                on_text=self._on_text,
            )
        except Exception as e:
            self._on_error(str(e))
            return
        self._on_done()

    def _on_text(self, chunk: str) -> None:
        if self._spinner is not None:
            self._spinner.remove()
            self._spinner = None
        if self._body is None:
            return
        # The Static keeps growing as the model streams. Markdown re-parses
        # on every delta — acceptable for the typical report length.
        self._body.update(Markdown(self._buffer + chunk))
        # Keep our own running buffer because the Static doesn't expose it.
        self._buffer += chunk
        self.query_one("#body-scroll", VerticalScroll).scroll_end(animate=False)

    def _on_done(self) -> None:
        self._busy = False
        self._done = True
        self.query_one("#status", Static).update("ready — Ctrl+S to save")

    def _on_error(self, msg: str) -> None:
        self._busy = False
        if self._spinner is not None:
            self._spinner.remove()
            self._spinner = None
        scroll = self.query_one("#body-scroll", VerticalScroll)
        scroll.mount(Static(
            f"[bold red]error[/bold red] {escape(msg)}", markup=True,
        ))
        self.query_one("#status", Static).update("error")

    def action_close(self) -> None:
        if self._busy:
            return
        self.dismiss(None)

    def action_save(self) -> None:
        if not self._done or not self._buffer:
            self.app.notify(
                "Report isn't ready yet.", severity="warning", timeout=2,
            )
            return
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
        path = self._case_path / f"report-{ts}.md"
        path.write_text(self._buffer, encoding="utf-8")
        self._saved_path = path
        self.query_one("#status", Static).update(f"saved to {path.name}")
        self.app.notify(f"Saved {path.name}", severity="information", timeout=3)

    @property
    def saved_path(self) -> Path | None:
        return self._saved_path

    def _on_text_for_test(self, text: str) -> None:
        """Hook to drive the streaming path from tests without async."""
        self._on_text(text)

    def _finish_for_test(self) -> None:
        """Hook to mark the report ready from tests so save_action paths
        don't require running the worker against a real model."""
        self._on_done()

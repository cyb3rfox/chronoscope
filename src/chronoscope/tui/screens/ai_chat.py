from __future__ import annotations

from rich.markdown import Markdown
from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from ...ai.agent import AgentEvent, ChatAgent
from ...ai.settings import AISettings


SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class _SpinnerLine(Static):
    """A single inline transcript line that shows an animated braille spinner
    next to a short label ("thinking…" / "calling search_events…"). Drives
    its own animation via set_interval so it visibly moves while the agent
    is awaiting the model or executing a tool."""

    DEFAULT_CSS = """
    _SpinnerLine { color: $accent; height: 1; margin: 0 0 1 0; }
    """

    def __init__(self, label: str = "thinking…") -> None:
        super().__init__("", markup=True)
        self._frame = 0
        self._label = label

    def on_mount(self) -> None:
        self._render_frame()
        self.set_interval(0.08, self._tick)

    def set_label(self, label: str) -> None:
        self._label = label
        self._render_frame()

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
        self._render_frame()

    def _render_frame(self) -> None:
        self.update(
            f"[bold yellow]{SPINNER_FRAMES[self._frame]}[/bold yellow] "
            f"{escape(self._label)}"
        )


class AIChatScreen(ModalScreen[None]):
    """Modal chat with the configured AI provider. Renders user/assistant
    turns and tool calls as a stream of Static rows in a VerticalScroll, so
    the in-flight assistant message can be updated character-by-character as
    the model streams. An inline animated _SpinnerLine appears whenever the
    agent is awaiting the model or executing a tool, so the user always has
    visible feedback that something is happening."""

    DEFAULT_CSS = """
    AIChatScreen { align: center middle; }
    AIChatScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 90%; height: 90%;
    }
    AIChatScreen #transcript {
        height: 1fr;
        border: solid $accent;
        padding: 0 1;
    }
    AIChatScreen Input { margin: 1 0 0 0; }
    AIChatScreen .turn { margin: 0 0 1 0; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("ctrl+c", "close", "Close", priority=True),
    ]

    def __init__(self, agent: ChatAgent, settings: AISettings) -> None:
        super().__init__()
        self._agent = agent
        self._settings = settings
        # True while an agent turn is running in its worker. Guards against a
        # second submit and against closing the screen mid-turn.
        self._turn_active: bool = False
        # The Static currently receiving streaming text deltas, if any. None
        # between turns or while a tool call is in-flight.
        self._streaming_line: Static | None = None
        self._streaming_buffer: str = ""
        # The animated spinner line, mounted inline in the transcript while
        # waiting on the model or a tool. None when not visible.
        self._spinner_line: _SpinnerLine | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"AI chat — {self._settings.model}")
            yield VerticalScroll(id="transcript")
            yield Input(placeholder="ask about the case…", id="prompt")

    def on_mount(self) -> None:
        names = ", ".join(escape(n) for n in self._tool_names())
        self._mount_line(
            Static(f"[dim]Tools: {names}[/dim]", markup=True, classes="turn")
        )
        self._replay_history()
        self.query_one("#prompt", Input).focus()

    def _replay_history(self) -> None:
        """Render the prior conversation that the agent loaded from disk so
        the user can see the context it's working from. Skips the system
        message (it's an internal prompt, not chat content)."""
        for msg in self._agent.messages:
            if msg.role == "system":
                continue
            if msg.role == "user":
                self._mount_line(
                    Static(
                        f"[bold cyan]you[/bold cyan]  {escape(msg.content or '')}",
                        markup=True, classes="turn",
                    )
                )
            elif msg.role == "assistant":
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        self._mount_line(
                            Static(
                                f"[yellow]→ {escape(tc.name)}[/yellow] "
                                f"[dim]{escape(_truncate(tc.arguments, 200))}[/dim]",
                                markup=True, classes="turn",
                            )
                        )
                if msg.content:
                    self._mount_line(
                        Static("[bold magenta]ai[/bold magenta]", markup=True)
                    )
                    body = Static(classes="turn ai-body")
                    self._mount_line(body)
                    body.update(Markdown(msg.content))
            elif msg.role == "tool":
                self._mount_line(
                    Static(
                        f"[green]← {escape(msg.name or '')}[/green] "
                        f"[dim]{escape(_truncate(msg.content or '', 200))}[/dim]",
                        markup=True, classes="turn",
                    )
                )

    def _tool_names(self) -> list[str]:
        # Read-only peek; the agent owns the registry.
        return self._agent._registry.names()  # noqa: SLF001

    def _mount_line(self, widget: Static) -> None:
        scroll = self.query_one("#transcript", VerticalScroll)
        scroll.mount(widget)
        scroll.scroll_end(animate=False)

    def _show_spinner(self, label: str) -> None:
        if self._spinner_line is None:
            self._spinner_line = _SpinnerLine(label)
            self._mount_line(self._spinner_line)
        else:
            self._spinner_line.set_label(label)

    def _hide_spinner(self) -> None:
        if self._spinner_line is not None:
            self._spinner_line.remove()
            self._spinner_line = None

    def action_close(self) -> None:
        if self._turn_active:
            return
        self.dismiss(None)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._turn_active:
            return
        prompt = (event.value or "").strip()
        if not prompt:
            return
        event.input.value = ""
        # Run the turn in a worker — NOT awaited inline. Awaiting it here
        # would park the screen's message pump for the whole turn, so the
        # spinner couldn't animate and streamed text couldn't repaint until
        # the model was done.
        self._turn_active = True
        self.run_worker(
            self._send(prompt),
            name="chat-turn",
            group="chat-turn",
            exclusive=True,
            exit_on_error=False,
        )

    async def _send(self, prompt: str) -> None:
        try:
            await self._agent.send(prompt, on_event=self._on_event)
        finally:
            self._hide_spinner()
            self._streaming_line = None
            self._turn_active = False

    def _on_event(self, event: AgentEvent) -> None:
        if event.kind == "user":
            self._mount_line(
                Static(
                    f"[bold cyan]you[/bold cyan]  {escape(event.text)}",
                    markup=True, classes="turn",
                )
            )
        elif event.kind == "thinking":
            # Reset any in-flight assistant streaming state and show the
            # spinner — this fires before each LLM call.
            self._streaming_line = None
            self._streaming_buffer = ""
            self._show_spinner("thinking…")
        elif event.kind == "text_delta":
            self._hide_spinner()
            if self._streaming_line is None:
                self._mount_line(
                    Static("[bold magenta]ai[/bold magenta]", markup=True)
                )
                self._streaming_buffer = ""
                self._streaming_line = Static(classes="turn ai-body")
                self._mount_line(self._streaming_line)
            # Model output is markdown; render it through rich.markdown so
            # headings, bullets, fenced code, tables, bold/italic show
            # formatted instead of raw. Static.update() takes any Renderable,
            # so we swap the Markdown renderable on every delta.
            self._streaming_buffer += event.text
            self._streaming_line.update(Markdown(self._streaming_buffer))
            self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)
        elif event.kind == "tool_call":
            self._streaming_line = None
            self._hide_spinner()
            self._mount_line(
                Static(
                    f"[yellow]→ {escape(event.name)}[/yellow] "
                    f"[dim]{escape(_truncate(event.text, 200))}[/dim]",
                    markup=True, classes="turn",
                )
            )
            self._show_spinner(f"calling {event.name}…")
        elif event.kind == "tool_result":
            self._hide_spinner()
            self._mount_line(
                Static(
                    f"[green]← {escape(event.name)}[/green] "
                    f"[dim]{escape(_truncate(event.text, 200))}[/dim]",
                    markup=True, classes="turn",
                )
            )
            self._show_spinner("thinking…")
        elif event.kind == "assistant_complete":
            self._streaming_line = None
            self._hide_spinner()
        elif event.kind == "stop":
            self._hide_spinner()
        elif event.kind == "error":
            self._streaming_line = None
            self._hide_spinner()
            self._mount_line(
                Static(
                    f"[bold red]error[/bold red]  {escape(event.text)}",
                    markup=True, classes="turn",
                )
            )


def _truncate(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[: n - 1] + "…"

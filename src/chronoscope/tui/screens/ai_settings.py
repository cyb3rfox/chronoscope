from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Input, Label, Static

from ...ai.settings import AISettings


class AISettingsScreen(ModalScreen["AISettings | None"]):
    """Edit AI provider, model, key env var, and safety caps. Persists via
    save_ai_settings on the parent's apply callback."""

    DEFAULT_CSS = """
    AISettingsScreen { align: center middle; }
    AISettingsScreen > Vertical {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 70; height: auto;
    }
    AISettingsScreen Input { margin: 0 0 1 0; }
    AISettingsScreen Checkbox { margin: 0 0 1 0; }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    def __init__(self, settings: AISettings) -> None:
        super().__init__()
        self._settings = settings

    def compose(self) -> ComposeResult:
        s = self._settings
        with Vertical():
            yield Label("AI settings")
            yield Checkbox("Enabled", value=s.enabled, id="enabled")
            yield Label("Base URL (OpenAI-compatible):")
            yield Input(value=s.base_url, id="base_url")
            yield Label("Model:")
            yield Input(value=s.model, id="model")
            yield Label("API key environment variable:")
            yield Input(value=s.api_key_env, id="api_key_env")
            yield Label("Max tool iterations per turn:")
            yield Input(value=str(s.max_tool_iterations), id="max_iters")
            yield Label("Max results per tool call:")
            yield Input(value=str(s.max_results_per_call), id="max_results")
            yield Static("", id="error")
            yield Static("Ctrl+S: save  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#base_url", Input).focus()

    def action_save(self) -> None:
        try:
            new = self._settings.with_changes(
                enabled=self.query_one("#enabled", Checkbox).value,
                base_url=self.query_one("#base_url", Input).value.strip()
                or self._settings.base_url,
                model=self.query_one("#model", Input).value.strip()
                or self._settings.model,
                api_key_env=self.query_one("#api_key_env", Input).value.strip()
                or self._settings.api_key_env,
                max_tool_iterations=int(self.query_one("#max_iters", Input).value),
                max_results_per_call=int(self.query_one("#max_results", Input).value),
            )
        except ValueError as e:
            self.query_one("#error", Static).update(f"invalid: {e}")
            return
        if new.max_tool_iterations < 1 or new.max_results_per_call < 1:
            self.query_one("#error", Static).update("limits must be ≥ 1")
            return
        self.dismiss(new)

    def action_cancel(self) -> None:
        self.dismiss(None)

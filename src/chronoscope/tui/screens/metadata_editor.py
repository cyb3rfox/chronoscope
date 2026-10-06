from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static, TextArea

from ...core.metadata import CaseMetadata


class MetadataEditorScreen(ModalScreen["CaseMetadata | None"]):
    """Edit the case's investigator-curated metadata. Headline scalars get
    Input widgets; the three indicator lists each get a TextArea where one
    line equals one entry — fast for paste-ins from existing notes."""

    DEFAULT_CSS = """
    MetadataEditorScreen { align: center middle; }
    MetadataEditorScreen > VerticalScroll {
        background: $panel; border: solid $primary; padding: 1 2;
        width: 90%; height: 90%;
    }
    MetadataEditorScreen Input { margin: 0 0 1 0; }
    MetadataEditorScreen TextArea { height: 5; margin: 0 0 1 0; }
    MetadataEditorScreen #notes { height: 6; }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    def __init__(self, metadata: CaseMetadata) -> None:
        super().__init__()
        self._initial = metadata

    def compose(self) -> ComposeResult:
        m = self._initial
        with VerticalScroll():
            yield Label("Case metadata")
            yield Label("Company / org:")
            yield Input(value=m.company, id="company")
            yield Label("Incident summary (one-liner):")
            yield Input(value=m.incident, id="incident")
            yield Label("Incident started (free-form, e.g. 2024-03-12 ~02:00 UTC):")
            yield Input(value=m.incident_started, id="incident_started")
            yield Label("Incident discovered:")
            yield Input(value=m.incident_discovered, id="incident_discovered")
            yield Label("Compromised accounts (one per line):")
            yield TextArea(
                "\n".join(m.compromised_accounts), id="compromised_accounts"
            )
            yield Label("Compromised machines (one per line):")
            yield TextArea(
                "\n".join(m.compromised_machines), id="compromised_machines"
            )
            yield Label("Known IOCs (one per line):")
            yield TextArea("\n".join(m.known_iocs), id="known_iocs")
            yield Label("Notes (free-form):")
            yield TextArea(m.notes, id="notes")
            yield Static("", id="error")
            yield Static("Ctrl+S: save  |  Esc: cancel")

    def on_mount(self) -> None:
        self.query_one("#company", Input).focus()

    def action_save(self) -> None:
        try:
            new = CaseMetadata(
                company=self.query_one("#company", Input).value,
                incident=self.query_one("#incident", Input).value,
                incident_started=self.query_one("#incident_started", Input).value,
                incident_discovered=self.query_one("#incident_discovered", Input).value,
                notes=self.query_one("#notes", TextArea).text,
            )
            for cat in ("compromised_accounts", "compromised_machines", "known_iocs"):
                lines = self.query_one(f"#{cat}", TextArea).text.splitlines()
                new = new.with_list(cat, lines)
        except ValueError as e:  # pragma: no cover - defensive
            self.query_one("#error", Static).update(f"invalid: {e}")
            return
        self.dismiss(new)

    def action_cancel(self) -> None:
        self.dismiss(None)

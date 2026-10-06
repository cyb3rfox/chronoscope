# Chronoscope

A terminal UI for working through [Plaso](https://plaso.readthedocs.io/) super-timelines without leaving the keyboard.

Chronoscope ingests forensic timeline data into a local, SQLite-backed **case**, then lets you scroll, filter, bracket by time, annotate, color, and reason over millions of events from a fast [Textual](https://textual.textualize.io/) TUI. An optional, bring-your-own-key AI assistant can read the case — and persist confirmed findings — through a sandboxed tool interface.

---

## Contents

- [What is a timeline?](#what-is-a-timeline)
- [Creating a timeline with Plaso](#creating-a-timeline-with-plaso)
- [Install](#install)
- [Quick start](#quick-start)
- [Working with the program](#working-with-the-program)
  - [Cases](#cases)
  - [Adding timelines](#adding-timelines)
  - [The event table](#the-event-table)
  - [Filtering, sorting, and time brackets](#filtering-sorting-and-time-brackets)
  - [Annotations](#annotations)
  - [Color rules](#color-rules)
  - [Overview and navigation](#overview-and-navigation)
  - [Exhibits](#exhibits)
  - [Case metadata](#case-metadata)
  - [Exporting](#exporting)
- [Configuring the AI assistant](#configuring-the-ai-assistant)
- [Menu reference](#menu-reference)
- [Key bindings](#key-bindings)
- [Case layout on disk](#case-layout-on-disk)
- [Development](#development)
- [Status & license](#status--license)

---

## What is a timeline?

In digital forensics, a **timeline** is a single, time-ordered stream of everything that happened on a system, merged from every artifact that records time. A modern computer scatters timestamps across hundreds of places: filesystem MFT records, EVTX event logs, registry hive key-write times, browser history, prefetch, shellbags, link files, scheduled tasks, log files, and more. Each of these uses a different format and lives in a different place.

A **super-timeline** normalizes all of them into one sequence of events. Each event is roughly:

> *at this UTC instant, this kind of thing happened, described like this, sourced from this artifact.*

Plaso (the engine behind `log2timeline`) is the standard tool for building super-timelines. It parses a disk image, mounted volume, or loose set of files, and emits millions of `(timestamp, timestamp_description, data_type, message, …)` records. Because everything is on one clock, you can read an incident as a story — "the phishing attachment opened at 14:02, a child process spawned at 14:02:11, an outbound connection at 14:03, a new service installed at 14:05" — instead of pivoting between a dozen tools.

The catch is **volume**. A single workstation easily produces 5–50 million events. That is far too much to read top-to-bottom; the analyst's job is to *filter down* to the handful of events that matter and *annotate* them so the narrative survives. That filter-and-annotate loop is exactly what Chronoscope is built for. Chronoscope does **not** parse disk images — Plaso does that. Chronoscope consumes Plaso's output and gives you a fast, keyboard-driven workbench on top of it.

A Chronoscope **event** carries:

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC instant (microsecond precision internally) |
| `timestamp_desc` | what the time means — `Creation Time`, `Last Written`, `Program Execution`, … |
| `data_type` | the artifact class — `windows:evtx:record`, `fs:stat`, `windows:registry:key`, … |
| `source` / `display_name` | where it came from |
| `message` | the human-readable rendering of the event |
| everything else | the full parser payload, kept verbatim and viewable in the detail pane |

---

## Creating a timeline with Plaso

Chronoscope reads what Plaso produces. You run Plaso yourself (it is heavyweight and image-specific); Chronoscope ingests the result. There are two stages, and Plaso's two binaries map onto them:

1. **`log2timeline.py`** parses your evidence and writes a **Plaso storage container** — a `.plaso` file. This is an internal SQLite database of raw, *un-rendered* events.
2. **`psort.py`** post-processes that container: it sorts, optionally filters, and — crucially — runs the per-artifact **formatters** that turn raw fields into readable `message` strings. It can write CSV, JSON Line, and other formats.

### Step 1 — build the storage container

```bash
# Parse a disk image (or a mounted dir, a single file, a device…) into a .plaso container.
log2timeline.py --storage-file case.plaso /evidence/disk.E01
```

This is the slow step (minutes to hours). The output `case.plaso` is the "Plaso container" — a complete, raw record of every timestamped artifact found.

### Step 2 — render to JSONL (recommended)

```bash
# Produce a fully-rendered JSON Line timeline that Chronoscope ingests.
psort.py -o json_line -w timeline.jsonl case.plaso
```

`json_line` writes one JSON object per line. Because `psort` ran the formatters, every event has a populated `message` field. **This is the recommended input** — it is the richest, and ingest is a tolerant line-by-line stream (malformed lines are skipped and counted, so a truncated export still loads).

You can also let `psort` pre-filter to shrink the file before it ever reaches Chronoscope, e.g. a date window:

```bash
psort.py -o json_line -w timeline.jsonl case.plaso \
  "date > '2026-05-01 00:00:00' AND date < '2026-05-08 00:00:00'"
```

### Ingesting the `.plaso` container directly

Chronoscope can also read a modern `.plaso` storage file **directly**, skipping the JSONL export:

```text
Add timeline… → point at case.plaso
```

Be aware of the trade-off, because of how Plaso works: **the `.plaso` container does not store rendered `message` strings** — those are generated by `psort`'s formatter plugins. When you ingest a `.plaso` directly, Chronoscope synthesizes a best-effort message from the most informative raw field (`display_name`, `filename`, `query`, …), but it will never match the richness of a `psort` rendering. **For the best timeline, export to JSONL with `psort` and ingest that.**

Direct `.plaso` ingest also requires a **modern** container: plaso **format version ≥ 20230327** with the `json` serializer (the standard since the early-2023 releases). Older `.plaso` files use a legacy ZIP-of-pickles format Chronoscope can't read — convert them first:

```bash
psort.py -o json_line -w timeline.jsonl legacy.plaso
```

### Which format am I looking at?

Chronoscope auto-detects on the first 16 bytes of the file — a SQLite magic header means a `.plaso` store, a leading `{` means JSONL — so you just point "Add timeline…" at the file and it does the right thing.

| Input | Produce with | Message quality | Notes |
| --- | --- | --- | --- |
| **Plaso JSONL** (recommended) | `psort.py -o json_line -w timeline.jsonl case.plaso` | Full (formatter-rendered) | Streamed, malformed-line tolerant |
| **Plaso storage `.plaso`** | `log2timeline.py --storage-file case.plaso <evidence>` | Synthesized fallback | Needs format version ≥ 20230327, `json` serializer |

> The optional `plaso` install extra (below) only matters if you want to run Plaso *from the same virtualenv*. Chronoscope never invokes `log2timeline`/`psort` for you — it consumes their output.

---

## Install

Requires **Python 3.11+**.

```bash
git clone <this repo>
cd chronoscope
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the `chronoscope` console script into `.venv/bin/`. Either keep the venv activated, call the binary directly (`./.venv/bin/chronoscope …`), or alias it in your shell rc:

```bash
alias chronoscope="$HOME/dev/chronoscope/.venv/bin/chronoscope"
```

The `plaso` extra (`pip install -e ".[plaso,dev]"`) is optional — only needed to drive Plaso itself from the same environment.

> **Moved the project after installing?** The venv's script shebangs still point at the old path and you'll get `bad interpreter: … no such file or directory`. Recreate the venv: `rm -rf .venv && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`.

---

## Quick start

```bash
# 1. Build a rendered timeline with Plaso (outside Chronoscope)
log2timeline.py --storage-file case.plaso /evidence/disk.E01
psort.py -o json_line -w timeline.jsonl case.plaso

# 2. Launch Chronoscope
chronoscope

# 3. In the launcher: press N → "New case…", give it a name and a target directory
# 4. Inside the case: Alt+T → "Add timeline…" → point at timeline.jsonl (or case.plaso)
# 5. Work the table; press ? at any time for the full keybinding overview
```

`chronoscope <case-path>` opens an existing case directly and skips the launcher.

---

## Working with the program

### Cases

A **case** is a self-contained directory — the unit you open, share, and archive. It holds a `case.toml` manifest, an `events.db` SQLite store (timelines, events, annotations, metadata, color rules, exhibits), and a `tmp/` scratch dir. Create one with **File → New case…** (`N` in the launcher), open one with **File → Open case…**. The launcher remembers recent cases. A case can hold many timelines.

### Adding timelines

**Alt+T → Add timeline…**, then point at a `timeline.jsonl` or a `.plaso` file. Ingest:

- streams the file in 10k-row batches with a progress display,
- deduplicates by source SHA-256 (re-adding the same file is a no-op),
- computes a stable, content-derived `event_hash` (blake3) per event, so **annotations bind to event content, not row numbers — they survive re-ingestion**.

Add several timelines to one case (e.g. multiple hosts) and view them merged or one at a time, each with its own color. **Timeline → List timelines** (`L`) shows them; **Remove timeline…** deletes one and its events.

### The event table

The main screen is a virtualized table over the whole (filtered) event set — it scrolls smoothly across millions of rows. Move with arrows / `PageUp`/`PageDown`; a colored gutter shows each row's source timeline. Press `d` to toggle the **detail pane**, which shows the full parser payload for the cursor event (`w` cycles its width). Annotation state (★, tags, 💬) renders inline.

### Filtering, sorting, and time brackets

Press `f` for the **filter / sort editor**. You can constrain by:

- **timeline**, **data type**, **source**
- **free text** match on the message
- **tag** and **star** state
- a **time bracket** — an explicit `[start, end]` window

The time bracket has fast keyboard control, since scoping to a window is the most common move:

| Key | Action |
| --- | --- |
| `[` / `]` | Set bracket start / end **from the cursor row** |
| `b` then `o` | Open the bracket editor |
| `b` then `c` | Clear the bracket |
| `b` then `{` / `}` | Contract / expand the window by ±1 minute |
| `b` then `=` | Recenter the window on the cursor |
| `b` then `z` | Zoom to ±50 events around the cursor |

`b` is a **prefix chord** — press it and a which-key overlay shows the follow-ups. `X` clears all filters. Filtering runs asynchronously with a loading indicator so the UI never blocks.

### Annotations

Annotations are how findings persist. On the cursor event:

| Key | Action |
| --- | --- |
| `s` | Toggle **star** |
| `t` / `u` | Add / remove a **tag** |
| `c` | Add a threaded **comment** |
| `e` / `D` | Edit / delete the latest comment |
| `T` | Open the **tag manager** |

**Visual mode** applies annotations in bulk: press `V` to start a selection, extend it with `Shift+↑/↓` (or `Shift+PageUp/PageDown`), then star/tag the whole range at once. `Space` toggles a sticky selection, `Escape` cancels.

### Color rules

**Case → Color rules…** (`C`) opens a rule editor. Rules highlight matching rows so important activity jumps out — color all `EVTX` records, off-hours activity, a specific suspect username, a `data_type`, etc. Rules are saved with the case.

### Overview and navigation

- **`O` — Overview**: hour/day histograms of event volume, to spot bursts of activity.
- **`g` — Jump**: type a timestamp and jump the cursor there.
- **`L` — Timeline panel**: list / side-by-side view of the case's timelines.

### Exhibits

Some evidence isn't a timeline event — a recovered script, a config file dump, a snippet of malware, a chat transcript. Attach these as **exhibits**: **Case → Add exhibit…** stores a titled block of text in the case. **List exhibits** / **Remove exhibit…** manage them. Exhibits are referenced by title in the AI draft report (and appended verbatim in an *Exhibits* section), and the AI chat can read them as context.

### Case metadata

**Case → Metadata…** (`M`) stores structured case facts: company / incident description, IOCs, known-compromised hosts/accounts, and similar lists. This metadata is surfaced to the AI assistant as a briefing at the start of each chat session, so the model has the case context without you re-typing it.

### Exporting

- **Case → Export annotations…** writes your starred / tagged / commented events to JSON — the curated findings, not the whole timeline.
- **Case → Export filtered to CSV…** writes the **current filtered view** to CSV — whatever your filters and time bracket currently show — for handing to another tool or a report.

---

## Configuring the AI assistant

The assistant is **opt-in** and **bring-your-own-key**. It defaults to a [DeepSeek](https://platform.deepseek.com/)-compatible endpoint, but anything speaking the **OpenAI chat-completions API** works (OpenAI, DeepSeek, a local Ollama / llama.cpp / vLLM gateway, an Azure / OpenRouter proxy, …).

### Set it up

Open **AI → Settings…** (`A`) and configure:

| Setting | Default | Meaning |
| --- | --- | --- |
| **Enabled** | off | Master switch — chat / report are inert until this is on |
| **Base URL** | `https://api.deepseek.com` | The OpenAI-compatible endpoint |
| **Model** | `deepseek-chat` | Model id to call |
| **API-key env var** | `DEEPSEEK_API_KEY` | **Name** of the environment variable holding your key |
| **Max tool iterations** | `12` | How many tool-call rounds the agent may take per turn |
| **Max results per call** | `200` | Cap on rows any single tool returns to the model |

### About the API key

Chronoscope **never stores your API key**. The settings file records only the *name* of an environment variable; the key itself is read from that variable at call time. So you export it in your shell:

```bash
export DEEPSEEK_API_KEY="sk-…"      # or whatever you named the var
```

Point the assistant at a different provider by changing **Base URL**, **Model**, and **API-key env var** together — e.g. `https://api.openai.com/v1` + `gpt-4o` + `OPENAI_API_KEY`. If the named variable is unset, the chat shows a clear "not configured" message instead of failing mid-call.

Settings persist to **`~/.config/chronoscope/config.toml`** (honoring `XDG_CONFIG_HOME`) under an `[ai]` table — the same file holds your color-rule config.

### What the assistant can do

The agent runs a tool loop over **your local case** — it does not get raw file access, only a defined toolset:

- **Read:** `search_events`, `get_event`, `count_events`, `histogram`, `list_timelines`, `list_tags`, `case_overview`, `read_case_metadata`, `list_exhibits`, `get_exhibit`
- **Drive the UI:** `apply_filters`, `clear_filters` — the model can set up a view for you
- **Persist findings:** `tag_event`, `untag_event`, `add_event_comment`, `set_case_metadata_field`, `add_metadata_entry`, `remove_metadata_entry` — so confirmed conclusions are saved as real annotations / metadata, surviving the session

It is instructed to cite events by id and to never invent data — see `src/chronoscope/ai/agent.py` for the full system prompt.

- **`a` — Chat**: an embedded conversation pane. The model is briefed with the case metadata, then answers questions and investigates using the tools above.
- **`R` — Draft report**: a one-shot generator over the **current filter / time bracket**. It sends your tagged / commented events (and confirms first), then produces a saveable Markdown draft that weaves in your annotations and references exhibits.

---

## Menu reference

Inside a case the top menubar is always visible. Open a menu with `Alt+F` / `Alt+C` / `Alt+T` / `Alt+A` / `Alt+H` (or click it).

| Menu | Items |
| --- | --- |
| **File** | New case… · Open case… · Close case · Quit |
| **Case** | Metadata… (`M`) · Color rules… (`C`) · Export annotations… · Export filtered to CSV… · Add exhibit… · List exhibits · Remove exhibit… |
| **Timeline** | Add timeline… · List timelines (`L`) · Remove timeline… |
| **AI** | Chat (`a`) · Draft report (`R`) · Settings… (`A`) |
| **Help** | Keybindings (`?`) · About |

---

## Key bindings

Press `?` for the grouped, searchable overview; prefix chords (like `b…`) pop a which-key overlay. The essentials:

| Key | Action |
| --- | --- |
| `f` / `X` | Open filter / sort editor · clear filters |
| `g` | Jump to timestamp |
| `d` / `w` | Toggle detail pane · cycle its width |
| `[` / `]` | Set time-bracket start / end from cursor |
| `b…` | Time-bracket prefix (open editor, clear, expand, contract, recenter, zoom) |
| `s` / `t` / `u` / `c` | Star · add tag · remove tag · add comment |
| `e` / `D` / `T` | Edit comment · delete comment · tag manager |
| `V`, `Shift+↑/↓` | Visual selection for bulk annotation |
| `L` / `O` | Timeline panel · Overview |
| `C` | Color rules editor |
| `a` / `A` | AI chat · AI settings |
| `M` / `R` | Case metadata · draft AI report |
| `F2` / `Shift+F2` | Cycle the footer's binding group |
| `?` / `q` | Help · quit |

---

## Case layout on disk

```
mycase/
  case.toml         # manifest: name, schema version, timeline order, created-at
  events.db         # SQLite: timeline, event, annotation_*, metadata, color_rule, exhibit, …
  tmp/              # scratch space used during ingest
```

The schema is versioned and migrated automatically on open. `event_hash` is content-derived (blake3), so annotations bind to events rather than row ids and survive re-ingestion of the same source.

---

## Development

```bash
pip install -e ".[dev]"
pytest                  # ingest, query, TUI, annotations, AI tools, …
ruff check src tests
```

The codebase is organized by concern:

```
src/chronoscope/
  cli.py            # typer entrypoint
  core/             # case, schema, events, metadata, exhibits
  ingest/           # format detection, JSONL pipeline, direct .plaso reader
  query/            # filter state + SQL builder + CSV export
  annotations/      # stars, tags, comments, bulk ops, export
  coloring/         # rule model + render + config
  report/           # overview / report data shaping
  ai/               # OpenAI-compatible client, tools, agent loop, settings, jobs
  tui/              # textual app, screens, widgets, key bindings
```

---

## Status & license

`0.0.1` — pre-release. The on-disk schema is versioned and migrated, but there are no cross-release compatibility guarantees yet. Bug reports and PRs welcome.

License: **TBD.**

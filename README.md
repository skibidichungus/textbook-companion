# Textbook Companion

A personal CLI reading companion for coding textbooks. Point it at any
textbook PDF, and it extracts chapters, generates summaries, then lets you
ask grounded questions, jot notes, and track your progress as you read.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for dependency management
- An Anthropic API key (`sk-ant-...`) with credits

## Install

From the repo root:

```
uv sync --all-extras
```

This creates `.venv/` and installs `pydantic`, `anthropic`, `pymupdf`,
`pytest`, and `mypy`.

## Ingest a textbook

Before using the companion, ingest a PDF to extract chapters and generate
metadata:

```
uv run python -m textbook_companion.ingest path/to/textbook.pdf
```

This creates a `data/<book_id>/` directory with chapter text files, LLM
summaries, and session state. The book ID is derived from the PDF filename.

Chapter detection uses a layered strategy:

1. **PDF TOC bookmarks** — reads the PDF's embedded table of contents. Most
   reliable; works even when chapter headers are graphical/decorative.
2. **Section-numbering heuristic** — detects N.1 restarts (e.g. "1.1",
   "2.1"). Catches textbooks with decorative chapter headers but standard
   section numbers.
3. **Keyword regex** — matches "Chapter N" / "Part N" in extracted text.
   Fallback for simpler PDFs.

If multiple books are ingested, the companion auto-detects them at startup
and lets you pick which one to study.

## Set your API key

Add it to your shell profile so you don't paste it into terminals where it
might leak:

```
echo 'export ANTHROPIC_API_KEY=sk-ant-your-key' >> ~/.zshrc
source ~/.zshrc
```

## Run

```
uv run textbook-companion
```

You'll see a greeting with where you left off, then a `>` prompt. Type
`quit` or `exit` to leave — your progress is saved after every
state-changing command, so restarting always picks up where you stopped.

## Commands

| Command | LLM? | What it does |
|---|:---:|---|
| `starting ch<N>` | no | Set chapter N as active. Confirms before abandoning an incomplete chapter; prints a refresher for prerequisites completed >3 days ago. |
| `done ch<N>` | no | Mark chapter N as complete with a timestamp. |
| `ask <question>` | yes | Send a question grounded in your active chapter's full text. Answer printed immediately; logged to the reading log. |
| `note <text>` | no | Log a free-form note attached to the active chapter. |
| `status` | no | Current chapter, in-progress chapters, completed chapters. |
| `quit` / `exit` | no | Leave. |

Commands are matched by prefix; chapter numbers can be `ch5` or `ch05`,
case-insensitive. Any unrecognized input prints `Unknown command: ...` and
returns to the prompt.

## What persists

Everything lives under `data/<book_id>/`:

```
book_overview.json       book metadata (generated during ingestion)
chapters/ch01.json …     per-chapter LLM summary
chapters/ch01.txt …      per-chapter raw extracted text (source of truth)
session_state.json       your current chapter, in-progress set,
                         completed set — atomic writes
reading_log.jsonl        append-only log of every question, answer, and note
```

You can re-ingest a PDF at any time to regenerate the metadata. Your
session state and reading log are separate and won't be overwritten.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Auth for the Anthropic SDK. |
| `TC_DEBUG` | *(unset)* | Set to any value to re-enable the LLM cache-threshold warning on stderr. |

## Testing

```
uv run pytest                # 140 tests, offline
uv run pytest -m live        # 3 smoke tests that hit the real API
```

The live tests require `ANTHROPIC_API_KEY` to be set; they skip silently
otherwise.

## Project layout

```
src/textbook_companion/
├── __init__.py
├── __main__.py      package entry point
├── commands.py      pure CLI parser → frozen dataclasses
├── fixtures.py      hand-authored Gaddis fixtures (Phase 1 legacy)
├── ingest.py        PDF extraction, chapter splitting, LLM metadata gen
├── llm.py           LLMClient protocol + ClaudeClient (only import site
│                    for `anthropic`)
├── models.py        Pydantic data models
├── session.py       CLI loop; state mutations; LLM orchestration
├── storage.py       atomic JSON writes + JSONL append helpers
└── prompts/
    ├── session_system.txt
    ├── ingest_book_overview.txt
    └── ingest_chapter_summary.txt
```

Swapping the LLM backend (e.g. a local Ollama model) is a matter of writing
a second class implementing `LLMClient`.

## Status

Phase 2 is feature-complete. The tool ingests any textbook PDF, extracts
chapters via a layered detection strategy (TOC bookmarks → section numbering
→ regex), generates per-chapter summaries, and provides a grounded reading
companion. Tested across 7 textbooks covering C++, Python, C, operating
systems, databases, software testing, and statistics.

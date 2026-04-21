# Textbook Companion

A personal CLI reading companion for coding textbooks. You read chapters in a
PDF viewer or on paper; this tool helps you recall, connect, and retain what
you read across chapters — and lets you ask grounded questions or jot notes as
you go.

**This is Phase 1.** The book content is hand-authored fixture data for
*Starting Out with Python* (Gaddis, 6e). Real PDF ingestion is Phase 2. The
tool is not a general Q&A chatbot — every question is answered in the context
of your active chapter, every note is attached to a chapter, and every quiz
answer is evaluated against that chapter's material.

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for dependency management
- An Anthropic API key (`sk-ant-...`) with credits

## Install

From the repo root:

```
uv sync --all-extras
```

This creates `.venv/` and installs `pydantic`, `anthropic`, `pytest`, and
`mypy`.

## First-time setup

1. Generate the fixture book data (writes to `./data/gaddis_python_6e/`):

   ```
   uv run python -m textbook_companion.fixtures
   ```

2. Set your API key. Easiest way is to add it to your shell profile so you
   don't paste it into terminals where it might leak:

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

Everything the companion understands:

| Command | LLM? | What it does |
|---|:---:|---|
| `starting ch<N>` | no | Set chapter N as active. Confirms before abandoning an incomplete chapter; prints a refresher for prerequisites completed >3 days ago. |
| `done ch<N>` | yes | End-of-chapter flow: Claude writes a recap, asks 2–3 quiz questions, gives tutor-style feedback on each answer, then asks for reflections. Marks the chapter complete. |
| `ask <question>` | yes | Send a question to Claude grounded in your active chapter. Answer printed immediately; logged to the reading log. |
| `note <text>` | no | Log a free-form note attached to the active chapter. |
| `attempting <label>` | no | Log a problem attempt. Detects when the label belongs to a different chapter (e.g. `1.1` while reading ch2) and asks whether to reroute. |
| `struggling with <term>` | no | Flag a concept you're stuck on; attaches to the current chapter. |
| `what was ch<N> about` | no | Print the chapter's one-liner + overview. |
| `recap ch<N>` | no | Print the chapter's overview, key concepts, and worked-example labels. |
| `concept <term>` | no | Look up a term in the concept graph: definition, where it was introduced, where it gets reused. |
| `status` | no | Current chapter, in-progress chapters with timestamps, completed chapters, active struggle flags. |
| `quit` / `exit` | no | Leave. |

Commands are matched by prefix; chapter numbers can be `ch5` or `ch05`,
case-insensitive. Any unrecognized input prints `Unknown command: ...` and
returns to the prompt.

## What persists

Everything lives under `data/gaddis_python_6e/`:

```
book_overview.json       immutable book metadata (from fixtures)
chapters/ch01.json …     one file per chapter (from fixtures)
concept_graph.json       cross-chapter concept reuse (from fixtures)
session_state.json       your current chapter, in-progress set,
                         completed set, struggle flags — atomic writes
reading_log.jsonl        append-only log of every quiz answer,
                         reflection, question, note, problem attempt,
                         struggle flag
```

The fixture files (first three) can be regenerated at any time with
`python -m textbook_companion.fixtures`. Your state + log are yours — don't
let the fixtures command overwrite them if you want to keep history.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Auth for the Anthropic SDK. |
| `TC_DEBUG` | *(unset)* | Set to any value to re-enable the LLM cache-threshold warning on stderr. Silenced by default to keep the interactive loop clean. |

## Testing

```
uv run pytest                # 101 tests, offline
uv run pytest -m live        # 2 smoke tests that hit the real API
```

The live tests require `ANTHROPIC_API_KEY` to be set; they skip silently
otherwise. See [WALKTHROUGH.md](WALKTHROUGH.md) for a realistic session.

## Project layout

```
src/textbook_companion/
├── __init__.py
├── commands.py      pure CLI parser → frozen dataclasses
├── fixtures.py      hand-authored Gaddis fixtures + data writer
├── llm.py           LLMClient protocol + ClaudeClient (only import site
│                    for `anthropic`)
├── models.py        Pydantic data models
├── session.py       CLI loop; state mutations; LLM orchestration
├── storage.py       atomic JSON writes + JSONL append helpers
└── prompts/
    ├── session_system.txt
    ├── chapter_recap.txt
    ├── end_of_chapter_quiz.txt
    └── quiz_feedback.txt
```

Swapping the LLM backend (e.g. a local Ollama model) is a matter of writing
a second class implementing `LLMClient`.

## Status

Phase 1 is feature-complete. See `textbook_companion_handoff.md` for the
original spec and milestone-by-milestone history (M1 through M4.9 + M5).

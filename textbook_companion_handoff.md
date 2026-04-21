# Textbook Companion — Phase 1 Handoff

You're building Phase 1 of a personal CLI tool: a reading companion for coding textbooks. I read chapters in a PDF viewer or on paper; the app helps me recall, connect, and retain what I read across chapters. It's a companion that remembers what I've read and surfaces it back at the right time — and it also lets me type in ad-hoc questions or notes that come up while reading. Questions are answered in the context of the active chapter (not generic programming help); notes get logged so I can revisit them later.

Phase 1 uses fake fixture data only. No PDF ingestion.

## Working agreement (read this first)

Ship in five milestones. After each, **stop and report**: what you built, the key decisions you made, and anything you'd flag for review. Do not start the next milestone until I confirm. I'd rather catch design drift early than rebuild later.

If you hit a fork that isn't specified, pick the simpler option, do it, and surface the choice in your milestone report. Don't block on trivia. Block on real ambiguity.

This is a personal tool, not a library. Small testable functions over clever abstractions. Type hints on everything. Don't add features I didn't ask for.

## Stack (locked unless you have a strong reason)

- Python 3.11+, `uv` for deps, `pyproject.toml`
- `anthropic` SDK. **Verify the current model string before coding** — check `https://docs.claude.com/en/docs/about-claude/models` and use the latest Opus. Don't trust any model string quoted from memory in this prompt.
- `pydantic` v2 for data models. The `structured()` LLM call needs JSON schemas, and Pydantic gives them for free; mixing dataclasses and BaseModels creates two parallel serialization paths.
- `pytest` for tests
- Plain stdin/stdout CLI — no `rich`, `textual`, or TUI
- Storage: JSON for structured data, JSONL for append-only logs. No SQLite, no ChromaDB, no vector search.
- Prompt caching enabled on system prompt + active chapter summary

## Project layout

```
textbook_companion/
├── books/                          # source PDFs (empty in phase 1)
├── data/
│   └── gaddis_python_6e/
│       ├── book_overview.json
│       ├── chapters/ch01.json … ch15.json
│       ├── concept_graph.json
│       ├── reading_log.jsonl       # append-only
│       └── session_state.json
├── src/textbook_companion/
│   ├── __init__.py
│   ├── models.py                   # pydantic models
│   ├── llm.py                      # LLMClient protocol + ClaudeClient
│   ├── session.py                  # CLI loop
│   ├── storage.py                  # load/save with atomic writes
│   ├── fixtures.py                 # generate fake data
│   └── prompts/
│       ├── session_system.txt
│       ├── chapter_recap.txt
│       └── end_of_chapter_quiz.txt
├── tests/
├── .env                            # ANTHROPIC_API_KEY
├── pyproject.toml
└── README.md
```

## Data models

Pydantic v2 `BaseModel` for everything. Chapter numbers are **always 1-indexed** in code, files, and prompts. No `n - 1` math anywhere.

```python
class Concept(BaseModel):
    term: str
    definition: str
    first_introduced_in: int          # 1-indexed
    also_used_in: list[int]

class ChapterSummary(BaseModel):
    book_id: str
    chapter_num: int                  # 1-indexed
    chapter_title: str
    one_line: str
    overview: str                     # 2–3 paragraphs
    key_concepts: list[Concept]
    code_patterns: list[str]
    depends_on_chapters: list[int]
    worked_examples: list[str]        # Gaddis labels these "Program 4-5" etc.
    common_pitfalls: list[str]
    end_of_chapter_problems: list[str]

class BookOverview(BaseModel):
    book_id: str
    title: str
    author: str
    edition: str
    total_chapters: int
    chapter_titles: dict[int, str]    # {1: "Intro to Python", ...}
    arc_summary: str

class SessionState(BaseModel):
    book_id: str
    current_chapter: int | None
    chapters_completed: dict[int, str]    # chapter_num -> ISO timestamp completed
    struggle_flags: dict[str, list[int]]  # concept_term -> chapter_nums flagged
    last_active: str                      # ISO timestamp

class LogEntry(BaseModel):
    timestamp: str
    book_id: str
    chapter_num: int
    entry_type: Literal["reflection", "quiz_answer", "struggle_flag", "problem_attempt", "question", "note"]
    content: str
    metadata: dict
```

## Milestones

### M1 — Skeleton + models + storage

- `pyproject.toml` with `uv`, lockfile committed
- All Pydantic models in `models.py`
- `storage.py` with load/save helpers, including **atomic writes** via temp file + `os.replace` for `session_state.json`. JSONL append for `reading_log.jsonl` — never rewrite that file.
- Tests: round-trip every model; atomic write leaves no partial files if interrupted; JSONL append produces one line per entry.

Stop and report.

### M2 — Fixtures

`fixtures.py` writes a populated `data/gaddis_python_6e/` tree. 15 chapters:

1. Introduction to Computers and Python
2. Input, Processing, and Output
3. Decision Structures and Boolean Logic
4. Repetition Structures
5. Functions
6. Files and Exceptions
7. Lists and Tuples
8. More About Strings
9. Dictionaries and Sets
10. Classes and Object-Oriented Programming
11. Inheritance
12. Recursion
13. GUI Programming
14. Database Programming
15. Pick a plausible final chapter (web programming, data structures, etc.) and note your choice in the milestone report.

Chapters 1–5 fully populated (rich `key_concepts`, `code_patterns`, `worked_examples`). Chapters 6–15 may have only `one_line` + short `overview` and empty/sparse lists.

Build `concept_graph.json` linking introduced concepts to their reuse (e.g., `function` introduced ch5, used ch7, ch10, ch11).

**Hand-author the fixtures.** Do not call the LLM to generate them — we need determinism for testing the session flow.

Stop and report.

### M3 — LLM client

```python
class LLMClient(Protocol):
    def chat(
        self,
        system: str,
        messages: list[dict],
        cache_system: bool = True,
    ) -> str: ...

    def structured[T: BaseModel](
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> T: ...
```

- `ClaudeClient` is the only concrete implementation.
- `structured()` is implemented via **forced tool use**: build a tool whose `input_schema` comes from `schema.model_json_schema()`, force the model to call it (`tool_choice={"type": "tool", "name": ...}`), parse the tool input through `schema.model_validate(...)`. Anthropic does not have a JSON-mode flag like OpenAI; this is the canonical structured-output pattern.
- `cache_system=True` adds `cache_control={"type": "ephemeral"}` to the system block. Be aware of the minimum-tokens threshold for caching — log a warning if the system prompt is below it.
- Smoke test in `tests/`: hit the real API with a trivial prompt. Mark with `@pytest.mark.live` so it can be skipped offline.
- Do **not** import `anthropic` anywhere outside `llm.py`. The point of the protocol is swap-ability for local models later.

Stop and report.

### M4 — Session loop

CLI reads from a `>` prompt, routes by simple prefix match. Commands:

- `starting ch<N>` — load chapter N, set as `current_chapter`, show its `depends_on_chapters`. If any prereq was completed >3 days ago (use `chapters_completed[n]` timestamp), offer a one-line recap of those prereqs and wait for input.
- `done ch<N>` — end-of-chapter flow:
  1. Show recap (LLM-generated from the cached ChapterSummary, using `chapter_recap.txt` content)
  2. Ask 2–3 quiz questions (LLM-generated via `end_of_chapter_quiz.txt`); log each answer as a `LogEntry`
  3. Prompt for free-form reflections; log as `reflection`
  4. Ask which `end_of_chapter_problems` were attempted; log each as `problem_attempt`
  5. Mark chapter completed with current timestamp
- `what was ch<N> about` — print `one_line` + `overview`
- `recap ch<N>` — overview + key concepts + worked examples (no LLM call needed; pull from fixture)
- `concept <term>` — look up in `concept_graph.json`, show definition + chapters
- `struggling with <term>` — append struggle flag to both `session_state` and the log
- `status` — current chapter, completed list, active struggle flags
- `quit` / `exit`

Implementation notes:

- Load `session_state.json` on startup. Greet me with where I left off.
- Write `session_state.json` atomically after every state-changing command.
- The session system prompt = `session_system.txt` content + the `BookOverview` JSON. Mark cacheable.
- When a chapter is active, append its `ChapterSummary` JSON as a second cached system block. Re-cache when the active chapter changes.
- `chapter_recap.txt` and `end_of_chapter_quiz.txt` are loaded as additional system content during those specific flows, not as user turns.
- Prompts in `prompts/*.txt` are loaded once at startup.
- Errors from the API: print `API error: <msg>` and return to the prompt. Don't crash the loop. Don't retry beyond what the SDK does by default.

Tests: command parsing (no LLM needed), state transitions, log append behavior. Mock `LLMClient` for everything except the M3 smoke test.

Stop and report.

### M4.5 — Ad-hoc questions and notes

Added after the original M4 ship so the companion is more than a command dispatcher. Two new commands:

- `ask <question>` — sends the question to Claude with the base system prompt (session_system + book overview + active chapter JSON, cached). Prints the answer and logs a `question` entry whose `content` is the question and whose `metadata.answer` is the model's reply. Requires an active chapter so answers stay grounded.
- `note <text>` — logs a `note` entry attached to the active chapter. No LLM call. Requires an active chapter.

Extend `EntryType` with `"question"` and `"note"`. Tests: parser round-trip for both; session tests that verify the log entries are written with the right fields and that both commands refuse cleanly without an active chapter.

Stop and report.

### M4.6 — UX cleanups from first real use

Shook out in the first interactive session. Four fixes:

1. **Silence the cache-threshold warning in `session.main()`.** The `textbook_companion.llm` logger still emits the warning (tests still verify it), but `main()` sets that logger to ERROR by default. Set `TC_DEBUG=1` in the env to re-enable it.
2. **Rename the reactions prompt to "reflections".** The word "reactions" confused the user mid-flow. Prompt now reads *"Any reflections on this chapter? (what clicked, what didn't — blank to skip)"*. The `LogEntry.entry_type` was also renamed from `"reaction"` to `"reflection"` in M4.7 to keep UI and schema in sync.
3. **Add `attempting <label>` command.** Logs a `problem_attempt` entry the moment you actually sit down and work a problem, rather than batching at `done`. Requires an active chapter.
4. **Drop the end-of-chapter "which problems did you attempt" batch question.** `attempting` replaces it. The done-flow is now: recap → quiz → reflections → mark complete.
5. **Smart `starting chN` behaviour.** Covers the full case table:
   - `current == N`: no-op with "Already reading chN.", skip deps/refresher.
   - `current == M (≠ N)` and M is **not** in `chapters_completed`: confirm prompt *"You're currently reading chM (not marked complete). Switch to chN anyway? [y/N]"*. Declining keeps you on M; accepting switches to N and leaves M uncompleted so you can come back.
   - `current == M (≠ N)` and M **is** completed: switch cleanly, no confirm.
   - Revisiting a chapter already in `chapters_completed`: switch with a soft note *"Revisiting chN (already completed)."*.

Tests cover every branch of the starting case table, the attempting command (parser + session), the removed batch problems prompt, and the new reflections wording.

Stop and report.

### M4.7 — Proper reflection rename and in-progress chapter tracking

Two changes:

1. **Schema rename: `EntryType` value `"reaction"` → `"reflection"`.** Done properly this time (M4.6 only updated the UI). `LogEntry.entry_type` now validates against the new literal and rejects the old string with a Pydantic error. If any local `reading_log.jsonl` has legacy `"reaction"` entries they'll fail to load — regenerate fixtures (`python -m textbook_companion.fixtures`) to reset the log, or hand-edit the file. No runtime migration is provided; this is a personal tool with disposable data.
2. **New `SessionState.chapters_in_progress: dict[int, str]`** (chapter_num → ISO timestamp of first start). Orthogonal to `current_chapter`, which is just the focus pointer — a chapter is "in progress" until you run `done chN` on it. Abandoning (switching to another chapter without `done`) leaves the prior chapter in `chapters_in_progress` so the signal isn't lost.

Behavior changes:

- `cmd_starting(n)` adds N to `chapters_in_progress` on first real start. Revisiting a completed chapter does **not** re-open it (you're already done). If multiple chapters are now in progress, the starting message lists the others: *"(Also in progress: ch3)"*.
- `cmd_done(n)` pops N from `chapters_in_progress` and adds to `chapters_completed`.
- `status` shows an **"In progress:"** section listing each tracked chapter with its start timestamp.
- Greeting mentions other in-progress chapters after the main "you left off in chN" line.

Tests: model round-trip for the new field; session tests for marking in-progress on start, removing on done, preserving across abandonment, not re-opening on revisit; status and greeting output.

Stop and report.

### M5 — Polish

- `README.md`: install (`uv sync`), env setup, run command, the full command list with one-line descriptions
- A walkthrough doc showing a sample 10–15 turn session against the fixtures
- Confirm `uv run textbook-companion` (or your chosen entry point) works end to end

## Explicitly NOT in Phase 1

- PDF ingestion (that's Phase 2)
- Vector search, embeddings, ChromaDB
- Web UI, TUI, rich terminal output
- Cross-book concept tracking
- Spaced-repetition scheduling logic
- LLM-generated fixtures
- Auth, multi-user, anything cloud

## Style

- Small testable functions; classes only where state genuinely lives together
- Type hints everywhere; `mypy --strict` should pass on `models.py` and `storage.py` at minimum
- Don't over-abstract. The `LLMClient` protocol is the only abstraction I've asked for; resist adding more.
- Keep prompts as plain `.txt` files

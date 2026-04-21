"""CLI session loop — the reading companion.

Reads commands from stdin, dispatches to `Session` methods, mutates
`session_state.json` atomically, appends to `reading_log.jsonl`, and talks to
the LLM only through the `LLMClient` protocol.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field

from . import commands, storage
from .llm import ClaudeClient, LLMClient, LLMError
from .models import ChapterSummary, EntryType, LogEntry


BOOK_ID = "gaddis_python_6e"
DEFAULT_DATA_ROOT = Path("data")
STALE_PREREQ_DAYS = 3

_PROMPTS_DIR = Path(__file__).parent / "prompts"


class QuizSet(BaseModel):
    """Structured-output schema for the end-of-chapter quiz flow."""

    questions: list[str] = Field(default_factory=list)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


class Session:
    """Holds state + the event loop. `out` and `ask` are injected so tests can
    drive the CLI without touching real stdin/stdout."""

    def __init__(
        self,
        data_root: Path,
        book_id: str,
        llm: LLMClient,
        out: Callable[[str], None] = print,
        ask: Callable[[str], str] = input,
    ) -> None:
        self.data_root = data_root
        self.book_id = book_id
        self.llm = llm
        self.out = out
        self.ask = ask

        self.book_overview = storage.load_book_overview(data_root, book_id)
        self.concept_graph = storage.load_concept_graph(data_root, book_id)
        self.state = storage.load_session_state(data_root, book_id)

        self.session_system_prompt = _read_prompt("session_system.txt")
        self.chapter_recap_prompt = _read_prompt("chapter_recap.txt")
        self.end_of_chapter_quiz_prompt = _read_prompt("end_of_chapter_quiz.txt")
        self.quiz_feedback_prompt = _read_prompt("quiz_feedback.txt")

    # ----- event loop -----

    def run(self) -> None:
        self._greet()
        while True:
            try:
                raw = self.ask("> ")
            except EOFError:
                self.out("")
                return
            cmd = commands.parse(raw)
            if isinstance(cmd, commands.Quit):
                self.out("bye.")
                return
            try:
                self._dispatch(cmd)
            except LLMError as e:
                self.out(f"API error: {e}")

    def _dispatch(self, cmd: commands.Command) -> None:
        match cmd:
            case commands.StartChapter(n):
                self.cmd_starting(n)
            case commands.DoneChapter(n):
                self.cmd_done(n)
            case commands.WhatWasChapter(n):
                self.cmd_what_was(n)
            case commands.RecapChapter(n):
                self.cmd_recap(n)
            case commands.LookupConcept(term):
                self.cmd_concept(term)
            case commands.StrugglingWith(term):
                self.cmd_struggling(term)
            case commands.Ask(question):
                self.cmd_ask(question)
            case commands.Note(text):
                self.cmd_note(text)
            case commands.Attempting(label):
                self.cmd_attempting(label)
            case commands.Status():
                self.cmd_status()
            case commands.Unknown(raw):
                if raw:
                    self.out(f"Unknown command: {raw!r}")

    # ----- commands -----

    def cmd_starting(self, n: int) -> None:
        current = self.state.current_chapter

        # Already on this chapter — silently no-op with a clear message,
        # skip deps/refresher spam.
        if current == n:
            self.out(f"Already reading ch{n}.")
            return

        ch = self._load_chapter(n)
        if ch is None:
            return

        # Abandoning an incomplete chapter. Confirm before overwriting
        # current_chapter — catches fat-finger typos and makes deliberate
        # jumps explicit.
        if (
            current is not None
            and current not in self.state.chapters_completed
        ):
            answer = self.ask(
                f"You're currently reading ch{current} (not marked complete). "
                f"Switch to ch{n} anyway? [y/N] "
            ).strip().lower()
            if not answer.startswith("y"):
                self.out(f"Staying on ch{current}.")
                return

        revisiting = n in self.state.chapters_completed
        # Mark in-progress on first real start. Revisiting a completed
        # chapter does NOT put it back in progress — you're already done.
        if not revisiting and n not in self.state.chapters_in_progress:
            self.state.chapters_in_progress[n] = _now_iso()
        self.state.current_chapter = n
        self._save_state()

        if revisiting:
            self.out(
                f"Revisiting ch{n}: {ch.chapter_title} (already completed)."
            )
        elif n in self.state.chapters_in_progress and len(
            self.state.chapters_in_progress
        ) > 1:
            # The user has other chapters still in progress — worth flagging.
            others = sorted(
                m for m in self.state.chapters_in_progress if m != n
            )
            others_str = ", ".join(f"ch{m}" for m in others)
            self.out(f"Starting ch{n}: {ch.chapter_title}")
            self.out(f"(Also in progress: {others_str})")
        else:
            self.out(f"Starting ch{n}: {ch.chapter_title}")

        if ch.depends_on_chapters:
            deps = ", ".join(f"ch{d}" for d in ch.depends_on_chapters)
            self.out(f"Depends on: {deps}")
        stale = self._stale_prereqs(ch)
        if stale:
            self.out(
                f"Refresher on prereqs completed >{STALE_PREREQ_DAYS} days ago:"
            )
            for prereq_num in stale:
                prereq = storage.load_chapter(self.data_root, self.book_id, prereq_num)
                self.out(f"  ch{prereq_num}: {prereq.one_line}")
            self.ask("(press enter to continue) ")

    def cmd_done(self, n: int) -> None:
        ch = self._load_chapter(n)
        if ch is None:
            return

        base_sys = self._base_system(ch)

        # 1. Recap
        self.out(f"\n== Recap for ch{n}: {ch.chapter_title} ==")
        recap_sys = base_sys + "\n\n" + self.chapter_recap_prompt
        recap = self.llm.chat(
            system=recap_sys,
            messages=[{"role": "user", "content": f"Recap ch{n}."}],
            cache_system=True,
        )
        self.out(recap)

        # 2. Quiz
        quiz_sys = base_sys + "\n\n" + self.end_of_chapter_quiz_prompt
        quiz = self.llm.structured(
            system=quiz_sys,
            user=f"Generate 2-3 quiz questions for ch{n}.",
            schema=QuizSet,
        )
        if quiz.questions:
            feedback_sys = base_sys + "\n\n" + self.quiz_feedback_prompt
            self.out(f"\n== Quiz ({len(quiz.questions)} questions) ==")
            for i, q in enumerate(quiz.questions, 1):
                self.out(f"Q{i}: {q}")
                answer = self.ask("A: ").strip()
                feedback = self.llm.chat(
                    system=feedback_sys,
                    messages=[
                        {
                            "role": "user",
                            "content": f"Question: {q}\nStudent's answer: {answer}",
                        }
                    ],
                    cache_system=True,
                )
                self.out(feedback)
                self._log(
                    n,
                    "quiz_answer",
                    answer,
                    metadata={
                        "question": q,
                        "q_num": i,
                        "feedback": feedback,
                    },
                )

        # 3. Reflections
        self.out(
            "\nAny reflections on this chapter? "
            "(what clicked, what didn't — blank to skip)"
        )
        reflection = self.ask("> ").strip()
        if reflection:
            self._log(n, "reflection", reflection, metadata={})

        # 4. Mark complete
        # Problems aren't asked here — log them in-the-moment with
        # `attempting <label>` while you're actually working them.
        self.state.chapters_completed[n] = _now_iso()
        self.state.chapters_in_progress.pop(n, None)
        self._save_state()
        self.out(f"\nch{n} marked complete.")

    def cmd_what_was(self, n: int) -> None:
        ch = self._load_chapter(n)
        if ch is None:
            return
        self.out(f"ch{n}: {ch.chapter_title}")
        self.out(ch.one_line)
        self.out("")
        self.out(ch.overview)

    def cmd_recap(self, n: int) -> None:
        ch = self._load_chapter(n)
        if ch is None:
            return
        self.out(f"ch{n}: {ch.chapter_title}")
        self.out("")
        self.out(ch.overview)
        if ch.key_concepts:
            self.out("\nKey concepts:")
            for c in ch.key_concepts:
                self.out(f"  - {c.term}: {c.definition}")
        if ch.worked_examples:
            self.out("\nWorked examples:")
            for e in ch.worked_examples:
                self.out(f"  - {e}")

    def cmd_concept(self, term: str) -> None:
        key = term.strip().lower()
        matches = [
            e for e in self.concept_graph.concepts if e.term.lower() == key
        ]
        if not matches:
            self.out(f"No concept '{term}' found in the concept graph.")
            return
        entry = matches[0]
        self.out(f"{entry.term}: {entry.definition}")
        self.out(f"  first introduced in ch{entry.first_introduced_in}")
        if entry.also_used_in:
            reused = ", ".join(f"ch{n}" for n in entry.also_used_in)
            self.out(f"  also used in: {reused}")

    def cmd_struggling(self, term: str) -> None:
        chapter_num = self.state.current_chapter
        if chapter_num is None:
            self.out(
                "No active chapter. Start one with `starting ch<N>` first."
            )
            return
        chapters = self.state.struggle_flags.setdefault(term, [])
        if chapter_num not in chapters:
            chapters.append(chapter_num)
        self._log(chapter_num, "struggle_flag", term, metadata={})
        self._save_state()
        self.out(f"Flagged '{term}' as a struggle in ch{chapter_num}.")

    def cmd_ask(self, question: str) -> None:
        chapter_num = self.state.current_chapter
        if chapter_num is None:
            self.out(
                "No active chapter. Start one with `starting ch<N>` first — "
                "questions are answered in the context of a chapter."
            )
            return
        ch = self._load_chapter(chapter_num)
        if ch is None:
            return
        answer = self.llm.chat(
            system=self._base_system(ch),
            messages=[{"role": "user", "content": question}],
            cache_system=True,
        )
        self.out(answer)
        self._log(
            chapter_num,
            "question",
            question,
            metadata={"answer": answer},
        )
        self._save_state()

    def cmd_note(self, text: str) -> None:
        chapter_num = self.state.current_chapter
        if chapter_num is None:
            self.out(
                "No active chapter. Start one with `starting ch<N>` first."
            )
            return
        self._log(chapter_num, "note", text, metadata={})
        self._save_state()
        self.out(f"Note logged for ch{chapter_num}.")

    def cmd_attempting(self, label: str) -> None:
        chapter_num = self.state.current_chapter
        if chapter_num is None:
            self.out(
                "No active chapter. Start one with `starting ch<N>` first."
            )
            return
        self._log(chapter_num, "problem_attempt", label, metadata={})
        self._save_state()
        self.out(f"Logged problem attempt '{label}' for ch{chapter_num}.")

    def cmd_status(self) -> None:
        if self.state.current_chapter is not None:
            self.out(f"Current chapter: ch{self.state.current_chapter}")
        else:
            self.out("Current chapter: (none)")
        if self.state.chapters_in_progress:
            self.out("In progress:")
            for n in sorted(self.state.chapters_in_progress):
                self.out(
                    f"  ch{n}: started {self.state.chapters_in_progress[n]}"
                )
        if self.state.chapters_completed:
            self.out("Completed:")
            for n in sorted(self.state.chapters_completed):
                self.out(f"  ch{n}: {self.state.chapters_completed[n]}")
        else:
            self.out("Completed: (none)")
        if self.state.struggle_flags:
            self.out("Struggle flags:")
            for t, chs in sorted(self.state.struggle_flags.items()):
                marked = ", ".join(f"ch{c}" for c in chs)
                self.out(f"  {t}: {marked}")

    # ----- helpers -----

    def _greet(self) -> None:
        bo = self.book_overview
        self.out(f"Textbook Companion — {bo.title} ({bo.edition}), {bo.author}")
        if self.state.current_chapter is not None:
            msg = f"You left off in ch{self.state.current_chapter}."
            others = sorted(
                n
                for n in self.state.chapters_in_progress
                if n != self.state.current_chapter
            )
            if others:
                others_str = ", ".join(f"ch{n}" for n in others)
                msg += f" Also in progress: {others_str}."
            self.out(msg)
        elif self.state.chapters_completed:
            latest = max(self.state.chapters_completed)
            self.out(f"No active chapter. Last completed: ch{latest}.")
        else:
            self.out("No progress yet — start with `starting ch1`.")
        if self.state.struggle_flags:
            terms = ", ".join(sorted(self.state.struggle_flags.keys()))
            self.out(f"Active struggle flags: {terms}")

    def _load_chapter(self, n: int) -> ChapterSummary | None:
        try:
            return storage.load_chapter(self.data_root, self.book_id, n)
        except FileNotFoundError:
            self.out(f"No such chapter: ch{n}")
            return None

    def _stale_prereqs(self, ch: ChapterSummary) -> list[int]:
        now = datetime.now(timezone.utc)
        threshold = timedelta(days=STALE_PREREQ_DAYS)
        stale: list[int] = []
        for prereq_num in ch.depends_on_chapters:
            ts = self.state.chapters_completed.get(prereq_num)
            if not ts:
                continue
            completed = datetime.fromisoformat(ts)
            if now - completed > threshold:
                stale.append(prereq_num)
        return stale

    def _base_system(self, chapter: ChapterSummary) -> str:
        parts = [
            self.session_system_prompt.rstrip(),
            "# Book Overview",
            json.dumps(self.book_overview.model_dump(), indent=2),
            "# Active Chapter",
            json.dumps(chapter.model_dump(), indent=2),
        ]
        return "\n\n".join(parts)

    def _save_state(self) -> None:
        self.state.last_active = _now_iso()
        storage.save_session_state(self.data_root, self.state)

    def _log(
        self,
        chapter_num: int,
        entry_type: EntryType,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        entry = LogEntry(
            timestamp=_now_iso(),
            book_id=self.book_id,
            chapter_num=chapter_num,
            entry_type=entry_type,
            content=content,
            metadata=metadata,
        )
        storage.append_log(
            storage.reading_log_path(self.data_root, self.book_id), entry
        )


def main() -> None:
    # The LLM client logs a cache-threshold warning when a system prompt is
    # below Opus 4.7's 4096-token minimum. Useful for development, ugly
    # mid-conversation. Suppress by default; set TC_DEBUG=1 to see it.
    llm_log_level = logging.DEBUG if os.environ.get("TC_DEBUG") else logging.ERROR
    logging.getLogger("textbook_companion.llm").setLevel(llm_log_level)

    data_root = DEFAULT_DATA_ROOT
    book_id = BOOK_ID
    state_path = storage.session_state_path(data_root, book_id)
    if not state_path.exists():
        print(
            f"No session state at {state_path}. "
            f"Run `uv run python -m textbook_companion.fixtures` first.",
            file=sys.stderr,
        )
        sys.exit(1)
    Session(data_root, book_id, ClaudeClient()).run()


if __name__ == "__main__":
    main()

"""Session loop integration tests.

The LLM is replaced by a FakeLLM that records every call and returns canned
responses. User input is fed through a scripted `ask` callable; output is
captured into a list. No real Anthropic calls are made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest
from pydantic import BaseModel

from textbook_companion import fixtures, storage
from textbook_companion.fixtures import BOOK_ID
from textbook_companion.llm import StructuredOutputError
from textbook_companion.session import Session


# --- Fakes ---------------------------------------------------------------


@dataclass
class FakeLLMCall:
    method: str
    system: str
    payload: Any


class FakeLLM:
    def __init__(
        self,
        chat_returns: list[Any] | None = None,
        structured_returns: list[Any] | None = None,
    ) -> None:
        # Each entry can be either a string/value to return or an Exception to raise.
        self._chat = iter(chat_returns if chat_returns is not None else ["(fake recap)"])
        self._structured = iter(
            structured_returns
            if structured_returns is not None
            else [_QuizReturn(["q1?", "q2?"])]
        )
        self.calls: list[FakeLLMCall] = []

    def chat(
        self, system: str, messages: list[dict[str, Any]], cache_system: bool = True
    ) -> str:
        self.calls.append(FakeLLMCall("chat", system, messages))
        val = next(self._chat)
        if isinstance(val, Exception):
            raise val
        return val  # type: ignore[no-any-return]

    def structured(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        self.calls.append(FakeLLMCall("structured", system, user))
        val = next(self._structured)
        if isinstance(val, Exception):
            raise val
        if isinstance(val, _QuizReturn):
            return schema.model_validate({"questions": val.questions})
        return val  # type: ignore[no-any-return]


@dataclass
class _QuizReturn:
    questions: list[str] = field(default_factory=list)


def scripted_ask(inputs: list[str]) -> Callable[[str], str]:
    it = iter(inputs)

    def _ask(prompt: str) -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError(f"ran out of scripted input at prompt: {prompt!r}")

    return _ask


def collecting_out() -> tuple[Callable[[str], None], list[str]]:
    lines: list[str] = []

    def _out(s: str) -> None:
        lines.append(s)

    return _out, lines


# --- Fixtures ------------------------------------------------------------


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    fixtures.write_fixtures(tmp_path)
    return tmp_path


def _make_session(
    data_root: Path,
    llm: FakeLLM,
    inputs: list[str] | None = None,
) -> tuple[Session, list[str]]:
    out, lines = collecting_out()
    ask = scripted_ask(inputs or [])
    session = Session(data_root, BOOK_ID, llm=llm, out=out, ask=ask)
    return session, lines


# --- Greeting ------------------------------------------------------------


def test_greeting_with_no_progress(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session._greet()
    joined = "\n".join(lines)
    assert "Textbook Companion" in joined
    assert "Starting Out with Python" in joined
    assert "No progress yet" in joined


def test_greeting_with_active_chapter(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 5
    storage.save_session_state(data_root, state)
    session, lines = _make_session(data_root, FakeLLM())
    session._greet()
    assert any("left off in ch5" in l for l in lines)


# --- starting chN --------------------------------------------------------


def test_starting_updates_state(data_root: Path) -> None:
    session, _ = _make_session(data_root, FakeLLM())
    session.cmd_starting(5)
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert reloaded.current_chapter == 5


def test_starting_shows_deps_and_no_stale_refresher_when_fresh(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    # ch4 completed right now — not stale.
    state.chapters_completed[4] = datetime.now(timezone.utc).isoformat()
    storage.save_session_state(data_root, state)

    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_starting(5)
    joined = "\n".join(lines)
    assert "Depends on:" in joined
    assert "Refresher" not in joined


def test_starting_triggers_stale_prereq_refresher(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    # ch4 completed 10 days ago — stale.
    state.chapters_completed[4] = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).isoformat()
    storage.save_session_state(data_root, state)

    session, lines = _make_session(
        data_root, FakeLLM(), inputs=["" ]  # pressing enter to continue
    )
    session.cmd_starting(5)
    joined = "\n".join(lines)
    assert "Refresher on prereqs" in joined
    assert "ch4:" in joined  # stale prereq listed
    # No LLM call made on starting (it's pure state update + file reads).
    assert session.llm.calls == []


def test_starting_unknown_chapter(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_starting(99)
    assert any("No such chapter" in l for l in lines)
    # State unchanged.
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert reloaded.current_chapter is None


def test_starting_same_chapter_is_noop(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 5
    storage.save_session_state(data_root, state)
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_starting(5)
    assert any("Already reading ch5" in l for l in lines)
    # Deps output skipped.
    assert not any("Depends on:" in l for l in lines)


def test_starting_abandoning_incomplete_chapter_declined(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 3
    storage.save_session_state(data_root, state)
    # The confirm prompt comes through ask(); answer 'n' to decline.
    session, lines = _make_session(data_root, FakeLLM(), inputs=["n"])
    session.cmd_starting(5)
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert reloaded.current_chapter == 3  # did NOT switch
    assert any("Staying on ch3" in l for l in lines)


def test_starting_abandoning_incomplete_chapter_confirmed(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 3
    storage.save_session_state(data_root, state)
    session, lines = _make_session(data_root, FakeLLM(), inputs=["y"])
    session.cmd_starting(5)
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert reloaded.current_chapter == 5  # switched
    # ch3 stays uncompleted — user can come back.
    assert 3 not in reloaded.chapters_completed


def test_starting_from_completed_chapter_switches_without_confirm(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 3
    state.chapters_completed[3] = datetime.now(timezone.utc).isoformat()
    storage.save_session_state(data_root, state)
    # No input scripted — no confirm prompt should be asked.
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_starting(5)
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert reloaded.current_chapter == 5


def test_starting_revisiting_completed_chapter_announces(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.chapters_completed[2] = datetime.now(timezone.utc).isoformat()
    storage.save_session_state(data_root, state)
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_starting(2)
    assert any("Revisiting ch2" in l and "already completed" in l for l in lines)


# --- in-progress tracking -----------------------------------------------


def test_starting_marks_chapter_in_progress(data_root: Path) -> None:
    session, _ = _make_session(data_root, FakeLLM())
    session.cmd_starting(5)
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert 5 in reloaded.chapters_in_progress
    # Value is an ISO timestamp.
    assert reloaded.chapters_in_progress[5]


def test_revisiting_completed_chapter_does_not_reopen_in_progress(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.chapters_completed[2] = datetime.now(timezone.utc).isoformat()
    storage.save_session_state(data_root, state)
    session, _ = _make_session(data_root, FakeLLM())
    session.cmd_starting(2)
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert 2 not in reloaded.chapters_in_progress
    assert 2 in reloaded.chapters_completed


def test_abandoning_leaves_previous_chapter_in_progress(data_root: Path) -> None:
    # Abandon ch3 mid-flight, switch to ch5. ch3 should still be in progress.
    session, _ = _make_session(data_root, FakeLLM())
    session.cmd_starting(3)
    # User confirms the switch:
    session.ask = scripted_ask(["y"])
    session.cmd_starting(5)
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert set(reloaded.chapters_in_progress) == {3, 5}
    assert reloaded.current_chapter == 5


def test_done_removes_chapter_from_in_progress(data_root: Path) -> None:
    llm = FakeLLM(
        chat_returns=["recap"],
        structured_returns=[_QuizReturn([])],
    )
    session, _ = _make_session(data_root, llm, inputs=[""])  # blank reflection
    session.cmd_starting(5)
    session.cmd_done(5)
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert 5 not in reloaded.chapters_in_progress
    assert 5 in reloaded.chapters_completed


def test_status_shows_in_progress_section(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 5
    state.chapters_in_progress = {
        3: "2026-04-15T10:00:00Z",
        5: "2026-04-20T10:00:00Z",
    }
    storage.save_session_state(data_root, state)
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_status()
    joined = "\n".join(lines)
    assert "In progress:" in joined
    assert "ch3:" in joined
    assert "ch5:" in joined


def test_greeting_mentions_other_in_progress_chapters(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 5
    state.chapters_in_progress = {
        3: "2026-04-15T10:00:00Z",
        5: "2026-04-20T10:00:00Z",
    }
    storage.save_session_state(data_root, state)
    session, lines = _make_session(data_root, FakeLLM())
    session._greet()
    joined = "\n".join(lines)
    assert "left off in ch5" in joined
    assert "Also in progress: ch3" in joined


# --- done chN ------------------------------------------------------------


def test_done_flow_logs_and_marks_complete(data_root: Path) -> None:
    llm = FakeLLM(
        chat_returns=[
            "Recap of ch5: functions etc.",
            "You've got the DRY instinct; functions also let you update logic in one place.",
            "Right about locals; remember globals are visible across the whole module.",
        ],
        structured_returns=[_QuizReturn(["Why use functions?", "What is scope?"])],
    )
    # Scripted: 2 quiz answers, then reflection. No more batch problem-attempts
    # question — that's logged in-the-moment via `attempting <label>`.
    inputs = [
        "because DRY",      # A1
        "local variables",  # A2
        "liked this one",   # reflection
    ]
    session, lines = _make_session(data_root, llm, inputs=inputs)
    session.cmd_done(5)

    # Chapter marked complete.
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert 5 in reloaded.chapters_completed

    # Log has quiz_answer x2, reflection x1. No more batch problem_attempt entries.
    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    types = [e.entry_type for e in entries]
    assert types == ["quiz_answer", "quiz_answer", "reflection"]
    quiz_entries = [e for e in entries if e.entry_type == "quiz_answer"]
    assert quiz_entries[0].metadata["question"] == "Why use functions?"
    assert quiz_entries[0].metadata["q_num"] == 1
    # Each quiz entry now carries the per-answer feedback text.
    assert quiz_entries[0].metadata["feedback"].startswith("You've got the DRY")
    assert quiz_entries[1].metadata["feedback"].startswith("Right about locals")

    # LLM calls: recap (chat) + quiz (structured) + 2 feedback (chat per answer).
    assert [c.method for c in llm.calls] == ["chat", "structured", "chat", "chat"]
    assert '"chapter_num": 5' in llm.calls[0].system
    assert '"chapter_num": 5' in llm.calls[1].system
    assert "Recap instructions" in llm.calls[0].system
    assert "Quiz instructions" in llm.calls[1].system
    assert "Quiz feedback instructions" in llm.calls[2].system
    assert "Quiz feedback instructions" in llm.calls[3].system
    # Feedback user messages carry both the question and the student's answer.
    assert "Why use functions?" in llm.calls[2].payload[0]["content"]
    assert "because DRY" in llm.calls[2].payload[0]["content"]

    # UX: the reflections prompt uses the new wording.
    joined = "\n".join(lines)
    assert "reflections" in joined.lower()
    # And the old batch problems question is gone.
    assert "Which end-of-chapter problems" not in joined
    # Feedback text is printed back to the user immediately after their answer.
    assert any("DRY instinct" in l for l in lines)


def test_done_flow_feedback_is_printed_and_logged(data_root: Path) -> None:
    llm = FakeLLM(
        chat_returns=["(recap)", "feedback text for q1"],
        structured_returns=[_QuizReturn(["q1?"])],
    )
    session, lines = _make_session(
        data_root, llm, inputs=["my answer", ""]  # answer + blank reflection
    )
    session.cmd_done(5)

    # Feedback printed back to the user.
    assert any("feedback text for q1" in l for l in lines)

    # Feedback persisted in the quiz_answer log entry's metadata.
    entries = [
        e
        for e in storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
        if e.entry_type == "quiz_answer"
    ]
    assert len(entries) == 1
    assert entries[0].metadata["feedback"] == "feedback text for q1"


def test_done_flow_skips_quiz_section_when_no_questions(data_root: Path) -> None:
    llm = FakeLLM(
        chat_returns=["Recap of ch5."],
        structured_returns=[_QuizReturn([])],  # empty quiz
    )
    inputs = [
        "",  # reflection skipped
    ]
    session, _ = _make_session(data_root, llm, inputs=inputs)
    session.cmd_done(5)
    # No quiz_answer, no reflection.
    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    assert [e.entry_type for e in entries] == []


# --- what was / recap ----------------------------------------------------


def test_what_was_prints_one_line_and_overview(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_what_was(5)
    joined = "\n".join(lines)
    assert "Functions" in joined  # chapter title
    assert "Defining and calling functions" in joined  # one_line


def test_recap_prints_overview_concepts_and_examples_no_llm(data_root: Path) -> None:
    llm = FakeLLM()
    session, lines = _make_session(data_root, llm)
    session.cmd_recap(5)
    joined = "\n".join(lines)
    assert "Functions" in joined
    assert "Key concepts:" in joined
    assert "Worked examples:" in joined
    assert "Program 5-" in joined
    # No LLM call.
    assert llm.calls == []


# --- concept -------------------------------------------------------------


def test_concept_found(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_concept("function")
    joined = "\n".join(lines)
    assert "function:" in joined
    assert "first introduced in ch5" in joined
    assert "also used in:" in joined


def test_concept_case_insensitive(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_concept("FUNCTION")
    assert any("first introduced in ch5" in l for l in lines)


def test_concept_not_found(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_concept("monads")
    assert any("No concept 'monads' found" in l for l in lines)


# --- struggling ----------------------------------------------------------


def test_struggling_updates_state_and_log(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 12
    storage.save_session_state(data_root, state)

    session, _ = _make_session(data_root, FakeLLM())
    session.cmd_struggling("recursion")

    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert reloaded.struggle_flags == {"recursion": [12]}

    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    assert len(entries) == 1
    assert entries[0].entry_type == "struggle_flag"
    assert entries[0].content == "recursion"
    assert entries[0].chapter_num == 12


def test_struggling_requires_active_chapter(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_struggling("anything")
    assert any("No active chapter" in l for l in lines)
    # State unchanged.
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert reloaded.struggle_flags == {}


def test_struggling_with_same_term_twice_dedupes_chapter_list(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 12
    storage.save_session_state(data_root, state)
    session, _ = _make_session(data_root, FakeLLM())
    session.cmd_struggling("recursion")
    session.cmd_struggling("recursion")
    reloaded = storage.load_session_state(data_root, BOOK_ID)
    assert reloaded.struggle_flags == {"recursion": [12]}


# --- status --------------------------------------------------------------


def test_status_shows_everything(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 7
    state.chapters_completed = {1: "2026-04-10T00:00:00+00:00"}
    state.struggle_flags = {"recursion": [12]}
    storage.save_session_state(data_root, state)

    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_status()
    joined = "\n".join(lines)
    assert "Current chapter: ch7" in joined
    assert "ch1:" in joined
    assert "Struggle flags:" in joined
    assert "recursion" in joined


# --- ask -----------------------------------------------------------------


def test_ask_calls_llm_and_logs_question_and_answer(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 5
    storage.save_session_state(data_root, state)

    llm = FakeLLM(chat_returns=["Because a bare `return` is the same as `return None`."])
    session, lines = _make_session(data_root, llm)
    session.cmd_ask("why does a function return None by default?")

    # Answer was printed.
    assert any("bare `return`" in l for l in lines)

    # Exactly one chat call; system prompt contained the active chapter JSON.
    assert [c.method for c in llm.calls] == ["chat"]
    assert '"chapter_num": 5' in llm.calls[0].system

    # Log has a single 'question' entry with the answer in metadata.
    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == "question"
    assert entry.chapter_num == 5
    assert entry.content == "why does a function return None by default?"
    assert entry.metadata["answer"].startswith("Because a bare")


def test_ask_requires_active_chapter(data_root: Path) -> None:
    llm = FakeLLM()
    session, lines = _make_session(data_root, llm)
    session.cmd_ask("anything")
    assert any("No active chapter" in l for l in lines)
    assert llm.calls == []
    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    assert entries == []


# --- note ----------------------------------------------------------------


def test_note_logs_entry_and_does_not_call_llm(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 7
    storage.save_session_state(data_root, state)

    llm = FakeLLM()
    session, lines = _make_session(data_root, llm)
    session.cmd_note("slicing syntax still trips me up")

    assert any("Note logged for ch7" in l for l in lines)
    assert llm.calls == []
    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == "note"
    assert entry.chapter_num == 7
    assert entry.content == "slicing syntax still trips me up"
    assert entry.metadata == {}


def test_note_requires_active_chapter(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_note("untethered thought")
    assert any("No active chapter" in l for l in lines)
    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    assert entries == []


# --- attempting ---------------------------------------------------------


def test_attempting_logs_problem_attempt_entry(data_root: Path) -> None:
    state = storage.load_session_state(data_root, BOOK_ID)
    state.current_chapter = 5
    storage.save_session_state(data_root, state)

    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_attempting("5.4")
    assert any("Logged problem attempt '5.4' for ch5" in l for l in lines)

    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == "problem_attempt"
    assert entry.chapter_num == 5
    assert entry.content == "5.4"
    assert entry.metadata == {}


def test_attempting_requires_active_chapter(data_root: Path) -> None:
    session, lines = _make_session(data_root, FakeLLM())
    session.cmd_attempting("5.4")
    assert any("No active chapter" in l for l in lines)
    entries = storage.read_log(storage.reading_log_path(data_root, BOOK_ID))
    assert entries == []


# --- API error handling --------------------------------------------------


def test_api_error_during_chat_does_not_crash_loop(data_root: Path) -> None:
    llm = FakeLLM(
        chat_returns=[StructuredOutputError("boom from the fake API")],
        structured_returns=[_QuizReturn(["q?"])],
    )
    session, lines = _make_session(data_root, llm, inputs=["done ch5", "quit"])

    session.run()
    joined = "\n".join(lines)
    assert "API error:" in joined
    assert "boom from the fake API" in joined
    # Loop exited cleanly via quit, not a crash.
    assert "bye." in joined


# --- run() loop smoke ----------------------------------------------------


def test_run_loop_dispatches_then_quits(data_root: Path) -> None:
    llm = FakeLLM()
    session, lines = _make_session(
        data_root, llm, inputs=["status", "quit"]
    )
    session.run()
    joined = "\n".join(lines)
    assert "Current chapter" in joined
    assert "bye." in joined


def test_run_loop_handles_unknown_commands(data_root: Path) -> None:
    session, lines = _make_session(
        data_root, FakeLLM(), inputs=["what even", "quit"]
    )
    session.run()
    assert any("Unknown command" in l for l in lines)

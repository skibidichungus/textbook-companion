"""Round-trip every model through JSON."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from textbook_companion.models import (
    BookOverview,
    ChapterSummary,
    Concept,
    ConceptGraph,
    ConceptGraphEntry,
    LogEntry,
    SessionState,
)


def test_concept_round_trip() -> None:
    c = Concept(
        term="variable",
        definition="A named reference to a value.",
        first_introduced_in=1,
        also_used_in=[2, 3, 4],
    )
    assert Concept.model_validate_json(c.model_dump_json()) == c


def test_chapter_summary_round_trip() -> None:
    cs = ChapterSummary(
        book_id="gaddis_python_6e",
        chapter_num=5,
        chapter_title="Functions",
        one_line="Defining and calling functions.",
        overview="A chapter about functions.\n\nIt covers params and returns.",
        key_concepts=[
            Concept(term="function", definition="Named block.", first_introduced_in=5, also_used_in=[7, 10])
        ],
        code_patterns=["def name(args):"],
        depends_on_chapters=[1, 2, 3, 4],
        worked_examples=["Program 5-1"],
        common_pitfalls=["Forgetting return"],
        end_of_chapter_problems=["5.1", "5.2"],
    )
    assert ChapterSummary.model_validate_json(cs.model_dump_json()) == cs


def test_book_overview_round_trip() -> None:
    bo = BookOverview(
        book_id="gaddis_python_6e",
        title="Starting Out with Python",
        author="Tony Gaddis",
        edition="6th",
        total_chapters=15,
        chapter_titles={1: "Intro", 2: "IO"},
        arc_summary="Procedural then OO.",
    )
    round = BookOverview.model_validate_json(bo.model_dump_json())
    assert round == bo
    assert round.chapter_titles[1] == "Intro"


def test_session_state_round_trip() -> None:
    s = SessionState(
        book_id="gaddis_python_6e",
        current_chapter=5,
        chapters_in_progress={5: "2026-04-15T10:00:00Z"},
        chapters_completed={1: "2026-04-10T10:00:00Z", 2: "2026-04-11T10:00:00Z"},
        struggle_flags={"recursion": [12]},
        last_active="2026-04-18T10:00:00Z",
    )
    round = SessionState.model_validate_json(s.model_dump_json())
    assert round == s
    assert round.chapters_completed[1] == "2026-04-10T10:00:00Z"
    assert round.chapters_in_progress[5] == "2026-04-15T10:00:00Z"


def test_session_state_defaults() -> None:
    s = SessionState(book_id="b", last_active="2026-04-18T00:00:00Z")
    assert s.current_chapter is None
    assert s.chapters_in_progress == {}
    assert s.chapters_completed == {}
    assert s.struggle_flags == {}


def test_log_entry_round_trip() -> None:
    e = LogEntry(
        timestamp="2026-04-18T10:00:00Z",
        book_id="gaddis_python_6e",
        chapter_num=5,
        entry_type="reflection",
        content="The functions chapter clicked.",
        metadata={"mood": "good"},
    )
    assert LogEntry.model_validate_json(e.model_dump_json()) == e


def test_log_entry_rejects_legacy_reaction_type() -> None:
    # `reaction` was renamed to `reflection` in M4.7 — verify the old value
    # no longer validates so stale data doesn't silently slip in.
    with pytest.raises(ValidationError):
        LogEntry(
            timestamp="x",
            book_id="b",
            chapter_num=1,
            entry_type="reaction",  # type: ignore[arg-type]
            content="c",
            metadata={},
        )


def test_log_entry_rejects_invalid_type() -> None:
    with pytest.raises(ValidationError):
        LogEntry(
            timestamp="x",
            book_id="b",
            chapter_num=1,
            entry_type="bogus",  # type: ignore[arg-type]
            content="c",
            metadata={},
        )


def test_chapter_rejects_zero_index() -> None:
    with pytest.raises(ValidationError):
        ChapterSummary(
            book_id="b",
            chapter_num=0,
            chapter_title="t",
            one_line="o",
            overview="v",
        )


def test_concept_graph_round_trip() -> None:
    g = ConceptGraph(
        book_id="gaddis_python_6e",
        concepts=[
            ConceptGraphEntry(
                term="function",
                definition="Named reusable block.",
                first_introduced_in=5,
                also_used_in=[7, 10, 11],
            )
        ],
    )
    assert ConceptGraph.model_validate_json(g.model_dump_json()) == g

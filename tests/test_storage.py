"""Atomic writes, JSONL append, and model save/load round-trips."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from textbook_companion import storage
from textbook_companion.models import (
    BookOverview,
    ChapterSummary,
    Concept,
    ConceptGraph,
    ConceptGraphEntry,
    LogEntry,
    SessionState,
)


def _sample_state() -> SessionState:
    return SessionState(
        book_id="gaddis_python_6e",
        current_chapter=3,
        chapters_completed={1: "2026-04-10T10:00:00Z"},
        struggle_flags={"recursion": [12]},
        last_active="2026-04-18T10:00:00Z",
    )


def _sample_chapter(num: int = 5) -> ChapterSummary:
    return ChapterSummary(
        book_id="gaddis_python_6e",
        chapter_num=num,
        chapter_title="Functions",
        one_line="Defining and calling functions.",
        overview="Intro to functions.",
        key_concepts=[Concept(term="function", definition="Named block.", first_introduced_in=5, also_used_in=[7])],
        code_patterns=["def name(args):"],
        depends_on_chapters=[1, 2, 3, 4],
        worked_examples=["Program 5-1"],
    )


def test_save_load_book_overview(tmp_path: Path) -> None:
    bo = BookOverview(
        book_id="gaddis_python_6e",
        title="Starting Out with Python",
        author="Tony Gaddis",
        edition="6th",
        total_chapters=15,
        chapter_titles={1: "Intro", 2: "IO"},
        arc_summary="Procedural then OO.",
    )
    storage.save_book_overview(tmp_path, bo)
    assert storage.load_book_overview(tmp_path, bo.book_id) == bo


def test_save_load_chapter(tmp_path: Path) -> None:
    c = _sample_chapter()
    storage.save_chapter(tmp_path, c)
    loaded = storage.load_chapter(tmp_path, c.book_id, c.chapter_num)
    assert loaded == c


def test_save_load_session_state(tmp_path: Path) -> None:
    s = _sample_state()
    storage.save_session_state(tmp_path, s)
    loaded = storage.load_session_state(tmp_path, s.book_id)
    assert loaded == s


def test_save_load_concept_graph(tmp_path: Path) -> None:
    g = ConceptGraph(
        book_id="gaddis_python_6e",
        concepts=[
            ConceptGraphEntry(
                term="function",
                definition="Named block.",
                first_introduced_in=5,
                also_used_in=[7, 10],
            )
        ],
    )
    storage.save_concept_graph(tmp_path, g)
    assert storage.load_concept_graph(tmp_path, g.book_id) == g


def test_atomic_write_leaves_no_partial(tmp_path: Path) -> None:
    """If the process dies mid-write, the final file should not exist or be whole."""
    target = tmp_path / "state.json"
    # First, a successful write so there's known good content.
    target.write_text('{"hello": "old"}')

    # Now simulate a mid-write crash: os.replace raises.
    with patch("textbook_companion.storage.os.replace", side_effect=RuntimeError("crash")):
        with pytest.raises(RuntimeError):
            storage._write_atomic(target, '{"hello": "new"}')

    # The final target still has the old content — not partial.
    assert target.read_text() == '{"hello": "old"}'

    # A .tmp file may linger but it's not the real file.
    stray = list(tmp_path.glob("*.tmp"))
    assert len(stray) <= 1
    assert all(p.suffix == ".tmp" for p in stray)


def test_atomic_write_overwrites_cleanly(tmp_path: Path) -> None:
    s = _sample_state()
    storage.save_session_state(tmp_path, s)
    s.current_chapter = 7
    storage.save_session_state(tmp_path, s)
    loaded = storage.load_session_state(tmp_path, s.book_id)
    assert loaded.current_chapter == 7

    # No leftover temp files.
    tmp_files = list((tmp_path / s.book_id).glob("*.tmp"))
    assert tmp_files == []


def test_append_log_one_line_per_entry(tmp_path: Path) -> None:
    log = storage.reading_log_path(tmp_path, "gaddis_python_6e")
    entries = [
        LogEntry(
            timestamp=f"2026-04-18T10:00:0{i}Z",
            book_id="gaddis_python_6e",
            chapter_num=5,
            entry_type="reflection",
            content=f"note {i}",
            metadata={"i": i},
        )
        for i in range(3)
    ]
    for e in entries:
        storage.append_log(log, e)

    with open(log, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 3
    # Each line is a complete JSON object (no file-level array).
    for line in lines:
        json.loads(line)
    # No newlines inside a record.
    for line in lines:
        assert line.count("\n") == 1

    loaded = storage.read_log(log)
    assert loaded == entries


def test_append_log_preserves_existing_lines(tmp_path: Path) -> None:
    log = storage.reading_log_path(tmp_path, "gaddis_python_6e")
    first = LogEntry(
        timestamp="t1", book_id="gaddis_python_6e", chapter_num=1,
        entry_type="reflection", content="first", metadata={},
    )
    second = LogEntry(
        timestamp="t2", book_id="gaddis_python_6e", chapter_num=1,
        entry_type="quiz_answer", content="second", metadata={},
    )
    storage.append_log(log, first)
    # Capture size after first write; second write must only add to the file.
    size_after_first = log.stat().st_size
    storage.append_log(log, second)
    assert log.stat().st_size > size_after_first
    assert storage.read_log(log) == [first, second]

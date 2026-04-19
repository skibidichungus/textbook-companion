"""Fixtures produce a consistent, loadable tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from textbook_companion import fixtures, storage
from textbook_companion.fixtures import BOOK_ID, CHAPTER_TITLES


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    fixtures.write_fixtures(tmp_path)
    return tmp_path


def test_book_overview_loads_with_15_chapters(data_root: Path) -> None:
    bo = storage.load_book_overview(data_root, BOOK_ID)
    assert bo.book_id == BOOK_ID
    assert bo.total_chapters == 15
    assert set(bo.chapter_titles.keys()) == set(range(1, 16))
    assert bo.chapter_titles[1] == CHAPTER_TITLES[1]
    assert bo.chapter_titles[15] == CHAPTER_TITLES[15]


def test_every_chapter_file_exists_and_loads(data_root: Path) -> None:
    for n in range(1, 16):
        ch = storage.load_chapter(data_root, BOOK_ID, n)
        assert ch.chapter_num == n
        assert ch.chapter_title == CHAPTER_TITLES[n]
        assert ch.one_line
        assert ch.overview


def test_populated_chapters_are_rich(data_root: Path) -> None:
    for n in range(1, 6):
        ch = storage.load_chapter(data_root, BOOK_ID, n)
        assert len(ch.key_concepts) >= 5, f"ch{n} should have >=5 key concepts"
        assert len(ch.code_patterns) >= 1, f"ch{n} should have code patterns"
        assert len(ch.worked_examples) >= 1, f"ch{n} should have worked examples"
        assert len(ch.common_pitfalls) >= 1, f"ch{n} should have pitfalls"
        assert len(ch.end_of_chapter_problems) >= 1, f"ch{n} should have problems"


def test_sparse_chapters_have_overview_even_if_empty_lists(data_root: Path) -> None:
    for n in range(6, 16):
        ch = storage.load_chapter(data_root, BOOK_ID, n)
        assert ch.one_line
        assert ch.overview
        # Sparse chapters are allowed empty lists, but must still be valid.


def test_chapter_dependencies_reference_real_chapters(data_root: Path) -> None:
    for n in range(1, 16):
        ch = storage.load_chapter(data_root, BOOK_ID, n)
        for dep in ch.depends_on_chapters:
            assert 1 <= dep < n, (
                f"ch{n} depends on ch{dep}, which must be an earlier real chapter"
            )


def test_concept_graph_loads(data_root: Path) -> None:
    graph = storage.load_concept_graph(data_root, BOOK_ID)
    assert graph.book_id == BOOK_ID
    assert len(graph.concepts) > 0


def test_concept_graph_references_real_chapters(data_root: Path) -> None:
    graph = storage.load_concept_graph(data_root, BOOK_ID)
    for entry in graph.concepts:
        assert 1 <= entry.first_introduced_in <= 15
        for n in entry.also_used_in:
            assert 1 <= n <= 15
            assert n > entry.first_introduced_in, (
                f"'{entry.term}' reuses in ch{n}, which must be after its intro "
                f"ch{entry.first_introduced_in}"
            )


def test_concept_graph_matches_populated_chapter_concepts(data_root: Path) -> None:
    """Every populated-chapter concept with also_used_in should appear in the graph."""
    graph = storage.load_concept_graph(data_root, BOOK_ID)
    graph_terms = {e.term: e for e in graph.concepts}
    for n in range(1, 6):
        ch = storage.load_chapter(data_root, BOOK_ID, n)
        for concept in ch.key_concepts:
            if concept.also_used_in:
                assert concept.term in graph_terms, (
                    f"ch{n} concept '{concept.term}' reuses {concept.also_used_in} "
                    f"but is missing from the concept graph"
                )
                ge = graph_terms[concept.term]
                assert ge.first_introduced_in == concept.first_introduced_in
                assert ge.also_used_in == concept.also_used_in


def test_initial_session_state(data_root: Path) -> None:
    s = storage.load_session_state(data_root, BOOK_ID)
    assert s.book_id == BOOK_ID
    assert s.current_chapter is None
    assert s.chapters_completed == {}
    assert s.struggle_flags == {}
    assert s.last_active  # non-empty ISO timestamp


def test_reading_log_exists_and_empty(data_root: Path) -> None:
    log = storage.reading_log_path(data_root, BOOK_ID)
    assert log.exists()
    assert log.read_text() == ""
    assert storage.read_log(log) == []


def test_write_fixtures_is_idempotent(tmp_path: Path) -> None:
    fixtures.write_fixtures(tmp_path)
    fixtures.write_fixtures(tmp_path)  # must not raise
    # And re-writing resets the reading log to empty (fresh slate semantics).
    log = storage.reading_log_path(tmp_path, BOOK_ID)
    assert log.read_text() == ""


def test_chapter_file_naming_is_zero_padded(data_root: Path) -> None:
    chapters_dir = storage.book_dir(data_root, BOOK_ID) / "chapters"
    names = sorted(p.name for p in chapters_dir.glob("ch*.json"))
    assert names == [f"ch{n:02d}.json" for n in range(1, 16)]

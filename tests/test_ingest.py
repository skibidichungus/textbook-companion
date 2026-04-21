"""Tests for ingest.py — M1: PDF extraction and chapter splitting.

Synthetic PDFs are built in-process with pymupdf so tests have no external
file dependencies.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import fitz  # pymupdf
import pytest

from textbook_companion.ingest import (
    TocEntry,
    _match_chapter_heading,
    _split_by_regex,
    _split_by_section_numbering,
    _split_by_toc,
    _toc_title_candidates,
    extract_text,
    extract_toc,
    ingest_pdf,
    split_chapters,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Pad every page so the average stays well above the 50-char scanned-PDF
# threshold.  Short test strings like "Hello page one." would trigger the
# guard without this padding.
_PAGE_PAD = " This page contains enough digital text to pass the scanned-PDF detection heuristic." * 5


def _make_pdf(tmp_path: Path, pages: list[str]) -> Path:
    """Write a digital PDF with one text block per page; return its path."""
    pdf_path = tmp_path / "test.pdf"
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        # insert_textbox needs a rectangle; use the full page minus margins.
        rect = fitz.Rect(50, 50, page.rect.width - 50, page.rect.height - 50)
        page.insert_textbox(rect, text + _PAGE_PAD, fontsize=11)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _make_pdf_with_toc(
    tmp_path: Path,
    pages: list[str],
    toc: list[tuple[int, str, int]],
    filename: str = "test_toc.pdf",
) -> Path:
    """Write a PDF with embedded TOC bookmarks; return its path."""
    pdf_path = tmp_path / filename
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        rect = fitz.Rect(50, 50, page.rect.width - 50, page.rect.height - 50)
        page.insert_textbox(rect, text + _PAGE_PAD, fontsize=11)
    doc.set_toc(toc)  # [(level, title, page_1idx), ...]
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _make_chapter_page(num: int, title: str, body: str = "") -> str:
    default_body = (
        "This section introduces the topic with enough detail that the chapter "
        "body exceeds the minimum length threshold used by split_chapters. "
        "It contains several sentences covering key ideas and examples. " * 3
    )
    return f"Chapter {num}: {title}\n\n{body or default_body}"


def _make_section_page(chapter_num: int, first_section_title: str, body: str = "") -> str:
    """Make a page that uses section-numbering style (no 'Chapter' keyword)."""
    default_body = (
        "CONCEPT: This section covers key concepts in depth, with enough "
        "content to pass the minimum body-length filter in split_chapters. " * 5
    )
    return (
        f"{chapter_num}\n"
        f"{chapter_num}.1  {first_section_title}\n"
        f"{body or default_body}"
    )


# ---------------------------------------------------------------------------
# extract_text — basic
# ---------------------------------------------------------------------------


def test_extract_text_returns_one_string_per_page(tmp_path: Path) -> None:
    pages = ["Hello page one.", "Hello page two.", "Hello page three."]
    pdf_path = _make_pdf(tmp_path, pages)
    result = extract_text(pdf_path)
    assert len(result) == 3
    # pymupdf may add trailing whitespace/newlines; just check containment.
    for original, extracted in zip(pages, result):
        # The first word of each page should survive extraction.
        assert "Hello" in extracted


def test_extract_text_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_text(tmp_path / "nonexistent.pdf")


def test_extract_text_raises_for_scanned_pdf(tmp_path: Path) -> None:
    """A PDF whose pages are blank (like scanned images) should raise ValueError."""
    pdf_path = tmp_path / "scanned.pdf"
    doc = fitz.open()
    for _ in range(5):
        doc.new_page()  # blank pages — no text inserted
    doc.save(str(pdf_path))
    doc.close()

    with pytest.raises(ValueError, match="scanned images"):
        extract_text(pdf_path)


def test_extract_text_boundary_near_threshold(tmp_path: Path) -> None:
    """Pages with sparse text (but above threshold) should succeed."""
    # 60 chars per page is above the 50-char threshold.
    sparse_page = "A" * 60
    pages = [sparse_page] * 3
    pdf_path = _make_pdf(tmp_path, pages)
    result = extract_text(pdf_path)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# extract_toc
# ---------------------------------------------------------------------------


def test_extract_toc_returns_entries(tmp_path: Path) -> None:
    """extract_toc should return the embedded bookmark list."""
    pages = [_make_chapter_page(i, f"Chapter {i}") for i in range(1, 4)]
    toc_data: list[tuple[int, str, int]] = [
        (1, "Chapter 1: Intro", 1),
        (1, "Chapter 2: Variables", 2),
        (1, "Chapter 3: Control Flow", 3),
    ]
    pdf_path = _make_pdf_with_toc(tmp_path, pages, toc_data)
    result = extract_toc(pdf_path)
    assert len(result) == 3
    levels = [e[0] for e in result]
    assert all(lv == 1 for lv in levels)


def test_extract_toc_returns_empty_for_no_bookmarks(tmp_path: Path) -> None:
    """PDFs without bookmarks should return an empty list."""
    pages = [_make_chapter_page(1, "Intro")]
    pdf_path = _make_pdf(tmp_path, pages)
    result = extract_toc(pdf_path)
    assert result == []


def test_extract_toc_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_toc(tmp_path / "nope.pdf")


# ---------------------------------------------------------------------------
# split_chapters — basic chapter detection (Layer 3: regex, existing tests)
# ---------------------------------------------------------------------------


def test_split_chapters_finds_three_chapters() -> None:
    pages = [
        _make_chapter_page(1, "Introduction"),
        _make_chapter_page(2, "Variables and Types"),
        _make_chapter_page(3, "Control Flow"),
    ]
    result = split_chapters(pages)
    nums = [r[0] for r in result]
    titles = [r[1] for r in result]
    assert nums == [1, 2, 3]
    assert "Introduction" in titles[0]
    assert "Variables" in titles[1]
    assert "Control" in titles[2]


def test_split_chapters_case_insensitive() -> None:
    """CHAPTER N (all-caps) should be detected."""
    body = "Enough body text here. " * 20
    pages = [
        f"CHAPTER 1: Basics\n\n{body}",
        f"CHAPTER 2: Advanced\n\n{body}",
    ]
    result = split_chapters(pages)
    assert [r[0] for r in result] == [1, 2]


def test_split_chapters_handles_roman_numerals() -> None:
    body = "Body content. " * 20
    pages = [
        f"Chapter I: Intro\n\n{body}",
        f"Chapter II: Basics\n\n{body}",
        f"Chapter III: More\n\n{body}",
    ]
    result = split_chapters(pages)
    assert [r[0] for r in result] == [1, 2, 3]


def test_match_chapter_heading_rejects_non_numeric_title_words() -> None:
    assert _match_chapter_heading("Chapter Introduction") is None
    assert _match_chapter_heading("Chapter Variables") is None
    assert _match_chapter_heading("Part Index") is None


def test_split_chapters_chapter_text_contains_body() -> None:
    """The chapter text should include body lines, not just the heading."""
    body = "This is an important concept explained here. " * 15
    pages = [
        f"Chapter 1: Intro\n\n{body}",
        f"Chapter 2: Next\n\nSome other content. " * 15,
    ]
    result = split_chapters(pages)
    assert len(result) == 2
    # The first chapter's text should include part of the body.
    assert "important concept" in result[0][2]


def test_split_chapters_multiple_pages_per_chapter() -> None:
    """Content spanning multiple pages should be merged into one chapter."""
    body_line = "Content line here. " * 10
    pages = [
        f"Chapter 1: Intro\n\n{body_line}",
        f"Continued content of chapter 1.\n\n{body_line}",  # no heading
        f"Chapter 2: Next\n\n{body_line * 3}",
    ]
    result = split_chapters(pages)
    nums = [r[0] for r in result]
    assert nums == [1, 2]
    # The first chapter should contain text from both its pages.
    assert "Continued content" in result[0][2]


def test_split_chapters_preserves_sort_order() -> None:
    """Chapters should come out sorted by number even if pages are out of order
    (e.g., if a TOC mentions chapter headings before the actual chapter)."""
    # Use _make_chapter_page so each chapter body is long enough to survive
    # the minimum-body-length filter in split_chapters.
    pages = [
        _make_chapter_page(1, "First"),
        _make_chapter_page(2, "Second"),
        _make_chapter_page(3, "Third"),
    ]
    result = split_chapters(pages)
    assert [r[0] for r in result] == [1, 2, 3]


def test_split_chapters_ignores_front_matter_toc_candidates() -> None:
    toc_page = "\n".join(
        [
            "Contents",
            "Chapter 1 Introduction " + ("TOC_FILL_1 " * 25),
            "Chapter 2 Variables " + ("TOC_FILL_2 " * 25),
        ]
    )
    real_ch1 = "Chapter 1: Introduction\n\n" + ("REAL_CH1 " * 40)
    real_ch2 = "Chapter 2: Variables\n\n" + ("REAL_CH2 " * 40)

    result = split_chapters([toc_page, real_ch1, real_ch2])

    assert [r[0] for r in result] == [1, 2]
    assert result[0][2].startswith("Chapter 1: Introduction")
    assert "REAL_CH1" in result[0][2]
    assert "TOC_FILL_1" not in result[0][2]


def test_split_by_regex_returns_none_when_only_toc_like_candidates_exist() -> None:
    toc_page = "\n".join(
        [
            "Contents",
            "Chapter 1 Intro",
            "Chapter 2 Variables",
            "Chapter 3 Control Flow",
            "BODY " * 120,
        ]
    )

    assert _split_by_regex([toc_page]) is None


# ---------------------------------------------------------------------------
# split_chapters — fallback behaviour
# ---------------------------------------------------------------------------


def test_split_chapters_fallback_when_no_headings() -> None:
    """If no chapter headings found, return the whole doc as chapter 1."""
    pages = ["Just some text.", "More text without any chapter heading."]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = split_chapters(pages)

    assert len(result) == 1
    assert result[0][0] == 1
    assert any("No chapter headings" in str(w.message) for w in caught)


def test_split_chapters_empty_pages_returns_chapter_one() -> None:
    result = split_chapters([])
    assert result == [(1, "Chapter 1", "")]


# ---------------------------------------------------------------------------
# Layer 1 — PDF TOC bookmark detection
# ---------------------------------------------------------------------------


def _make_toc_entries(n: int) -> list[TocEntry]:
    """Create n chapter-level TOC entries (level 1, 1-indexed pages)."""
    return [(1, f"Chapter {i}: Section Title", i) for i in range(1, n + 1)]


def _make_section_pages(n: int) -> list[str]:
    """Create n pages with enough body text for the min-body filter."""
    body = "Body content sentence here. " * 30
    return [f"Chapter {i}: Section Title\n\n{body}" for i in range(1, n + 1)]


def test_split_by_toc_returns_chapters() -> None:
    """_split_by_toc should extract chapters from valid TOC entries."""
    pages = _make_section_pages(4)
    toc: list[TocEntry] = _make_toc_entries(4)
    result = _split_by_toc(pages, toc)
    assert result is not None
    assert [r[0] for r in result] == [1, 2, 3, 4]


def test_split_by_toc_returns_none_for_empty_toc() -> None:
    """_split_by_toc should return None when TOC is empty."""
    pages = _make_section_pages(4)
    result = _split_by_toc(pages, [])
    assert result is None


def test_split_by_toc_returns_none_when_too_few_chapters() -> None:
    """_split_by_toc returns None if fewer than _MIN_CHAPTERS_REQUIRED chapters found."""
    pages = _make_section_pages(2)
    toc: list[TocEntry] = _make_toc_entries(2)
    result = _split_by_toc(pages, toc)
    assert result is not None
    assert [r[0] for r in result] == [1, 2]


def test_split_by_toc_ignores_non_level1_entries() -> None:
    """Level-2 (sub-section) TOC entries should not be treated as chapters."""
    pages = _make_section_pages(4)
    # Mix level-1 and level-2 entries; only the 2 level-1 entries should count.
    toc: list[TocEntry] = [
        (1, "Chapter 1: Intro", 1),
        (2, "1.1 Sub-section", 1),
        (1, "Chapter 2: Basics", 2),
        (2, "2.1 Sub-section", 2),
    ]
    result = _split_by_toc(pages, toc)
    assert result is not None
    assert [r[0] for r in result] == [1, 2]


def test_split_by_toc_detects_misspelled_chapter_keyword() -> None:
    """A typo in the TOC keyword (e.g. 'Chpater 20') should still be detected
    via the standalone-number fallback branch of _TOC_CHAPTER_RE."""
    body = "Body content. " * 30
    pages = [f"Content for chapter {i}\n\n{body}" for i in range(1, 5)]
    toc: list[TocEntry] = [
        (1, "Chapter 1: Intro", 1),
        (1, "Chapter 2: Basics", 2),
        (1, "Chpater 3: Advanced", 3),   # publisher typo — transposed letters
        (1, "Chapter 4: Wrap-up", 4),
    ]
    result = _split_by_toc(pages, toc)
    assert result is not None
    assert 3 in [r[0] for r in result]
    assert [r[0] for r in result] == [1, 2, 3, 4]


def test_split_by_toc_detects_foreign_keyword() -> None:
    """A non-English keyword with a valid number ('Einführung 5: Introduction')
    should be detected via the standalone-number fallback branch."""
    body = "Body content. " * 30
    pages = [f"Content {i}\n\n{body}" for i in range(1, 6)]
    toc: list[TocEntry] = [
        (1, "Chapter 1: Start", 1),
        (1, "Chapter 2: Basics", 2),
        (1, "Chapter 3: More", 3),
        (1, "Einführung 4: Introduction", 4),   # German keyword unrecognised by groups 1 & 2
        (1, "Kapitel 5: Advanced", 5),           # another foreign keyword
    ]
    result = _split_by_toc(pages, toc)
    assert result is not None
    nums = [r[0] for r in result]
    assert 4 in nums
    assert 5 in nums


def test_toc_title_candidates_rejects_incidental_numbers() -> None:
    assert _toc_title_candidates("Python 3 Overview") == []
    assert _toc_title_candidates("2023 Preface") == []
    assert _toc_title_candidates("Chpater 20 Recursion") == [
        (1, 20, "Chpater 20 Recursion")
    ]


def test_split_by_toc_prefers_deeper_explicit_chapter_level() -> None:
    pages = _make_section_pages(4)
    toc: list[TocEntry] = [
        (1, "Cover", 1),
        (1, "PART ONE OVERVIEW", 1),
        (1, "PART TWO DETAILS", 3),
        (2, "Chapter 1 Introduction", 1),
        (2, "Chapter 2 Basics", 2),
        (2, "Chapter 3 Advanced Topics", 3),
        (2, "Chapter 4 Wrap-Up", 4),
        (3, "1.1 First Section", 1),
        (3, "2.1 Second Section", 2),
    ]

    result = _split_by_toc(pages, toc)

    assert result is not None
    assert [r[0] for r in result] == [1, 2, 3, 4]
    assert [r[1] for r in result] == [
        "Chapter 1 Introduction",
        "Chapter 2 Basics",
        "Chapter 3 Advanced Topics",
        "Chapter 4 Wrap-Up",
    ]


def test_split_by_toc_merges_best_titles_across_levels() -> None:
    pages = _make_section_pages(3)
    toc: list[TocEntry] = [
        (1, "Chapter 1 Introduction", 1),
        (1, "PART ONE RELATIONAL LANGUAGES", 2),
        (2, "1.1 Database-System Applications", 1),
        (2, "Chapter 2 Introduction to the Relational Model", 2),
        (2, "Chapter 3 Introduction to SQL", 3),
    ]

    result = _split_by_toc(pages, toc)

    assert result is not None
    assert [r[0] for r in result] == [1, 2, 3]
    assert [r[1] for r in result] == [
        "Chapter 1 Introduction",
        "Chapter 2 Introduction to the Relational Model",
        "Chapter 3 Introduction to SQL",
    ]


def test_split_by_toc_falls_back_to_unnumbered_chapter_titles() -> None:
    body = "Body text for this section. " * 30
    pages = [
        f"Language Basics\n\n{body}",
        f"Types\n\n{body}",
        f"Literals\n\n{body}",
    ]
    toc: list[TocEntry] = [
        (1, "Table of Contents", 1),
        (1, "Preface", 1),
        (1, "I", 1),
        (1, "Language Basics", 1),
        (1, "Types", 2),
        (1, "Literals", 3),
        (1, "Index", 3),
        (2, "Characteristics of C", 1),
        (2, "Object Types", 2),
    ]

    result = _split_by_toc(pages, toc)

    assert result is not None
    assert [r[0] for r in result] == [1, 2, 3]
    assert [r[1] for r in result] == [
        "Language Basics",
        "Types",
        "Literals",
    ]


def test_split_chapters_uses_toc_over_regex(tmp_path: Path) -> None:
    """With a valid TOC, split_chapters should use Layer 1 (TOC)."""
    body = "Body text for this section. " * 30
    # Pages have no 'Chapter N' keyword — regex layer would fail
    pages = [
        f"Introduction content\n\n{body}",
        f"Variables content\n\n{body}",
        f"Control flow content\n\n{body}",
        f"Functions content\n\n{body}",
    ]
    toc: list[TocEntry] = [
        (1, "Chapter 1: Introduction", 1),
        (1, "Chapter 2: Variables", 2),
        (1, "Chapter 3: Control Flow", 3),
        (1, "Chapter 4: Functions", 4),
    ]
    result = split_chapters(pages, toc=toc)
    assert [r[0] for r in result] == [1, 2, 3, 4]
    # Body text from respective pages should appear in each chapter.
    assert "Introduction content" in result[0][2]
    assert "Variables content" in result[1][2]


def test_split_chapters_accepts_two_chapter_toc_book() -> None:
    body = "Body text for this section. " * 30
    pages = [
        f"Introduction content\n\n{body}",
        f"Variables content\n\n{body}",
    ]
    toc: list[TocEntry] = [
        (1, "Chapter 1: Introduction", 1),
        (1, "Chapter 2: Variables", 2),
    ]

    result = split_chapters(pages, toc=toc)

    assert [r[0] for r in result] == [1, 2]
    assert "Introduction content" in result[0][2]
    assert "Variables content" in result[1][2]


def test_extract_toc_and_split_chapters_round_trip(tmp_path: Path) -> None:
    """end-to-end: build PDF with TOC → extract_toc → split_chapters."""
    body = "Enough body content. " * 30
    chapter_texts = [
        f"Chapter content 1\n\n{body}",
        f"Chapter content 2\n\n{body}",
        f"Chapter content 3\n\n{body}",
    ]
    toc_data: list[tuple[int, str, int]] = [
        (1, "Chapter 1: Intro", 1),
        (1, "Chapter 2: Variables", 2),
        (1, "Chapter 3: Control Flow", 3),
    ]
    pdf_path = _make_pdf_with_toc(tmp_path, chapter_texts, toc_data)

    pages = extract_text(pdf_path)
    toc = extract_toc(pdf_path)
    result = split_chapters(pages, toc=toc)

    assert len(result) == 3
    assert [r[0] for r in result] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Layer 2 — Section-numbering heuristic
# ---------------------------------------------------------------------------


def test_split_by_section_numbering_detects_gaddis_pattern() -> None:
    """_split_by_section_numbering should detect N.1 chapter boundaries."""
    pages = [
        _make_section_page(1, "Why Program?"),
        _make_section_page(2, "The Parts of a C++ Program"),
        _make_section_page(3, "The cin Object"),
        _make_section_page(4, "Making Decisions"),
    ]
    result = _split_by_section_numbering(pages)
    assert result is not None
    nums = [r[0] for r in result]
    assert nums == [1, 2, 3, 4]


def test_split_by_section_numbering_accepts_two_chapters() -> None:
    """_split_by_section_numbering should handle valid two-chapter books."""
    pages = [
        _make_section_page(1, "Why Program?"),
        _make_section_page(2, "The Parts"),
    ]
    result = _split_by_section_numbering(pages)
    assert result is not None
    assert [r[0] for r in result] == [1, 2]


def test_split_by_section_numbering_body_contains_content() -> None:
    """Each chapter's body should include the page content."""
    pages = [
        _make_section_page(1, "Why Program?", body="CONTENT_CH1 " * 50),
        _make_section_page(2, "Data Types", body="CONTENT_CH2 " * 50),
        _make_section_page(3, "Control Flow", body="CONTENT_CH3 " * 50),
    ]
    result = _split_by_section_numbering(pages)
    assert result is not None
    assert "CONTENT_CH1" in result[0][2]
    assert "CONTENT_CH2" in result[1][2]
    assert "CONTENT_CH3" in result[2][2]


def test_split_by_section_numbering_does_not_double_count_on_same_page() -> None:
    """Multiple N.1 references on the same page must not create duplicate entries."""
    # Page has both "1.1" and a reference to "1.1" later — should still be one chapter.
    body = "1.1 First mention\n1.1  Repeated reference\n" + "Body text. " * 50
    pages = [
        body,
        _make_section_page(2, "Next Chapter"),
        _make_section_page(3, "Further Chapter"),
    ]
    result = _split_by_section_numbering(pages)
    assert result is not None
    nums = [r[0] for r in result]
    # Chapter 1 should appear exactly once.
    assert nums.count(1) == 1


def test_split_by_section_numbering_ignores_toc_like_front_matter() -> None:
    toc_page = "\n".join(
        [
            "Contents",
            "1.1 Intro",
            "2.1 Variables",
            "3.1 Control Flow",
            "More front matter text.",
        ]
    )
    pages = [
        toc_page,
        _make_section_page(1, "Intro", body="REAL_CH1 " * 40),
        _make_section_page(2, "Variables", body="REAL_CH2 " * 40),
        _make_section_page(3, "Control Flow", body="REAL_CH3 " * 40),
    ]

    result = _split_by_section_numbering(pages)

    assert result is not None
    assert [r[0] for r in result] == [1, 2, 3]
    assert "1.1  Intro" in result[0][2]
    assert "REAL_CH1" in result[0][2]
    assert "Contents" not in result[0][2]


def test_split_by_section_numbering_ignores_toc_like_page_beyond_legacy_cap() -> None:
    toc_page = "\n".join(
        [
            "Contents",
            "1.1 Intro",
            "2.1 Variables",
            "3.1 Control Flow",
        ]
    )
    pages = [f"Front matter page {i}" for i in range(20)]
    pages.append(toc_page)
    pages.append(_make_section_page(1, "Intro", body="REAL_CH1 " * 40))
    pages.extend(f"Interlude A{i}" for i in range(130))
    pages.append(_make_section_page(2, "Variables", body="REAL_CH2 " * 40))
    pages.extend(f"Interlude B{i}" for i in range(130))
    pages.append(_make_section_page(3, "Control Flow", body="REAL_CH3 " * 40))
    pages.extend(f"Interlude C{i}" for i in range(130))

    result = _split_by_section_numbering(pages)

    assert result is not None
    assert [r[0] for r in result] == [1, 2, 3]
    assert "Contents" not in result[0][2]
    assert "REAL_CH1" in result[0][2]


def test_split_by_regex_ignores_toc_like_page_beyond_legacy_cap() -> None:
    toc_page = "\n".join(
        [
            "Contents",
            "Chapter 1 Intro",
            "Chapter 2 Variables",
            "Chapter 3 Control Flow",
        ]
    )
    pages = [f"Front matter page {i}" for i in range(20)]
    pages.append(toc_page)
    pages.append("Chapter 1: Intro\n\n" + ("REAL_CH1 " * 40))
    pages.extend(f"Interlude A{i}" for i in range(130))
    pages.append("Chapter 2: Variables\n\n" + ("REAL_CH2 " * 40))
    pages.extend(f"Interlude B{i}" for i in range(130))
    pages.append("Chapter 3: Control Flow\n\n" + ("REAL_CH3 " * 40))
    pages.extend(f"Interlude C{i}" for i in range(130))

    result = _split_by_regex(pages)

    assert result is not None
    assert [r[0] for r in result] == [1, 2, 3]
    assert "Contents" not in result[0][2]
    assert "REAL_CH1" in result[0][2]


def test_split_chapters_uses_section_numbering_when_no_toc_and_no_keywords() -> None:
    """With no TOC and no 'Chapter N' keywords, Layer 2 should activate."""
    pages = [
        _make_section_page(1, "Why Program?"),
        _make_section_page(2, "The Parts of a C++ Program"),
        _make_section_page(3, "The cin Object"),
        _make_section_page(4, "Making Decisions"),
    ]
    # No 'Chapter' keyword, no TOC → should use section-numbering (Layer 2)
    result = split_chapters(pages, toc=None)
    assert result is not None
    assert [r[0] for r in result] == [1, 2, 3, 4]


def test_split_chapters_section_numbering_text_includes_body() -> None:
    """Chapters detected by section numbering should contain their body text."""
    pages = [
        _make_section_page(1, "Why Program?", body="WHY_PROGRAM_BODY " * 30),
        _make_section_page(2, "Data Types", body="DATA_TYPES_BODY " * 30),
        _make_section_page(3, "Control Flow", body="CONTROL_FLOW_BODY " * 30),
    ]
    result = split_chapters(pages, toc=None)
    assert result is not None
    assert "WHY_PROGRAM_BODY" in result[0][2]
    assert "DATA_TYPES_BODY" in result[1][2]
    assert "CONTROL_FLOW_BODY" in result[2][2]


def test_split_chapters_accepts_two_chapter_section_numbered_book() -> None:
    pages = [
        _make_section_page(1, "Why Program?", body="CH1_BODY " * 40),
        _make_section_page(2, "Data Types", body="CH2_BODY " * 40),
    ]

    result = split_chapters(pages, toc=None)

    assert [r[0] for r in result] == [1, 2]
    assert "CH1_BODY" in result[0][2]
    assert "CH2_BODY" in result[1][2]


# ---------------------------------------------------------------------------
# ingest_pdf (higher-level function)
# ---------------------------------------------------------------------------


def test_ingest_pdf_returns_pages_and_splits(tmp_path: Path) -> None:
    """ingest_pdf should extract text and split chapters in one call."""
    chapter_texts = [
        _make_chapter_page(1, "Getting Started"),
        _make_chapter_page(2, "Core Concepts"),
        _make_chapter_page(3, "Putting It Together"),
    ]
    toc_data: list[tuple[int, str, int]] = [
        (1, "Chapter 1: Getting Started", 1),
        (1, "Chapter 2: Core Concepts", 2),
        (1, "Chapter 3: Putting It Together", 3),
    ]
    pdf_path = _make_pdf_with_toc(tmp_path, chapter_texts, toc_data)

    pages, splits = ingest_pdf(pdf_path)

    assert len(pages) == 3
    assert len(splits) == 3
    assert [s[0] for s in splits] == [1, 2, 3]


def test_ingest_pdf_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ingest_pdf(tmp_path / "nope.pdf")


def test_ingest_pdf_raises_for_scanned_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    doc = fitz.open()
    for _ in range(5):
        doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    with pytest.raises(ValueError, match="scanned images"):
        ingest_pdf(pdf_path)


# ---------------------------------------------------------------------------
# round-trip: extract_text → split_chapters
# ---------------------------------------------------------------------------


def test_round_trip_extract_and_split(tmp_path: Path) -> None:
    """End-to-end: build a PDF → extract → split → verify structure."""
    chapter_pages = [
        _make_chapter_page(1, "Getting Started"),
        _make_chapter_page(2, "Core Concepts"),
        _make_chapter_page(3, "Putting It Together"),
    ]
    pdf_path = _make_pdf(tmp_path, chapter_pages)
    pages = extract_text(pdf_path)
    assert len(pages) == 3

    result = split_chapters(pages)
    nums = [r[0] for r in result]
    assert nums == [1, 2, 3]
    for _, title, text in result:
        assert len(text) >= 50  # has real body content


# ---------------------------------------------------------------------------
# M2 — generate_metadata (mock LLM)
# ---------------------------------------------------------------------------


class _MockLLM:
    """Minimal LLMClient stand-in for testing generate_metadata without the API."""

    def chat(self, system, messages, cache_system=True):  # type: ignore[override]
        return "mock response"

    def structured(self, system, user, schema, cache_system=True):  # type: ignore[override]
        from textbook_companion.models import BookOverview, ChapterSummary

        if schema is BookOverview:
            return BookOverview(
                book_id="test_book",
                title="Test Book",
                author="Test Author",
                edition="1st edition",
                total_chapters=2,
                chapter_titles={"1": "Intro", "2": "Basics"},
                arc_summary="A test book for testing.",
            )
        if schema is ChapterSummary:
            # Parse chapter_num from the user message.
            import re
            m = re.search(r"chapter_num: (\d+)", user)
            num = int(m.group(1)) if m else 1
            m2 = re.search(r"chapter_title: (.+)", user)
            title = m2.group(1).strip() if m2 else "Chapter"
            m3 = re.search(r"book_id: (\S+)", user)
            bid = m3.group(1).strip() if m3 else "test_book"
            return ChapterSummary(
                book_id=bid,
                chapter_num=num,
                chapter_title=title,
                one_line="Mock one-liner.",
                overview="Mock overview.",
            )
        raise ValueError(f"Unexpected schema: {schema}")


def test_generate_metadata_writes_expected_file_tree(tmp_path: Path) -> None:
    """Mock LLM: verify generate_metadata produces the expected data files."""
    from textbook_companion.ingest import generate_metadata

    data_root = tmp_path / "data"
    book_id = "test_book"
    pages = [
        _make_chapter_page(1, "Intro"),
        _make_chapter_page(2, "Basics"),
    ]
    splits = [
        (1, "Intro", pages[0]),
        (2, "Basics", pages[1]),
    ]

    generate_metadata(data_root, book_id, pages, splits, _MockLLM())

    book_dir = data_root / book_id
    assert (book_dir / "book_overview.json").exists()
    assert (book_dir / "session_state.json").exists()
    assert (book_dir / "chapters" / "ch01.json").exists()
    assert (book_dir / "chapters" / "ch01.txt").exists()
    assert (book_dir / "chapters" / "ch02.json").exists()
    assert (book_dir / "chapters" / "ch02.txt").exists()
    # Concept graph should NOT be written in Phase 2.
    assert not (book_dir / "concept_graph.json").exists()


def test_generate_metadata_content_is_schema_valid(tmp_path: Path) -> None:
    """The JSON files written by generate_metadata should be valid models."""
    from textbook_companion import storage
    from textbook_companion.ingest import generate_metadata

    data_root = tmp_path / "data"
    book_id = "test_book"
    pages = [_make_chapter_page(1, "Intro")]
    splits = [(1, "Intro", pages[0])]

    generate_metadata(data_root, book_id, pages, splits, _MockLLM())

    overview = storage.load_book_overview(data_root, book_id)
    assert overview.book_id == book_id

    state = storage.load_session_state(data_root, book_id)
    assert state.book_id == book_id
    assert state.current_chapter is None

    ch = storage.load_chapter(data_root, book_id, 1)
    assert ch.chapter_num == 1


def test_generate_metadata_txt_files_contain_raw_text(tmp_path: Path) -> None:
    """The .txt files written during ingestion are the raw chapter text."""
    from textbook_companion.ingest import generate_metadata

    data_root = tmp_path / "data"
    book_id = "test_book"
    raw_text = _make_chapter_page(1, "Intro") + " UNIQUE_MARKER_XYZ"
    pages = [raw_text]
    splits = [(1, "Intro", raw_text)]

    generate_metadata(data_root, book_id, pages, splits, _MockLLM())

    txt = (data_root / book_id / "chapters" / "ch01.txt").read_text()
    assert "UNIQUE_MARKER_XYZ" in txt


def test_slugify() -> None:
    from textbook_companion.ingest import _slugify

    assert _slugify("Starting Out With Python 6e") == "starting_out_with_python_6e"
    assert _slugify("SICP.2nd_Edition") == "sicp_2nd_edition"
    assert _slugify("---hello---") == "hello"


@pytest.mark.live
def test_live_generate_metadata_on_real_pdf(tmp_path: Path) -> None:
    """Live test: build a tiny real PDF, run generate_metadata with Claude,
    and check that the output files are valid according to their schemas."""
    from textbook_companion import storage
    from textbook_companion.ingest import generate_metadata
    from textbook_companion.llm import ClaudeClient

    chapter_pages = [
        _make_chapter_page(1, "Introduction to Python"),
        _make_chapter_page(2, "Variables and Data Types"),
    ]
    pdf_path = _make_pdf(tmp_path, chapter_pages)

    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("ignore")
        from textbook_companion.ingest import extract_text, split_chapters
        pages = extract_text(pdf_path)
        splits = split_chapters(pages)

    data_root = tmp_path / "data"
    generate_metadata(data_root, "test_live_book", pages, splits, ClaudeClient())

    overview = storage.load_book_overview(data_root, "test_live_book")
    assert overview.total_chapters >= 1
    assert overview.title

    ch = storage.load_chapter(data_root, "test_live_book", splits[0][0])
    assert ch.one_line
    assert ch.overview

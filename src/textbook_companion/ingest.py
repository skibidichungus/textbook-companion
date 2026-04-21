"""PDF ingestion pipeline for the textbook companion.

M1: text extraction and chapter splitting. No LLM calls.
M2: LLM-powered book overview and chapter summaries; CLI entry point.

Public API:
    extract_text(pdf_path)       -> list[str]                  one string per page
    extract_toc(pdf_path)        -> list[tuple[int,str,int]]   TOC entries (level, title, page_1idx)
    split_chapters(pages, toc)   -> list[tuple[int,str,str]]   (num, title, text)
    ingest_pdf(pdf_path)         -> tuple[list[str], list[...]] pages + chapter splits
    generate_metadata(...)       -> None                        writes all data files

CLI usage:
    uv run python -m textbook_companion.ingest path/to/textbook.pdf
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import fitz  # pymupdf

if TYPE_CHECKING:
    from .llm import LLMClient

from . import storage
from .models import BookOverview, ChapterSummary, SessionState


# Heuristic: if the average extracted characters per page is below this
# threshold, the PDF is likely scanned images rather than digital text.
_SCAN_THRESHOLD_CHARS_PER_PAGE = 50

# Early pages are the likeliest place for a table of contents or front matter
# to mention many chapter headings before the real chapter 1 begins.
_FRONT_MATTER_MAX_PAGE = 15

# Minimum number of chapters we require before accepting a detection strategy.
# If a strategy finds fewer than this, we fall through to the next layer.
_MIN_CHAPTERS_REQUIRED = 3


def extract_text(pdf_path: Path) -> list[str]:
    """Return one text string per page.

    Raises:
        FileNotFoundError: if pdf_path does not exist.
        ValueError: if the PDF appears to be scanned images (avg chars/page
            below ``_SCAN_THRESHOLD_CHARS_PER_PAGE``).
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages: list[str] = []
    try:
        for page in doc:
            pages.append(page.get_text())
    finally:
        doc.close()

    if not pages:
        return pages

    avg_chars = sum(len(p) for p in pages) / len(pages)
    if avg_chars < _SCAN_THRESHOLD_CHARS_PER_PAGE:
        raise ValueError(
            "This PDF appears to be scanned images. "
            "OCR is not supported yet. "
            f"(Average {avg_chars:.1f} chars/page; "
            f"threshold is {_SCAN_THRESHOLD_CHARS_PER_PAGE}.)"
        )

    return pages


# TOC entry: (level, title, page_number)  — page_number is 1-indexed as
# returned by fitz.Document.get_toc().
TocEntry = tuple[int, str, int]


def extract_toc(pdf_path: Path) -> list[TocEntry]:
    """Return the PDF's embedded TOC (bookmark tree).

    Each entry is ``(level, title, page_1idx)`` where ``level`` is 1 for
    top-level entries, 2 for sub-entries, etc., and ``page_1idx`` is the
    1-based page number the bookmark points to.

    Returns an empty list if the PDF has no embedded bookmark tree.

    Raises:
        FileNotFoundError: if pdf_path does not exist.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    try:
        toc: list[TocEntry] = [(lv, title, pg) for lv, title, pg in doc.get_toc(simple=True)]
    finally:
        doc.close()
    return toc


def ingest_pdf(pdf_path: Path) -> tuple[list[str], list[tuple[int, str, str]]]:
    """Open the PDF once, extract both text and TOC, and split chapters.

    This is the preferred high-level entry point: it avoids opening the file
    twice and passes TOC data through to ``split_chapters`` automatically.

    Returns:
        ``(pages, chapter_splits)`` where *pages* is one string per PDF page
        and *chapter_splits* is ``[(num, title, text), ...]``.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(str(pdf_path))
    pages: list[str] = []
    toc: list[TocEntry] = []
    try:
        for page in doc:
            pages.append(page.get_text())
        toc = [(lv, title, pg) for lv, title, pg in doc.get_toc(simple=True)]
    finally:
        doc.close()

    if not pages:
        return pages, [(1, "Chapter 1", "")]

    avg_chars = sum(len(p) for p in pages) / len(pages)
    if avg_chars < _SCAN_THRESHOLD_CHARS_PER_PAGE:
        raise ValueError(
            "This PDF appears to be scanned images. "
            "OCR is not supported yet. "
            f"(Average {avg_chars:.1f} chars/page; "
            f"threshold is {_SCAN_THRESHOLD_CHARS_PER_PAGE}.)"
        )

    splits = split_chapters(pages, toc=toc)
    return pages, splits


# ---------------------------------------------------------------------------
# Chapter splitting
# ---------------------------------------------------------------------------

# Patterns that mark the start of a new chapter heading.
# Priority order: the first match wins for each line.
#   Group 1 (number): decimal digits OR roman numerals
#   Group 2 (rest):   optional title text on the same line
_CHAPTER_PATTERNS: list[re.Pattern[str]] = [
    # "Chapter 3: Title" / "CHAPTER 3 Title" / "Chapter III"
    re.compile(
        r"^\s*(?:chapter|ch\.?)\s+"
        r"((?:[IVXLCDM]+|\d+))"  # roman or decimal
        r"(?=$|[:\s\-–—])"      # token must end before title text begins
        r"[:\s\-–—]*(.*)",
        re.IGNORECASE,
    ),
    # "Part 2 — Title" (some books use Part instead of Chapter)
    re.compile(
        r"^\s*part\s+"
        r"((?:[IVXLCDM]+|\d+))"
        r"(?=$|[:\s\-–—])"
        r"[:\s\-–—]*(.*)",
        re.IGNORECASE,
    ),
]

# Minimum token of text (rough) before a "chapter" heading is considered
# real content (avoids treating a cover-page mention as ch1).
_MIN_CHAPTER_BODY_CHARS = 200

# Regex for section-number heuristic: a line that is *exactly* "N.1" (or
# "N.1 <optional title>"), where N is a positive integer and the ".1" restart
# signals a new chapter.  We allow optional leading whitespace and require
# that "1" is the sub-section index (not "2", "3", …).
_SECTION_ONE_RE = re.compile(
    r"^\s*(\d+)\.1(?:\s+.*)?$"
)

# TOC title patterns that look like chapter entries (contain a chapter number
# or the words Chapter/Part).
_TOC_CHAPTER_RE = re.compile(
    r"(?:chapter|part)\s+(\d+|[IVXLCDM]+)"  # group 1: keyword + number
    r"|^(\d+)\s+\S"                           # group 2: bare leading number
    r"|\b(\d{1,3})\b",                        # group 3: any standalone number (typos/foreign)
    re.IGNORECASE,
)


def _parse_chapter_num(token: str) -> int:
    """Convert a decimal string or Roman numeral to int."""
    token = token.strip().upper()
    if token.isdigit():
        return int(token)
    # Roman numeral decoder (handles I–MMMCMXCIX)
    roman_values = {
        "M": 1000, "CM": 900, "D": 500, "CD": 400,
        "C": 100, "XC": 90, "L": 50, "XL": 40,
        "X": 10, "IX": 9, "V": 5, "IV": 4, "I": 1,
    }
    result = 0
    i = 0
    while i < len(token):
        two = token[i : i + 2]
        if two in roman_values:
            result += roman_values[two]
            i += 2
        elif token[i] in roman_values:
            result += roman_values[token[i]]
            i += 1
        else:
            # Not a recognisable Roman numeral — treat as 0 so the caller
            # can discard this match.
            return 0
    return result


def _match_chapter_heading(line: str) -> tuple[int, str] | None:
    """Return (chapter_num, title) if the line is a chapter heading, else None."""
    for pattern in _CHAPTER_PATTERNS:
        m = pattern.match(line)
        if m:
            num = _parse_chapter_num(m.group(1))
            if num > 0:
                title = m.group(2).strip().rstrip(":").strip()
                return num, title
    return None


# ---------------------------------------------------------------------------
# Layer 1 — PDF TOC bookmarks
# ---------------------------------------------------------------------------

def _split_by_toc(
    pages: list[str],
    toc: list[TocEntry],
) -> list[tuple[int, str, str]] | None:
    """Attempt chapter splitting via embedded PDF TOC bookmarks.

    Returns a list of ``(chapter_num, title, text)`` tuples if at least
    ``_MIN_CHAPTERS_REQUIRED`` chapter-level entries are found, otherwise
    returns ``None`` to signal that the next layer should be tried.

    Only level-1 TOC entries whose titles look like chapter headings are
    considered. The page numbers in the TOC are 1-indexed; we convert to
    0-indexed before slicing ``pages``.
    """
    if not toc:
        return None

    # Filter to level-1 entries that look like chapters.
    chapter_entries: list[tuple[int, str, int]] = []  # (chapter_num, title, page_0idx)
    for level, title, pg_1idx in toc:
        if level != 1:
            continue
        m = _TOC_CHAPTER_RE.search(title)
        if not m:
            continue
        # Extract chapter number from whichever group matched.
        num_token = m.group(1) or m.group(2) or m.group(3) or ""
        num = _parse_chapter_num(num_token)
        if num <= 0:
            continue
        page_0idx = max(0, pg_1idx - 1)
        chapter_entries.append((num, title.strip(), page_0idx))

    if len(chapter_entries) < _MIN_CHAPTERS_REQUIRED:
        return None

    # Sort by page order (not chapter number) in case the TOC is reordered.
    chapter_entries.sort(key=lambda e: e[2])

    # Remove duplicates by chapter number (keep first occurrence).
    seen: set[int] = set()
    unique: list[tuple[int, str, int]] = []
    for num, title, pg in chapter_entries:
        if num not in seen:
            seen.add(num)
            unique.append((num, title, pg))
    chapter_entries = unique

    # Build flat text and page-start offsets.
    page_starts, flat = _build_flat(pages)

    results: list[tuple[int, str, str]] = []
    for i, (num, title, pg_0) in enumerate(chapter_entries):
        start = page_starts[pg_0] if pg_0 < len(page_starts) else len(flat)
        if i + 1 < len(chapter_entries):
            next_pg = chapter_entries[i + 1][2]
            end = page_starts[next_pg] if next_pg < len(page_starts) else len(flat)
        else:
            end = len(flat)
        body = flat[start:end].strip()
        if len(body) >= _MIN_CHAPTER_BODY_CHARS:
            results.append((num, title, body))

    if len(results) < _MIN_CHAPTERS_REQUIRED:
        return None

    return sorted(results, key=lambda t: t[0])


# ---------------------------------------------------------------------------
# Layer 2 — Section-numbering heuristic
# ---------------------------------------------------------------------------

def _split_by_section_numbering(
    pages: list[str],
) -> list[tuple[int, str, str]] | None:
    """Attempt chapter splitting by detecting N.1 section restarts.

    Many textbooks that use decorative chapter headers still use numeric
    section numbering (1.1, 2.1, 3.1, …). The first occurrence of "N.1" on
    a page signals the beginning of chapter N.

    Returns a list of ``(chapter_num, title, text)`` tuples if at least
    ``_MIN_CHAPTERS_REQUIRED`` distinct chapter numbers are found, otherwise
    returns ``None``.
    """
    # Walk every page; collect (chapter_num, page_0idx) for each N.1 restart.
    boundaries: list[tuple[int, int]] = []  # (chapter_num, page_0idx)
    seen_chapters: set[int] = set()

    for page_idx, page_text in enumerate(pages):
        for line in page_text.splitlines():
            m = _SECTION_ONE_RE.match(line)
            if m:
                chapter_num = int(m.group(1))
                if chapter_num > 0 and chapter_num not in seen_chapters:
                    seen_chapters.add(chapter_num)
                    boundaries.append((chapter_num, page_idx))
                break  # only consider the first N.1 per page

    if len(boundaries) < _MIN_CHAPTERS_REQUIRED:
        return None

    # Sort by page order.
    boundaries.sort(key=lambda b: b[1])

    page_starts, flat = _build_flat(pages)

    results: list[tuple[int, str, str]] = []
    for i, (chapter_num, pg_0) in enumerate(boundaries):
        start = page_starts[pg_0]
        if i + 1 < len(boundaries):
            end = page_starts[boundaries[i + 1][1]]
        else:
            end = len(flat)
        body = flat[start:end].strip()
        # Derive a minimal title from the first non-empty line of the section.
        title = _derive_section_title(body, chapter_num)
        if len(body) >= _MIN_CHAPTER_BODY_CHARS:
            results.append((chapter_num, title, body))

    if len(results) < _MIN_CHAPTERS_REQUIRED:
        return None

    return sorted(results, key=lambda t: t[0])


def _derive_section_title(body: str, chapter_num: int) -> str:
    """Extract a human-readable title from the first lines of a chapter body."""
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip bare page numbers or very short tokens.
        if line.isdigit():
            continue
        # Skip the "N.1 Section title" line itself — use whatever comes before
        # it. But if we haven't found anything better, use the section line.
        if _SECTION_ONE_RE.match(line):
            # e.g. "1.1  Why Program?" — strip the "N.1" prefix
            sub = re.sub(r"^\s*\d+\.\d+\s*", "", line).strip()
            if sub:
                return f"Chapter {chapter_num}: {sub}"
            continue
        # A non-trivial line — use it as the title basis.
        return f"Chapter {chapter_num}: {line[:80]}"
    return f"Chapter {chapter_num}"


# ---------------------------------------------------------------------------
# Layer 3 — Existing regex detection (unchanged logic, extracted as helper)
# ---------------------------------------------------------------------------

def _split_by_regex(pages: list[str]) -> list[tuple[int, str, str]] | None:
    """Attempt chapter splitting via heading-keyword regex matching.

    This is the original ``split_chapters`` algorithm, refactored as a
    helper that returns ``None`` instead of a fallback chapter when no
    headings are found.
    """
    candidates: list[tuple[int, str, int, int]] = []

    for page_idx, page_text in enumerate(pages):
        lines = page_text.splitlines()
        char_offset = 0
        for line in lines:
            match = _match_chapter_heading(line)
            if match:
                num, title = match
                candidates.append((num, title, page_idx, char_offset))
            char_offset += len(line) + 1  # +1 for the newline

    if not candidates:
        return None

    # Ignore likely TOC pages near the front of the PDF.
    toc_like_pages = {
        page_idx
        for page_idx in range(min(len(pages), _FRONT_MATTER_MAX_PAGE + 1))
        if len({num for num, _, pg, _ in candidates if pg == page_idx}) >= 2
    }
    filtered = [c for c in candidates if c[2] not in toc_like_pages]
    if not filtered:
        filtered = candidates

    # Collapse duplicates.
    boundaries: list[tuple[int, str, int, int]] = []
    seen_chapters: set[int] = set()
    max_seen = 0
    for num, title, page_idx, char_offset in filtered:
        if page_idx <= _FRONT_MATTER_MAX_PAGE and num < max_seen:
            boundaries.clear()
            seen_chapters.clear()
            max_seen = 0
        if num not in seen_chapters:
            seen_chapters.add(num)
            boundaries.append((num, title, page_idx, char_offset))
        if num > max_seen:
            max_seen = num

    page_starts, flat = _build_flat(pages)

    def abs_offset(page_idx: int, char_in_page: int) -> int:
        return page_starts[page_idx] + char_in_page

    results: list[tuple[int, str, str]] = []
    for i, (num, title, pg, ch) in enumerate(boundaries):
        start = abs_offset(pg, ch)
        if i + 1 < len(boundaries):
            nxt = boundaries[i + 1]
            end = abs_offset(nxt[2], nxt[3])
        else:
            end = len(flat)
        body = flat[start:end].strip()
        if len(body) >= _MIN_CHAPTER_BODY_CHARS:
            results.append((num, title, body))

    if not results:
        return None

    return sorted(results, key=lambda t: t[0])


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------

def _build_flat(pages: list[str]) -> tuple[list[int], str]:
    """Return (page_starts, flat_text).

    ``page_starts[i]`` is the character offset within ``flat_text`` at which
    page *i* begins.
    """
    page_starts: list[int] = []
    flat = ""
    for p in pages:
        page_starts.append(len(flat))
        flat += p + "\n"
    return page_starts, flat


# ---------------------------------------------------------------------------
# Public API — split_chapters (orchestrator)
# ---------------------------------------------------------------------------

def split_chapters(
    pages: list[str],
    toc: list[TocEntry] | None = None,
) -> list[tuple[int, str, str]]:
    """Split extracted pages into chapters using a layered detection strategy.

    Detection layers (tried in priority order; first to produce ≥ 3 chapters wins):

    1. **PDF TOC bookmarks** — uses embedded ``get_toc()`` data when provided.
       Most reliable; works even when chapter text is decorative/graphical.
    2. **Section-numbering heuristic** — detects N.1 restarts (e.g. "1.1", "2.1").
       Catches textbooks with graphical chapter headers but standard section numbers.
    3. **Keyword regex** — matches "Chapter N" / "Part N" patterns in extracted text.
       Classic fallback for traditionally typeset PDFs.

    Args:
        pages: One extracted text string per PDF page.
        toc:   Optional TOC from :func:`extract_toc` or :func:`ingest_pdf`
               (list of ``(level, title, page_1idx)`` tuples).

    Returns:
        List of ``(chapter_num, chapter_title, chapter_text)`` tuples sorted by
        chapter number.

    If no strategy succeeds, the entire document is returned as chapter 1 with
    a warning emitted to stderr.
    """
    if not pages:
        return [(1, "Chapter 1", "")]

    # --- Layer 1: PDF TOC bookmarks ---
    if toc:
        result = _split_by_toc(pages, toc)
        if result is not None:
            return result

    # --- Layer 2: Section-numbering heuristic ---
    result = _split_by_section_numbering(pages)
    if result is not None:
        return result

    # --- Layer 3: Keyword regex ---
    result = _split_by_regex(pages)
    if result is not None:
        # Mimic the old behaviour: warn if bodies were too short (result is empty
        # but candidates were found) — _split_by_regex already filters those and
        # returns None in that case, so we only reach here with valid results.
        return result

    # --- Final fallback ---
    warnings.warn(
        "No chapter headings detected in this PDF. "
        "Treating the entire document as chapter 1.",
        stacklevel=2,
    )
    return [(1, "Chapter 1", "\n".join(pages))]


# ---------------------------------------------------------------------------
# M2 — LLM-powered metadata generation
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _read_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _slugify(text: str) -> str:
    """Convert a filename stem to a safe book_id (lowercase, underscores)."""
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def generate_metadata(
    data_root: Path,
    book_id: str,
    pages: list[str],
    chapter_splits: list[tuple[int, str, str]],
    llm: "LLMClient",
) -> None:
    """Generate and write all data files for one book.

    Writes:
        data/<book_id>/book_overview.json
        data/<book_id>/chapters/chNN.txt   (raw text, source of truth)
        data/<book_id>/chapters/chNN.json  (light LLM summary)
        data/<book_id>/session_state.json  (initial session)

    Does *not* write a concept_graph.json — that file is not used in Phase 2.
    """
    from .llm import LLMClient as _LLMClient  # avoid circular import at module level  # noqa: F841

    overview_prompt = _read_prompt("ingest_book_overview.txt")
    summary_prompt = _read_prompt("ingest_chapter_summary.txt")

    # --- 1. Book overview from first chapter / front matter ---
    front_matter = chapter_splits[0][2] if chapter_splits else "\n".join(pages[:5])
    print(f"[ingest] generating book overview for '{book_id}'...")
    overview = llm.structured(
        system=[overview_prompt],
        user=(
            f"book_id: {book_id}\n\n"
            "Front matter / first chapter text:\n"
            f"{front_matter[:8000]}"
        ),
        schema=BookOverview,
        cache_system=False,
    )
    # Force the book_id we derived from the filename.
    overview = BookOverview(**{**overview.model_dump(), "book_id": book_id})
    storage.save_book_overview(data_root, overview)
    print(f"[ingest]   wrote book_overview.json ({overview.title})")

    # --- 2. Per-chapter text files + LLM summaries ---
    for chapter_num, chapter_title, chapter_text in chapter_splits:
        # 2a. Write raw text
        txt_path = (
            storage.book_dir(data_root, book_id)
            / "chapters"
            / f"ch{chapter_num:02d}.txt"
        )
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(chapter_text, encoding="utf-8")

        # 2b. Generate light summary
        print(f"[ingest] summarising ch{chapter_num}: {chapter_title}...")
        # Truncate very long chapters to stay within a single context window.
        truncated = chapter_text[:40000]
        summary = llm.structured(
            system=[summary_prompt],
            user=(
                f"book_id: {book_id}\n"
                f"chapter_num: {chapter_num}\n"
                f"chapter_title: {chapter_title}\n\n"
                f"{truncated}"
            ),
            schema=ChapterSummary,
            cache_system=False,
        )
        # Force the fields we know definitively.
        summary = ChapterSummary(
            **{
                **summary.model_dump(),
                "book_id": book_id,
                "chapter_num": chapter_num,
                "chapter_title": chapter_title,
            }
        )
        storage.save_chapter(data_root, summary)
        print(f"[ingest]   wrote ch{chapter_num:02d}.json + ch{chapter_num:02d}.txt")

    # --- 3. Initial session state ---
    from datetime import datetime, timezone

    state = SessionState(
        book_id=book_id,
        current_chapter=None,
        last_active=datetime.now(timezone.utc).isoformat(),
    )
    storage.save_session_state(data_root, state)
    print("[ingest] wrote session_state.json")
    print("[ingest] ingestion complete.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> None:
    """CLI: uv run python -m textbook_companion.ingest <path/to/book.pdf>"""
    import logging

    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("Usage: python -m textbook_companion.ingest <path/to/book.pdf>", file=sys.stderr)
        sys.exit(1)

    pdf_path = Path(argv[0])
    data_root = Path("data")
    book_id = _slugify(pdf_path.stem)

    print(f"[ingest] book_id: {book_id}")
    print(f"[ingest] extracting text from {pdf_path}...")

    try:
        pages, chapter_splits = ingest_pdf(pdf_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ingest] error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[ingest] {len(pages)} pages extracted.")
    print(f"[ingest] found {len(chapter_splits)} chapter(s).")

    # LLM client — import here so ingest.py has no hard import-time dependency
    # on anthropic when running tests without the real SDK.
    logging.getLogger("textbook_companion.llm").setLevel(logging.ERROR)
    from .llm import ClaudeClient

    llm = ClaudeClient()
    generate_metadata(data_root, book_id, pages, chapter_splits, llm)


if __name__ == "__main__":
    _main()

"""File I/O helpers: atomic JSON writes and JSONL append."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .models import (
    BookOverview,
    ChapterSummary,
    ConceptGraph,
    LogEntry,
    SessionState,
)


T = TypeVar("T", bound=BaseModel)


def _write_atomic(path: Path, text: str) -> None:
    """Write text to path atomically (temp file + os.replace).

    Leaves no partial file on the final path if the process is killed mid-write.
    The temp file lives in the same directory so os.replace is a single rename
    on the same filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def save_model(path: Path, model: BaseModel) -> None:
    _write_atomic(path, model.model_dump_json(indent=2))


def load_model(path: Path, schema: type[T]) -> T:
    with open(path, "r", encoding="utf-8") as f:
        return schema.model_validate_json(f.read())


def append_log(path: Path, entry: LogEntry) -> None:
    """Append one JSON line to a JSONL file; never rewrite existing lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry.model_dump_json())
        f.write("\n")


def read_log(path: Path) -> list[LogEntry]:
    if not path.exists():
        return []
    entries: list[LogEntry] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(LogEntry.model_validate_json(line))
    return entries


def book_dir(data_root: Path, book_id: str) -> Path:
    return data_root / book_id


def save_book_overview(data_root: Path, overview: BookOverview) -> None:
    save_model(book_dir(data_root, overview.book_id) / "book_overview.json", overview)


def load_book_overview(data_root: Path, book_id: str) -> BookOverview:
    return load_model(book_dir(data_root, book_id) / "book_overview.json", BookOverview)


def save_chapter(data_root: Path, chapter: ChapterSummary) -> None:
    fname = f"ch{chapter.chapter_num:02d}.json"
    save_model(book_dir(data_root, chapter.book_id) / "chapters" / fname, chapter)


def load_chapter(data_root: Path, book_id: str, chapter_num: int) -> ChapterSummary:
    fname = f"ch{chapter_num:02d}.json"
    return load_model(
        book_dir(data_root, book_id) / "chapters" / fname, ChapterSummary
    )


def save_concept_graph(data_root: Path, graph: ConceptGraph) -> None:
    save_model(book_dir(data_root, graph.book_id) / "concept_graph.json", graph)


def load_concept_graph(data_root: Path, book_id: str) -> ConceptGraph:
    return load_model(book_dir(data_root, book_id) / "concept_graph.json", ConceptGraph)


def save_session_state(data_root: Path, state: SessionState) -> None:
    save_model(book_dir(data_root, state.book_id) / "session_state.json", state)


def load_session_state(data_root: Path, book_id: str) -> SessionState:
    return load_model(book_dir(data_root, book_id) / "session_state.json", SessionState)


def session_state_path(data_root: Path, book_id: str) -> Path:
    return book_dir(data_root, book_id) / "session_state.json"


def reading_log_path(data_root: Path, book_id: str) -> Path:
    return book_dir(data_root, book_id) / "reading_log.jsonl"

"""Pydantic v2 data models.

Chapter numbers are always 1-indexed across code, files, and prompts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


EntryType = Literal[
    "reflection",
    "quiz_answer",
    "struggle_flag",
    "problem_attempt",
    "question",
    "note",
]


class Concept(BaseModel):
    term: str
    definition: str
    first_introduced_in: int = Field(ge=1)
    also_used_in: list[int] = Field(default_factory=list)

    @field_validator("also_used_in")
    @classmethod
    def _validate_chapter_numbers(cls, v: list[int]) -> list[int]:
        for n in v:
            if n < 1:
                raise ValueError("chapter numbers are 1-indexed")
        return v


class ChapterSummary(BaseModel):
    book_id: str
    chapter_num: int = Field(ge=1)
    chapter_title: str
    one_line: str
    overview: str
    key_concepts: list[Concept] = Field(default_factory=list)
    code_patterns: list[str] = Field(default_factory=list)
    depends_on_chapters: list[int] = Field(default_factory=list)
    worked_examples: list[str] = Field(default_factory=list)
    common_pitfalls: list[str] = Field(default_factory=list)
    end_of_chapter_problems: list[str] = Field(default_factory=list)

    @field_validator("depends_on_chapters")
    @classmethod
    def _validate_deps(cls, v: list[int]) -> list[int]:
        for n in v:
            if n < 1:
                raise ValueError("chapter numbers are 1-indexed")
        return v


class BookOverview(BaseModel):
    book_id: str
    title: str
    author: str
    edition: str
    total_chapters: int = Field(ge=1)
    # JSON object keys are strings; pydantic coerces back to int on load.
    chapter_titles: dict[int, str]
    arc_summary: str


class ConceptGraphEntry(BaseModel):
    term: str
    definition: str
    first_introduced_in: int = Field(ge=1)
    also_used_in: list[int] = Field(default_factory=list)


class ConceptGraph(BaseModel):
    book_id: str
    concepts: list[ConceptGraphEntry]


class SessionState(BaseModel):
    book_id: str
    current_chapter: int | None = None
    # Chapters started but not yet `done`. Keyed by chapter_num, value is the
    # ISO timestamp of when the chapter was first started. Preserves the
    # "I was also reading chM" signal across chapter switches.
    chapters_in_progress: dict[int, str] = Field(default_factory=dict)
    chapters_completed: dict[int, str] = Field(default_factory=dict)
    struggle_flags: dict[str, list[int]] = Field(default_factory=dict)
    last_active: str


class LogEntry(BaseModel):
    timestamp: str
    book_id: str
    chapter_num: int = Field(ge=1)
    entry_type: EntryType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)

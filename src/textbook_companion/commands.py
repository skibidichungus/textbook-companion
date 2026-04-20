"""Pure command parser for the CLI session loop.

Kept separate from session.py so it can be tested without any I/O, data files,
or LLM client. `parse(line)` → one of the dataclasses below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class StartChapter:
    chapter_num: int


@dataclass(frozen=True)
class DoneChapter:
    chapter_num: int


@dataclass(frozen=True)
class WhatWasChapter:
    chapter_num: int


@dataclass(frozen=True)
class RecapChapter:
    chapter_num: int


@dataclass(frozen=True)
class LookupConcept:
    term: str


@dataclass(frozen=True)
class StrugglingWith:
    term: str


@dataclass(frozen=True)
class Status:
    pass


@dataclass(frozen=True)
class Quit:
    pass


@dataclass(frozen=True)
class Unknown:
    raw: str


Command = Union[
    StartChapter,
    DoneChapter,
    WhatWasChapter,
    RecapChapter,
    LookupConcept,
    StrugglingWith,
    Status,
    Quit,
    Unknown,
]


_CH_RE = re.compile(r"ch\s*0*(\d+)", re.IGNORECASE)


def _extract_chapter(text: str) -> int | None:
    m = _CH_RE.search(text)
    return int(m.group(1)) if m else None


def parse(line: str) -> Command:
    text = line.strip()
    if not text:
        return Unknown("")
    lower = text.lower()

    if lower in ("quit", "exit"):
        return Quit()
    if lower == "status":
        return Status()

    if lower.startswith("starting "):
        n = _extract_chapter(text)
        return StartChapter(n) if n is not None else Unknown(text)

    if lower.startswith("done "):
        n = _extract_chapter(text)
        return DoneChapter(n) if n is not None else Unknown(text)

    if lower.startswith("what was "):
        n = _extract_chapter(text)
        return WhatWasChapter(n) if n is not None else Unknown(text)

    if lower.startswith("recap "):
        n = _extract_chapter(text)
        return RecapChapter(n) if n is not None else Unknown(text)

    if lower.startswith("struggling with "):
        term = text[len("struggling with "):].strip()
        return StrugglingWith(term) if term else Unknown(text)

    if lower.startswith("concept "):
        term = text[len("concept "):].strip()
        return LookupConcept(term) if term else Unknown(text)

    return Unknown(text)

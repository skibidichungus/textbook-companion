"""Pure parser tests — no I/O, no LLM."""

from __future__ import annotations

from textbook_companion.commands import (
    Ask,
    DoneChapter,
    LookupConcept,
    Note,
    Quit,
    RecapChapter,
    StartChapter,
    Status,
    StrugglingWith,
    Unknown,
    WhatWasChapter,
    parse,
)


def test_starting_chapter() -> None:
    assert parse("starting ch5") == StartChapter(5)
    assert parse("starting ch05") == StartChapter(5)
    assert parse("STARTING CH5") == StartChapter(5)
    assert parse("  starting ch12  ") == StartChapter(12)


def test_done_chapter() -> None:
    assert parse("done ch7") == DoneChapter(7)
    assert parse("done CH07") == DoneChapter(7)


def test_what_was_chapter_about() -> None:
    assert parse("what was ch3 about") == WhatWasChapter(3)
    assert parse("what was ch10 about") == WhatWasChapter(10)


def test_recap_chapter() -> None:
    assert parse("recap ch2") == RecapChapter(2)


def test_concept_lookup() -> None:
    assert parse("concept variable") == LookupConcept("variable")
    assert parse("concept named constant") == LookupConcept("named constant")
    # Mixed case in the term is preserved for the lookup layer to normalise.
    assert parse("concept F-string") == LookupConcept("F-string")


def test_struggling_with() -> None:
    assert parse("struggling with recursion") == StrugglingWith("recursion")
    assert parse("struggling with for loop") == StrugglingWith("for loop")


def test_status_and_quit() -> None:
    assert isinstance(parse("status"), Status)
    assert isinstance(parse("quit"), Quit)
    assert isinstance(parse("exit"), Quit)
    assert isinstance(parse("QUIT"), Quit)


def test_unknown_when_no_chapter_number() -> None:
    # "starting" with no chapter should not silently become ch0 or similar.
    assert isinstance(parse("starting"), Unknown)
    assert isinstance(parse("done"), Unknown)
    assert isinstance(parse("recap the thing"), Unknown)
    # Empty input
    assert isinstance(parse(""), Unknown)
    assert isinstance(parse("   "), Unknown)


def test_unknown_when_term_missing() -> None:
    assert isinstance(parse("concept"), Unknown)
    assert isinstance(parse("concept   "), Unknown)
    assert isinstance(parse("struggling with"), Unknown)


def test_unknown_command() -> None:
    cmd = parse("make me a sandwich")
    assert isinstance(cmd, Unknown)
    assert cmd.raw == "make me a sandwich"


def test_ask_command() -> None:
    assert parse("ask why does a function return None by default") == Ask(
        "why does a function return None by default"
    )
    # leading/trailing whitespace in the question is stripped
    assert parse("ask   how is scope defined   ") == Ask("how is scope defined")


def test_ask_requires_a_question() -> None:
    assert isinstance(parse("ask"), Unknown)
    assert isinstance(parse("ask   "), Unknown)


def test_note_command() -> None:
    assert parse("note re-read Program 5-3") == Note("re-read Program 5-3")
    # Case of the verb matters only for the prefix, not the note body.
    assert parse("NOTE watch out for mutable defaults") == Note(
        "watch out for mutable defaults"
    )


def test_note_requires_text() -> None:
    assert isinstance(parse("note"), Unknown)
    assert isinstance(parse("note   "), Unknown)

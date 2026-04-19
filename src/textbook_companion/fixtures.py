"""Hand-authored fixtures for Gaddis's *Starting Out with Python*, 6e.

Phase 1 uses these static fixtures instead of real PDF ingestion. Chapters 1-5
are fully populated; chapters 6-15 have one_line + short overview and mostly
empty lists, per the handoff.

Chapter 15 was unspecified in the handoff. I picked **Data Structures** as the
final chapter: it ties naturally to lists/tuples (ch7), dicts/sets (ch9),
inheritance (ch11), and recursion (ch12), which gives the concept graph
meaningful cross-chapter reuse.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import storage
from .models import (
    BookOverview,
    ChapterSummary,
    Concept,
    ConceptGraph,
    ConceptGraphEntry,
    SessionState,
)


BOOK_ID = "gaddis_python_6e"


CHAPTER_TITLES: dict[int, str] = {
    1: "Introduction to Computers and Python",
    2: "Input, Processing, and Output",
    3: "Decision Structures and Boolean Logic",
    4: "Repetition Structures",
    5: "Functions",
    6: "Files and Exceptions",
    7: "Lists and Tuples",
    8: "More About Strings",
    9: "Dictionaries and Sets",
    10: "Classes and Object-Oriented Programming",
    11: "Inheritance",
    12: "Recursion",
    13: "GUI Programming",
    14: "Database Programming",
    15: "Data Structures",
}


def _book_overview() -> BookOverview:
    return BookOverview(
        book_id=BOOK_ID,
        title="Starting Out with Python",
        author="Tony Gaddis",
        edition="6th",
        total_chapters=15,
        chapter_titles=CHAPTER_TITLES,
        arc_summary=(
            "Gaddis builds a procedural foundation (ch1-5) before layering on "
            "data handling (ch6-9), object-oriented design (ch10-11), and "
            "advanced topics (ch12-15). Each chapter introduces a small set of "
            "new concepts and reuses earlier ones in worked examples."
        ),
    )


def _ch01() -> ChapterSummary:
    return ChapterSummary(
        book_id=BOOK_ID,
        chapter_num=1,
        chapter_title=CHAPTER_TITLES[1],
        one_line="How computers run programs and how to run your first Python script.",
        overview=(
            "Chapter 1 frames a computer as hardware (CPU, memory, storage, "
            "I/O) running software written in a programming language. It "
            "distinguishes machine language, assembly, and high-level "
            "languages, and introduces Python as an interpreted high-level "
            "language.\n\n"
            "The hands-on portion installs Python, opens IDLE, and walks "
            "through writing and running a trivial print program. The point "
            "is to separate *writing source code* from *running a process*."
        ),
        key_concepts=[
            Concept(term="hardware", definition="Physical components of a computer (CPU, RAM, storage, I/O).", first_introduced_in=1, also_used_in=[]),
            Concept(term="software", definition="Programs that tell the hardware what to do.", first_introduced_in=1, also_used_in=[]),
            Concept(term="program", definition="A sequence of instructions the computer executes.", first_introduced_in=1, also_used_in=[2, 3, 4, 5]),
            Concept(term="machine language", definition="Binary instructions the CPU executes directly.", first_introduced_in=1, also_used_in=[]),
            Concept(term="high-level language", definition="A human-readable language translated into machine code.", first_introduced_in=1, also_used_in=[]),
            Concept(term="interpreter", definition="A program that executes source code one statement at a time.", first_introduced_in=1, also_used_in=[]),
            Concept(term="source code", definition="The text of a program as written by a human.", first_introduced_in=1, also_used_in=[2, 3, 4, 5, 6]),
            Concept(term="IDLE", definition="Python's bundled integrated development and learning environment.", first_introduced_in=1, also_used_in=[]),
        ],
        code_patterns=[
            'print("Hello, World!")',
            "# saving source as hello.py and running it with python hello.py",
        ],
        depends_on_chapters=[],
        worked_examples=["Program 1-1 (hello world)", "Program 1-2 (simple arithmetic print)"],
        common_pitfalls=[
            "Not saving the file with a .py extension before running.",
            "Confusing the interactive shell with a script file.",
        ],
        end_of_chapter_problems=[
            "1.1 Write a program that prints your name.",
            "1.2 Modify Program 1-1 to print three lines of text.",
            "1.3 Describe the difference between source code and machine code.",
        ],
    )


def _ch02() -> ChapterSummary:
    return ChapterSummary(
        book_id=BOOK_ID,
        chapter_num=2,
        chapter_title=CHAPTER_TITLES[2],
        one_line="Variables, basic data types, reading input, and formatting output.",
        overview=(
            "Chapter 2 introduces variables as named references to values and "
            "covers the three core data types a beginner needs: int, float, "
            "and str. It walks through assignment, type conversion via "
            "int()/float()/str(), and the input() function.\n\n"
            "Output formatting is covered twice: with print() and its sep/end "
            "keyword arguments, and with f-strings. Named constants (by "
            "convention, UPPER_CASE) appear here and recur through the book."
        ),
        key_concepts=[
            Concept(term="variable", definition="A named reference to a value stored in memory.", first_introduced_in=2, also_used_in=[3, 4, 5, 7, 10]),
            Concept(term="assignment", definition="Binding a value to a variable with =.", first_introduced_in=2, also_used_in=[3, 4, 5]),
            Concept(term="data type", definition="The kind of value a variable holds (int, float, str).", first_introduced_in=2, also_used_in=[3, 7, 8]),
            Concept(term="int", definition="The whole-number data type.", first_introduced_in=2, also_used_in=[3, 4, 7]),
            Concept(term="float", definition="The real-number data type.", first_introduced_in=2, also_used_in=[3, 4]),
            Concept(term="str", definition="The string data type, a sequence of characters.", first_introduced_in=2, also_used_in=[3, 7, 8]),
            Concept(term="input()", definition="Built-in that reads a line from standard input as a string.", first_introduced_in=2, also_used_in=[3, 4, 6]),
            Concept(term="print()", definition="Built-in that writes to standard output.", first_introduced_in=2, also_used_in=[3, 4, 5, 7]),
            Concept(term="type conversion", definition="Converting a value from one type to another with int(), float(), str().", first_introduced_in=2, also_used_in=[3, 6]),
            Concept(term="f-string", definition="A formatted string literal prefixed with f, with {expr} placeholders.", first_introduced_in=2, also_used_in=[3, 5, 7, 8]),
            Concept(term="named constant", definition="A variable, conventionally UPPER_CASE, that should not be reassigned.", first_introduced_in=2, also_used_in=[5]),
            Concept(term="comment", definition="A line beginning with # that the interpreter ignores.", first_introduced_in=2, also_used_in=[]),
        ],
        code_patterns=[
            'name = input("Enter your name: ")',
            'age = int(input("Enter your age: "))',
            'print(f"Hello, {name}. You are {age}.")',
            "SALES_TAX = 0.07",
        ],
        depends_on_chapters=[1],
        worked_examples=[
            "Program 2-1 (simple assignment)",
            "Program 2-3 (input + int conversion)",
            "Program 2-5 (named constant for sales tax)",
            "Program 2-8 (f-string formatting)",
        ],
        common_pitfalls=[
            "Forgetting to convert input() to a number before arithmetic.",
            "Using = (assignment) where == (comparison) is meant — surfaces in ch3.",
            "Mixing up print(sep=) and print(end=).",
        ],
        end_of_chapter_problems=[
            "2.1 Ask for two numbers and print their sum.",
            "2.3 Convert Fahrenheit to Celsius using a named constant.",
            "2.7 Format a receipt using f-strings and a SALES_TAX constant.",
        ],
    )


def _ch03() -> ChapterSummary:
    return ChapterSummary(
        book_id=BOOK_ID,
        chapter_num=3,
        chapter_title=CHAPTER_TITLES[3],
        one_line="Making decisions with if / elif / else and boolean expressions.",
        overview=(
            "Chapter 3 introduces conditional execution. Boolean expressions "
            "are built from comparison operators (==, !=, <, <=, >, >=) and "
            "combined with the logical operators and/or/not. The core "
            "constructs are if, if/else, and the if/elif/else chain.\n\n"
            "Nested decisions and short-circuit evaluation round out the "
            "chapter. The common mistake the book flags repeatedly is using = "
            "instead of ==; the other is indentation, since Python uses it to "
            "delimit blocks."
        ),
        key_concepts=[
            Concept(term="boolean", definition="A value that is either True or False.", first_introduced_in=3, also_used_in=[4, 5, 7, 9]),
            Concept(term="comparison operator", definition="An operator (==, !=, <, <=, >, >=) producing a boolean.", first_introduced_in=3, also_used_in=[4, 7, 9]),
            Concept(term="if statement", definition="Runs a block only when a boolean expression is True.", first_introduced_in=3, also_used_in=[4, 5, 6, 10]),
            Concept(term="else clause", definition="Runs when the if condition is False.", first_introduced_in=3, also_used_in=[4, 6]),
            Concept(term="elif chain", definition="Tests a series of conditions in order; the first True branch runs.", first_introduced_in=3, also_used_in=[4, 5]),
            Concept(term="logical operator", definition="and, or, not — combine boolean expressions.", first_introduced_in=3, also_used_in=[4, 9]),
            Concept(term="nested if", definition="An if statement inside another if.", first_introduced_in=3, also_used_in=[4, 5]),
            Concept(term="short-circuit evaluation", definition="and/or stop evaluating once the result is known.", first_introduced_in=3, also_used_in=[]),
        ],
        code_patterns=[
            "if x > 0:\n    print('positive')",
            "if x > 0:\n    ...\nelif x == 0:\n    ...\nelse:\n    ...",
            "if age >= 18 and has_license:\n    drive()",
        ],
        depends_on_chapters=[1, 2],
        worked_examples=[
            "Program 3-1 (simple if)",
            "Program 3-4 (if/else pay calculation)",
            "Program 3-7 (elif chain for letter grades)",
            "Program 3-10 (nested if for shipping eligibility)",
        ],
        common_pitfalls=[
            "Writing `if x = 5:` instead of `if x == 5:`.",
            "Forgetting the colon at the end of the if line.",
            "Inconsistent indentation inside a block.",
        ],
        end_of_chapter_problems=[
            "3.1 Print whether a number is positive, negative, or zero.",
            "3.4 Compute a letter grade from a numeric score using elif.",
            "3.8 Decide whether a year is a leap year.",
        ],
    )


def _ch04() -> ChapterSummary:
    return ChapterSummary(
        book_id=BOOK_ID,
        chapter_num=4,
        chapter_title=CHAPTER_TITLES[4],
        one_line="Repeating work with while and for loops.",
        overview=(
            "Chapter 4 covers repetition: while loops for condition-controlled "
            "iteration and for loops for count-controlled iteration over a "
            "range. It introduces the accumulator pattern, counters, and "
            "sentinel-controlled input loops.\n\n"
            "Nested loops appear toward the end, usually to process "
            "two-dimensional data. The chapter repeatedly warns about "
            "off-by-one errors in range() bounds and infinite loops caused by "
            "forgetting to update the loop variable."
        ),
        key_concepts=[
            Concept(term="while loop", definition="Repeats a block while a condition is True.", first_introduced_in=4, also_used_in=[5, 6, 7, 12]),
            Concept(term="for loop", definition="Iterates over a sequence of values.", first_introduced_in=4, also_used_in=[5, 6, 7, 8, 9, 10]),
            Concept(term="range()", definition="Built-in producing a sequence of integers for for loops.", first_introduced_in=4, also_used_in=[5, 7]),
            Concept(term="counter variable", definition="A variable incremented each pass to count iterations.", first_introduced_in=4, also_used_in=[5, 7]),
            Concept(term="accumulator pattern", definition="Building a running total inside a loop.", first_introduced_in=4, also_used_in=[5, 7]),
            Concept(term="sentinel value", definition="A special input value that signals the loop should stop.", first_introduced_in=4, also_used_in=[6, 7]),
            Concept(term="nested loop", definition="A loop inside another loop.", first_introduced_in=4, also_used_in=[5, 7]),
            Concept(term="infinite loop", definition="A loop whose condition never becomes False.", first_introduced_in=4, also_used_in=[]),
        ],
        code_patterns=[
            "total = 0\nfor n in range(1, 11):\n    total += n",
            "x = int(input())\nwhile x != -1:\n    process(x)\n    x = int(input())",
            "for row in range(rows):\n    for col in range(cols):\n        ...",
        ],
        depends_on_chapters=[1, 2, 3],
        worked_examples=[
            "Program 4-1 (while countdown)",
            "Program 4-3 (accumulator for average)",
            "Program 4-6 (sentinel-controlled input)",
            "Program 4-9 (nested loops for a multiplication table)",
        ],
        common_pitfalls=[
            "Forgetting to update the loop variable in a while loop — infinite loop.",
            "Off-by-one error: range(1, 10) does not include 10.",
            "Initializing an accumulator inside the loop instead of before it.",
        ],
        end_of_chapter_problems=[
            "4.1 Print the numbers 1 to 100.",
            "4.4 Compute the average of user-entered numbers, ending on -1.",
            "4.7 Print a multiplication table using nested loops.",
        ],
    )


def _ch05() -> ChapterSummary:
    return ChapterSummary(
        book_id=BOOK_ID,
        chapter_num=5,
        chapter_title=CHAPTER_TITLES[5],
        one_line="Defining and calling functions; parameters, returns, and scope.",
        overview=(
            "Chapter 5 introduces the function as a named, reusable block. It "
            "distinguishes parameters (the formal names) from arguments (the "
            "values passed), explains positional vs keyword arguments, "
            "default argument values, and the return statement.\n\n"
            "Scope is the second big idea: local variables live inside a "
            "function, global variables live at module level, and Gaddis "
            "strongly encourages avoiding globals for mutable state. The "
            "chapter closes by motivating modular programming — splitting a "
            "program into small, single-purpose functions."
        ),
        key_concepts=[
            Concept(term="function", definition="A named, reusable block of code that takes parameters and may return a value.", first_introduced_in=5, also_used_in=[6, 7, 8, 9, 10, 11, 12]),
            Concept(term="parameter", definition="A variable named in a function's definition.", first_introduced_in=5, also_used_in=[6, 10, 11]),
            Concept(term="argument", definition="A value passed to a function when it is called.", first_introduced_in=5, also_used_in=[6, 10]),
            Concept(term="return statement", definition="Ends a function and optionally sends a value back to the caller.", first_introduced_in=5, also_used_in=[6, 7, 10, 12]),
            Concept(term="local variable", definition="A variable defined inside a function, invisible outside it.", first_introduced_in=5, also_used_in=[10]),
            Concept(term="global variable", definition="A variable defined at module level, visible everywhere.", first_introduced_in=5, also_used_in=[]),
            Concept(term="scope", definition="The region of code in which a name is accessible.", first_introduced_in=5, also_used_in=[10, 11]),
            Concept(term="default argument", definition="A parameter with a fallback value used when the caller omits it.", first_introduced_in=5, also_used_in=[10]),
            Concept(term="keyword argument", definition="An argument passed by name, e.g. f(x=1).", first_introduced_in=5, also_used_in=[10]),
            Concept(term="modular programming", definition="Structuring a program as small, focused functions.", first_introduced_in=5, also_used_in=[10, 11]),
            Concept(term="docstring", definition="A string literal at the top of a function describing what it does.", first_introduced_in=5, also_used_in=[10]),
        ],
        code_patterns=[
            'def greet(name):\n    """Print a greeting."""\n    print(f"Hello, {name}")',
            "def area(length, width=1):\n    return length * width",
            "total = area(length=5, width=3)",
        ],
        depends_on_chapters=[1, 2, 3, 4],
        worked_examples=[
            "Program 5-1 (hello function)",
            "Program 5-3 (function returning a value)",
            "Program 5-5 (default arguments)",
            "Program 5-8 (program built from several functions)",
        ],
        common_pitfalls=[
            "Forgetting `return` — the function silently returns None.",
            "Modifying a global variable without declaring `global`.",
            "Confusing parameters with arguments when reading errors.",
        ],
        end_of_chapter_problems=[
            "5.1 Write a function that returns the square of a number.",
            "5.4 Write a function with a default argument.",
            "5.8 Refactor a long script into several small functions.",
        ],
    )


def _sparse_chapter(
    num: int,
    one_line: str,
    overview: str,
    depends_on: list[int],
) -> ChapterSummary:
    return ChapterSummary(
        book_id=BOOK_ID,
        chapter_num=num,
        chapter_title=CHAPTER_TITLES[num],
        one_line=one_line,
        overview=overview,
        key_concepts=[],
        code_patterns=[],
        depends_on_chapters=depends_on,
        worked_examples=[],
        common_pitfalls=[],
        end_of_chapter_problems=[],
    )


def _sparse_chapters() -> list[ChapterSummary]:
    return [
        _sparse_chapter(
            6,
            "Reading and writing text files and handling exceptions.",
            "Introduces file I/O with open()/read()/write()/close() and the "
            "with statement. Exception handling arrives here: try/except, "
            "specific exception types, and the else/finally clauses.",
            [1, 2, 3, 4, 5],
        ),
        _sparse_chapter(
            7,
            "Lists and tuples: ordered, indexable sequences.",
            "Lists are mutable sequences; tuples are their immutable siblings. "
            "Covers indexing, slicing, iteration, membership, common methods, "
            "and the difference between mutating and rebinding.",
            [1, 2, 3, 4, 5],
        ),
        _sparse_chapter(
            8,
            "More string methods, slicing, and formatting.",
            "A deeper pass over strings than chapter 2: string methods "
            "(upper/lower/split/join/find/replace), slicing, and parsing "
            "simple input.",
            [1, 2, 3, 4, 5, 7],
        ),
        _sparse_chapter(
            9,
            "Dictionaries and sets: unordered collections keyed by value.",
            "Dictionaries map keys to values; sets hold unique values. Covers "
            "iteration, containment, and common use cases (counting, "
            "deduplication, lookup tables).",
            [1, 2, 3, 4, 5, 7],
        ),
        _sparse_chapter(
            10,
            "Classes and object-oriented programming.",
            "Defines classes, instances, attributes, and methods. Introduces "
            "__init__, self, and encapsulation. Motivates OOP as a way to "
            "bundle data and behavior.",
            [1, 2, 3, 4, 5, 7, 9],
        ),
        _sparse_chapter(
            11,
            "Inheritance: extending classes.",
            "Subclassing, method overriding, and super(). Discusses is-a vs "
            "has-a and when inheritance is appropriate.",
            [5, 10],
        ),
        _sparse_chapter(
            12,
            "Recursion: functions that call themselves.",
            "Base cases, recursive cases, and the call stack. Classic "
            "examples: factorial, Fibonacci, and simple list processing.",
            [4, 5],
        ),
        _sparse_chapter(
            13,
            "GUI programming with tkinter.",
            "Event-driven programming, widgets (Label, Button, Entry), "
            "geometry managers, and callback functions.",
            [5, 10],
        ),
        _sparse_chapter(
            14,
            "Database programming with SQLite.",
            "Connecting to a database, running SQL from Python, and mapping "
            "rows to Python data structures.",
            [6, 7, 9, 10],
        ),
        _sparse_chapter(
            15,
            "Data structures: linked lists, stacks, queues, trees.",
            "Implements classic data structures in Python using classes and "
            "references. Ties together lists (ch7), dicts (ch9), classes "
            "(ch10), inheritance (ch11), and recursion (ch12).",
            [7, 9, 10, 11, 12],
        ),
    ]


def _concept_graph() -> ConceptGraph:
    """Cross-chapter concept reuse map.

    Kept consistent with the `also_used_in` lists on each Concept in the
    populated chapters 1-5. Only includes concepts that are reused across
    chapters — terms introduced and never reappearing are skipped.
    """
    return ConceptGraph(
        book_id=BOOK_ID,
        concepts=[
            ConceptGraphEntry(term="program", definition="A sequence of instructions the computer executes.", first_introduced_in=1, also_used_in=[2, 3, 4, 5]),
            ConceptGraphEntry(term="source code", definition="The text of a program as written by a human.", first_introduced_in=1, also_used_in=[2, 3, 4, 5, 6]),
            ConceptGraphEntry(term="variable", definition="A named reference to a value stored in memory.", first_introduced_in=2, also_used_in=[3, 4, 5, 7, 10]),
            ConceptGraphEntry(term="assignment", definition="Binding a value to a variable with =.", first_introduced_in=2, also_used_in=[3, 4, 5]),
            ConceptGraphEntry(term="data type", definition="The kind of value a variable holds.", first_introduced_in=2, also_used_in=[3, 7, 8]),
            ConceptGraphEntry(term="int", definition="The whole-number data type.", first_introduced_in=2, also_used_in=[3, 4, 7]),
            ConceptGraphEntry(term="float", definition="The real-number data type.", first_introduced_in=2, also_used_in=[3, 4]),
            ConceptGraphEntry(term="str", definition="The string data type, a sequence of characters.", first_introduced_in=2, also_used_in=[3, 7, 8]),
            ConceptGraphEntry(term="input()", definition="Reads a line from standard input as a string.", first_introduced_in=2, also_used_in=[3, 4, 6]),
            ConceptGraphEntry(term="print()", definition="Writes to standard output.", first_introduced_in=2, also_used_in=[3, 4, 5, 7]),
            ConceptGraphEntry(term="type conversion", definition="Converting a value from one type to another.", first_introduced_in=2, also_used_in=[3, 6]),
            ConceptGraphEntry(term="f-string", definition="A formatted string literal with {expr} placeholders.", first_introduced_in=2, also_used_in=[3, 5, 7, 8]),
            ConceptGraphEntry(term="named constant", definition="A variable, conventionally UPPER_CASE, that should not be reassigned.", first_introduced_in=2, also_used_in=[5]),
            ConceptGraphEntry(term="boolean", definition="True or False.", first_introduced_in=3, also_used_in=[4, 5, 7, 9]),
            ConceptGraphEntry(term="comparison operator", definition="==, !=, <, <=, >, >=.", first_introduced_in=3, also_used_in=[4, 7, 9]),
            ConceptGraphEntry(term="if statement", definition="Runs a block when a condition is True.", first_introduced_in=3, also_used_in=[4, 5, 6, 10]),
            ConceptGraphEntry(term="else clause", definition="Runs when the if condition is False.", first_introduced_in=3, also_used_in=[4, 6]),
            ConceptGraphEntry(term="elif chain", definition="Tests a sequence of conditions; the first True branch runs.", first_introduced_in=3, also_used_in=[4, 5]),
            ConceptGraphEntry(term="logical operator", definition="and, or, not.", first_introduced_in=3, also_used_in=[4, 9]),
            ConceptGraphEntry(term="nested if", definition="An if statement inside another if.", first_introduced_in=3, also_used_in=[4, 5]),
            ConceptGraphEntry(term="while loop", definition="Repeats while a condition is True.", first_introduced_in=4, also_used_in=[5, 6, 7, 12]),
            ConceptGraphEntry(term="for loop", definition="Iterates over a sequence.", first_introduced_in=4, also_used_in=[5, 6, 7, 8, 9, 10]),
            ConceptGraphEntry(term="range()", definition="Built-in producing a sequence of integers.", first_introduced_in=4, also_used_in=[5, 7]),
            ConceptGraphEntry(term="counter variable", definition="Incremented each pass to count iterations.", first_introduced_in=4, also_used_in=[5, 7]),
            ConceptGraphEntry(term="accumulator pattern", definition="Building a running total in a loop.", first_introduced_in=4, also_used_in=[5, 7]),
            ConceptGraphEntry(term="sentinel value", definition="Special input value signaling the loop to stop.", first_introduced_in=4, also_used_in=[6, 7]),
            ConceptGraphEntry(term="nested loop", definition="A loop inside another loop.", first_introduced_in=4, also_used_in=[5, 7]),
            ConceptGraphEntry(term="function", definition="A named, reusable block of code.", first_introduced_in=5, also_used_in=[6, 7, 8, 9, 10, 11, 12]),
            ConceptGraphEntry(term="parameter", definition="A variable named in a function's definition.", first_introduced_in=5, also_used_in=[6, 10, 11]),
            ConceptGraphEntry(term="argument", definition="A value passed to a function when it is called.", first_introduced_in=5, also_used_in=[6, 10]),
            ConceptGraphEntry(term="return statement", definition="Ends a function and optionally returns a value.", first_introduced_in=5, also_used_in=[6, 7, 10, 12]),
            ConceptGraphEntry(term="local variable", definition="A variable defined inside a function.", first_introduced_in=5, also_used_in=[10]),
            ConceptGraphEntry(term="scope", definition="The region of code where a name is accessible.", first_introduced_in=5, also_used_in=[10, 11]),
            ConceptGraphEntry(term="default argument", definition="A parameter with a fallback value.", first_introduced_in=5, also_used_in=[10]),
            ConceptGraphEntry(term="keyword argument", definition="An argument passed by name.", first_introduced_in=5, also_used_in=[10]),
            ConceptGraphEntry(term="modular programming", definition="Structuring a program as small, focused functions.", first_introduced_in=5, also_used_in=[10, 11]),
            ConceptGraphEntry(term="docstring", definition="A string literal describing what a function does.", first_introduced_in=5, also_used_in=[10]),
        ],
    )


def _initial_session_state() -> SessionState:
    return SessionState(
        book_id=BOOK_ID,
        current_chapter=None,
        chapters_completed={},
        struggle_flags={},
        last_active=datetime.now(timezone.utc).isoformat(),
    )


def all_chapters() -> list[ChapterSummary]:
    return [_ch01(), _ch02(), _ch03(), _ch04(), _ch05(), *_sparse_chapters()]


def write_fixtures(data_root: Path) -> None:
    """Write the full Gaddis Python 6e fixture tree under `data_root`.

    Overwrites any existing fixture files. The reading log is reset to empty.
    """
    storage.save_book_overview(data_root, _book_overview())
    for ch in all_chapters():
        storage.save_chapter(data_root, ch)
    storage.save_concept_graph(data_root, _concept_graph())
    storage.save_session_state(data_root, _initial_session_state())

    # Ensure the reading log exists as an empty file so the M4 loop can append
    # without a first-time branch. Reset it if it already exists — fixtures
    # imply a fresh slate.
    log = storage.reading_log_path(data_root, BOOK_ID)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")


def main() -> None:
    """Write fixtures to ./data (relative to cwd)."""
    data_root = Path("data")
    write_fixtures(data_root)
    print(f"Fixtures written to {data_root.resolve()}/{BOOK_ID}/")


if __name__ == "__main__":
    main()

# Walkthrough — a typical session

A ~15-turn session through the fixtures. Every command is exercised at least
once. LLM responses below are real in shape but trimmed for brevity —
Claude's actual output is usually a paragraph or two rather than one line.

Assume you've already run `uv run python -m textbook_companion.fixtures` and
exported `ANTHROPIC_API_KEY`.

```
$ uv run textbook-companion

Textbook Companion — Starting Out with Python (6th), Tony Gaddis
No progress yet — start with `starting ch1`.
>
```

---

### Turn 1 — start chapter 1

```
> starting ch1
Starting ch1: Introduction to Computers and Python
```

No dependencies, no refresher (nothing to be rusty about yet), no LLM call.
Chapter is now marked in-progress.

---

### Turn 2 — look up a concept before diving in

```
> concept variable
variable: A named reference to a value stored in memory.
  first introduced in ch2
  also used in: ch3, ch4, ch5, ch7, ch10
```

Pulls from `concept_graph.json`. No LLM call.

---

### Turn 3 — ask a real question

```
> ask why does python use indentation instead of braces
Python's designer chose indentation as the block delimiter so the visual
layout *is* the structure — no mismatch between what the indentation suggests
and what the compiler sees. You'll feel this matter in ch3 (if/elif) and ch4
(loops), where the body of a block is defined purely by the indent level.
For ch1, the only thing you need is: save your file with a .py extension and
keep indentation consistent.
```

Grounded in ch1: references ch3 and ch4 only as foreshadowing, doesn't
explain either of them. Logged to the reading log as a `question` entry,
with the answer in metadata.

---

### Turn 4 — jot a note

```
> note come back and redo Program 1-1 tomorrow morning
Note logged for ch1.
```

No LLM call. Appended to `reading_log.jsonl` as a `note` entry.

---

### Turn 5 — log that you're attempting a problem

```
> attempting 1.1
Logged problem attempt '1.1' for ch1.
```

`1.1` matches a problem in ch1's fixture, so no confirmation needed. If you'd
typed `attempting 5.4` while on ch1, the companion would ask whether to
reroute it under ch5 — that's the M4.9 attribution check.

---

### Turn 6 — flag a concept you're struggling with

```
> struggling with machine language vs assembly
Flagged 'machine language vs assembly' as a struggle in ch1.
```

Goes into `session_state.struggle_flags` and the log. Status will surface it.

---

### Turn 7 — status check

```
> status
Current chapter: ch1
In progress:
  ch1: started 2026-04-21T13:33:53.144682+00:00
Completed: (none)
Struggle flags:
  machine language vs assembly: ch1
```

Nothing completed yet.

---

### Turn 8 — finish the chapter

```
> done ch1

== Recap for ch1: Introduction to Computers and Python ==
Chapter 1's central idea is the distinction between *writing source code* and
*running a process*. Worth reinforcing: the hardware/software split, the role
of the Python interpreter in turning your .py file into work the CPU can do,
and the small-but-real habit of actually saving with a .py extension. Nothing
to tie back to yet — this is the foundation ch2 will build on when you start
taking input and producing output.

== Quiz (3 questions) ==
Q1: If you type the same print statement into IDLE's interactive shell and
into a saved .py file, what is different about how Python handles each?
A: reads it line by line
You've got the interactive-shell half right: IDLE does evaluate each line
as you type it. What's worth adding is what happens with the script: Python
reads the whole file, parses it, and then executes it top to bottom in one
go. Here's how I'd put it: interactive = one statement at a time, script =
whole file submitted as a unit.

Q2: ... (two more questions and feedbacks follow)

Any reflections on this chapter? (what clicked, what didn't — blank to skip)
> the interpreter vs machine code split finally landed

ch1 marked complete.
```

This is the only flow that hits the LLM multiple times: one call for the
recap, one structured call for the quiz, and one feedback call per answer.
Each quiz answer is persisted with its `question`, `q_num`, and `feedback`
in metadata.

---

### Turn 9 — move to chapter 2

```
> starting ch2
Starting ch2: Input, Processing, and Output
Depends on: ch1
```

`ch1` is in `chapters_completed`, so no abandonment prompt. If ch1 were still
mid-flight, you'd see a `[y/N]` confirm before switching.

---

### Turn 10 — attempting a problem that belongs elsewhere

```
> attempting 1.2
'1.2' looks like a ch1 problem, not your current ch2. Log under ch1 instead? [y/N] y
Logged problem attempt '1.2' for ch1.
```

The owner map caught the mismatch. Your current chapter is still ch2.

---

### Turn 11 — ask a cross-chapter question

```
> ask how will the input() function change once we learn about type conversion
`input()` always returns a string — that doesn't change. What changes is what
you do *with* that string: once you pick up type conversion later in this
chapter, you'll wrap it as `int(input(...))` or `float(input(...))` to turn
it into a number you can do arithmetic with. The raw string-returning
behavior stays the same; the habit of immediately converting is new.
```

Grounded in ch2. If you tried the same question on ch10, the answer would
thread through classes instead — the active chapter JSON is in the system
prompt.

---

### Turn 12 — check where you are

```
> status
Current chapter: ch2
In progress:
  ch2: started 2026-04-21T13:50:10.123456+00:00
Completed:
  ch1: 2026-04-21T13:43:35.059621+00:00
Struggle flags:
  machine language vs assembly: ch1
```

---

### Turn 13 — revisit ch1 without disturbing ch2

```
> starting ch1
Revisiting ch1: Introduction to Computers and Python (already completed).
Depends on:
```

`current_chapter` is now ch1 again but ch1 stays in `chapters_completed`;
it is *not* re-added to `chapters_in_progress`. Ch2 is still tracked as
in-progress separately.

---

### Turn 14 — one more look, then stop

```
> recap ch1
ch1: Introduction to Computers and Python

Chapter 1 frames a computer as hardware running software...
(...key concepts, worked examples follow...)
```

`recap` pulls straight from the fixture — no LLM call.

```
> quit
bye.
```

---

### Relaunch — pick up where you left off

```
$ uv run textbook-companion
Textbook Companion — Starting Out with Python (6th), Tony Gaddis
You left off in ch1. Also in progress: ch2.
Active struggle flags: machine language vs assembly
>
```

Everything round-trips. The reading log keeps growing; state stays accurate.

---

### What the log looks like

A few lines from `data/gaddis_python_6e/reading_log.jsonl` after the session:

```json
{"timestamp":"2026-04-21T13:...","book_id":"gaddis_python_6e","chapter_num":1,"entry_type":"question","content":"why does python use indentation instead of braces","metadata":{"answer":"Python's designer chose indentation..."}}
{"timestamp":"2026-04-21T13:...","book_id":"gaddis_python_6e","chapter_num":1,"entry_type":"note","content":"come back and redo Program 1-1 tomorrow morning","metadata":{}}
{"timestamp":"2026-04-21T13:...","book_id":"gaddis_python_6e","chapter_num":1,"entry_type":"problem_attempt","content":"1.1","metadata":{}}
{"timestamp":"2026-04-21T13:...","book_id":"gaddis_python_6e","chapter_num":1,"entry_type":"struggle_flag","content":"machine language vs assembly","metadata":{}}
{"timestamp":"2026-04-21T13:...","book_id":"gaddis_python_6e","chapter_num":1,"entry_type":"quiz_answer","content":"reads it line by line","metadata":{"question":"If you type...","q_num":1,"feedback":"You've got the interactive-shell half right..."}}
{"timestamp":"2026-04-21T13:...","book_id":"gaddis_python_6e","chapter_num":1,"entry_type":"reflection","content":"the interpreter vs machine code split finally landed","metadata":{}}
```

Every turn that produced something is captured, ordered, and queryable as
append-only JSONL — grep-friendly, easy to load later for review.

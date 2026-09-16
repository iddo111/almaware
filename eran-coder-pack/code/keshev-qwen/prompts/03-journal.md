Write file 1 of your build order: `app/journal.py`, plus `tests/test_journal.py`.

Requirements you set yourself: append-only JSONL, one honest line per fact, every
component writes through it, and it must be able to reconstruct what happened.

Hard-won constraints from the system it replaces — obey them:
- The event vocabulary is CLOSED: an unknown event name raises at the WRITER, not
  silently vanishing from dashboards. A real outage happened because a module
  journalled an event name nobody had added to the vocabulary: the exception
  killed the thread and the app reported "healthy" for four hours while typing
  nothing. Include every name your PLAN.md failure table and pipeline need.
- Open the file per write and close it; hold no handle. The process can die
  mid-line and the reader must skip a torn last line without crashing.
- rotate() renames, never deletes.
- Timestamps are local ISO-8601 with milliseconds and an explicit +03:00 offset.
- Thread-safe within one process.

Output exactly two complete files, each in its own fenced block preceded by a line
`FILE: app/journal.py` and `FILE: tests/test_journal.py`. Python 3.13, stdlib only,
unittest (not pytest-specific APIs). No ellipses. The tests must actually fail if
the laws above are broken — including one that asserts an unknown event name
raises, and one that asserts a torn final line is skipped by the reader.

Write file 9 of your build order: `app/filter.py`, plus `tests/test_filter.py`.

It answers one question: is this transcription his speech, or junk that must never
reach his window? It sees text and decode metadata only — never audio, never the
network.

Every rule below comes from something that actually got typed into his chat as him:
- Whisper's near-silence hallucinations: "you", "thank you", "thanks for watching",
  "bye", "so", "subtitles by the amara.org community", and Hebrew cousins
  "תודה", "תודה רבה", "תודה שצפיתם", "כתוביות". Compare stripped, casefolded,
  trailing punctuation removed.
- Repetition loops: "This is the one who is" repeated ~50 times was typed and
  ENTERED. Catch both vocabulary collapse and exact n-gram cycling.
- A yawn: one token containing a long run of the same character ("אההההההה…",
  230 chars) — one word, so word-level loop detection never saw it.
- Language whitelist ('he','en','ru'); language None is unrepresentable — a None
  once let noise return as Icelandic.
- A confidence floor. WARNING: do not repeat the dead-guard mistake — a floor was
  once shipped at a value the real distribution never reached and never fired
  once. State the floor you choose and mark it ASSUMED unless you can name the
  measurement behind it. Note that his own real Hebrew decodes at avg_logprob
  -0.02 to -0.5, and confident English garbage on his Hebrew audio lands at
  -0.6 to -1.5.
- Every rejection returns a distinct machine-readable reason for the journal.

Output exactly two complete files with `FILE:` headers. Python 3.13, stdlib only,
unittest. Tests must include the yawn, the loop, each hallucination, the None
language, and a case proving your floor actually fires on real-shaped data.

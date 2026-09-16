You are starting KESHEV-QWEN from nothing, in `D:\CLAUDE\keshev-qwen`.

Design it yourself. Do not copy an existing layout — decide what the modules are
and justify each one in a sentence.

Context you should use, from the live system this replaces:
- Today's actual failure: the energy gate sat at RMS 0.020 while his speech ranges
  0.018–0.098, so the natural pauses between his words closed the segment and his
  sentences arrived as 0.4–0.6 s fragments that decoded as the English word "you".
  Segmentation, not decoding, is what breaks a dictation mic.
- A dead-guard scar: a confidence floor was shipped at a value the real
  distribution never reached, so it never fired once. Every threshold you choose
  must come with the measurement that justifies it, or be marked UNCALIBRATED.
- A silent-death scar: a background thread died on an unhandled exception and the
  app kept reporting "healthy" for four hours while typing nothing.
- Latency budget: capture 100 ms blocks, decode round-trip ~330 ms; a sentence
  must appear within about a second of him finishing it.

Deliver, in this order:
1. ARCHITECTURE — the module list. For each: name, the ONE question it answers,
   its inputs/outputs, and what it is forbidden to know about.
2. THREADS — exactly which threads exist, what each owns, and what happens when
   any one of them dies.
3. THE SEGMENTER — your design for deciding where an utterance starts and ends so
   that a natural mid-sentence pause does NOT cut it, while a 3-second silence
   does. Give the actual parameters and say which are calibrated vs guessed.
4. FAILURE TABLE — for each way it can break (no mic, server down, focus lost,
   junk decode, thread death, machine reboot): what the user SEES, what the
   journal records, and how it recovers.
5. TEST PLAN — the list of tests you will write, each named after the law it
   defends.
6. BUILD ORDER — the sequence of files you will write, and which one you start
   with.

Be concrete and opinionated. This is your design; you will write it next.

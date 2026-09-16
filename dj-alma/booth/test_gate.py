# -*- coding: utf-8 -*-
"""test_gate.py — a take that is not the model's own work must be UNREACHABLE.

WHY THIS FILE EXISTS
--------------------
2026-09-05. Iddo was asked three times in one day to judge "the model" and was
handed something else each time: two of the four DJ ALMIDO takes he could click
carried `source=corpus-transcription` -- a passage of the REAL Darwish, played
back to him as if it were the transformer's composition.

The page already printed a coloured badge saying which was which. A badge is
not a gate. This test asserts the gate: a non-model take must not be composed,
must not be listed, and must not be SERVED -- and the refusal must be a
refusal, not a 404 that looks like a missing file.

It plants a real fake take on disk, asks the real server for it over a real
socket, and requires a 403. Then it removes it. If the gate is ever loosened,
this test goes red.

Run:  PYTHONIOENCODING=utf-8 python test_gate.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import almido as A  # noqa: E402

FAKE = "test-gate-not-the-model"
PLANTED = []
FAILURES = []


def check(label, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (" -- " + detail if detail else ""))
    if not ok:
        FAILURES.append(label)


def plant(stem, source):
    """Write a take on disk exactly as make_take would, with a chosen source."""
    audio = stem + ".wav"
    midi = stem + ".mid"
    for name in (audio, midi):
        p = os.path.join(A.TAKES, name)
        with open(p, "wb") as f:
            f.write(b"RIFF____WAVEfmt ")     # not real audio; never played
        PLANTED.append(p)
    meta = {"name": stem, "audio": audio, "midi": midi, "source": source,
            "when": "2026-09-05 00:00:00", "n_notes": 0, "n_chord_events": 0}
    p = os.path.join(A.TAKES, stem + ".json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    PLANTED.append(p)
    return meta


def cleanup():
    for p in PLANTED:
        try:
            os.remove(p)
        except OSError:
            pass


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    print(__doc__.strip().splitlines()[0])
    print()

    # ---------------------------------------------------------------- unit
    print("the predicate:")
    check("model-v2 take is publishable",
          A.take_is_publishable({"source": "model-v2"}) is True)
    for bad in ({"source": "corpus-transcription"}, {"source": None}, {}, None,
                {"source": "model-v3"}, {"source": "MODEL-V2"}):
        check("refuses %r" % (bad,), A.take_is_publishable(bad) is False)

    # ------------------------------------------------------------ on disk
    print("\nnothing already on disk is a non-model take:")
    leaked = []
    for fn in os.listdir(A.TAKES):
        if fn.endswith(".json") and not fn.startswith(FAKE):
            try:
                m = json.load(open(os.path.join(A.TAKES, fn), encoding="utf-8"))
            except Exception:
                continue
            if not A.take_is_publishable(m):
                leaked.append((fn, m.get("source")))
    check("takes/ holds only source=model-v2 sidecars", not leaked, str(leaked))

    # ----------------------------------------------------------- planted
    print("\na planted non-model take:")
    plant(FAKE, "corpus-transcription")
    files = A.publishable_files()
    check("its audio is NOT in publishable_files()", FAKE + ".wav" not in files)
    check("its midi  is NOT in publishable_files()", FAKE + ".mid" not in files)

    n = A.load_existing_takes()
    listed = [t.get("name") for t in A.STATE["takes"]]
    check("it is NOT listed by load_existing_takes()", FAKE not in listed,
          "listed=%d" % n)

    # a model-labelled control, to prove the gate is not simply refusing all
    plant(FAKE + "-control", "model-v2")
    check("a model-v2 take IS in publishable_files()",
          FAKE + "-control.wav" in A.publishable_files())

    # ------------------------------------------------- the voices are split
    # Iddo, same evening: "אין לזה שום הרמוניה, שום מלודיה". The chords were
    # in the MIDI all along -- but every pitched note went out on channel 0
    # under one program, so bass, lead and inner voices arrived as one timbre.
    # This asserts the split on a hand-built score, so it needs no model and
    # no checkpoint to stay true.
    print("\nthe emitted MIDI carries separate voices:")
    import compose as C
    import poly_tok as PT
    sc = PT.Score(bpm=143.55, key_pc=0, n_steps=64, drums=[PT.Drum(0, 0, 2)],
                  notes=[PT.Note(0, 36, 4), PT.Note(0, 60, 4), PT.Note(0, 64, 4),
                         PT.Note(0, 67, 4),                       # a real chord
                         PT.Note(16, 38, 4), PT.Note(16, 62, 4), PT.Note(16, 65, 4),
                         PT.Note(32, 72, 2), PT.Note(48, 40, 4)])
    tmp = os.path.join(A.TAKES, FAKE + "-voices.mid")
    PLANTED.append(tmp)
    C.write_midi(sc, tmp)

    import mido
    pitched, prog, drums = {}, {}, 0
    for msg in mido.MidiFile(tmp):
        if msg.type == "program_change":
            prog[msg.channel] = msg.program
        if msg.type == "note_on" and msg.velocity > 0:
            if msg.channel == 9:
                drums += 1
            else:
                pitched[msg.channel] = pitched.get(msg.channel, 0) + 1
    chans = sorted(set(pitched) | ({9} if drums else set()))
    check("the MIDI has more than 2 channels", len(chans) > 2, str(chans))
    check("pitched material is split across at least 3 channels",
          len(pitched) >= 3, str(dict(pitched)))
    check("each pitched channel has its own GM program",
          len({prog[c] for c in pitched if c in prog}) >= 3, str(prog))
    check("bass and lead are NOT the same program",
          prog.get(C.ROLE_CHANNEL["bass"]) != prog.get(C.ROLE_CHANNEL["lead"]),
          "bass=%s lead=%s" % (prog.get(1), prog.get(0)))
    roles = C.split_roles(sc)
    check("the chord's top note is lead and its bottom note is bass",
          roles[0] == "bass" and roles[3] == "lead",
          "roles of the 4-note chord = %s" % roles[:4])
    check("an inner chord voice is a pad voice", "pad" in roles[:4],
          str(roles[:4]))

    # ------------------------------------------------------- over a socket
    print("\nover a real HTTP socket:")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), A.H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = "http://127.0.0.1:%d" % port
        for name in (FAKE + ".wav", FAKE + ".mid"):
            code, body = get(base + "/takes/" + name)
            check("GET /takes/%s is refused (403)" % name, code == 403,
                  "got %s" % code)
            check("   ...and the body says it was refused",
                  b"REFUSED" in body, body[:60].decode("utf-8", "replace"))
        code, _ = get(base + "/takes/" + FAKE + "-control.wav")
        check("GET a model-v2 take still succeeds (200)", code == 200,
              "got %s" % code)
        # path traversal must not walk around the whitelist
        for evil in ("../compose.py", "..%2Fcompose.py", "%2e%2e/almido.py"):
            code, _ = get(base + "/takes/" + evil)
            check("GET /takes/%s does not escape" % evil, code in (403, 404),
                  "got %s" % code)
    finally:
        srv.shutdown()
        cleanup()
        A.load_existing_takes()

    print()
    if FAILURES:
        print("FAILED: %d" % len(FAILURES))
        for f in FAILURES:
            print("   " + f)
        return 1
    print("ALL GATE CHECKS PASS - a non-model take cannot be served.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        cleanup()
        raise

"""router tests — the pipeline end-to-end with fakes, every terminal state."""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.router import Router  # noqa: E402
from app.stt import DecodeResult  # noqa: E402
from app.typer import FocusInfo, Typer  # noqa: E402


class _MemJournal:
    def __init__(self):
        self.events = []

    def event(self, name, **fields):
        self.events.append((name, fields))
        return {"evt": name, **fields}

    def names(self):
        return [n for n, _ in self.events]


class _MemSpool:
    def __init__(self, ids):
        self._pending = list(ids)
        self.completed = []

    def pending(self):
        return list(self._pending)

    def complete(self, rec_id):
        if rec_id in self._pending:
            self._pending.remove(rec_id)
        self.completed.append(rec_id)


class _ScriptedStt:
    """Returns scripted results per call; records attempts per id."""
    def __init__(self, script):
        self.script = dict(script)      # id -> list[DecodeResult]
        self.attempts = {}

    def decode(self, rec_id, wav_bytes, lang_hint="auto"):
        self.attempts[rec_id] = self.attempts.get(rec_id, 0) + 1
        seq = self.script[rec_id]
        return seq.pop(0) if len(seq) > 1 else seq[0]


def ok_result(text="שלום עולם", lang="he", lp=-0.2):
    return DecodeResult(ok=True, text=text, lang=lang, avg_logprob=lp, ms=300)


class _MemCorpus:
    """Records add() calls; can be armed to raise (a corpus bug must never
    cost a typed sentence)."""
    def __init__(self, raise_on_add=False):
        self.calls = []                 # (rec_id, pcm, text)
        self.raise_on_add = raise_on_add

    def add(self, rec_id, pcm, text):
        if self.raise_on_add:
            raise OSError("disk on fire")
        self.calls.append((rec_id, pcm, text))
        return True


def make_router(j, spool, stt, *, presence=(True, True, "ok"), send_ok=True,
                auto_enter=True, corpus=None):
    focus = FocusInfo(1, 2, "claude.exe")
    typer = Typer(journal=j, presence_verdict=lambda: presence,
                  focus_fn=lambda: focus,
                  send_text=lambda t: send_ok, send_enter=lambda: send_ok)
    return Router(journal=j, spool=spool, stt=stt, typer=typer,
                  read_wav=lambda rid: b"RIFF" if rid != "no-audio" else None,
                  focus_fn=lambda: focus, auto_enter=auto_enter,
                  corpus=corpus)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.j = _MemJournal()

    def test_happy_path_types_and_enters(self):
        spool = _MemSpool(["r-1"])
        r = make_router(self.j, spool, _ScriptedStt({"r-1": [ok_result()]}))
        self.assertEqual(r.process_one("r-1"), "typed")
        self.assertEqual(spool.completed, ["r-1"])
        for evt in ("DECODE", "TYPED", "ENTER"):
            self.assertIn(evt, self.j.names())

    def test_one_retry_then_park_keeps_the_record(self):
        """The park law: a dead server costs a PARK, never a loss."""
        spool = _MemSpool(["r-1"])
        stt = _ScriptedStt({"r-1": [DecodeResult(ok=False, reason="timeout")]})
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "parked")
        self.assertEqual(stt.attempts["r-1"], 2, "exactly one retry")
        self.assertIn("r-1", spool.pending(), "parked stays in the spool")
        self.assertIn("DECODE_PARKED", self.j.names())

    def test_retry_succeeds_second_time(self):
        spool = _MemSpool(["r-1"])
        stt = _ScriptedStt({"r-1": [DecodeResult(ok=False, reason="http"),
                                    ok_result()]})
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "typed")

    def test_late_reply_is_not_retried(self):
        """late_reply is a poisoned reply, not a flaky link — no retry."""
        spool = _MemSpool(["r-1"])
        stt = _ScriptedStt({"r-1": [DecodeResult(ok=False, reason="late_reply")]})
        r = make_router(self.j, spool, stt)
        r.process_one("r-1")
        self.assertEqual(stt.attempts["r-1"], 1)

    def test_hallucination_gated_and_completed(self):
        spool = _MemSpool(["r-1"])
        stt = _ScriptedStt({"r-1": [ok_result(text="Thank you.", lang="en")]})
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "gated")
        self.assertEqual(spool.completed, ["r-1"])
        reasons = [f.get("reason") for n, f in self.j.events
                   if n == "GUARD_DROP"]
        self.assertIn("hallucination", reasons)

    def test_presence_refusal_parks_speech(self):
        """Iddo away → his words wait for him; they do not vanish."""
        spool = _MemSpool(["r-1"])
        r = make_router(self.j, spool, _ScriptedStt({"r-1": [ok_result()]}),
                        presence=(False, False, "idle_no_type"))
        self.assertEqual(r.process_one("r-1"), "parked")
        self.assertIn("r-1", spool.pending())

    def test_0946_typed_but_no_enter(self):
        spool = _MemSpool(["r-1"])
        r = make_router(self.j, spool, _ScriptedStt({"r-1": [ok_result()]}),
                        presence=(True, False, "idle_no_enter"))
        self.assertEqual(r.process_one("r-1"), "typed_no_enter")
        self.assertIn("TYPED", self.j.names())
        self.assertNotIn("ENTER", self.j.names())

    def test_missing_audio_journals_and_moves_on(self):
        spool = _MemSpool(["no-audio"])
        r = make_router(self.j, spool, _ScriptedStt({"no-audio": [ok_result()]}))
        self.assertEqual(r.process_one("no-audio"), "gated")

    # ------------------------------------------------ LANG_FLIP rescue --
    # Measured live 2026-08-20 00:18: Iddo said "שומע אותי או לא?" three
    # times; eran1 auto-detected EN, returned garbage ("Show me out your own.")
    # at lp -0.66..-0.96, the floor dropped it — INVISIBLY. Forced he: lp -0.02.
    # 18 of 24 drops in that window were his Hebrew. Visible beats invisible;
    # invisible loss beats nothing. So: a would-be-dropped EN decode gets ONE
    # second chance as Hebrew; the model's own confidence picks.
    def _rescue_stt(self, first, second):
        class _Stt:
            def __init__(s):
                s.calls = []          # (rec_id, lang_hint)
            def decode(s, rec_id, wav_bytes, lang_hint="auto"):
                s.calls.append((rec_id, lang_hint))
                return first if lang_hint == "auto" else second
        return _Stt()

    def test_en_garbage_below_floor_is_rescued_as_hebrew(self):
        spool = _MemSpool(["r-1"])
        stt = self._rescue_stt(
            ok_result(text="Show me out your own.", lang="en", lp=-0.663),
            ok_result(text="שומע אותי או לא?", lang="he", lp=-0.02))
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "typed")
        self.assertEqual(stt.calls, [("r-1", "auto"), ("r-1", "he")],
                         "exactly one rescue decode, forced he")
        names = self.j.names()
        self.assertIn("DECODE", names, "a DECODE always follows a SEG")
        self.assertIn("LANG_FLIP", names)
        self.assertIn("TYPED", names)
        self.assertNotIn("GUARD_DROP", names, "a rescued record is not a drop")
        flip = [f for n, f in self.j.events if n == "LANG_FLIP"][0]
        self.assertEqual(flip["id"], "r-1")
        self.assertEqual((flip["frm"], flip["to"]), ("en", "he"))
        self.assertEqual(flip["why"], "floor")
        self.assertEqual(r.stats.rescued, 1)
        # the TYPED length is the HEBREW text, not the garbage
        typed = [f for n, f in self.j.events if n == "TYPED"][0]
        self.assertEqual(typed["len"], len("שומע אותי או לא?"))

    def test_rescue_that_also_fails_floor_stays_dropped_once(self):
        spool = _MemSpool(["r-1"])
        stt = self._rescue_stt(
            ok_result(text="And you can clap your mouth.", lang="en", lp=-0.933),
            ok_result(text="אני אוהב את זה ככה עשוי מה עשוי.", lang="he", lp=-0.91))
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "gated")
        self.assertEqual(len(stt.calls), 2)
        drops = [f for n, f in self.j.events if n == "GUARD_DROP"]
        self.assertEqual(len(drops), 1, "one drop line, not two")
        self.assertEqual(drops[0]["reason"], "logprob")
        self.assertEqual(drops[0]["rescue"], "he_failed")
        self.assertNotIn("LANG_FLIP", self.j.names())
        self.assertEqual(spool.completed, ["r-1"])

    def test_rescue_decode_failure_falls_back_to_the_drop_no_park(self):
        """The first decode SUCCEEDED and was judged; a blinking server on the
        rescue must not park the record (the lane moves on) nor retry again."""
        spool = _MemSpool(["r-1"])
        stt = self._rescue_stt(
            ok_result(text="please follow me", lang="en", lp=-1.468),
            DecodeResult(ok=False, reason="timeout"))
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "gated")
        self.assertEqual(len(stt.calls), 2, "no second retry on the rescue")
        self.assertNotIn("DECODE_PARKED", self.j.names())
        self.assertEqual(spool.completed, ["r-1"])

    # Measured 2026-08-20 00:45 on 160 live TYPED records: 19 were EN above
    # the floor; decoded again as he, the model was MORE confident in Hebrew
    # on 12 — 'Makore.'→'מה קורה?' (-0.48→-0.07), 'Show melody?'→'שומע אותי?'
    # (-0.35→-0.04), 'Ma?'→'מה?', 'Ken Ken Ken'→'כן, כן, כן' — and LESS on the
    # 7 that were real English ('Ignorance is a bliss.' -0.15 vs -0.36). So an
    # EN decode that PASSES also gets the he decode, and the model's own
    # confidence picks (INSIGHTS §4's dual-decode, as designed). Symmetric
    # costs: either wrong answer is visibly wrong; argmax is the honest rule.
    def test_en_passing_flips_when_hebrew_is_more_confident(self):
        spool = _MemSpool(["r-1"])
        stt = self._rescue_stt(ok_result(text="Makore.", lang="en", lp=-0.48),
                               ok_result(text="מה קורה?", lang="he", lp=-0.07))
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "typed")
        self.assertEqual(stt.calls, [("r-1", "auto"), ("r-1", "he")])
        flip = [f for n, f in self.j.events if n == "LANG_FLIP"][0]
        self.assertEqual(flip["why"], "confidence")
        typed = [f for n, f in self.j.events if n == "TYPED"][0]
        self.assertEqual(typed["len"], len("מה קורה?"))

    def test_en_passing_stays_english_when_english_is_more_confident(self):
        """Real English is not rewritten in Hebrew letters (the 08-19 scar)."""
        spool = _MemSpool(["r-1"])
        stt = self._rescue_stt(ok_result(text="Ignorance is a bliss.", lang="en", lp=-0.15),
                               ok_result(text="יגנורינס זה בליס.", lang="he", lp=-0.36))
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "typed")
        self.assertEqual(len(stt.calls), 2)
        self.assertNotIn("LANG_FLIP", self.j.names())
        typed = [f for n, f in self.j.events if n == "TYPED"][0]
        self.assertEqual(typed["len"], len("Ignorance is a bliss."))

    def test_en_passing_stays_english_when_hebrew_fails_the_gate(self):
        """A Hebrew candidate below the floor / a hallucination never replaces
        a passing English decode, whatever its logprob says."""
        spool = _MemSpool(["r-1"])
        stt = self._rescue_stt(ok_result(text="then", lang="en", lp=-0.49),
                               ok_result(text="הן.", lang="he", lp=-0.79))
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "typed")
        self.assertNotIn("LANG_FLIP", self.j.names())
        typed = [f for n, f in self.j.events if n == "TYPED"][0]
        self.assertEqual(typed["len"], len("then"))

    def test_en_passing_with_rescue_server_blink_still_types_english(self):
        spool = _MemSpool(["r-1"])
        stt = self._rescue_stt(ok_result(text="fix now", lang="en", lp=-0.5),
                               DecodeResult(ok=False, reason="timeout"))
        r = make_router(self.j, spool, stt)
        self.assertEqual(r.process_one("r-1"), "typed")
        self.assertEqual(len(stt.calls), 2, "no retry on a rescue blink")
        self.assertNotIn("DECODE_PARKED", self.j.names())
        self.assertNotIn("LANG_FLIP", self.j.names())

    def test_no_rescue_for_hebrew_or_russian_or_other_reasons(self):
        """he below floor: forcing he again is the same answer. ru below floor:
        forcing he transliterates his Russian (the 08-19 18:57 scar). A loop or
        a hallucination is never rescued — it is not his speech."""
        cases = [
            ok_result(text="תוסעגגגגליה", lang="he", lp=-0.68),
            ok_result(text="привет", lang="ru", lp=-0.9),
            ok_result(text="Thank you.", lang="en", lp=-0.1),                    # hallucination
            ok_result(text=" ".join(["go"] * 12), lang="en", lp=-0.9),          # loop
            ok_result(text="", lang="en", lp=-0.9),                              # empty
        ]
        for res in cases:
            j = _MemJournal()
            spool = _MemSpool(["r-1"])
            stt = self._rescue_stt(res, ok_result(text="רק לא זה", lang="he", lp=-0.1))
            r = make_router(j, spool, stt)
            self.assertEqual(r.process_one("r-1"), "gated", res)
            self.assertEqual(stt.calls, [("r-1", "auto")], res)
            self.assertNotIn("LANG_FLIP", j.names(), res)

    def test_drain_survives_a_raising_record_and_alarms(self):
        """The beat thread died at 22:20:48 on 2026-08-19 because ONE record
        raised inside drain() — no heartbeat for 4 h. A record that raises is
        journalled as ALARM and the lane moves on; the thread never dies."""
        spool = _MemSpool(["boom", "r-2"])

        class _Stt:
            def decode(self, rec_id, wav_bytes, lang_hint="auto"):
                if rec_id == "boom":
                    raise RuntimeError("journal vocab, say")
                return ok_result()
        r = make_router(self.j, spool, _Stt())
        out = r.drain()
        self.assertEqual(out.get("error"), 1)
        self.assertEqual(out.get("typed"), 1, "the record AFTER the bomb still types")
        alarms = [f for n, f in self.j.events if n == "ALARM"]
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0]["id"], "boom")
        self.assertIn("RuntimeError", alarms[0]["err"])
        self.assertEqual(spool.completed, ["boom", "r-2"],
                         "a record that raises is completed, not re-raised every beat")

    # ------------------------------------------------- corpus capture --
    # "Make the mic always train": every TYPED record — and ONLY a typed
    # record — is handed to the corpus writer with the spool PCM and the
    # text that actually landed in Iddo's window. Room audio is never
    # typed, so room audio can never train (client/corpus.py's law).
    def test_typed_record_reaches_the_corpus_with_pcm_and_text(self):
        spool = _MemSpool(["r-1"])
        corpus = _MemCorpus()
        r = make_router(self.j, spool, _ScriptedStt({"r-1": [ok_result()]}),
                        corpus=corpus)
        self.assertEqual(r.process_one("r-1"), "typed")
        self.assertEqual(corpus.calls, [("r-1", b"RIFF", "שלום עולם")])

    def test_typed_no_enter_still_reaches_the_corpus(self):
        """The text landed in the window — Enter's fate changes nothing."""
        spool = _MemSpool(["r-1"])
        corpus = _MemCorpus()
        r = make_router(self.j, spool, _ScriptedStt({"r-1": [ok_result()]}),
                        presence=(True, False, "idle_no_enter"), corpus=corpus)
        self.assertEqual(r.process_one("r-1"), "typed_no_enter")
        self.assertEqual(len(corpus.calls), 1)

    def test_lang_flip_stores_the_hebrew_that_was_typed(self):
        """The corpus trains on what landed in the window, never on the
        EN garbage the first decode produced."""
        spool = _MemSpool(["r-1"])
        corpus = _MemCorpus()
        stt = self._rescue_stt(
            ok_result(text="Show me out your own.", lang="en", lp=-0.663),
            ok_result(text="שומע אותי או לא?", lang="he", lp=-0.02))
        r = make_router(self.j, spool, stt, corpus=corpus)
        self.assertEqual(r.process_one("r-1"), "typed")
        self.assertEqual(corpus.calls[0][2], "שומע אותי או לא?")

    def test_untyped_records_never_reach_the_corpus(self):
        """gated / parked / presence-refused: not typed, not trained on."""
        cases = [
            dict(stt=_ScriptedStt({"r-1": [ok_result(text="Thank you.",
                                                     lang="en")]})),      # gated
            dict(stt=_ScriptedStt({"r-1": [DecodeResult(ok=False,
                                                        reason="timeout")]})),  # parked
            dict(stt=_ScriptedStt({"r-1": [ok_result()]}),
                 presence=(False, False, "idle_no_type")),               # presence
        ]
        for case in cases:
            corpus = _MemCorpus()
            spool = _MemSpool(["r-1"])
            r = make_router(_MemJournal(), spool, case["stt"],
                            presence=case.get("presence", (True, True, "ok")),
                            corpus=corpus)
            r.process_one("r-1")
            self.assertEqual(corpus.calls, [], case)

    def test_recovered_records_never_reach_the_corpus(self):
        """§1.3 backlog goes to recovered.txt, never to live focus — and
        never to training: nobody accepted those words into a window."""
        spool = _MemSpool(["r-1"])
        spool.recovered_ids = {"r-1"}
        corpus = _MemCorpus()
        r = make_router(self.j, spool, _ScriptedStt({"r-1": [ok_result()]}),
                        corpus=corpus)
        self.assertEqual(r.process_one("r-1"), "gated")
        self.assertEqual(corpus.calls, [])

    def test_corpus_exception_never_costs_the_type_or_the_enter(self):
        spool = _MemSpool(["r-1"])
        r = make_router(self.j, spool, _ScriptedStt({"r-1": [ok_result()]}),
                        corpus=_MemCorpus(raise_on_add=True))
        self.assertEqual(r.process_one("r-1"), "typed",
                         "a corpus bug is an ALARM, never a lost sentence")
        self.assertIn("ENTER", self.j.names())
        alarms = [f for n, f in self.j.events if n == "ALARM"]
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0]["kind"], "corpus_exception")
        self.assertEqual(alarms[0]["id"], "r-1")
        self.assertIn("OSError", alarms[0]["err"])

    def test_no_corpus_wired_is_fine(self):
        spool = _MemSpool(["r-1"])
        r = make_router(self.j, spool, _ScriptedStt({"r-1": [ok_result()]}))
        self.assertEqual(r.process_one("r-1"), "typed")

    def test_real_corpus_end_to_end_wav_and_manifest_on_disk(self):
        """The seam the fakes cannot see: the REAL writer, called by the REAL
        router, produces the file + line eran4's trainer will read."""
        import json
        import shutil
        import tempfile
        from app.corpus import Corpus
        td = tempfile.mkdtemp()
        try:
            root = pathlib.Path(td) / "corpus"
            corpus = Corpus(root, journal=self.j)
            spool = _MemSpool(["ab12cd34-000001"])
            r = make_router(self.j, spool,
                            _ScriptedStt({"ab12cd34-000001": [ok_result()]}),
                            corpus=corpus)
            self.assertEqual(r.process_one("ab12cd34-000001"), "typed")
            self.assertTrue(
                (root / "ab12cd34" / "ab12cd34-000001.wav").exists())
            rec = json.loads((root / "manifest.jsonl").read_text(
                encoding="utf-8"))
            self.assertEqual(rec["text"], "שלום עולם")
            self.assertEqual(rec["source"], "typed")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_drain_is_in_order_and_counts(self):
        spool = _MemSpool(["r-1", "r-2"])
        stt = _ScriptedStt({"r-1": [ok_result()],
                            "r-2": [DecodeResult(ok=False, reason="timeout")]})
        r = make_router(self.j, spool, stt)
        out = r.drain()
        self.assertEqual(out.get("typed"), 1)
        self.assertEqual(out.get("parked"), 1)
        self.assertEqual(r.stats.typed, 1)
        self.assertEqual(r.stats.parked, 1)


if __name__ == "__main__":
    unittest.main()

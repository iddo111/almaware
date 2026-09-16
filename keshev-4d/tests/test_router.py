"""KING'S CANONICAL TESTS — router. Workers may not edit this file.

The law: one lane, in order; one retry only on timeout/http; parked stays
in the spool; presence refusals park speech; hallucinations complete;
Enter is its own verdict.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.router import Router  # noqa: E402
from app.sttclient import DecodeResult  # noqa: E402


class _J:
    def __init__(self): self.events = []
    def event(self, name, **f):
        self.events.append((name, f)); return {"evt": name, **f}
    def names(self): return [n for n, _ in self.events]


class _Spool:
    def __init__(self, ids): self._p = list(ids); self.completed = []
    def pending(self): return list(self._p)
    def complete(self, rid):
        if rid in self._p: self._p.remove(rid)
        self.completed.append(rid)


class _Stt:
    def __init__(self, script): self.script = dict(script); self.attempts = {}
    def decode(self, rid, body, lang_hint="auto"):
        self.attempts[rid] = self.attempts.get(rid, 0) + 1
        seq = self.script[rid]
        return seq.pop(0) if len(seq) > 1 else seq[0]


class _Typer:
    def __init__(self, deliver=(True, "ok"), enter=(True, "ok")):
        self._d, self._e = deliver, enter
        self.delivered = []
    def deliver(self, rid, text):
        self.delivered.append((rid, text)); return self._d
    def enter(self, rid, focus): return self._e


def ok(text="שלום עולם", lang="he", lp=-0.2):
    return DecodeResult(ok=True, text=text, lang=lang, avg_logprob=lp, ms=300)


class RouterTests(unittest.TestCase):
    def setUp(self): self.j = _J()

    def _r(self, spool, stt, typer=None, auto_enter=True):
        return Router(self.j, spool, stt, typer or _Typer(),
                      read_wav=lambda rid: b"RIFF" if rid != "noaud" else None,
                      auto_enter=auto_enter)

    def test_happy_path_typed(self):
        sp = _Spool(["r1"])
        r = self._r(sp, _Stt({"r1": [ok()]}))
        self.assertEqual(r.process_one("r1"), "typed")
        self.assertEqual(sp.completed, ["r1"])
        self.assertIn("DECODE", self.j.names())

    def test_one_retry_then_park(self):
        sp = _Spool(["r1"])
        stt = _Stt({"r1": [DecodeResult(ok=False, reason="timeout")]})
        r = self._r(sp, stt)
        self.assertEqual(r.process_one("r1"), "parked")
        self.assertEqual(stt.attempts["r1"], 2)
        self.assertIn("r1", sp.pending())
        self.assertIn("DECODE_PARKED", self.j.names())

    def test_late_reply_not_retried(self):
        sp = _Spool(["r1"])
        stt = _Stt({"r1": [DecodeResult(ok=False, reason="late_reply")]})
        r = self._r(sp, stt)
        r.process_one("r1")
        self.assertEqual(stt.attempts["r1"], 1)

    def test_hallucination_gated_and_completed(self):
        sp = _Spool(["r1"])
        r = self._r(sp, _Stt({"r1": [ok(text="Thank you.", lang="en")]}))
        self.assertEqual(r.process_one("r1"), "gated")
        self.assertEqual(sp.completed, ["r1"])

    def test_presence_refusal_parks(self):
        sp = _Spool(["r1"])
        t = _Typer(deliver=(False, "presence"))
        r = self._r(sp, _Stt({"r1": [ok()]}), t)
        self.assertEqual(r.process_one("r1"), "parked")
        self.assertIn("r1", sp.pending())

    def test_enter_refused_is_typed_no_enter(self):
        sp = _Spool(["r1"])
        t = _Typer(enter=(False, "presence"))
        r = self._r(sp, _Stt({"r1": [ok()]}), t)
        self.assertEqual(r.process_one("r1"), "typed_no_enter")

    def test_missing_audio_gated(self):
        sp = _Spool(["noaud"])
        r = self._r(sp, _Stt({"noaud": [ok()]}))
        self.assertEqual(r.process_one("noaud"), "gated")

    def test_drain_in_order(self):
        sp = _Spool(["r1", "r2"])
        stt = _Stt({"r1": [ok()],
                    "r2": [DecodeResult(ok=False, reason="timeout")]})
        r = self._r(sp, stt)
        out = r.drain()
        self.assertEqual(out.get("typed"), 1)
        self.assertEqual(out.get("parked"), 1)


if __name__ == "__main__":
    unittest.main()

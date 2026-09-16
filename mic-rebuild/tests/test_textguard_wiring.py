"""K13 WIRING TDD — client/textguard.py actually plugged into the router's
`guard_fn` seam, proven end-to-end through a REAL Router.

WHY THIS FILE EXISTS
--------------------
tests/test_textguard.py::test_import_discipline_client_only_router passes
VACUOUSLY today: it asserts "nobody but router.py imports textguard", and
nobody imports textguard AT ALL — client/router.py still ships the K12
placeholder `default_guard` (client/router.py:344), whose own docstring says
"K13 replaces it via the guard_fn seam".

So the guard that this whole rebuild exists for — the one that stops
'תודה רבה' / 'חחחחח' / 'Thanks for watching' typing themselves into Iddo's
screen on silence — is wired to NOTHING.

THE SEAM, QUOTED FROM client/router.py (all three call sites, verbatim):

    client/router.py:369   guard_fn: Callable[[dict], str | None] = default_guard
    client/router.py:428   text = self.guard_fn(res)          # live typing lane
    client/router.py:498   text = self.guard_fn(res)          # _divert / stale lane
    client/router.py:557   text = self.guard_fn(res)          # _drain_recovery lane

and at every one of the three the router then does:

    if text is None:            -> journal GUARD_DROP
    if not text.strip():        -> journal EMPTY

THE MISMATCH (real, not papered over)
-------------------------------------
textguard's public entry is
    final(text: str, *, lang, avg_logprob, lang_hint="auto") -> Verdict
i.e. FOUR arguments in and a rich Verdict out. The router's seam is
ONE dict in and `str | None` out. They cannot be connected without an
adapter. The adapter belongs in textguard.py (its owner), not in app.py —
tests/test_textguard.py:248 forbids any module but router.py from importing
the guard, so the entry point can only ever reach it via router.py.

This file pins BOTH shapes so the seam is a one-import change for whoever
owns client/router.py:
    textguard.guard(res)        -> str | None   (the CURRENT K12 contract)
    textguard.from_result(res)  -> Verdict      (the lossless widened one)

Everything below drives the REAL Router + REAL Spool + REAL Telemetry +
REAL textguard. The only fake is the worker (a scripted decode reply dict) —
no device, no network, no model. Nothing here touches audio.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client import textguard  # noqa: E402
from client.router import Router  # noqa: E402
from client.spool import RecoveredTranscript, Spool  # noqa: E402
from client.telemetry import Telemetry  # noqa: E402

PCM = b"\x01\x00" * 320

# The entry the router seam is wired to. If client/router.py ever widens the
# seam to `Callable[[dict], Verdict]`, this is the ONE line that changes
# (to textguard.from_result) — see test_seam_shape_has_a_matching_entry.
ROUTER_GUARD = textguard.guard

# Rig sentinel: build the Router with NO guard_fn argument at all, so what it
# runs on is whatever client/router.py DECLARES as the default.
NO_INJECTION = object()


# ------------------------------------------------------------------ fakes


class Clock:
    def __init__(self, start: float = 10_000.0) -> None:
        self.t = float(start)
        self._start = float(start)
        self._wall0 = datetime(2026, 8, 12, 12, 0, 0)

    def mono(self) -> float:
        return self.t

    def now(self) -> float:
        return self.t

    def wall(self) -> datetime:
        return self._wall0 + timedelta(seconds=self.t - self._start)


class Recorder(Telemetry):
    """The REAL K3 telemetry (closed vocabulary enforced) + in-memory tap."""

    def __init__(self, tmp: str) -> None:
        super().__init__(tmp, session_id="aabbccdd")
        self.tap: list[tuple[str, dict]] = []

    def event(self, evt: str, level: str = "INFO", **fields) -> None:
        super().event(evt, level, **fields)
        self.tap.append((evt, dict(fields)))

    def of(self, evt: str) -> list[dict]:
        return [f for e, f in self.tap if e == evt]

    def close_quiet(self) -> None:
        try:
            self.close()
        except RuntimeError:
            return


class ScriptedWorker:
    """Returns ONE scripted decode reply — the exact dict shape the real
    WorkerManager.decode() hands the router (client/worker_mgr.py:244)."""

    def __init__(self, reply: dict) -> None:
        self.state = "READY"
        self.local_state = "READY"
        self.worker_rss_mb = 100
        self.worker_vram_mb = 1000
        self.reply = reply

    def decode(self, rec_id: str, pcm: bytes, *, engine: str,
               lang_hint: str = "auto") -> dict:
        res = dict(self.reply)
        res.setdefault("ok", True)
        res.setdefault("decode_ms", 400)
        res["id"] = rec_id
        res["engine"] = engine
        return res

    def ping(self) -> bool:
        return True

    def probe(self) -> dict:
        return {"event": "probe_result", "state": "READY", "healthy": True,
                "decode_p50_ms": 400, "decode_p95_ms": 1200, "uptime_s": 9999}


class Rig:
    """Real Router + real Spool + real Telemetry + the REAL textguard."""

    def __init__(self, td: str, reply: dict, **router_kw) -> None:
        self.td = Path(td)
        self.clock = Clock()
        self.worker = ScriptedWorker(reply)
        self.tel = Recorder(td)
        self.spool = Spool(self.td / "spool", now_fn=self.clock.now)
        self.recovered_path = self.td / "recovered.txt"
        self.recovered = RecoveredTranscript(self.recovered_path)
        self.typed: list[str] = []

        def type_fn(text: str) -> bool:
            self.typed.append(text)
            return True

        kw = dict(recovered=self.recovered, type_fn=type_fn,
                  guard_fn=ROUTER_GUARD, stale_sec=25.0,
                  monotonic=self.clock.mono, now=self.clock.now,
                  wallclock=self.clock.wall, pop_timeout=0.01)
        kw.update(router_kw)
        if kw.get("guard_fn") is NO_INJECTION:
            del kw["guard_fn"]             # run on the router's OWN default
        self.router = Router(self.spool, self.worker, self.tel, **kw)
        self._seq = 0

    def feed(self, *, age_s: float = 0.0) -> str:
        self._seq += 1
        rid = f"d13d13d1-{self._seq:06d}"
        t_end = self.clock.now() - age_s
        rec = self.spool.write_ahead(PCM, seg_id=rid, t_start=t_end - 1.0,
                                     t_end=t_end, duration_ms=1000,
                                     rms_raw=0.01, gain=1.0)
        self.spool.enqueue(rec)
        return rid

    def journal(self) -> list[dict]:
        p = self.spool.journal_path
        if not p.is_file():
            return []
        return [json.loads(x) for x in
                p.read_text(encoding="utf-8").splitlines() if x.strip()]

    def outcomes(self, outcome: str) -> list[str]:
        return [e["id"] for e in self.journal() if e["outcome"] == outcome]

    def recovered_text(self) -> str:
        if not self.recovered_path.is_file():
            return ""
        return self.recovered_path.read_text(encoding="utf-8")


class RigCase(unittest.TestCase):
    def make_rig(self, reply: dict, **kw) -> Rig:
        td = TemporaryDirectory()
        self.addCleanup(td.cleanup)
        rig = Rig(td.name, reply, **kw)
        self.addCleanup(rig.tel.close_quiet)   # LIFO: closes before cleanup
        return rig


# ============================================================ the seam shape


class SeamShape(unittest.TestCase):
    """The adapter must MATCH what client/router.py actually calls — pinned
    against the router source so a widened seam is caught, not guessed."""

    ROUTER_SRC = (REPO / "client" / "router.py").read_text(encoding="utf-8")
    CALL_SITE = "text = self.guard_fn(res)"

    def test_router_calls_the_seam_with_one_dict(self):
        # the exact quoted call site, at all three lanes (live/stale/recovery)
        n = self.ROUTER_SRC.count(self.CALL_SITE)
        self.assertGreaterEqual(
            n, 1, f"router no longer contains {self.CALL_SITE!r} — the K13 "
                  "seam moved; re-read client/router.py before trusting this")

    def test_seam_shape_has_a_matching_entry(self):
        """Whatever shape the router's guard_fn annotation declares,
        client/textguard.py must already expose an entry of that shape.
        Non-blocking by design: it adapts to the widened seam instead of
        failing when someone else lands it."""
        ann = re.search(r"guard_fn:\s*Callable\[\[dict\],\s*([^\]]+)\]",
                        self.ROUTER_SRC)
        self.assertIsNotNone(ann, "guard_fn annotation not found in router")
        shape = ann.group(1).strip()
        if "Verdict" in shape:
            fn = textguard.from_result
            out = fn({"text": "shalom", "lang": "he", "avg_logprob": -0.2})
            self.assertIsInstance(out, textguard.Verdict)
        else:
            self.assertEqual(shape, "str | None", f"unknown seam shape {shape!r}")
            fn = textguard.guard
            out = fn({"text": "shalom", "lang": "he", "avg_logprob": -0.2})
            self.assertIsInstance(out, str)
        self.assertIs(ROUTER_GUARD, fn,
                      "ROUTER_GUARD in this file no longer matches the router "
                      "seam shape — flip it to the entry named above")

    def test_adapter_lives_in_textguard_not_elsewhere(self):
        """The guard stays one copy (scar 28): both adapters are defined in
        client/textguard.py, so router.py needs a single import."""
        src = (REPO / "client" / "textguard.py").read_text(encoding="utf-8")
        self.assertIn("def guard(", src)
        self.assertIn("def from_result(", src)


# ====================================================== drops through router


class RealGuardDropsHallucinations(RigCase):
    """The REAL textguard, reached only through Router.step(). Each case is
    a production failure family from alma-mic — a decode the old mic TYPED."""

    def assert_dropped(self, reply: dict) -> None:
        rig = self.make_rig(reply)
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [], f"HALLUCINATION TYPED: {reply!r}")
        self.assertEqual(rig.outcomes("GUARD_DROP"), [rid])
        self.assertEqual(len(rig.tel.of("GUARD_DROP")), 1)

    def test_hebrew_laughter_blob_is_dropped(self):
        # laughfix 2026-08-08: 'חחח' sat below the char-run threshold and
        # typed all night.
        self.assert_dropped({"text": "חחחחח", "lang": "he",
                             "avg_logprob": -0.3})

    def test_hebrew_todah_on_silence_is_dropped(self):
        self.assert_dropped({"text": "תודה רבה.", "lang": "he",
                             "avg_logprob": -0.25})

    def test_english_subtitle_credit_is_dropped(self):
        self.assert_dropped({"text": "Thanks for watching", "lang": "en",
                             "avg_logprob": -0.2})

    def test_arabic_subscribe_is_dropped(self):
        self.assert_dropped({"text": "اشتركوا في القناة", "lang": "ar",
                             "avg_logprob": -0.2})

    def test_repeated_token_loop_is_dropped(self):
        self.assert_dropped({"text": "מה מה מה מה", "lang": "he",
                             "avg_logprob": -0.4})

    def test_char_run_is_dropped(self):
        self.assert_dropped({"text": "אאאאאאאאאאאא", "lang": "he",
                             "avg_logprob": -0.3})

    def test_low_avg_logprob_is_dropped(self):
        # real-looking words, garbage confidence — scar 27 layer 5
        self.assert_dropped({"text": "שלום מה נשמע היום", "lang": "he",
                             "avg_logprob": -1.4})

    def test_off_whitelist_language_is_dropped_with_a_legal_journal_outcome(self):
        """langpolicy allows he/en only. The router journal has NO
        'LANG_DROP' outcome (client/spool.py:58) — journaling one would raise
        UnknownOutcomeError. Proving the drop lands as GUARD_DROP proves the
        adapter cannot crash the router.

        The sentence is deliberately NOT on the blocklist, so the drop can
        only come from layer 4 (off-whitelist), not layer 3."""
        self.assertEqual(textguard.hallucination_reason(
            "это настоящее предложение"), "")
        self.assert_dropped({"text": "это настоящее предложение", "lang": "ru",
                             "avg_logprob": -0.3})


# ====================================================== passes through router


class RealGuardPassesRealSpeech(RigCase):

    def test_real_hebrew_utterance_types_verbatim(self):
        text = "אבא בוא נלך לגן עם הכלב"
        rig = self.make_rig({"text": text, "lang": "he", "avg_logprob": -0.35})
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [text])          # EXACT, guard never mutates
        self.assertEqual(rig.outcomes("TYPED"), [rid])

    def test_real_english_utterance_types_verbatim(self):
        text = "open the router file and read the guard seam"
        rig = self.make_rig({"text": text, "lang": "en", "avg_logprob": -0.3})
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [text])
        self.assertEqual(rig.outcomes("TYPED"), [rid])

    def test_sentence_that_merely_mentions_a_blocklist_phrase_passes(self):
        # scar 28: full-text match, never substring-anywhere
        text = "please subscribe him to the mailing list tomorrow morning"
        rig = self.make_rig({"text": text, "lang": "en", "avg_logprob": -0.3})
        rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [text])

    def test_missing_avg_logprob_fails_OPEN_and_types(self):
        """An engine that stops reporting logprobs must not mute dictation
        (scar-49 asymmetry: the loss-critical path fails open)."""
        rig = self.make_rig({"text": "שלום עולם", "lang": "he"})
        rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, ["שלום עולם"])

    def test_whitespace_only_decode_journals_EMPTY_not_GUARD_DROP(self):
        """The adapter must route an EMPTY verdict into the router's EMPTY
        branch (client/router.py:434), keeping the ledger honest about WHY
        nothing was typed."""
        rig = self.make_rig({"text": "   ", "lang": "he", "avg_logprob": -0.3})
        rid = rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [])
        self.assertEqual(rig.outcomes("EMPTY"), [rid])
        self.assertEqual(rig.outcomes("GUARD_DROP"), [])


# =================================================== the other two lanes


class GuardAppliesToEveryLane(RigCase):
    """client/router.py:498 (stale divert) and :557 (recovery drain) use the
    SAME seam — a hallucination must not reach recovered.txt either."""

    def test_stale_hallucination_never_reaches_recovered_txt(self):
        rig = self.make_rig({"text": "תודה רבה", "lang": "he",
                             "avg_logprob": -0.3})
        rid = rig.feed(age_s=40.0)          # > stale_sec=25 -> _divert
        rig.router.step()
        self.assertEqual(rig.typed, [])
        self.assertEqual(rig.recovered_text(), "")
        self.assertEqual(rig.outcomes("GUARD_DROP"), [rid])

    def test_stale_real_speech_still_reaches_recovered_txt(self):
        text = "זה משפט אמיתי שנאמר מאוחר מדי"
        rig = self.make_rig({"text": text, "lang": "he", "avg_logprob": -0.3})
        rid = rig.feed(age_s=40.0)
        rig.router.step()
        self.assertEqual(rig.typed, [])     # scar 16: never live focus
        self.assertIn(text, rig.recovered_text())
        self.assertEqual(rig.outcomes("RECOVERED"), [rid])


# ============================================== the lossless Verdict entry


class LosslessVerdictEntry(unittest.TestCase):
    """from_result() keeps everything the str|None seam throws away —
    the telemetry event name (LANG_DROP vs GUARD_DROP), the reason, and the
    detail. It is what a widened seam should use."""

    def test_from_result_reports_lang_drop_distinctly(self):
        # NOT a blocklist phrase, so layer 4 (off-whitelist) is what fires —
        # this is exactly the information the str|None seam throws away.
        v = textguard.from_result({"text": "это настоящее предложение",
                                   "lang": "ru", "avg_logprob": -0.3})
        self.assertFalse(v.ok)
        self.assertEqual(v.event, "LANG_DROP")
        self.assertEqual(v.reason, "off_whitelist")
        # …and the narrow seam collapses it to a bare None -> GUARD_DROP
        self.assertIsNone(textguard.guard({"text": "это настоящее предложение",
                                           "lang": "ru", "avg_logprob": -0.3}))

    def test_from_result_names_the_rule_that_fired(self):
        v = textguard.from_result({"text": "חחחחח", "lang": "he",
                                   "avg_logprob": -0.3})
        self.assertEqual(v.event, "GUARD_DROP")
        self.assertEqual(v.reason, "filter")
        self.assertEqual(v.detail, "laughter_blob")

    def test_from_result_detail_never_carries_user_speech(self):
        secret = "הסיסמה שלי היא אלפא ביתא גימל"
        v = textguard.from_result({"text": secret, "lang": "he",
                                   "avg_logprob": -3.0})
        self.assertFalse(v.ok)
        self.assertNotIn("אלפא", v.detail)
        self.assertNotIn(secret, v.detail)

    def test_from_result_honours_a_forced_lang_hint(self):
        # a user-forced language skips the whitelist layer (alma-mic parity)
        v = textguard.from_result({"text": "продолжение следует", "lang": "ru",
                                   "avg_logprob": -0.3, "lang_hint": "ru"})
        self.assertEqual(v.event, "GUARD_DROP")   # blocklist still fires
        v2 = textguard.from_result({"text": "это настоящее предложение",
                                    "lang": "ru", "avg_logprob": -0.3,
                                    "lang_hint": "ru"})
        self.assertTrue(v2.ok)

    def test_guard_and_from_result_agree_on_every_pass(self):
        for reply in ({"text": "שלום", "lang": "he", "avg_logprob": -0.2},
                      {"text": "hello there", "lang": "en", "avg_logprob": -0.2}):
            with self.subTest(reply=reply):
                self.assertEqual(textguard.guard(reply),
                                 textguard.from_result(reply).text)

    def test_adapters_tolerate_a_malformed_reply(self):
        """A worker reply missing every field must drop quietly, never raise
        inside the router thread."""
        self.assertEqual(textguard.guard({}), "")     # -> router's EMPTY lane
        self.assertEqual(textguard.from_result({}).event, "EMPTY")


# ============================================ the DEFAULT must be the guard


class TheDefaultIsTheRealGuard(RigCase):
    """The dispute, settled by execution.

    Every test above injects `guard_fn=ROUTER_GUARD` by hand. That proves the
    ADAPTER works; it proves nothing about what a Router runs on when nobody
    injects anything — which is exactly what the entry point does
    (client/app.py:596 `if guard_fn is None: guard_fn = resolve_guard_fn()`).

    So this class injects NOTHING. If client/router.py still declares
    `guard_fn=default_guard`, a hallucination is TYPED and app assembly
    refuses to boot.
    """

    def test_router_declares_the_real_guard_as_its_default(self):
        import inspect
        declared = inspect.signature(
            Router.__init__).parameters["guard_fn"].default
        self.assertIs(declared, ROUTER_GUARD,
                      "client/router.py's guard_fn default is "
                      f"{declared.__module__}.{declared.__qualname__} — the K12 "
                      "pass-through placeholder. textguard is wired to nothing.")

    def test_the_entry_point_resolves_the_guard_off_the_real_router(self):
        """client/app.py refuses to assemble on the placeholder — so this is
        also the boot check: no wiring, no program."""
        from client import app, router
        self.assertIs(app.resolve_guard_fn(router), ROUTER_GUARD)

    def test_uninjected_router_drops_todah_on_silence(self):
        rig = self.make_rig({"text": "תודה רבה", "lang": "he",
                             "avg_logprob": -0.2}, guard_fn=NO_INJECTION)
        rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, [],
                         "HALLUCINATION TYPED by a router nobody injected a "
                         "guard into — the K13 seam is not wired")
        self.assertEqual(len(rig.outcomes("GUARD_DROP")), 1)

    def test_uninjected_router_still_types_real_speech(self):
        rig = self.make_rig({"text": "שלום עולם זה משפט אמיתי", "lang": "he",
                             "avg_logprob": -0.2}, guard_fn=NO_INJECTION)
        rig.feed()
        rig.router.step()
        self.assertEqual(rig.typed, ["שלום עולם זה משפט אמיתי"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

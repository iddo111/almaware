"""K13 TDD tests — client/textguard.py (PHASE2-DESIGN.md section 2 textguard
row + section 4.1; PHASE1-INQUIRY.md scars 27 layers 5-7, 28; criterion 10).

The guard is the LAST pipeline stage before typing (scar 28): the knowledge
ported from alma-mic stt.py as behaviour, re-tested here from scratch:

  * multilingual hallucination blocklist matched on the FULL normalized text
    (Hebrew תודה family, כתוביות, subscribe-junk, amara-junk, CJK/RU/AR),
  * laughter-blob rule (3-5 char חחח/אהה blobs) with the guaranteed
    aba/ima-pass property (אבא/אמא and every real word sail through),
  * 8+ char-runs, low-variety strings, repeated-token / repeated-fragment
    loops, ultra-short 1-2 char junk,
  * post-hoc avg_logprob floor (decode_params.AVG_LOGPROB_DROP — ONE truth),
  * off-whitelist language drop (auto mode only; whitelist = langpolicy's).

Pipeline-order law (scar 28, the drifting-copies scar):
  * the guard runs LAST, after ALL text mutation — proven with a mutation
    chain whose pieces individually PASS the guard but whose final joined
    text must DROP (guard-before-mutation would have typed junk);
  * a PASS verdict returns the text EXACTLY as given (the guard never
    mutates, so nothing downstream can "fix up" guard-approved text);
  * exactly ONE copy of the guard exists (grep assert over the repo);
  * only the router may import it client-side; the server NEVER filters
    (scar 28: textguard is client-only).

Criterion 10 (corpus half, text-level): zero hallucinated typing on the
known-failing corpus; Hebrew CER on real transcribed utterances from the
alma-mic voice_corpus <= baseline + 2% absolute. At the guard stage the
baseline is identity (CER 0.0) — the decode CER itself was measured at
K9/K10 model-side — so the guard's whole CER budget is 2%: it must not
eat real speech. Text-only, CPU-side; no decode, no GPU, no device.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools" / "replay"))

from client import textguard  # noqa: E402
from common import decode_params, langpolicy  # noqa: E402
import textmetrics  # noqa: E402

MANIFEST = REPO / "tools" / "replay" / "textguard_corpus.json"

# A good decode: confident, routed Hebrew. Individual tests override fields.
GOOD = dict(lang="he", avg_logprob=-0.30)


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


class VerdictContract(unittest.TestCase):
    """final() returns a Verdict whose events map onto the telemetry vocab."""

    def test_pass_verdict(self):
        v = textguard.final("שלום עולם", **GOOD)
        self.assertTrue(v.ok)
        self.assertEqual(v.text, "שלום עולם")
        self.assertEqual(v.reason, "pass")
        self.assertIsNone(v.event)

    def test_empty_is_EMPTY(self):
        for raw in ("", "   ", "\n\t "):
            with self.subTest(raw=repr(raw)):
                v = textguard.final(raw, **GOOD)
                self.assertFalse(v.ok)
                self.assertIsNone(v.text)
                self.assertEqual(v.reason, "empty")
                self.assertEqual(v.event, "EMPTY")

    def test_filter_is_GUARD_DROP(self):
        v = textguard.final("חחח", **GOOD)
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "filter")
        self.assertEqual(v.event, "GUARD_DROP")
        self.assertTrue(v.detail)          # names the rule that fired

    def test_low_logprob_is_GUARD_DROP(self):
        v = textguard.final("שלום עולם", lang="he", avg_logprob=-1.5)
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "low_logprob")
        self.assertEqual(v.event, "GUARD_DROP")

    def test_off_whitelist_is_LANG_DROP(self):
        v = textguard.final("привет мир", lang="ru", avg_logprob=-0.3)
        self.assertFalse(v.ok)
        self.assertEqual(v.reason, "off_whitelist")
        self.assertEqual(v.event, "LANG_DROP")

    def test_events_exist_in_telemetry_vocab(self):
        from client.telemetry import EVENT_VOCABULARY
        for ev in ("EMPTY", "GUARD_DROP", "LANG_DROP"):
            self.assertIn(ev, EVENT_VOCABULARY)


class LogprobFloor(unittest.TestCase):
    """Scar 27 layer 5 — the floor is decode_params.AVG_LOGPROB_DROP, ONE truth."""

    def test_floor_is_the_shared_constant(self):
        self.assertEqual(textguard.LOGPROB_FLOOR, decode_params.AVG_LOGPROB_DROP)

    # Bound to the CONSTANT, never to a literal. These read -1.0 until
    # 2026-08-14, when the floor was recalibrated to -0.6 on 138 measured
    # decodes — and the literals failed, which invites the next reader to
    # "fix" the test by reverting a calibration that was correct. The floor
    # is a measured, movable number; what the tests own is the BEHAVIOUR at
    # its edges, not its value.
    FLOOR = textguard.LOGPROB_FLOOR

    def test_below_floor_drops(self):
        v = textguard.final("טקסט אמיתי לגמרי", lang="he",
                            avg_logprob=self.FLOOR - 0.01)
        self.assertEqual(v.reason, "low_logprob")

    def test_at_floor_passes(self):
        v = textguard.final("טקסט אמיתי לגמרי", lang="he",
                            avg_logprob=self.FLOOR)
        self.assertTrue(v.ok)

    def test_above_floor_passes(self):
        v = textguard.final("טקסט אמיתי לגמרי", lang="he",
                            avg_logprob=self.FLOOR + 0.4)
        self.assertTrue(v.ok)

    def test_floor_sits_between_invention_and_quiet_speech(self):
        """TWO measurements, one day, and they disagree — which is the finding.

        avg_logprob on Iddo's OWN decodes, same mic, same model:
            morning  loud  (rms 0.027)   median -0.367   worst -0.913
            night    quiet (rms 0.0046)  median -0.685   worst -1.720

        A constant cannot separate "the model is inventing" from "he is talking
        quietly", because they score the same. -1.0 never fired at all in the
        morning; -0.6 then ate 450 of 499 segments at night. So this test does
        NOT assert a magic value. It asserts the floor stays in the only band
        that is defensible: low enough that ordinary quiet speech survives
        (scar 17/18 — losing a real word is the worse failure), and not so low
        it can never fire at all.

        When the adaptive gate lands (lp relative to a rolling median), delete
        this test and assert the RELATIVE rule instead.
        """
        self.assertLessEqual(
            textguard.LOGPROB_FLOOR, -0.9,
            "floor is tight enough to eat quiet speech: his night median was "
            "-0.685 and real sentences reached -1.72")
        self.assertGreater(
            textguard.LOGPROB_FLOOR, -2.0,
            "floor is below anything ever observed — a guard nothing can trip "
            "is not a guard (that was the -1.0 bug)")


class OffWhitelist(unittest.TestCase):
    """Scar 27 layer 7 — whitelist truth is langpolicy.WHITELIST (one source)."""

    def test_whitelist_is_langpolicy(self):
        self.assertEqual(tuple(textguard.LANG_WHITELIST), langpolicy.WHITELIST)

    def test_whitelist_langs_pass(self):
        for lang in langpolicy.WHITELIST:
            with self.subTest(lang=lang):
                self.assertTrue(textguard.final("real text here", lang=lang,
                                                avg_logprob=-0.3).ok)

    def test_off_whitelist_drops_in_auto(self):
        for lang in ("ru", "ar", "ja", "is", None):
            with self.subTest(lang=lang):
                v = textguard.final("real text here", lang=lang, avg_logprob=-0.3)
                self.assertEqual(v.reason, "off_whitelist")

    def test_forced_hint_skips_whitelist_check(self):
        # parity with alma-mic: the off-whitelist drop guards AUTO routing only;
        # a user-forced language is honoured (the drop cannot fire on it anyway
        # in KESHEV because langpolicy never emits an off-whitelist lang).
        v = textguard.final("real text here", lang="ru", avg_logprob=-0.3,
                            lang_hint="he")
        self.assertTrue(v.ok)


class LaughterBlobAndProperty(unittest.TestCase):
    """The laughfix rule (2026-08-08): 3-5 char laughter blobs sat BELOW the
    char-run thresholds and typed all night. Blobs drop; real words pass."""

    BLOBS = ["חחח", "חחחח", "חחחחח", "אהה", "אההה", "אהההה",
             "חחח.", " חחח ", "ההה", "אאא"]
    REAL = ["אבא", "אמא", "אבא בוא הנה", "אמא שלי",
            "החתול חתך חתיכת חסה",      # ח-heavy REAL sentence
            "ההר ההוא",                  # ה-heavy REAL phrase
            "כן", "לא", "אה",            # short real fillers (alma-mic parity)
            "שלום", "בסדר גמור"]

    def test_blobs_drop(self):
        for t in self.BLOBS:
            with self.subTest(text=t):
                v = textguard.final(t, **GOOD)
                self.assertFalse(v.ok, f"laughter blob typed: {t!r}")

    def test_aba_ima_pass_property(self):
        for t in self.REAL:
            with self.subTest(text=t):
                v = textguard.final(t, **GOOD)
                self.assertTrue(v.ok, f"real word eaten: {t!r} ({v.reason}/{v.detail})")


class DetectorClasses(unittest.TestCase):
    """Char-runs, repeat loops, ultra-short junk — each a real logged failure."""

    def test_char_runs_drop(self):
        for t in ("אבגאהההההההה", "aaaaaaaaaaaa", "בבבבבבבבב",
                  "xyxyxyxyxyxyxyxy"):       # repeated 2-char fragment
            with self.subTest(text=t):
                self.assertFalse(textguard.final(t, **GOOD).ok, t)

    def test_repeat_loops_drop(self):
        for t in ("ма ма ма ма ма", "אמא אמא אמא אמא אמא",
                  "amma amma amma amma"):
            with self.subTest(text=t):
                self.assertFalse(textguard.final(t, **GOOD).ok, t)

    def test_ultra_short_junk_drops(self):
        for t in ("a", "?", "1", ".."):
            with self.subTest(text=t):
                self.assertFalse(textguard.final(t, **GOOD).ok, t)

    def test_short_real_words_pass(self):
        for t in ("ok", "כן", "לא", "hi"):
            with self.subTest(text=t):
                self.assertTrue(textguard.final(t, **GOOD).ok, t)

    def test_long_real_sentences_pass(self):
        for t in ("תריץ את הסקריפט על eran1 עכשיו בבקשה",
                  "This is spoken English, plain and simple.",
                  "אני רוצה לבדוק את המיקרופון החדש שבנינו היום",
                  "הכתובת היא www.example.com ותשמור אותה בקובץ"):
            with self.subTest(text=t):
                self.assertTrue(textguard.final(t, **GOOD).ok, t)


class PipelineOrder(unittest.TestCase):
    """Scar 28: guard LAST after all mutation; ONE copy; client-only."""

    def test_guard_must_run_after_mutation(self):
        # Two decode pieces that each PASS the guard on their own…
        parts = ["אה", "הא"]
        for p in parts:
            self.assertTrue(textguard.final(p, **GOOD).ok, p)
        # …but the pipeline's real mutation (segment join + ws-normalize, the
        # same shape as the worker's " ".join(s.text.strip() ...)) yields a
        # laughter blob. Guard-on-raw-parts (the alma-mic bug: guards ran on
        # raw_text while text mutated afterwards) would have TYPED it; the
        # guard as the FINAL stage must DROP it.
        joined = re.sub(r"\s+", " ", " ".join(p.strip() for p in parts)).strip()
        v = textguard.final(joined, **GOOD)
        self.assertFalse(v.ok, f"post-mutation junk typed: {joined!r}")

    def test_pass_verdict_returns_text_exactly(self):
        # The guard never mutates: what it approves is what gets typed, so no
        # mutation can happen AFTER the guard by construction.
        for t in ("שלום עולם", "  padded  ", "Mixed עברית and English!"):
            with self.subTest(text=t):
                v = textguard.final(t, **GOOD)
                self.assertTrue(v.ok)
                self.assertEqual(v.text, t)

    @staticmethod
    def _source_files():
        skip_dirs = {"tests", "_genizah", "__pycache__", "state", ".git"}
        for p in REPO.rglob("*.py"):
            if not any(part in skip_dirs for part in p.parts):
                yield p

    def test_exactly_one_guard_copy(self):
        marker = "_HALLUCINATION" + "_BLOCKLIST"
        owners = [p for p in self._source_files()
                  if marker in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual([p.relative_to(REPO).as_posix() for p in owners],
                         ["client/textguard.py"])

    def test_import_discipline_client_only_router(self):
        # only the router (the ONLY caller of typer, section 4.1) may import
        # the guard client-side; the server never filters (scar 28).
        imp = re.compile(r"^\s*(?:import|from)\s+\S*textguard", re.M)
        for p in self._source_files():
            rel = p.relative_to(REPO).as_posix()
            if rel in ("client/textguard.py", "client/router.py"):
                continue
            with self.subTest(file=rel):
                self.assertIsNone(imp.search(p.read_text(encoding="utf-8", errors="replace")),
                                  f"{rel} imports textguard — guard is router-only")


class Criterion10Corpus(unittest.TestCase):
    """The known-failing-clips corpus (text level): zero hallucinated typing;
    real Hebrew utterances survive with CER <= baseline(0) + 2% absolute."""

    @classmethod
    def setUpClass(cls):
        if not MANIFEST.is_file():
            raise unittest.SkipTest(f"corpus manifest missing: {MANIFEST} "
                                    "(run tools/build_textguard_corpus.py)")
        cls.man = load_manifest()

    def test_manifest_coverage(self):
        classes = {h["class"] for h in self.man["hallucinations"]}
        for required in ("laughter", "todah", "subtitles", "subscribe",
                         "cjk", "ru", "ar", "repeat", "charrun", "short"):
            self.assertIn(required, classes)
        self.assertGreaterEqual(len(self.man["hallucinations"]), 25)
        self.assertGreaterEqual(len(self.man["real_he"]), 20)
        # scar 49: transcripts never enter git — real entries are file
        # references + integrity hashes, never text.
        for e in self.man["real_he"]:
            self.assertNotIn("text", e)

    def test_zero_hallucinated_typing(self):
        for case in self.man["hallucinations"]:
            with self.subTest(id=case["id"], text=case["text"]):
                v = textguard.final(case["text"], **GOOD)
                self.assertFalse(v.ok,
                                 f"hallucination TYPED: {case['id']} {case['text']!r}")

    def test_must_pass_cases(self):
        for case in self.man["must_pass"]:
            with self.subTest(id=case["id"], text=case["text"]):
                v = textguard.final(case["text"], **GOOD)
                self.assertTrue(v.ok, f"real speech eaten: {case['id']} "
                                      f"{case['text']!r} ({v.reason}/{v.detail})")

    def test_real_hebrew_cer_within_budget(self):
        corpus_dir = Path(self.man["voice_corpus_dir"])
        if not corpus_dir.is_dir():
            self.skipTest(f"voice corpus not on this machine: {corpus_dir}")
        pairs = []
        dropped = []
        for e in self.man["real_he"]:
            f = corpus_dir / e["file"]
            self.assertTrue(f.is_file(), f"pinned real clip missing: {f}")
            ref = textmetrics.normalize_ws(f.read_text(encoding="utf-8",
                                                       errors="replace"))
            self.assertEqual(textmetrics.sha256_text(ref), e["sha256"],
                             f"pinned transcript changed on disk: {f}")
            v = textguard.final(ref, **GOOD)
            hyp = v.text if v.ok else ""
            if not v.ok:
                dropped.append((e["file"], v.reason, v.detail))
            pairs.append((ref, hyp))
        agg = textmetrics.aggregate_cer(pairs)
        print(f"\n[criterion-10] real-he guard CER: n={agg['n']} "
              f"ref_chars={agg['ref_chars']} edits={agg['edits']} "
              f"cer={agg['cer']:.4f} dropped={dropped}")
        # baseline at the guard stage is identity (0.0); budget is +2% absolute
        self.assertLessEqual(agg["cer"], 0.02,
                             f"guard ate real speech: {agg} dropped={dropped}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

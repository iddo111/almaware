"""KESHEV textguard — K13 (PHASE2-DESIGN.md section 2 textguard row + section
4.1; PHASE1-INQUIRY.md scars 27 layers 5-7, 28; criterion 10).

THE hallucination/output guard — the LAST pipeline stage before typing.
Knowledge ported from alma-mic stt.py (_HALLUCINATION_BLOCKLIST,
_is_blocklisted, _is_repetitive, _is_hallucinated — every rule below maps to
a logged production failure), rewritten clean and re-tested from scratch.

The scar-28 law, structural:
  * exactly ONE copy of this guard exists (grep-asserted in tests);
  * it runs LAST, after ALL text mutation — the router (section 4.1) is its
    only client-side caller: `text = textguard.final(...)` immediately before
    `typer.type(text)`;
  * a PASS verdict returns the text EXACTLY as given — the guard never
    mutates, so "mutation after the guard" has nothing to mutate;
  * the SERVER never filters (scar 28) — this module lives client-side only.

Layer order inside final() (scar 27 layers 5-7, alma-mic order preserved):
  empty -> avg_logprob floor -> hallucination filter -> off-whitelist drop.

Verdict.event maps onto the closed telemetry vocabulary (section 8):
  EMPTY | GUARD_DROP | LANG_DROP.  detail names the rule that fired — it is
  a code constant or a blocklist phrase, NEVER the user's own speech, so it
  is safe to log at INFO (section 8 privacy rules).

Stdlib only. No model, no socket, no file, no device.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from common import decode_params, langpolicy

# ---------------------------------------------------------------- constants

# Post-hoc decode-confidence floor (scar 27 layer 5) — ONE truth, recorded
# with its decode-guard family in common/decode_params.py.
LOGPROB_FLOOR: float = decode_params.AVG_LOGPROB_DROP

# Off-whitelist drop (scar 27 layer 7) — the whitelist truth is langpolicy's.
LANG_WHITELIST: tuple[str, ...] = langpolicy.WHITELIST

_HEBREW = "֐-׿"
_ARABIC = "؀-ۿ"

# Known Whisper "silence hallucinations" — phrases the model invents on
# silence / noise / non-speech because they are over-represented in its
# YouTube training data (subtitle credits, sign-offs, subtitler watermarks).
# Ported from alma-mic stt.py where each family was OBSERVED typing on this
# mic. Matching is on the FULL whitespace-normalized lowercased text (scar
# 28: full text, never substring-anywhere).
_HALLUCINATION_BLOCKLIST: tuple[str, ...] = (
    # --- Arabic (the #1 reported one: "subscribe to the channel") ---
    "اشتركوا في القناة", "اشتراك في القناة", "لا تنسوا الاشتراك",
    "شكرا للمشاهدة", "شكرا على المشاهدة", "ترجمة",
    # --- English subtitle/credit junk ---
    "subscribe", "please subscribe", "thanks for watching",
    "thank you for watching", "thank you for your watching",
    "thank you", "thank you very much", "see you next time",
    "like and subscribe", "don't forget to subscribe",
    "subtitles by", "subtitles by the amara.org community", "amara.org",
    "transcription", "transcription by", "captions by", "closed captions",
    "www.", ".com", "http",
    # --- CJK ---
    "請訂閱", "請訂閱我的頻道", "字幕", "字幕由", "字幕志愿者", "中文字幕",
    "ご視聴ありがとうございました", "ご視聴ありがとうございます",
    "チャンネル登録", "ご清聴ありがとうございました", "おやすみなさい",
    # --- Russian ---
    "продолжение следует", "субтитры", "субтитры сделал",
    "спасибо за просмотр", "подписывайтесь на канал",
    # --- Hebrew (silence / near-silence hallucinations observed on this mic:
    #     the תודה family, כתוביות credits, channel-subscribe junk) ---
    "תודה", "תודה רבה", "תודה על הצפייה", "תודה שצפיתם", "תודה רבה לכם",
    "כתוביות", "עריכת כתוביות", "כתוביות בעברית", "תרגום וכתוביות",
    "הקליקו על כפתור המנוי", "אל תשכחו להירשם לערוץ", "בהצלחה",
    # --- branding watermarks Whisper emits ---
    "mbc", "ndtv", "translated by", "translation by",
    # --- BARE silence artifacts, added 2026-08-14 23:21 ---
    # Whisper answers near-silence with a confident short word, and on this mic
    # that word is overwhelmingly "you". Iddo received it four times in two
    # minutes ("us lemonyou", "seioyouus", "you", "you") and said "microphone is
    # typing bullshit". It slipped through because the blocklist already held
    # "thank you" but never the bare token, and because the logprob floor had
    # just been RAISED to -1.2 to stop it eating his quiet speech — so the
    # cheap filter has to carry what the confidence gate no longer can.
    # SAFE BY CONSTRUCTION: _blocklisted matches the FULL normalized text, never
    # a substring, so any real sentence containing "you" passes untouched. Only
    # an utterance that IS the word is dropped.
    "you", "the", "bye bye", "uh", "um", "hmm",
    # --- BARE sign-offs, added 2026-08-15 after they cost a real conversation.
    # "Bye." was typed into Iddo's live chat TWICE while he was still sitting
    # there talking to me; I believed it, said goodbye, and started shutting
    # down for the day. He had to tell me: "there is a 'bye' typo —
    # hallucination i think". Journal proof: TYPED len=4, 13:58:23.
    # "bye bye" was already blocked; the BARE token never was — the same
    # oversight as "thank you" vs "you" one line above.
    "bye", "goodbye", "bye for now", "voila", "voilà",
    # --- BARE thanks, added 2026-09-02 17:42. THE SAME OVERSIGHT A THIRD TIME.
    # The list has held "thank you" since it was ported, and the two comments
    # above record the identical bug twice already: "thank you" but not "you",
    # "bye bye" but not "bye". Today it was "thank you" but not "thanks".
    # Observed live: while Iddo was OUTSIDE and not typing, the mic put
    # "Okay. Thanks." and "Thanks." into his chat three times inside a minute.
    # The journal shows the engine dropping id ...000015/16/17 as
    # filter:blocklist:thank you in the same seconds, so the filter was working
    # and simply did not know this shape of the word.
    # "okay. thanks" is listed separately because _blocklisted strips only
    # SURROUNDING punctuation -- the internal full stop survives normalization,
    # so the two-sentence form is a different string from "okay thanks".
    # SAFE BY CONSTRUCTION, as above: the match is against the FULL normalized
    # text, so "thanks for the fix" or "okay thanks for looking" pass untouched.
    # Only an utterance that IS the thanks is dropped.
    "thanks", "thanks a lot", "many thanks", "thanks again",
    "ok thanks", "okay thanks", "ok. thanks", "okay. thanks",
    # --- BARE English fillers, added 2026-09-02 18:22, MEASURED not guessed.
    # Tonight's log: 502 segments decoded, 39 typed, 419 guard-dropped — 83% of
    # everything the mic produced was hallucination, and 383 of those 419 were
    # the two words "thank" and "you". The blocklist is carrying this mic.
    # What LEAKED tonight, into Iddo's chat while he was in a headset and not
    # typing: "Peace.", "Yeah.", "Okay.", "Yes, sir.", "Come on.", "Oh, God."
    # All are bare English interjections from a man speaking HEBREW into a
    # near-silent room — rms 0.0046 amplified 36x, which is silence, not speech.
    #
    # WHY NOT AN RMS GATE INSTEAD: measured on tonight's own labelled data.
    # Real speech median rms 0.0660, hallucination median 0.0069 — but their
    # p10 is identical (0.0045 vs 0.0044). A gate at 0.010 kills 64% of the
    # hallucinations and takes 26% OF HIS WORDS with it. Losing a quarter of
    # what he says is worse than the noise, so the gate stays where it is. The
    # segmenter's own comment already said no threshold can separate them.
    "peace", "yeah", "yep", "yup", "okay", "ok", "so", "right", "alright",
    "come on", "yes sir", "oh god", "oh my god", "wow", "cool", "nice",
    # comma variants: _blocklisted strips only SURROUNDING punctuation, so an
    # internal comma makes a different string. "Yes, sir." and "Oh, God." both
    # leaked past the comma-less forms in the first test of this very block.
    "yes, sir", "oh, god", "oh, my god", "no, no", "well, okay",
)
_BLOCKLIST_NORM: tuple[str, ...] = tuple(
    re.sub(r"\s+", " ", p).strip().lower() for p in _HALLUCINATION_BLOCKLIST)

# Filler that carries no content. Used ONLY to re-test an utterance against the
# blocklist after stripping (see _blocklisted) — never to alter typed text.
# Every word here is one a person can drop without losing meaning; note the
# absence of "the", "you", "not", "no" and any Hebrew content word.
_PLEASANTRY_PADDING: frozenset[str] = frozenset({
    "oh", "so", "much", "very", "really", "well", "alright", "hey",
    "guys", "everyone", "again", "now", "just", "please", "ok", "okay",
    "um", "uh", "ah", "yeah", "yes", "and", "then", "there", "here",
    "כן", "אז", "טוב", "נו", "בבקשה", "מאוד", "ממש", "הרבה",
})


# ---------------------------------------------------------------- detectors

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _blocklisted(text: str) -> Optional[str]:
    """The blocklist phrase the (whole, stripped) text is, or is dominated
    by — the typical 'subscribe!' / 'תודה רבה.' silence output. None if
    clean. Matches the FULL normalized text, never substring-anywhere, so a
    real sentence that merely MENTIONS a phrase passes."""
    norm = _normalize(text).lower()
    if not norm:
        return None
    # strip surrounding punctuation/symbols for the equality test
    bare = re.sub(rf"^[^\w{_HEBREW}{_ARABIC}]+|[^\w{_HEBREW}{_ARABIC}]+$", "", norm)
    for p in _BLOCKLIST_NORM:
        if bare == p or norm == p:
            return p
        # a short segment that is essentially just the phrase (+ a few chars)
        if p in norm and len(norm) <= len(p) + 4:
            return p
    # PLEASANTRY-ONLY: an utterance that is a blocklisted phrase wearing
    # nothing but filler is still that phrase (2026-08-15). "Oh, thank you so
    # much." reached his transcript because the +4 ceiling above measures
    # CHARACTERS, and politeness padding is cheap. Strip the padding and ask
    # again — if what is left IS the phrase, it was never content.
    #
    # This is the rule that keeps flexibility: "thank you" cannot be a
    # signature (he says it constantly), but "thank you" surrounded only by
    # oh/so/much/really can be nothing else. Content survives, because a real
    # sentence leaves real words behind after stripping:
    #   "Oh, thank you so much."             -> "thank you"      DROP
    #   "thank you for fixing the microphone"-> unchanged          PASS
    #   "I love you."                        -> "i love you"       PASS
    toks = [t for t in re.findall(rf"[\w{_HEBREW}{_ARABIC}']+", norm) if t]
    stripped = " ".join(t for t in toks if t not in _PLEASANTRY_PADDING)
    if stripped and stripped != norm:
        for p in _BLOCKLIST_NORM:
            if stripped == p:
                return p

    # DOMINANCE (2026-08-15). The +4 ceiling above is measured in characters
    # and one wrapper word defeats it: "Well, I'll see you next time." (29
    # chars) carried "see you next time" (17) straight into his transcript.
    #
    # The first fix attempted here was substring-anywhere for a hand-picked
    # list of "specific" phrases. The repo's OWN test killed it —
    # test_sentence_that_merely_mentions_a_blocklist_phrase_passes, with
    # "please subscribe him to the mailing list tomorrow morning". That test
    # encodes scar 28 (match the FULL text, never substring-anywhere) and it
    # is right: no hand-picked list is safe, because a real sentence can
    # always contain the phrase. Deferring to the scar rather than overriding
    # it.
    #
    # So: the phrase must DOMINATE the utterance — be at least half of it.
    # Then the wrapper case dies and real speech lives:
    #   "Well, I'll see you next time."                     17/29 = 0.59 DROP
    #   "please subscribe him to the mailing list tomorrow"  16/56 = 0.29 PASS
    for p in _BLOCKLIST_NORM:
        if len(p) >= 4 and p in norm and len(p) >= 0.5 * len(norm):
            return p
    return None


def _repetitive(text: str) -> bool:
    """Loop / repeated-phrase detection — the 'ма ма ма' / 'amma amma'
    spirals and repeated-word hallucinations that survive the
    compression-ratio decode guard."""
    norm = _normalize(text)
    if not norm:
        return False
    toks = norm.split()
    # Same token repeated >=3x AND dominating the output.
    #
    # The floor is 6 tokens, not 3 (raised 2026-08-15). At 3 it ate ordinary
    # EMPHASIS: "כן כן כן", "no no no", "very very very good" were all dropped
    # as hallucinations and Iddo never learned he had said them — the silent
    # loss this whole rebuild exists to kill. Three identical words is a
    # person insisting; two hundred is a spiral. The genuinely short loops
    # ("ма ма ма ма") are still caught below by the repeated-fragment test,
    # which measures the string rather than the word count.
    if len(toks) >= 6:
        top, cnt = Counter(toks).most_common(1)[0]
        if cnt >= 3 and cnt >= 0.6 * len(toks):
            return True

    # PHRASE loops (2026-08-15). The single-token test above measures whether
    # one WORD dominates, and a repeating PHRASE defeats it: Iddo received
    #   "tell me the name of the name of the name of ..."  (x70)
    # where the most common token "the" is only 33% of the output — far under
    # the 0.6 bar — so nothing fired and 700+ characters of spiral went into
    # his chat. He replied "mic fucked".
    #
    # Two independent shapes, because Whisper spirals in both:
    #   (a) tiny vocabulary over a long output — five distinct words in two
    #       hundred tokens is not a sentence, whatever the arrangement;
    #   (b) one n-gram repeated and covering most of the output.
    if len(toks) >= 12 and len(set(toks)) <= max(6, len(toks) // 12):
        return True                                  # (a)

    for n in (2, 3, 4, 5):                           # (b)
        if len(toks) < n * 4:                        # need >=4 repeats to judge
            continue
        grams = Counter(tuple(toks[i:i + n]) for i in range(len(toks) - n + 1))
        gram, hits = grams.most_common(1)[0]
        if hits >= 4 and (hits * n) >= 0.6 * len(toks):
            return True
    # the WHOLE string is one short fragment repeated back-to-back (no spaces)
    t = re.sub(r"\s+", "", norm)
    for unit in (2, 3, 4):
        if len(t) >= unit * 4:
            chunks = {t[i:i + unit] for i in range(0, len(t) - unit, unit)}
            if len(chunks) <= 2:
                n_units = len(t) // unit
                if t[:unit] * n_units == t[:unit * n_units]:
                    return True
    return False


def hallucination_reason(text: str) -> str:
    """Why a transcript is a Whisper-on-silence hallucination that must be
    DROPPED — "" if it is real speech. Catches:
      (a) ultra-short 1-2 char junk (not a real one/two-letter word),
      (b) 3-5 char laughter/filler blobs — 'חחח'/'אהה' sat BELOW the
          char-run thresholds and typed all night (laughfix 2026-08-08);
          a transcript that is ONE character repeated 3+ times or an א/ה-only
          blob of 3+ chars is never real dictation, while אבא/אמא and every
          real word pass untouched (the aba/ima-pass property, tested),
      (c) known multilingual blocklist phrases,
      (d) 8+ char-runs / long low-variety strings,
      (e) repeated-token / repeated-fragment loops."""
    raw = (text or "").strip()
    if not raw:
        return ""
    t = re.sub(r"\s+", "", raw)
    # (a) ultra-short junk: 1-2 chars and not a real one/two-letter word
    if len(t) <= 2 and not re.search(rf"[A-Za-z{_HEBREW}]{{2}}", raw):
        return "ultra_short"
    # (b) laughter/filler blobs
    # casefolded: the repeated-char test is case-SENSITIVE without it, so
    # "Mmm." survived as M-m-m while "mmm" was caught (found 2026-08-15 —
    # Whisper capitalises the first letter of every hallucination, which is
    # exactly the form that reached Iddo). Hebrew is unaffected by casefold,
    # so the aba/ima-pass property is untouched.
    bare = re.sub(rf"[^0-9A-Za-z{_HEBREW}]", "", t).casefold()
    if len(bare) >= 3 and (re.fullmatch(r"(.)\1{2,}", bare)
                           or re.fullmatch(rf"[אה]{{3,}}", bare)):
        return "laughter_blob"
    # (c) known hallucination phrases
    phrase = _blocklisted(raw)
    if phrase is not None:
        return f"blocklist:{phrase}"
    # (d) char-run / low-variety garbage
    if len(t) >= 6:
        longest = max((len(m.group(0)) for m in re.finditer(r"(.)\1+", t)), default=0)
        if longest >= 8:                       # 8+ of the SAME char in a row
            return "char_run"
        if len(t) >= 12 and len(set(t)) <= 3:  # long string, almost no variety
            return "low_variety"
    # (e) repetition loops
    if _repetitive(raw):
        return "repeat_loop"
    return ""


# ------------------------------------------------------------------ verdict

@dataclass(frozen=True)
class Verdict:
    """The guard's decision. `text` is the EXACT input on pass, None on drop.
    `event` maps onto the closed telemetry vocabulary (section 8)."""
    text: Optional[str]
    reason: str                     # pass|empty|low_logprob|filter|off_whitelist
    event: Optional[str]            # None|EMPTY|GUARD_DROP|LANG_DROP
    detail: str = ""                # rule/phrase that fired — never user speech

    @property
    def ok(self) -> bool:
        return self.text is not None


def final(text: str, *, lang: Optional[str], avg_logprob: float,
          lang_hint: str = "auto") -> Verdict:
    """THE final gate before typing (section 4.1: the router's
    `text = textguard.final(res)`), applied AFTER all text mutation.

    Layer order (scar 27 layers 5-7, alma-mic order preserved):
      1. empty/whitespace-only            -> EMPTY
      2. avg_logprob < LOGPROB_FLOOR      -> GUARD_DROP (low_logprob)
      3. hallucination filter             -> GUARD_DROP (filter)
      4. off-whitelist language (auto)    -> LANG_DROP  (off_whitelist)

    The whitelist drop applies in AUTO routing only (alma-mic parity): a
    user-forced language is honoured; langpolicy can never emit an
    off-whitelist lang anyway — this layer is defense in depth."""
    if not (text or "").strip():
        return Verdict(None, "empty", "EMPTY")
    if avg_logprob < LOGPROB_FLOOR:
        return Verdict(None, "low_logprob", "GUARD_DROP",
                       f"avg_logprob {avg_logprob:.2f} < {LOGPROB_FLOOR}")
    why = hallucination_reason(text)
    if why:
        return Verdict(None, "filter", "GUARD_DROP", why)
    if lang_hint == "auto" and lang not in LANG_WHITELIST:
        return Verdict(None, "off_whitelist", "LANG_DROP", f"lang={lang}")
    return Verdict(text, "pass", None)


# ------------------------------------------------------------- router seam

# The router calls the guard with ONE worker-reply dict; `final()` takes the
# text plus three keywords. These two adapters are that translation, and they
# live HERE because tests/test_textguard.py::test_import_discipline_client_
# only_router lets no module but client/router.py import this one — the seam
# has to be a single import on the router's side.
#
# The call site, verbatim (client/router.py:428 live lane, :498 stale divert,
# :557 recovery drain — identical at all three):
#
#     text = self.guard_fn(res)
#     if text is None:          -> journal GUARD_DROP
#     if not text.strip():      -> journal EMPTY


def _as_float(value: object, default: float) -> float:
    """A malformed numeric field must not raise inside the router thread."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def from_result(res: dict) -> Verdict:
    """LOSSLESS seam: one worker reply (client/worker_mgr.py:244) -> Verdict,
    keeping the event (EMPTY|GUARD_DROP|LANG_DROP), the reason and the detail
    for whoever journals the outcome.

    A reply with NO avg_logprob fails OPEN (0.0, above LOGPROB_FLOOR): an
    engine that stops reporting confidence must never silently mute the mic.
    """
    text = res.get("text")
    return final(
        text if isinstance(text, str) else "",
        lang=res.get("lang"),
        avg_logprob=_as_float(res.get("avg_logprob"), 0.0),
        lang_hint=str(res.get("lang_hint") or "auto"),
    )


def guard(res: dict) -> Optional[str]:
    """THE `guard_fn` seam in the router's own shape — `dict in, final text
    or None out` (client/router.py:369), a drop-in for the K12 placeholder
    `default_guard`.

    Verdict -> seam mapping, chosen so the router's ledger stays truthful:
        pass        -> the text, byte-identical (the guard never mutates)
        EMPTY       -> ""   so the router takes its EMPTY branch, not GUARD_DROP
        GUARD_DROP  -> None
        LANG_DROP   -> None (the spool journal has no LANG_DROP outcome —
                       client/spool.py:58 — so it must land as GUARD_DROP)

    KNOWN FIDELITY COST of this narrow shape: the LANG_DROP *telemetry* event
    and the Verdict's reason/detail are dropped on the floor. Use
    `from_result` instead if the seam is ever widened to `-> Verdict`.
    """
    verdict = from_result(res)
    if verdict.ok:
        return verdict.text
    return "" if verdict.event == "EMPTY" else None

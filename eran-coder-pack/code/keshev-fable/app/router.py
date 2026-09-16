"""router.py — the pipeline. spool → gates → stt → typer. Synchronous, one lane.

Laws inherited (INSIGHTS §1.11, §4; stt contract):
- SYNCHRONOUS single lane: one record at a time, in admission order. A's
  double-typing became structurally impossible only when the router became
  synchronous — parallel decode lanes are how the same audio types twice.
- one retry then PARK: stt gets two attempts per record (second attempt only
  on timeout/http); then the record STAYS in the spool, DECODE_PARKED, and
  the lane moves on. A dead server never loses speech and never wedges the
  lane forever.
- Every gate refusal journals through the gate's own vocabulary; the router
  adds only DECODE / DECODE_PARKED / LANG_FLIP plumbing.
- LANG_FLIP rescue (2026-08-20, measured on the live journal): eran1's auto
  language pick calls his SHORT Hebrew "en" and returns garbage at lp below
  the floor — "שומע אותי או לא?" ×3 at 00:18 came back as "Show me out your
  own." and was dropped INVISIBLY; forced he decoded it at lp -0.02. 18 of 24
  drops in that window were his Hebrew. So: a decode that is about to be
  dropped for LOGPROB while tagged EN gets exactly ONE more decode with
  lang_hint="he"; if the Hebrew passes the gate it is typed (LANG_FLIP), else
  the ORIGINAL drop stands (rescue="he_failed"). Never on a passing decode
  (visible beats invisible — INSIGHTS §4), never on he/ru (same answer /
  the 08-19 transliteration scar), never on loop/hallucination/empty. This is
  the dual-decode idea of INSIGHTS §4 returned with its demanded test: a
  DECODE always follows a SEG, the rescue can only ADD a line after it.
- Enter policy: auto_enter=True sends Enter as its own re-verified burst via
  typer.enter(); a refused Enter is a refusal, not an error — the text
  already landed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .gates import verdict as gate_verdict
from .stt import DecodeResult
from .typer import FocusInfo


def _r3(x: float | None) -> float | None:
    return None if x is None else round(float(x), 3)


class _JournalLike(Protocol):
    def event(self, name: str, **fields: object) -> dict: ...


class _SpoolLike(Protocol):
    def pending(self) -> list[str]: ...
    def complete(self, rec_id: str) -> None: ...


class _SttLike(Protocol):
    def decode(self, rec_id: str, wav_bytes: bytes,
               lang_hint: str = "auto") -> DecodeResult: ...


class _TyperLike(Protocol):
    def deliver(self, rec_id: str, text: str) -> tuple[bool, str]: ...
    def enter(self, rec_id: str, focus_at_type) -> tuple[bool, str]: ...


@dataclass
class RouterStats:
    decoded: int = 0
    typed: int = 0
    parked: int = 0
    gated: int = 0
    rescued: int = 0          # LANG_FLIP: en-garbage that was his Hebrew


# Languages whose BELOW-FLOOR decode earns one forced-Hebrew rescue. Only EN:
# every rescued record in the 2026-08-20 measurement was en→he; ru is excluded
# on purpose (forcing he on his Russian = Hebrew letters, the 18:57 scar).
RESCUE_FROM: tuple[str, ...] = ("en",)
RESCUE_TO: str = "he"


class Router:
    RETRYABLE = ("timeout", "http")

    def __init__(self, journal: _JournalLike, spool: _SpoolLike,
                 stt: _SttLike, typer: _TyperLike,
                 read_wav, focus_fn=None,
                 auto_enter: bool = True,
                 recovered_path=None,
                 owner_shadow=None,
                 owner_floor: float | None = None,
                 corpus=None) -> None:
        self.recovered_path = recovered_path
        self.owner_shadow = owner_shadow
        # corpus: the always-train loop (app/corpus.py). Fed on TYPED only —
        # the record that passed every gate above — with the exact PCM the
        # decoder heard and the text that landed in the window.
        self.corpus = corpus
        # owner_floor: enforce the clause-4 owner gate. A decode whose speaker
        # cosine to Iddo's reference is BELOW this floor is dropped as not-owner
        # (background TV / music / another person). None = shadow only (measure,
        # never block). Floor 0.60 chosen from 341 live cos values on 2026-08-19:
        # real speech sat p10=0.610 median=0.760; the impostor tail was 0.47-0.60.
        self.owner_floor = owner_floor
        self.journal = journal
        self.spool = spool
        self.stt = stt
        self.typer = typer
        self.read_wav = read_wav          # rec_id -> bytes (spool storage)
        self.focus_fn = focus_fn or (lambda: None)
        self.auto_enter = auto_enter
        self.stats = RouterStats()

    # ------------------------------------------------------------ one rec --
    def process_one(self, rec_id: str) -> str:
        """Returns the terminal state of this record:
        typed | typed_no_enter | gated | parked | type_refused
        """
        wav = self.read_wav(rec_id)
        if wav is None:
            # spool row without audio — journal and drop the row, not silence
            self.journal.event("GUARD_DROP", id=rec_id, reason="no_audio")
            self.spool.complete(rec_id)
            self.stats.gated += 1
            return "gated"

        recovered = getattr(self.spool, "recovered_ids", set())
        if rec_id in recovered:
            return self._process_recovered(rec_id, wav)

        res = self.stt.decode(rec_id, wav)
        if not res.ok and res.reason in self.RETRYABLE:
            res = self.stt.decode(rec_id, wav)          # one retry, exactly
        if not res.ok:
            # PARK: stays pending in the spool; the lane moves on
            self.journal.event("DECODE_PARKED", id=rec_id, reason=res.reason)
            self.stats.parked += 1
            return "parked"

        self.journal.event("DECODE", id=rec_id, ok=1, ms=res.ms)
        self.stats.decoded += 1

        ok, reason = gate_verdict(res.text, res.avg_logprob, res.lang)
        rescue_note: dict[str, object] = {}
        if res.lang in RESCUE_FROM and reason in ("ok", "logprob"):
            # LANG_FLIP — the dual decode of INSIGHTS §4, with the model's own
            # confidence picking. ONE forced-he decode for every EN verdict:
            #   below the floor ("floor"):      he wins if it passes the gate
            #                                   (else it was garbage; drop stands)
            #   above the floor ("confidence"): he wins only if it passes AND
            #                                   is MORE confident than the EN
            # A blinking rescue changes nothing — the first decode succeeded
            # and was judged; no park, no further retry.
            alt = self.stt.decode(rec_id, wav, lang_hint=RESCUE_TO)
            if alt.ok:
                alt_ok, alt_reason = gate_verdict(alt.text, alt.avg_logprob, alt.lang)
                lp0 = res.avg_logprob if res.avg_logprob is not None else float("-inf")
                lp1 = alt.avg_logprob if alt.avg_logprob is not None else float("-inf")
                take = alt_ok and (not ok or lp1 > lp0)
                if take:
                    self.journal.event(
                        "LANG_FLIP", id=rec_id, frm=res.lang, to=alt.lang,
                        why="floor" if not ok else "confidence",
                        lp_frm=_r3(res.avg_logprob), lp_to=_r3(alt.avg_logprob),
                        ms=alt.ms)
                    self.stats.rescued += 1
                    res, ok = alt, True
                elif not ok:
                    rescue_note = {"rescue": "he_failed", "lp_he": _r3(alt.avg_logprob),
                                   "he_reason": alt_reason}
            elif not ok:
                rescue_note = {"rescue": "he_" + (alt.reason or "failed")}
        if not ok:
            self.journal.event("GUARD_DROP", id=rec_id, reason=reason,
                               lp=_r3(res.avg_logprob), lang=res.lang,
                               chars=len(res.text or ""), **rescue_note)
            self.spool.complete(rec_id)                 # judged, refused, done
            self.stats.gated += 1
            return "gated"

        if self.owner_shadow is not None:
            cos = self.owner_shadow.cos(wav)
            if cos is not None:
                self.journal.event("STATE", state="OWNER_SHADOW",
                                   id=rec_id, cos=cos)
                # clause 4, ENFORCE phase (enabled 2026-08-19): a decode that is
                # real speech but NOT Iddo's voice — background TV, music, another
                # person — is dropped here. A shadow-miss (cos is None, gate down)
                # still types, so a dead gate never silences the mic.
                if self.owner_floor is not None and cos < self.owner_floor:
                    self.journal.event("OWNER_BLOCK", id=rec_id,
                                       cos=round(float(cos), 3),
                                       floor=self.owner_floor,
                                       chars=len(res.text or ""))
                    self.spool.complete(rec_id)
                    self.stats.gated += 1
                    return "owner_blocked"

        focus_at_type: FocusInfo | None = self.focus_fn()
        delivered, why = self.typer.deliver(rec_id, res.text)
        if not delivered:
            if why == "presence" and why != "dup":
                # parked speech, not lost: presence refusals keep the record
                self.stats.parked += 1
                return "parked"
            self.spool.complete(rec_id)
            return "type_refused"

        self.spool.complete(rec_id)
        self.stats.typed += 1

        if self.corpus is not None:
            # Fenced on its own: a corpus fault (disk, bug) is an ALARM line,
            # never a lost sentence and never a swallowed Enter — without this
            # fence process_one_safe would catch the raise and skip auto_enter.
            try:
                self.corpus.add(rec_id, wav, res.text)
            except Exception as e:  # noqa: BLE001 — typing outranks training
                try:
                    self.journal.event("ALARM", kind="corpus_exception",
                                       id=rec_id,
                                       err=f"{type(e).__name__}: {e}"[:300])
                except Exception:  # noqa: BLE001
                    pass

        if self.auto_enter:
            entered, _ = self.typer.enter(rec_id, focus_at_type)
            if not entered:
                return "typed_no_enter"
        return "typed"

    def _process_recovered(self, rec_id: str, wav: bytes) -> str:
        """§1.3: stale backlog NEVER reaches live focus. Decode, append the
        text to recovered.txt, complete. No typer, no Enter, ever."""
        res = self.stt.decode(rec_id, wav)
        if not res.ok:
            self.journal.event("DECODE_PARKED", id=rec_id, reason=res.reason,
                               recovered=1)
            self.stats.parked += 1
            return "parked"
        if self.recovered_path is not None and res.text.strip():
            with open(self.recovered_path, "a", encoding="utf-8") as f:
                f.write(res.text.strip() + "\n")
        self.journal.event("SPOOL_RECOVERED", id=rec_id, decoded=1,
                           chars=len(res.text or ""))
        self.spool.complete(rec_id)
        self.stats.decoded += 1
        return "gated"

    # --------------------------------------------------------------- lane --
    def process_one_safe(self, rec_id: str) -> str:
        """process_one that can NEVER kill its caller's thread. A raising
        record (2026-08-19 22:20:48: a journal-vocab error on OWNER_BLOCK
        killed the beat thread → 4 h without HEARTBEAT) is journalled as
        ALARM, completed so it cannot re-raise every beat, and counted as
        'error'. The journal line is the court record of the bug."""
        try:
            return self.process_one(rec_id)
        except Exception as e:  # noqa: BLE001 — the lane must live
            try:
                self.journal.event("ALARM", kind="router_exception", id=rec_id,
                                   err=f"{type(e).__name__}: {e}"[:300])
            except Exception:  # noqa: BLE001 — even a broken journal cannot kill us
                pass
            try:
                self.spool.complete(rec_id)
            except Exception:  # noqa: BLE001
                pass
            return "error"

    def drain(self, max_records: int = 50) -> dict[str, int]:
        """Process pending records in order. Parked records are skipped after
        their attempt this pass (they stay for the next drain)."""
        outcomes: dict[str, int] = {}
        for rec_id in list(self.spool.pending())[:max_records]:
            state = self.process_one_safe(rec_id)
            outcomes[state] = outcomes.get(state, 0) + 1
        return outcomes

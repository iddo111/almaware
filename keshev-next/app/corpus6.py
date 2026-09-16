# -*- coding: utf-8 -*-
"""KESHEV 6 / corpus6.py -- the mic's own training material. THE COLLECTOR.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

WHY THIS FILE EXISTS (the broken window it fixes)
-------------------------------------------------
Iddo, 2026-08-15: "make the mic always train". The capture half was built then,
in mic-rebuild/client/corpus.py, and it worked: every typed utterance was saved
and pushed to eran4 at 03:00, where keshev-lora.timer trained on it at 03:30.

Then the mic was rebuilt as KESHEV 6 (keshev-next/) and the collector was NOT
carried over. Measured 2026-09-12: `grep -rl corpus keshev-next/app` finds only
textguard.py. So since the cutover the pump has been dry --
mic-rebuild/state/corpus-push.log says "corpus is empty -- nothing to push"
every night from 09-04 to 09-12, and eran4's ledger shows the nightly retraining
the SAME 2,305 stale utterances nine nights running and rejecting itself every
time. The loop looked alive from every angle: a timer that fires, a trainer that
trains, a gate that says "rejected". Nothing said "there is no new data".

This restores the capture half, on the live mic.

WHAT MAY ENTER, AND WHY THAT IS SAFE
------------------------------------
Exactly the original rule (mic-rebuild/client/corpus.py, scar 49): an utterance
may enter the corpus ONLY if it was actually TYPED into Iddo's window. To be
typed it has already survived, in order: an authorised USB mic (never Bluetooth),
the energy floor, webrtcvad endpointing, the confidence floor, the hallucination
guard, textguard, and the focus/outbox check. Room audio is never typed, so room
audio can never be trained on.

It is not proof of identity, and that is named rather than hidden: if someone
else dictates at his machine while he is there, it lands here too.

OFF BY DEFAULT, AND ONE SWITCH
------------------------------
Capture is OFF unless KESHEV_CORPUS=1. An absent switch means no. Writing is
best-effort and never raises into the mic path: a collector must not be able to
break the microphone. Failures are recorded in CORPUS_SKIPPED, never swallowed.
"""
from __future__ import annotations

import json, os, sys, threading, time, wave

SAMPLE_RATE, SAMPLE_WIDTH, CHANNELS = 16000, 2, 1
DEFAULT_MAX_BYTES = 8 * 1024 * 1024 * 1024          # 8 GiB, then it stops -- never deletes
CORPUS_SKIPPED: list = []


class CorpusWriter:
    """Append-only (audio, text) writer. enabled=False is a hard no-op."""

    def __init__(self, root, *, enabled=False, max_bytes=DEFAULT_MAX_BYTES):
        self.root = root
        self.enabled = bool(enabled)
        self.max_bytes = int(max_bytes)
        self._lock = threading.Lock()
        self._bytes = None
        self.written = 0
        self.skipped = 0
        self.sid = time.strftime("%Y%m%d-%H%M%S")
        self._n = 0

    @property
    def manifest_path(self):
        return os.path.join(self.root, "manifest.jsonl")

    def total_bytes(self):
        if self._bytes is None:
            total = 0
            for dp, _dn, fn in os.walk(self.root) if os.path.isdir(self.root) else []:
                for f in fn:
                    if f.endswith(".wav"):
                        try: total += os.path.getsize(os.path.join(dp, f))
                        except OSError as exc: CORPUS_SKIPPED.append(f"stat {f}: {exc}")
            self._bytes = total
        return self._bytes

    def add(self, pcm: bytes, text: str, *, engine: str = "?", source: str = "typed") -> bool:
        """Store ONE accepted utterance. Never raises -- returns False instead."""
        if not self.enabled:
            return False
        try:
            text = (text or "").strip()
            if not text or not pcm:
                self.skipped += 1
                return False
            with self._lock:
                if self.total_bytes() + len(pcm) > self.max_bytes:
                    self.skipped += 1
                    CORPUS_SKIPPED.append("corpus full -- nothing deleted to make room, on purpose")
                    return False
                self._n += 1
                rec_id = "%s-%06d" % (self.sid, self._n)
                day = os.path.join(self.root, self.sid)
                os.makedirs(day, exist_ok=True)
                wav_path = os.path.join(day, rec_id + ".wav")
                with wave.open(wav_path, "wb") as w:
                    w.setnchannels(CHANNELS); w.setsampwidth(SAMPLE_WIDTH)
                    w.setframerate(SAMPLE_RATE); w.writeframes(pcm)
                rec = {"id": rec_id, "sid": self.sid,
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "wav": "%s/%s.wav" % (self.sid, rec_id),
                       "text": text,
                       "ms": int(len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH) * 1000),
                       "engine": engine, "source": source}
                with open(self.manifest_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                self._bytes = self.total_bytes() + len(pcm)
                self.written += 1
                return True
        except Exception as exc:                      # never break the mic (G1: never silent)
            self.skipped += 1
            CORPUS_SKIPPED.append("%s: %s" % (type(exc).__name__, exc))
            try:
                print("[corpus] skipped: %s: %s" % (type(exc).__name__, exc),
                      file=sys.stderr, flush=True)
            except Exception:
                pass
            return False


def from_env(state_dir):
    """The one switch. KESHEV_CORPUS=1 turns capture on; absent means no."""
    on = os.environ.get("KESHEV_CORPUS", "").strip() == "1"
    return CorpusWriter(os.path.join(state_dir, "corpus"), enabled=on)

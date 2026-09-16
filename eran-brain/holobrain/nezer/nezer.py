"""NEZER — נֵצֶר — a shoot off the living stem. Everything inside, deletable in one move.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30 23:30:

    *"שים בקופסאות מקום מיוחד להולובריין - בתוך ההולובריין - מין אופשוט בתוך הקיים
    שניתן למחוק ברגע וזה לא מזיז - שיש לו כל המודלים בפנים הכל מהכל - חבר אותו לפידבק
    לופ מלא ותן לו אוטונומיית אימון והתפתחות... בוא נראה מה יוצא ממנו."*

And, in the same breath, the observation that decides what it is FOR:

    *"האוזן שלי התאמנה על אלפי אנשים אלפי שעות אלפי וריאציות וסיטואציות תלויות הקשר."*

He is right, and it names the gap I measured today without being able to phrase it. On
ERAN's frozen cochlea, two humans saying the SAME syllable sit 0.575 apart while two
humans saying DIFFERENT syllables sit 0.881 apart — the within-speaker spread is 1.9x the
entire between-syllable signal. That is not a stupid ruler. **That is a ruler that has met
396 clips.** A human ear meets thousands of mouths in thousands of rooms, and solves it by
exposure and context, not by cleverness. So the shoot's job is exactly that: more mouths,
more hours, more situations — and the freedom to change itself in response.

## THE ONE PROPERTY EVERYTHING ELSE IS SUBORDINATE TO

**`rm -rf` on this one directory removes every trace, and nothing else moves.**

That is not a nice-to-have; it is what makes autonomy safe to grant at all. So:

  * every file it writes or learns lives under ROOT. Enforced in `_inside()`, checked on
    every single write, and the process refuses to start if ROOT is not a real directory
    it owns. The ONE outward read is the pantry: directories a person listed by hand in
    `corpus/sources.json`. It copies food IN from those and touches nothing else — the
    graft's root taking water from soil the gardener pointed at.
  * models are **COPIED IN, never symlinked**. Deleting the shoot can therefore never
    reach back and break the eye, the hand, the zivug, or anything ERAN wears.
  * it never touches a systemd unit, never restarts a service, never ssh's anywhere.
    **eran1 runs `eranb-life.service` — the organism itself — and this thing does not
    know that hostname exists.**
  * `touch ROOT/STOP` halts it at the next checkpoint, mid-round, no matter what.

## Autonomy, and the leash that makes it honest

It chooses its own next round of work, but **Murphy rules on every round before the
result is allowed to stand in the journal** (`murphy/murphy.py`, 8 of 8 on the real
failures of 2026-08-30, fitted cords in `murphy.json`). An autonomous trainer with no
adversary drifts into flattering itself within hours — 2026-08-30 alone produced an
encoder scoring below raw pixels and a hand scoring 86% while drawing dot-clouds.
Nothing here gets to skip that. A round that did no work is an honest no-op trace, and
Murphy fails it — that behaviour is load-bearing and tested.

Everything it does lands in `ROOT/journal.jsonl`, one line per round, readable by a person.

## THE SIX LOOPS (closed 2026-09-01, Iddo 04:39: *"תסגור טוב את כל הפידבק לופס של הנצר
## ותתחיל אותו שיתבשל כמו חמין"*)

  1. **INTAKE** — each round pulls a small batch of recordings from the pantry
     (`corpus/sources.json`) into `corpus/in/`, copy2 never link, never the same file
     twice. Small batches on purpose: chamin cooks on a low flame.
  2. **VET** — new food is mined into utterance candidates (energy segmentation at
     16 kHz mono) and every candidate is measured: duration, level, **burst attack-ms
     and rise15-dB** (the two numbers from the 2026-09-01 bet-barrier inquiry: human
     /b/ sits near 21 dB in 13 ms; ERAN's mouth can do 38.7 dB in 2 ms), and — when the
     ear3 judge's interpreter is configured — **ear3's wdist to the nearest human unit**.
     Both scores are stored per clip. A four-band gate (duration, level, attack, rise)
     is refitted each round from the measured candidates.
  3. **VALVE** — vetted winners are exported to `out/valve/` with a provenance manifest
     line each (source, session, license, sha256, every score). The core may DRAW from
     there; nothing ever flows back in. JSON always; an ALMA-loom weave summary too when
     the loom imports (honesty over ceremony — the JSON is the canonical record).
  4. **EXAM** — every round ends with the foreign exam: held-out HUMAN clips from a
     session it has never fed on, against synthetic negatives (ERAN's own mouth
     productions — the synthetic-corpus scar says those are never food, but they are
     exactly the right thing to be tested AGAINST). The metric is balanced accuracy;
     chance is 0.5; the baseline is the unfitted default gate. The round's number IS the
     exam number — progress is measured, not narrated.
  5. **APPETITE** — the next round's intake batch grows only when the exam improved and
     shrinks when it regressed. Written in `state/appetite.json` with the reason.
  6. **MURPHY** — unchanged and mandatory. Fitted cords load from the shoot's own copy.
     `--looked` lets a person put on record that they actually listened to the latest
     exports; until then every exporting round honestly declares an unlooked artifact.

## What it will NOT do, and I am not being coy about it

Iddo asked to *"חבר ליוטוב"*. **This does not scrape YouTube.** Not a technical limit — I
will not build something to take material against a platform's terms, and an autonomous
process doing it unattended is worse, not better. What it DOES take:

  * **openly licensed speech corpora** (Mozilla Common Voice is CC0 and has Hebrew)
  * **his own recordings** — the café-claude archive and the ant-farm/LoRA corpora
  * anything he hands it himself, listed in `corpus/sources.json`

Every pantry entry must declare `human: true` and a license, or intake refuses it — the
synthetic-corpus scar (clips not from a human mouth transfer at chance) is enforced at
the door, not remembered politely. Synthetic material may enter ONLY as exam negatives,
and only when the entry declares `human: false, synthetic: true` out loud.

## Where this goes next -- MANY shoots, and the one thing that breaks silently

Iddo, 2026-08-31 00:50: *"רעיון שמשלב בין חוות הנמלים להולובריין לנצר - לעשות מקסימום
אופשוטס בתוך ההולובריין, נצרים רבים - ואז לאחד אימון בצורה חכמה."*

That is exactly what deletability buys. A shoot that costs nothing to remove can be run
twenty at a time, each trying a different hypothesis, and nineteen thrown away without a
second thought. It is the voice ant farm's shape applied to whole holobrains.

**THE CONSTRAINT, written here because it fails QUIETLY:** merging trained weights by
averaging ("model soup") is only valid when the models sit in the same loss basin -- which
in practice means they were **forked from one checkpoint and one seed**. Average two
networks trained from DIFFERENT random inits and you do not get a blend, you get a broken
model that still loads, still runs, and still reports a number. That is the exact failure
class this project keeps hitting.

So: shoots FORK from a common parent, never start fresh. And when they cannot -- when the
architecture itself differs -- the merge is **selection, not averaging**: keep the winner,
discard the rest, and say which was which in the journal.

    python nezer.py --plant                          # build the shoot (copies models in)
    python nezer.py --selftest                       # prove the loops on a throwaway root
    python nezer.py --live --rounds 50               # let it run, foreground
    python nezer.py --live --simmer --pause 300      # chamin: nice 19, one round / 5 min
    python nezer.py --looked "listened to batch 7"   # a person actually looked
    rm -rf ~/nezer                                   # and it is gone
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import math
import os
import random
import shutil
import socket
import subprocess
import sys
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.expanduser("~/nezer")

# Boxes the shoot is allowed to live on. THE PC IS NOT ONE OF THEM, and that is a standing
# law of this workspace, not a preference: training on the PC is forbidden. It was broken
# tonight by agents I dispatched -- they ran eye.py and zivug.py locally, took the machine
# to 100% CPU while Iddo was working, and I had to kill them twice. So the shoot refuses,
# by hostname, rather than trusting anyone to remember.
#
# 2026-09-01: the DGXes' REAL hostnames are edgexpert-XXXX, so the original tuple
# ("eran1".."eran4") matched no fleet box at all — the guard would have refused the very
# machines it was written for. The measured suffixes of eran2/3/4 are allowlisted below.
# eran1's is DELIBERATELY absent and stays absent: the organism lives there, and this
# thing does not know that hostname exists. (The old tuple listed eran1 against the
# shoot's own docstring; that door is now closed by construction.)
FLEET = ("eran2", "eran3", "eran4",
         "edgexpert-041d",     # eran2 — the senses
         "edgexpert-01e6",     # eran3 — mostly idle; the shoot's intended soil
         "edgexpert-3636")     # eran4 — Darwish + audio

MODELS = [
    ("eye",     "eran-brain/eye/eye.py",            "eran-brain/eye/state/eye.pt"),
    ("letters", "eran-brain/eye/letters.py",        "eran-brain/eye/corpus/letters.npz"),
    ("hand",    "eran-brain/hand/hand_eye.py",      "eran-brain/hand/state/hand.pt"),
    ("zivug",   "eran-brain/holobrain/zivug.py",    "eran-brain/holobrain/ear-human.npz"),
    # 2026-09-06 code revision: zivug.py now does `import guards` (the fleet-hostname
    # refusal this file already carried, the eye/corpus shape check, and the corpus
    # fingerprint). Without this line the fleet copy of zivug.py dies on ImportError --
    # a guard that breaks the thing it guards is worse than no guard.
    ("guards",  "eran-brain/holobrain/guards.py",   None),
    ("murphy",  "murphy/murphy.py",                 "murphy/real_traps.py"),
    ("murphy-cords", "murphy/murphy.json",          None),   # the FITTED court, not defaults
    ("miko",    "miko/model/loop.py",               None),
    ("loom",    "alma-language/alma/loom.py",       None),
    ("alma-pkg", "alma-language/alma/__init__.py",  None),   # so `from alma.loom import` works
    ("alma-text",   "alma-language/alma/text.py",   None),   # __init__ pulls these two in;
    ("alma-spells", "alma-language/alma/spells.py", None),   # without them murphy cannot sit
]
# Directory-shaped organs (copied whole, symlinks FOLLOWED so none land inside).
MODEL_DIRS = [
    ("ear3",         "ear-v3/ear3"),
    ("ear3-legacy",  "ear-v3/legacy"),
    ("ear3-vendor",  "ear-v3/vendor"),
    ("ear3-targets", "ear-v3/targets-cache"),
]
MODEL_EXTRA_FILES = [("ear3-calib", "ear-v3/ear3-calib.json")]

# ---- the vet gate ---------------------------------------------------------------------
# Four bands. The DEFAULT gate is deliberately loose — it is the exam's BASELINE, the
# floor a fitted gate has to beat. Bands are (lo, hi) inclusive.
GATE_KEYS = ("dur", "rms_db", "attack_ms", "rise15_db")
DEFAULT_GATE = {"dur": (0.25, 3.2), "rms_db": (-38.0, 0.0),
                "attack_ms": (0.0, 250.0), "rise15_db": (0.0, 90.0)}
GATE_MIN_SAMPLES = 24          # refuse to fit a band on fewer measurements than this
EXAM_CAP = 60                  # positives cap; negatives are matched to positives
EAR3_CAP = 12                  # ear3-scored clips per round (2.6 s/clip on CPU — chamin)
BATCH_MIN, BATCH_MAX = 1, 6    # intake files per round


def _inside(root: str, path: str) -> bool:
    """Is this path really under the shoot? Called before every write, with no exceptions.

    realpath first, because a symlink pointing out of the root would otherwise walk right
    past a naive startswith() check and let an autonomous process write into the organism.
    """
    r = os.path.realpath(root)
    p = os.path.realpath(path)
    return p == r or p.startswith(r + os.sep)


# ------------------------------------------------------------------ signal, stdlib+numpy

def _np():
    import numpy as np
    return np


def _load_mono16k(path: str, max_seconds: float = None):
    """Any mono/stereo 16-bit PCM wav -> float32 mono at 16 kHz. Streamed, so a 45-minute
    café recording never sits in RAM at 48 kHz stereo. Integer-ratio rates are block-mean
    decimated (a crude but honest low-pass); odd rates fall back to linear interp and the
    caller's metadata says so."""
    np = _np()
    with wave.open(path, "rb") as w:
        ch, sw, fs, n = (w.getnchannels(), w.getsampwidth(),
                         w.getframerate(), w.getnframes())
        if sw != 2:
            raise ValueError("%s: expected 16-bit PCM, got width %d" % (path, sw))
        remain = n if max_seconds is None else min(n, int(max_seconds * fs))
        out, carry = [], np.zeros(0, dtype=np.float32)
        exact = fs % 16000 == 0
        d = fs // 16000 if exact else None
        while remain > 0:
            take = min(fs * 30, remain)
            x = np.frombuffer(w.readframes(take), dtype="<i2").astype(np.float32) / 32768.0
            remain -= take
            if ch > 1:
                x = x.reshape(-1, ch).mean(axis=1)
            x = np.concatenate([carry, x])
            if fs == 16000:
                out.append(x); carry = np.zeros(0, dtype=np.float32)
            elif exact:
                m = (len(x) // d) * d
                out.append(x[:m].reshape(-1, d).mean(axis=1)); carry = x[m:]
            else:
                out.append(x); carry = np.zeros(0, dtype=np.float32)
        y = np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
        if not exact and fs != 16000 and len(y):
            t_new = np.arange(int(len(y) * 16000 / fs)) * (fs / 16000.0)
            y = np.interp(t_new, np.arange(len(y)), y).astype(np.float32)
        return y


def _env_db(y, hop: int, win: int):
    """Short-time RMS in dB, one value per hop."""
    np = _np()
    if len(y) < win:
        y = np.pad(y, (0, win - len(y)))
    nf = 1 + (len(y) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(nf)[:, None]
    rms = np.sqrt((y[idx] ** 2).mean(axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-7))


def _segments(y, fs: int = 16000):
    """Energy VAD: 20 ms windows / 10 ms hop, threshold 9 dB over the 20th-percentile
    floor (never below -45 dBFS), gaps under 150 ms merged, utterances 0.25-3.2 s,
    padded 60 ms. Long stretches are split at 3.2 s. Returns [(s, e)] in samples."""
    np = _np()
    hop, win = fs // 100, fs // 50
    db = _env_db(y, hop, win)
    if not len(db):
        return []
    th = max(float(np.percentile(db, 20)) + 9.0, -45.0)
    act = db > th
    segs, i = [], 0
    while i < len(act):
        if act[i]:
            j = i
            while j < len(act) - 1 and (act[j + 1] or any(act[j + 1:j + 16])):
                j += 1
            segs.append((i, j)); i = j + 1
        else:
            i += 1
    out, pad = [], 6
    for s, e in segs:
        s, e = max(0, s - pad), min(len(db) - 1, e + pad)
        dur = (e - s) * hop / fs
        if dur < DEFAULT_GATE["dur"][0]:
            continue
        cap = int(DEFAULT_GATE["dur"][1] * fs / hop)
        while e - s > cap:
            out.append((s * hop, (s + cap) * hop)); s += cap
        if (e - s) * hop / fs >= DEFAULT_GATE["dur"][0]:      # no confetti tails
            out.append((s * hop, min(e * hop + win, len(y))))
    return out


def _burst(clip):
    """The two burst numbers from the 2026-09-01 bet-barrier inquiry, per clip onset.

    envelope at 1 ms hop / 4 ms window over the first 250 ms;
      attack_ms  = time from (onset peak - 15 dB) up to the onset peak
      rise15_db  = dB climbed in the 15 ms after that -15 dB crossing
    Human /b/ measured ~21 dB in ~13 ms; ERAN's unfenced mouth managed 38.7 dB in 2 ms.
    Stored on every clip so the gate — and anyone reading the manifest — can see it."""
    np = _np()
    head = clip[:4000]                                   # 250 ms
    env = _env_db(head, 16, 64)
    if len(env) < 3:
        return {"attack_ms": None, "rise15_db": None}
    look = min(len(env), 160)
    p = int(np.argmax(env[:look]))
    peak = float(env[p])
    below = np.where(env[:p + 1] <= peak - 15.0)[0]
    start = int(below[-1]) if len(below) else 0
    j = min(start + 15, len(env) - 1)
    return {"attack_ms": float(p - start),
            "rise15_db": float(env[j] - env[start])}


def _measure(clip, fs: int = 16000):
    np = _np()
    m = {"dur": round(len(clip) / fs, 3),
         "rms_db": round(float(20 * np.log10(max(np.sqrt((clip ** 2).mean()), 1e-7))), 2)}
    b = _burst(clip)
    m["attack_ms"] = None if b["attack_ms"] is None else round(b["attack_ms"], 1)
    m["rise15_db"] = None if b["rise15_db"] is None else round(b["rise15_db"], 2)
    return m


def _accepts(gate: dict, m: dict) -> bool:
    for k in GATE_KEYS:
        v = m.get(k)
        if v is None:
            return False
        lo, hi = gate[k]
        if not (lo <= v <= hi):
            return False
    return True


def _fit_gate(measures: list, old: dict) -> dict:
    """Per-band 5th..95th percentile of everything measured so far. A band with fewer
    than GATE_MIN_SAMPLES honest measurements keeps its previous value — a gate fitted
    on six clips is a guess wearing a number."""
    np = _np()
    gate = {k: tuple(old[k]) for k in GATE_KEYS}
    for k in GATE_KEYS:
        vals = [m[k] for m in measures if m.get(k) is not None]
        if len(vals) >= GATE_MIN_SAMPLES:
            gate[k] = (round(float(np.percentile(vals, 5)), 3),
                       round(float(np.percentile(vals, 95)), 3))
    return gate


def _gate_move(a: dict, b: dict) -> float:
    """How far the gate moved, normalised per band by the DEFAULT band width."""
    tot = 0.0
    for k in GATE_KEYS:
        w = max(DEFAULT_GATE[k][1] - DEFAULT_GATE[k][0], 1e-6)
        tot += (abs(a[k][0] - b[k][0]) + abs(a[k][1] - b[k][1])) / w
    return round(tot / len(GATE_KEYS), 4)


class Nezer:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.journal = os.path.join(self.root, "journal.jsonl")
        self.stop = os.path.join(self.root, "STOP")
        self._refused = set()      # per-process: refuse a bad source ONCE in the journal

    # ------------------------------------------------------------------ safety

    def guard(self) -> None:
        host = socket.gethostname().split(".")[0].lower()
        if not any(host.startswith(f) for f in FLEET):
            raise SystemExit(
                "nezer refuses to run on '%s'. It trains, and training does not happen on "
                "the PC -- that is this workspace's standing law and it was broken tonight "
                "by processes that took Iddo's machine to 100%% CPU. Run it on %s."
                % (host, "/".join(FLEET)))
        if os.path.exists(self.stop):
            raise SystemExit("STOP file present. Remove %s to let it run." % self.stop)

    def write(self, rel: str, data) -> str:
        p = os.path.join(self.root, rel)
        if not _inside(self.root, p):
            raise RuntimeError("REFUSED: %s is outside the shoot. Nothing may be written "
                               "outside ROOT -- that is what makes deleting it safe." % p)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        with io.open(p, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
            f.write(data)
        return p

    def _dest(self, rel: str) -> str:
        """A checked path under ROOT for writes that do not go through write()
        (copy2 destinations, wave writers). Same law, same refusal."""
        p = os.path.join(self.root, rel)
        if not _inside(self.root, p):
            raise RuntimeError("REFUSED: %s is outside the shoot." % p)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def note(self, kind: str, **fields) -> None:
        """One line per event, readable by a person who was not here."""
        rec = {"t": dt.datetime.now().isoformat(timespec="seconds"), "kind": kind}
        rec.update(fields)
        os.makedirs(self.root, exist_ok=True)
        with io.open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ----------------------------------------------------------------- state io

    def _load(self, rel: str, default):
        p = os.path.join(self.root, rel)
        try:
            with io.open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save(self, rel: str, obj) -> None:
        self.write(rel, json.dumps(obj, ensure_ascii=False, indent=1))

    # ------------------------------------------------------------------- plant

    def plant(self, src_root: str) -> int:
        """Copy everything in. COPY, never link -- deleting the shoot must reach nothing.

        guard() runs FIRST: the 2026-08-30 smoke shoot landed on the PC because planting
        was the one door without the hostname check on it. Closed."""
        self.guard()
        os.makedirs(self.root, exist_ok=True)
        manifest = []
        for name, code, state in MODELS:
            for rel in (code, state):
                if not rel:
                    continue
                s = os.path.join(src_root, rel)
                if not os.path.exists(s):
                    manifest.append({"model": name, "file": rel, "status": "MISSING"})
                    continue
                d = self._dest(os.path.join("models", rel))
                shutil.copy2(s, d)                       # copy2, never symlink
                h = hashlib.sha256(io.open(s, "rb").read()).hexdigest()[:16]
                manifest.append({"model": name, "file": rel, "bytes": os.path.getsize(d),
                                 "sha256_16": h, "status": "copied"})
        for name, rel in MODEL_DIRS:
            s = os.path.join(src_root, rel)
            if not os.path.isdir(s):
                manifest.append({"model": name, "dir": rel, "status": "MISSING"})
                continue
            d = os.path.join(self.root, "models", rel)
            if not _inside(self.root, d):
                raise RuntimeError("REFUSED: %s is outside the shoot." % d)
            if os.path.isdir(d):
                shutil.rmtree(d)
            shutil.copytree(s, d, symlinks=False)        # follow links: none land inside
            nfiles = sum(len(fs) for _, _, fs in os.walk(d))
            manifest.append({"model": name, "dir": rel, "files": nfiles, "status": "copied"})
        for name, rel in MODEL_EXTRA_FILES:
            s = os.path.join(src_root, rel)
            if os.path.exists(s):
                shutil.copy2(s, self._dest(os.path.join("models", rel)))
                manifest.append({"model": name, "file": rel, "status": "copied"})
            else:
                manifest.append({"model": name, "file": rel, "status": "MISSING"})
        # the shoot carries its own organism file: self-contained, self-describing
        shutil.copy2(os.path.abspath(__file__), self._dest("nezer.py"))
        for sub in ("corpus/in", "corpus/clips", "corpus/exam", "state", "out/valve/clips"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)
        if not os.path.exists(os.path.join(self.root, "corpus", "sources.json")):
            self._save("corpus/sources.json", {
                "ear3_python": None,
                "note": "pantry: every intake entry needs human:true and a license, or "
                        "the door refuses it. Synthetic material only as role "
                        "exam-negative with human:false, synthetic:true.",
                "sources": []})
        self._save("MANIFEST.json",
                   {"planted": dt.datetime.now().isoformat(timespec="seconds"),
                    "host": socket.gethostname(), "root": self.root, "files": manifest,
                    "delete_me": "rm -rf %s  -- removes every trace; nothing outside moves"
                                 % self.root})
        self.write("DELETE-ME.txt",
                   "This whole shoot is one directory.\n\n    rm -rf %s\n\n"
                   "Everything it learned, every model it holds and every file it wrote is\n"
                   "under here. Nothing outside it was modified, no service was touched and\n"
                   "no symlink leaves this tree. Deleting it costs nothing but the shoot.\n"
                   % self.root)
        ok = sum(1 for m in manifest if m["status"] == "copied")
        miss = [m.get("file") or m.get("dir") for m in manifest if m["status"] == "MISSING"]
        self.note("planted", copied=ok, missing=miss)
        print("planted at %s -- %d items copied in, %d missing" % (self.root, ok, len(miss)))
        for m in miss:
            print("   MISSING  %s" % m)
        print("\n    rm -rf %s      <- removes everything, moves nothing else" % self.root)
        return 0

    # ------------------------------------------------------- loop 1: the pantry

    def sources(self) -> dict:
        cfg = self._load("corpus/sources.json", {"sources": [], "ear3_python": None})
        ok = []

        def refuse(name, why):
            if (name, why) not in self._refused:
                self._refused.add((name, why))
                self.note("refused_source", name=name, why=why)

        for s in cfg.get("sources", []):
            role = s.get("role", "intake")
            if role in ("intake", "exam"):
                if s.get("human") is not True or not s.get("license"):
                    refuse(s.get("name"),
                           "intake/exam food must declare human:true and a license "
                           "-- the synthetic-corpus scar is enforced at the door")
                    continue
            elif role == "exam-negative":
                if s.get("human") is not False or s.get("synthetic") is not True:
                    refuse(s.get("name"),
                           "negatives must say human:false, synthetic:true out loud")
                    continue
            else:
                refuse(s.get("name"), "unknown role %r" % role)
                continue
            if not os.path.isdir(os.path.expanduser(s.get("dir", ""))):
                refuse(s.get("name"), "dir missing: %s" % s.get("dir"))
                continue
            ok.append(s)
        cfg["sources"] = ok
        return cfg

    def _pantry_files(self, src: dict) -> list:
        d = os.path.expanduser(src["dir"])
        excl = tuple(src.get("exclude_dates", []))
        out = []
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(".wav"):
                continue
            if excl and f.startswith(excl):
                continue
            out.append(os.path.join(d, f))
        return out

    def intake(self, cfg: dict, batch: int) -> list:
        """Pull at most `batch` never-seen files from intake sources into corpus/in.
        copy2, never link; a file is 'seen' by name+size so it is never taken twice."""
        seen = self._load("state/intake.json", {})
        taken = []
        for src in cfg["sources"]:
            if src.get("role", "intake") != "intake":
                continue
            for path in self._pantry_files(src):
                if len(taken) >= batch:
                    break
                key = "%s:%s:%d" % (src["name"], os.path.basename(path),
                                    os.path.getsize(path))
                if key in seen:
                    continue
                dest = self._dest(os.path.join("corpus", "in", src["name"],
                                               os.path.basename(path)))
                shutil.copy2(path, dest)
                seen[key] = {"t": dt.datetime.now().isoformat(timespec="seconds"),
                             "bytes": os.path.getsize(path)}
                taken.append({"src": src["name"], "file": dest,
                              "session": os.path.basename(path)[:8],
                              "license": src["license"],
                              "speaker": src.get("speaker", "?")})
        if taken:
            self._save("state/intake.json", seen)
            self.note("intake", files=[os.path.basename(t["file"]) for t in taken],
                      bytes=sum(os.path.getsize(t["file"]) for t in taken))
        return taken

    # --------------------------------------------------------- loop 2: mine+vet

    def mine(self, taken: list) -> list:
        """Segment new food into utterance candidates: 16 kHz mono clips + measures."""
        np = _np()
        meta = self._load("state/clips.json", {"n": 0, "clips": []})
        new = []
        for t in taken:
            try:
                y = _load_mono16k(t["file"])
            except Exception as e:                                   # noqa: BLE001
                self.note("mine_skip", file=os.path.basename(t["file"]), why=str(e)[:120])
                continue
            for s, e in _segments(y):
                clip = y[s:e]
                cid = "c%06d" % meta["n"]
                meta["n"] += 1
                rel = os.path.join("corpus", "clips", cid + ".wav")
                p = self._dest(rel)
                with wave.open(p, "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
                    w.writeframes((np.clip(clip, -1, 1) * 32767).astype("<i2").tobytes())
                m = _measure(clip)
                rec = {"clip": cid, "rel": rel, "source": t["src"],
                       "session": t["session"], "speaker": t["speaker"],
                       "license": t["license"], "t0_s": round(s / 16000, 2), **m}
                meta["clips"].append(rec)
                new.append(rec)
        self._save("state/clips.json", meta)
        if new:
            self.note("mined", candidates=len(new),
                      from_files=len({t["file"] for t in taken}))
        return new

    def ear3_scores(self, cfg: dict, recs: list) -> int:
        """The outside ear: ear3 features + wdist to the nearest human unit, run in the
        judge's own interpreter on the SHOOT'S copy of ear-v3. Both scores per clip land
        on the record. Unreachable is recorded as unreachable, never faked."""
        py = cfg.get("ear3_python")
        eardir = os.path.join(self.root, "models", "ear-v3")
        if not py or not os.path.exists(py) or not os.path.isdir(
                os.path.join(eardir, "ear3")):
            self.note("ear3", status="unreachable",
                      why="no ear3_python configured or no ear-v3 copy in the shoot")
            return 0
        todo = [r for r in recs if "ear3_wdist" not in r][:EAR3_CAP]
        if not todo:
            return 0
        scorer = os.path.join(eardir, "nezer_score.py")
        if not os.path.exists(scorer):
            self.write("models/ear-v3/nezer_score.py", _EAR3_SCORER)
        bf = self.write("state/ear3-batch.json",
                        json.dumps([os.path.join(self.root, r["rel"]) for r in todo]))
        of = os.path.join(self.root, "state", "ear3-out.json")
        try:
            subprocess.run([py, scorer, bf, of], cwd=eardir, check=True,
                           timeout=60 + 15 * len(todo),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            got = json.load(io.open(of, encoding="utf-8"))
        except Exception as e:                                       # noqa: BLE001
            self.note("ear3", status="failed", why=str(e)[:160])
            return 0
        by = {os.path.basename(g["clip"]).split(".")[0]: g for g in got}
        n = 0
        for r in todo:
            g = by.get(r["clip"])
            if g and "wdist" in g:
                r["ear3_unit"], r["ear3_wdist"] = g["unit"], round(g["wdist"], 4)
                n += 1
            elif g:
                r["ear3_error"] = g.get("error", "?")
        self.note("ear3", status="scored", clips=n)
        return n

    def vet(self, new_recs: list) -> tuple:
        """Refit the four-band gate on every measurement so far, then rule on the new
        candidates. Returns (accepted, gate, gate_move)."""
        meta = self._load("state/clips.json", {"clips": []})
        old = self._load("state/gate.json", None) or {k: list(DEFAULT_GATE[k])
                                                      for k in GATE_KEYS}
        old = {k: tuple(old[k]) for k in GATE_KEYS}
        gate = _fit_gate(meta["clips"], old)
        move = _gate_move(gate, old)
        self._save("state/gate.json", {k: list(gate[k]) for k in GATE_KEYS})
        accepted = [r for r in new_recs if _accepts(gate, r)]
        if new_recs:
            self.note("vetted", candidates=len(new_recs), accepted=len(accepted),
                      gate={k: list(gate[k]) for k in GATE_KEYS}, gate_move=move)
        return accepted, gate, move

    # ----------------------------------------------------------- loop 3: valve

    def valve(self, accepted: list, round_n: int) -> int:
        """One-way export. Winners are copy2'd to out/valve/clips and each gets a
        provenance manifest line: where it came from, whose voice, what license, what
        every judge said. The core DRAWS from here; nothing flows back."""
        if not accepted:
            return 0
        for r in accepted:
            src = os.path.join(self.root, r["rel"])
            shutil.copy2(src, self._dest(os.path.join("out", "valve", "clips",
                                                      r["clip"] + ".wav")))
            line = {"t": dt.datetime.now().isoformat(timespec="seconds"),
                    "round": round_n, "clip": r["clip"] + ".wav",
                    "sha256_16": hashlib.sha256(
                        io.open(src, "rb").read()).hexdigest()[:16],
                    "source": r["source"], "session": r["session"],
                    "speaker": r["speaker"], "license": r["license"],
                    "dur": r["dur"], "rms_db": r["rms_db"],
                    "burst_attack_ms": r["attack_ms"], "burst_rise15_db": r["rise15_db"],
                    "ear3_unit": r.get("ear3_unit"), "ear3_wdist": r.get("ear3_wdist")}
            with io.open(self._dest("out/valve/manifest.jsonl"), "a",
                         encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        self._weave_manifest(accepted, round_n)
        self.note("valve", round=round_n, exported=len(accepted))
        return len(accepted)

    def _weave_manifest(self, accepted: list, round_n: int) -> None:
        """The junction is supposed to speak ALMA. If the loom imports from the shoot's
        own copy, the batch is ALSO written as a run weave — one knot per clip, seeded
        with its ear3 distance (or 0), pooled into the valve. If not, the JSON manifest
        stands alone and the TODO is on the record instead of silently dropped."""
        try:
            sys.path.insert(0, os.path.join(self.root, "models", "alma-language"))
            from alma.loom import Loom, Weave                        # noqa: E402
            v = Weave("valve-%d" % round_n)
            v.knot("valve", "pass")
            for r in accepted:
                v.knot(r["clip"], "pass")
                v.thread(r["clip"], "valve")
                v.seed(r["clip"], float(r.get("ear3_wdist") or 0.0), beat=1)
            Loom().run(v)
            self.write("out/valve/weave-%04d.json" % round_n, json.dumps(
                {"weave": "valve-%d" % round_n, "alma": True,
                 "knots": [r["clip"] for r in accepted]}, ensure_ascii=False, indent=1))
        except Exception as e:                                       # noqa: BLE001
            self.note("valve_weave", status="TODO",
                      why="alma loom not importable here (%s) -- JSON manifest is the "
                          "record until the weave is wired" % str(e)[:80])

    # ------------------------------------------------------------ loop 4: exam

    def _build_exam(self, cfg: dict) -> dict:
        """Built ONCE: held-out human clips (a session never fed) as positives, ERAN's
        own productions as negatives, mined with the FIXED default segmentation and
        measured with the same rulers. Cached; the gate never fits on any of it."""
        ex = self._load("state/exam.json", None)
        if ex is not None:
            return ex
        np = _np()
        pos, neg = [], []
        for src in cfg["sources"]:
            role = src.get("role")
            bucket, label = (pos, "human") if role == "exam" else (neg, "synthetic")
            if role not in ("exam", "exam-negative"):
                continue
            for path in self._pantry_files(src):
                if len(bucket) >= EXAM_CAP:
                    break
                try:
                    y = _load_mono16k(path, max_seconds=240)
                except Exception as e:                               # noqa: BLE001
                    self.note("exam_skip", file=os.path.basename(path), why=str(e)[:100])
                    continue
                for s, e in _segments(y):
                    if len(bucket) >= EXAM_CAP:
                        break
                    m = _measure(y[s:e])
                    m["label"] = label
                    m["file"] = os.path.basename(path)
                    bucket.append(m)
        n = min(len(pos), len(neg))
        ex = {"built": dt.datetime.now().isoformat(timespec="seconds"),
              "positives": pos[:n] if n else pos, "negatives": neg[:n] if n else neg}
        ex["baseline"] = self._exam_score(ex, DEFAULT_GATE)
        self._save("state/exam.json", ex)
        self.note("exam_built", positives=len(ex["positives"]),
                  negatives=len(ex["negatives"]), baseline=ex["baseline"])
        return ex

    @staticmethod
    def _exam_score(ex: dict, gate: dict):
        """Balanced accuracy: accept the human, refuse the synthetic. Chance = 0.5 by
        construction — accepting everything or nothing both score exactly that."""
        pos, neg = ex.get("positives", []), ex.get("negatives", [])
        if not pos or not neg:
            return None
        tp = sum(1 for m in pos if _accepts(gate, m)) / len(pos)
        tn = sum(1 for m in neg if not _accepts(gate, m)) / len(neg)
        return round((tp + tn) / 2, 4)

    # -------------------------------------------------------- loop 5: appetite

    def appetite(self, exam_now, exam_prev) -> tuple:
        """The batch size is earned. Improvement doubles it (to a chamin-sized cap),
        regression halves it, nothing keeps it. Reasons on the record."""
        st = self._load("state/appetite.json", {"batch": BATCH_MIN, "last_exam": None})
        batch, why = st["batch"], "held"
        if exam_now is not None and exam_prev is not None:
            if exam_now > exam_prev + 1e-6:
                batch, why = min(batch * 2, BATCH_MAX), "exam improved %.4f -> %.4f" % (
                    exam_prev, exam_now)
            elif exam_now < exam_prev - 1e-6:
                batch, why = max(batch // 2, BATCH_MIN), "exam regressed %.4f -> %.4f" % (
                    exam_prev, exam_now)
        self._save("state/appetite.json", {"batch": batch, "last_exam": exam_now})
        return batch, why

    # ----------------------------------------------------------- a person looked

    def looked(self, note: str) -> int:
        """A person actually listened to the latest exports. Cheapest judge there is,
        and the one Murphy's `unlooked` witness is waiting for."""
        hist = [json.loads(l) for l in io.open(self.journal, encoding="utf-8")] \
            if os.path.exists(self.journal) else []
        last_export = max((h.get("round", -1) for h in hist if h["kind"] == "valve"),
                          default=-1)
        self._save("state/looked.json",
                   {"t": dt.datetime.now().isoformat(timespec="seconds"),
                    "note": note, "covers_round": last_export})
        self.note("looked", note=note, covers_round=last_export)
        print("on the record: a person looked (covers exports up to round %d)" % last_export)
        return 0

    # -------------------------------------------------------------------- live

    def live(self, rounds: int, seconds: float, pause: float = 0.0,
             simmer: bool = False) -> int:
        """Choose, feed, vet, export, sit the exam, be judged, record. Repeat.

        The judging is the point. An autonomous trainer with nobody to answer to writes
        itself a good report -- and this project has the receipts: an encoder that scored
        5.8% where raw pixels score 66.9%, and a hand at 86% drawing dot-clouds. Murphy
        rules on every round with his FITTED cords, and a round he calls FOOLING ITSELF
        is recorded as such. A round that did nothing claims nothing — its empty
        paperwork is read into the record, and the selftest proves the same emptiness
        CLAIMING success is failed."""
        self.guard()
        if simmer:
            try:
                os.nice(19)                       # chamin: the lowest flame the OS has
            except (AttributeError, OSError):
                pass
        sys.path.insert(0, os.path.join(self.root, "models", "murphy"))
        try:
            import murphy                                            # noqa: E402
        except Exception as e:                                       # noqa: BLE001
            print("no Murphy in the shoot (%s) -- refusing to run unjudged." % e)
            return 2
        mw, ml = murphy.load()                    # fitted cords from the shoot's own copy
        if mw is None:
            self.note("murphy_cords", status="DEFAULTS",
                      why="models/murphy/murphy.json missing or for another bench")

        rng = random.Random(1933)
        t0 = time.time()
        done = 0
        while done < rounds and time.time() - t0 < seconds:
            if os.path.exists(self.stop):
                self.note("stopped", reason="STOP file", rounds=done)
                print("STOP file seen. Halting cleanly after %d rounds." % done)
                return 0
            plan = self.choose(rng, done)
            self.note("chose", **plan)
            trace = self.run_round(plan, done)
            verdict, spoke, _ = murphy.rule(trace, weights=mw, lines=ml)
            fooling = verdict >= 1.0
            self.note("round", n=done, plan=plan["what"],
                      metric=trace["steps"][-1]["metric"] if trace["steps"] else None,
                      baseline=trace.get("baseline"), held_out=trace.get("held_out"),
                      exported=trace.get("exported", 0),
                      murphy="FOOLING ITSELF" if fooling else "sound",
                      witnesses=list(dict.fromkeys(spoke)))
            print("round %3d  %-34s  exam %s  murphy: %s  %s"
                  % (done, plan["what"][:34],
                     trace["steps"][-1]["metric"] if trace["steps"] else "--",
                     "FOOLING" if fooling else "sound",
                     ",".join(dict.fromkeys(spoke))))
            done += 1
            slept = 0.0
            while pause and slept < pause:        # STOP works mid-simmer too
                if os.path.exists(self.stop):
                    self.note("stopped", reason="STOP file", rounds=done)
                    print("STOP file seen mid-pause. Halting cleanly.")
                    return 0
                time.sleep(min(5.0, pause - slept))
                slept += 5.0
        self.note("finished", rounds=done, seconds=round(time.time() - t0, 1))
        return 0

    def choose(self, rng, n: int) -> dict:
        """What to do next — read from the shoot's own state, not from a schedule.
        Deliberately simple and READABLE, not clever: a plan a person can predict is
        worth more than a bandit nobody can audit, especially in the thing that is
        allowed to run unattended."""
        st = self._load("state/appetite.json", {"batch": BATCH_MIN, "last_exam": None})
        cfg = self.sources()
        seen = self._load("state/intake.json", {})
        unfed = 0
        for src in cfg["sources"]:
            if src.get("role", "intake") != "intake":
                continue
            for path in self._pantry_files(src):
                key = "%s:%s:%d" % (src["name"], os.path.basename(path),
                                    os.path.getsize(path))
                unfed += key not in seen
        if unfed == 0:
            return {"what": "digest: refit gate + exam, pantry empty",
                    "why": "no unfed food; last exam %s" % st["last_exam"],
                    "batch": 0}
        return {"what": "feed %d file(s), mine, vet, valve, exam"
                        % min(st["batch"], unfed),
                "why": "%d unfed file(s) in the pantry; last exam %s"
                       % (unfed, st["last_exam"]),
                "batch": min(st["batch"], unfed)}

    def halt_if_stopped(self, where: str) -> None:
        """The door's promise, kept: STOP halts MID-ROUND at a stage boundary,
        not only between rounds. In-flight work is dropped, on purpose — the
        whole shoot is deletable, so a half-round is too."""
        if os.path.exists(self.stop):
            self.note("stopped", reason="STOP file", where="mid-round:" + where)
            print("STOP file seen mid-round (%s). Halting cleanly." % where)
            raise SystemExit(0)

    def run_round(self, plan: dict, round_n: int = 0) -> dict:
        """One real round of the six loops, as a trace Murphy can rule on.

        Until 2026-09-01 this was an honest NO-OP; the seam is now wired: intake ->
        mine -> vet -> valve -> exam -> appetite. A round with nothing to do still
        returns the no-op trace — no movement, no floor, claimed_success False — and
        Murphy correctly fails it. That behaviour is tested, on purpose."""
        cfg = self.sources()
        taken = self.intake(cfg, plan.get("batch", 0)) if plan.get("batch") else []
        new = self.mine(taken)
        accepted, gate, move = self.vet(new)     # digest rounds refit on old measures too
        self.halt_if_stopped("before-ear3")      # ear3 is the long stage; STOP beats it
        heard = self.ear3_scores(cfg, accepted) if accepted else 0
        self.halt_if_stopped("before-valve")
        exported = self.valve(accepted, round_n)
        ex = self._build_exam(cfg)
        exam_prev = self._load("state/appetite.json", {}).get("last_exam")
        exam_now = self._exam_score(ex, gate)
        batch, why = self.appetite(exam_now, exam_prev)
        self.note("appetite", batch=batch, why=why)

        did_nothing = not taken and not new and move == 0.0
        if did_nothing and exam_now is None:
            # the sibling's honest no-op, kept verbatim in spirit: no work, no claim,
            # and the paperwork witnesses have every right to speak.
            return {"chance": 0.045, "baseline": None, "held_out": False,
                    "claimed_success": False,
                    "steps": [{"step": 0, "metric": 0.045, "terms": {"main": 1.0}}]}

        hist = self._load("state/exam_history.json", [])
        hist.append({"round": round_n, "metric": exam_now, "gate_move": move})
        self._save("state/exam_history.json", hist[-500:])
        # No `terms` on these steps, on purpose: gate_move is not a loss, and dressing
        # it as one made the collapse witness misread it (measured round 0, 2026-09-01).
        # It lives in the journal's `vetted` line instead; Murphy's watch() shows the
        # under-declaration honestly.
        steps = [{"step": h["round"], "metric": h["metric"], "terms": {}}
                 for h in hist[-200:] if h["metric"] is not None]
        looked = self._load("state/looked.json", None)
        last_export = max((h.get("round", -1) for h in
                           [json.loads(l) for l in io.open(self.journal,
                                                           encoding="utf-8")]
                           if h["kind"] == "valve"), default=-1) \
            if os.path.exists(self.journal) else -1
        return {
            "chance": 0.5,                       # accept-all and reject-all both score it
            "baseline": ex.get("baseline"),      # the unfitted DEFAULT gate, measured once
            "held_out": True if ex.get("positives") else
                        "no exam source configured -- nothing to hold out yet",
            "judge_in_loop": False,              # exam truth is provenance, not the gate
            "independent": heard > 0,            # ear3 actually heard clips this round
            "artifact": "out/valve/manifest.jsonl" if exported else None,
            "looked_at": bool(looked and looked.get("covers_round", -1) >= last_export),
            "claimed_success": bool(exported and exam_now is not None and
                                    ex.get("baseline") is not None and
                                    exam_now >= ex["baseline"]),
            "exported": exported,
            "steps": steps or [{"step": 0, "metric": exam_now if exam_now is not None
                                else 0.045, "terms": {}}],
        }

    # ---------------------------------------------------------------- selftest

    def selftest(self) -> int:
        """Prove every loop on a throwaway root. Fleet-only, like everything else."""
        self.guard()
        import tempfile
        base = tempfile.mkdtemp(prefix="nezer-selftest-")
        fails = []

        def check(name, cond, detail=""):
            print("  %-38s %s %s" % (name, "ok" if cond else "FAIL", detail))
            if not cond:
                fails.append(name)

        np = _np()
        try:
            # -- guard refuses foreign hostnames
            real = socket.gethostname
            socket.gethostname = lambda: "IDDO1-pc"
            try:
                Nezer(base).guard()
                check("guard refuses the PC", False)
            except SystemExit:
                check("guard refuses the PC", True)
            finally:
                socket.gethostname = real

            # -- writes cannot leave the root
            t = Nezer(os.path.join(base, "shoot"))
            os.makedirs(t.root, exist_ok=True)
            try:
                t.write("../escape.txt", "x")
                check("write refused outside ROOT", False)
            except RuntimeError:
                check("write refused outside ROOT", True)

            # -- mine: synthetic 48k stereo with 3 spoken bursts -> 3 clips, 16k mono
            fs = 48000
            sig = np.zeros(fs * 6, dtype=np.float32)
            rs = np.random.RandomState(7)
            for k in range(3):
                s = fs + k * fs * 3 // 2
                n = int(fs * 0.5)
                burst = rs.randn(n).astype(np.float32) * 0.2
                burst[:240] *= np.linspace(0, 1, 240).astype(np.float32)    # 5 ms attack
                burst[-2400:] *= np.linspace(1, 0, 2400).astype(np.float32)  # 50 ms tail
                sig[s:s + n] += burst
            pantry = os.path.join(base, "pantry")
            os.makedirs(pantry, exist_ok=True)
            wavp = os.path.join(pantry, "20260101120000.WAV")
            with wave.open(wavp, "wb") as w:
                w.setnchannels(2); w.setsampwidth(2); w.setframerate(fs)
                st = np.repeat((np.clip(sig, -1, 1) * 32767).astype("<i2"), 2)
                w.writeframes(st.tobytes())
            t._save("corpus/sources.json", {"ear3_python": None, "sources": [
                {"name": "synth", "dir": pantry, "role": "intake", "human": True,
                 "license": "selftest tone", "speaker": "test"}]})
            cfg = t.sources()
            check("pantry accepts a lawful source", len(cfg["sources"]) == 1)
            taken = t.intake(cfg, 2)
            check("intake copies once", len(taken) == 1)
            check("intake never re-takes", len(t.intake(cfg, 2)) == 0)
            new = t.mine(taken)
            check("mine finds the utterances", len(new) == 3, "got %d" % len(new))
            if new:
                with wave.open(os.path.join(t.root, new[0]["rel"]), "rb") as w:
                    check("clips are 16k mono", w.getframerate() == 16000
                          and w.getnchannels() == 1)
                check("burst numbers measured", new[0]["attack_ms"] is not None
                      and new[0]["rise15_db"] is not None,
                      "attack %s rise %s" % (new[0]["attack_ms"], new[0]["rise15_db"]))

            # -- burst ruler orders a click before a swell
            click = np.zeros(8000, dtype=np.float32)
            click[800:] = (rs.randn(7200) * 0.3).astype(np.float32)
            swell = (np.linspace(0, 1, 8000) ** 3 * rs.randn(8000) * 0.3).astype(np.float32)
            check("attack: click < swell",
                  _burst(click)["attack_ms"] < _burst(swell)["attack_ms"],
                  "%s vs %s" % (_burst(click)["attack_ms"], _burst(swell)["attack_ms"]))

            # -- vet: gate fits and refuses the unmeasurable
            acc, gate, move = t.vet(new)
            check("gate exists after vet", gate is not None)
            check("silence is refused",
                  not _accepts(gate, {"dur": 1.0, "rms_db": -70.0,
                                      "attack_ms": 5, "rise15_db": 10}))
            check("vet accepted the clean bursts", len(acc) == len(new),
                  "%d of %d" % (len(acc), len(new)))

            # -- provenance door: a synthetic 'intake' source is refused
            t2 = Nezer(os.path.join(base, "shoot2"))
            os.makedirs(t2.root, exist_ok=True)
            t2._save("corpus/sources.json", {"sources": [
                {"name": "bad", "dir": pantry, "role": "intake", "human": False,
                 "synthetic": True, "license": "nope"}]})
            check("synthetic intake refused", len(t2.sources()["sources"]) == 0)

            # -- exam: positives vs negatives, balanced, default baseline
            ex = {"positives": [{"dur": 0.8, "rms_db": -20, "attack_ms": 14,
                                 "rise15_db": 20}] * 4,
                  "negatives": [{"dur": 0.4, "rms_db": -12, "attack_ms": 2,
                                 "rise15_db": 39}] * 4}
            tight = {"dur": (0.5, 1.5), "rms_db": (-30, -15),
                     "attack_ms": (8, 30), "rise15_db": (10, 30)}
            check("exam: tight gate beats default",
                  Nezer._exam_score(ex, tight) == 1.0 and
                  Nezer._exam_score(ex, DEFAULT_GATE) == 0.5,
                  "tight %s default %s" % (Nezer._exam_score(ex, tight),
                                           Nezer._exam_score(ex, DEFAULT_GATE)))

            # -- appetite: earned, halved, floored
            t3 = Nezer(os.path.join(base, "shoot3"))
            os.makedirs(t3.root, exist_ok=True)
            b, _ = t3.appetite(0.7, 0.6)
            check("appetite grows on improvement", b == 2, "batch %d" % b)
            b, _ = t3.appetite(0.5, 0.7)
            check("appetite shrinks on regression", b == 1, "batch %d" % b)
            b, _ = t3.appetite(0.4, 0.5)
            check("appetite floors at 1", b == 1)

            # -- Murphy fails the no-op (needs the real court in a planted shoot)
            mdir = os.path.join(self.root, "models", "murphy")
            if os.path.isdir(mdir):
                sys.path.insert(0, mdir)
                try:
                    import murphy                                    # noqa: E402
                    mw, ml = murphy.load()
                    noop = {"chance": 0.045, "baseline": None, "held_out": False,
                            "claimed_success": False,
                            "steps": [{"step": 0, "metric": 0.045,
                                       "terms": {"main": 1.0}}]}
                    v, spoke, _ = murphy.rule(noop, weights=mw, lines=ml)
                    # Measured 2026-09-01 on the fitted cords: an honest no-op that
                    # CLAIMS NOTHING is ruled 0.00 -- "a run that claims nothing cannot
                    # be fooling anybody" -- but its empty paperwork is read into the
                    # record. The leash is the second half: the same emptiness CLAIMING
                    # success must be caught. Both halves are asserted.
                    check("no-op: paperwork witnesses speak",
                          {"at_chance", "no_holdout", "no_floor"} <= set(spoke),
                          "verdict %.2f (%s)" % (v, ",".join(spoke)))
                    lying = dict(noop, claimed_success=True)
                    v2, spoke2, _ = murphy.rule(lying, weights=mw, lines=ml)
                    check("no-op that claims success is FAILED", v2 >= 1.0,
                          "verdict %.2f (%s)" % (v2, ",".join(spoke2)))
                    check("murphy cords are the fitted ones", mw is not None)
                except Exception as e:                               # noqa: BLE001
                    check("murphy importable from shoot", False, str(e)[:80])
            else:
                print("  (no planted shoot at %s -- murphy check skipped)" % self.root)

            # -- valve: manifest carries provenance, copies are real files
            if acc:
                t.valve(acc, 0)
                man = [json.loads(l) for l in
                       io.open(os.path.join(t.root, "out/valve/manifest.jsonl"),
                               encoding="utf-8")]
                check("valve manifest has license+scores",
                      all("license" in m and "burst_attack_ms" in m for m in man))
                cp = os.path.join(t.root, "out", "valve", "clips", man[0]["clip"])
                check("valve clips are copies not links",
                      os.path.isfile(cp) and not os.path.islink(cp))
        finally:
            shutil.rmtree(base, ignore_errors=True)
        print("\nselftest: %d checks failed" % len(fails))
        return 1 if fails else 0


_EAR3_SCORER = '''\
"""ear3 scorer for the nezer valve -- runs under the ear's own interpreter, reads the
SHOOT'S copy of ear-v3, writes one JSON. Written by nezer.py; do not edit in place."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from ear3 import features as F
from ear3 import judge as J
batch = json.load(open(sys.argv[1], encoding="utf-8"))
stats = J.load_cache()
out = []
for p in batch:
    try:
        v = np.asarray(F.features_from_wav(p))
        near = J.nearest_table(v, stats)
        best = near[0] if isinstance(near, list) else near
        out.append({"clip": p, "unit": best["unit"], "wdist": float(best["wdist"])})
    except Exception as e:
        out.append({"clip": p, "error": str(e)[:160]})
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"))
'''


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NEZER -- the deletable shoot.")
    ap.add_argument("--root", default=os.environ.get("NEZER_ROOT", DEFAULT_ROOT))
    ap.add_argument("--src", default=os.path.abspath(os.path.join(HERE, "..", "..", "..")),
                    help="the workspace to copy models FROM")
    ap.add_argument("--plant", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--looked", metavar="NOTE",
                    help="record that a person listened to the latest exports")
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--seconds", type=float, default=3600)
    ap.add_argument("--pause", type=float, default=0.0,
                    help="seconds between rounds (STOP is honoured mid-pause)")
    ap.add_argument("--simmer", action="store_true",
                    help="chamin mode: nice 19 + slow rounds; pair with --pause")
    a = ap.parse_args(argv)

    n = Nezer(a.root)
    if a.plant:
        return n.plant(a.src)
    if a.selftest:
        return n.selftest()
    if a.looked:
        return n.looked(a.looked)
    if a.live:
        return n.live(a.rounds, a.seconds, pause=a.pause, simmer=a.simmer)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

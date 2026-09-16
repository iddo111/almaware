#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""dictionary.py -- ERAN's DICTIONARY RIG. A long reading session, hands free.

================================================================================
  איך משתמשים / HOW TO USE  --  קצר, כמו לילד בן עשר / short, for a ten-year-old
================================================================================

  עברית
  -----
  1. תחבר מיקרופון USB (BRIO או סקרלט). אוזניות בלוטות' אסורות. התוכנה
     תסרב לרוץ עליהן.
  2. אם "קשב" (המיקרופון של היום-יום) פתוח -- תסגור אותו. שניים לא יכולים
     להחזיק מיקרופון אחד.
  3. לחיצה כפולה על הקיצור "ERAN Dictionary" בשולחן העבודה.
  4. תשתוק שתי שניות. הוא מודד את שקט החדר.
  5. על המסך תופיע מילה גדולה. תגיד אותה. תעצור. הוא שומע לבד, שומר לבד,
     ועובר למילה הבאה לבד. אתה לא לוחץ כלום.
  6. אם משהו יצא רע הוא יגיד "שוב בבקשה" ויישאר על אותה מילה.
  7. מקשים (לא חובה):  s = לדלג   r = להקליט מחדש את האחרונה
                        p = הפסקה  q = לסיים ולשמור
  8. כל הקלטה נשמרת מיד. גם אם המחשב ייפול -- מה שהקראת נשאר.

  ENGLISH
  -------
  1. Plug in a USB microphone (BRIO or Scarlett). Bluetooth headsets are
     FORBIDDEN. This program refuses to run on one.
  2. If KESHEV (the everyday mic) is running, close it. Two programs cannot
     hold one microphone.
  3. Double-click the "ERAN Dictionary" shortcut on the Desktop.
  4. Stay quiet for two seconds. It measures the room's own silence.
  5. A big word appears. Say it. Stop. It hears you by itself, saves by
     itself, and moves to the next word by itself. You press nothing.
  6. If a take was bad it says "again please" and stays on the same word.
  7. Keys (optional):  s = skip   r = redo the last one
                       p = pause  q = finish and save
  8. Every clip is written to disk the moment it closes. If the machine
     dies, everything you already read is still there.

================================================================================
  WHAT THIS IS, AND WHAT IT REUSES
================================================================================

booth.py (the browser booth, port 8808) is a one-syllable-per-click machine:
every take is a fixed 1400 ms auto-stop and one button press. It cannot record
a sentence, let alone a dictionary. That is why this file exists.

NOTHING about microphone handling is re-invented here. This rig imports the
KESHEV mic stack from D:\CLAUDE\mic-rebuild, which runs every day:

  client/devices.py    THE device law (scars 21-23). `_NEVER_MIC` is the sole
                       authority; `forbidden_match()` sees only the device NAME
                       and no config can reach it. Bluetooth / hands-free /
                       headset / A2DP / HFP / AirPods and every loopback or
                       virtual device are refused BEFORE any probe or open.
                       MME is never opened. Same-physical-mic fallback chain
                       across WASAPI > DirectSound > WDM-KS, with the
                       transient-open retry. No allowed mic -> IDLE, never a
                       fallback.  (SACRED AUDIO LAW, in code, with its scars.)
  client/capture.py    format negotiation 16k -> native -> 48k -> 44.1k
                       (scar 24: the BRIO rejects a forced 16 kHz, -9997),
                       copy-out in the callback, downmix to mono, bounded
                       200-frame queue with a visible drop counter, the
                       silent-but-open watch (scar 25), and the ABOVE_NORMAL
                       capture-thread priority asserted at runtime (scar 45).
  client/resample.py   the streaming windowed-sinc FIR resampler to 16 kHz,
                       phase-continuous across callbacks (scar 24).
  client/segmenter.py  the utterance segmenter: energy gate, 600 ms hangover,
                       28 s split with 0.5 s overlap, the webrtcvad layer with
                       the measured faint-band bypass, and the BLIP rule
                       (MIN_UTTERANCE_MS=800 + BLIP_RMS=0.004) that exists
                       because on 2026-08-14 a 630 ms keyboard knock was
                       decoded as the confident, fluent, never-spoken word
                       "רפורמים". `PromptSegmenter` below SUBCLASSES it, so
                       feed(), the hangover, the split and the VAD verdict are
                       the same code KESHEV runs.

WHAT THIS FILE ADDS, and only this:
  * a PROMPT ENGINE -- the screen says a word, the person says it, the file is
    named for that word. The prompt IS the label. No recogniser anywhere in the
    labelling path (booth.py's founding decision, kept: a phone recogniser
    scored 5 of 22 on clips whose answer was already known).
  * a MANIFEST. booth/staged/t06/ has 657 clips and no manifest at all -- no
    text, no session, no timestamp, no device. That gap is closed here.
  * SESSION IDENTITY. One sitting = one talker tag = one leave-one-session-out
    fold. Measured 2026-08-23: talker t06 actually contains SIX sittings across
    eleven hours (09:12 to 20:12), collapsed into one tag, so the fence that
    exists to hold out acoustic variation cannot see any of it.
  * RAW AUDIO. KESHEV peak-normalises a segment before handing it to a decoder.
    A corpus must not: the 657 clips already on disk are raw, ERAN's ear is
    about to be given an energy contour it does not yet have, and you can
    always normalise later but you can never un-normalise. The gain KESHEV
    WOULD have applied is computed anyway -- because the accept/reject verdict
    must stay identical to KESHEV's -- and recorded in the manifest.

DEV-FOLD LANDMINE (measured 2026-08-24, still open on eran1):
  proof/measure.py::is_dev() returns `int(digits) % 6 == 0`, so talkers
  t06, t12, t18 ... are the dev fold, and body/school.py drops dev talkers from
  BOTH menus with no error and no warning. A whole night of reading allocated
  to such an id would be eaten by exactly nobody, silently. This rig therefore
  refuses to hand out a dev-fold talker id unless you pass --allow-dev-fold,
  and it writes `dev_fold` into session.json either way. The real repair is on
  eran1, in measure.py; this is the guard rail, not the fix.

NEVER PLAYS AUDIO. There is no output code path in this file or in anything it
imports (KESHEV lint gate G6 enforces that repo-wide). Sacred Audio Law.

  python dictionary.py --selftest          prove the rig, no microphone, no Iddo
  python dictionary.py --devices           list mics, show who is refused and why
  python dictionary.py --list lists/core31.txt --takes 3
  python dictionary.py --list lists/dict-alef.txt --id-prefix a --person iddo
  python dictionary.py --resume t07        continue after a crash, SAME session
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------- the KESHEV stack
ROOT = Path(__file__).resolve().parent                  # ...\eran-brain\booth
KESHEV = Path(os.environ.get("KESHEV_HOME", r"D:\CLAUDE\mic-rebuild"))
if not (KESHEV / "client" / "devices.py").exists():
    raise SystemExit(
        f"KESHEV mic stack not found at {KESHEV}. This rig does not contain a "
        f"microphone implementation of its own -- it reuses the one that works "
        f"every day. Set KESHEV_HOME if it moved.")
if str(KESHEV) not in sys.path:
    sys.path.insert(0, str(KESHEV))

from client import capture as kcapture              # noqa: E402
from client import devices as kdevices              # noqa: E402
from client import segmenter as kseg                # noqa: E402
from client.resample import TARGET_RATE             # noqa: E402

# ---------------------------------------------------------------- constants
RATE = TARGET_RATE                  # 16 000 -- the cochlea's rate, ears.py
CHANNELS = 1
SAMPWIDTH = 2                       # s16le, exactly like the 657 clips on disk

STAGE_DEFAULT = ROOT / "staged"
SELFTEST_OUT = ROOT / "selftest-out"

RESERVED_TALKERS = {0, 1, 2, 3, 4, 5}   # t00-t05 are eran1's synthetic seeds
TALKER_RE = re.compile(r"^t\d{2,}$")
UNIT_RE = re.compile(r"^[a-z0-9]{1,12}$")   # booth.py's SAFE, kept for compatibility

DEV_SESSION_MOD = 6                 # body/genome.py DEV_SESSION_MOD
DEV_SESSION_PICK = 0                # body/genome.py DEV_SESSION_PICK

# booth.py's client-side take gates, moved server-side where they belong.
MIN_PEAK = 0.03                     # "שקט מדי" -- too quiet
MAX_PEAK = 0.99                     # "חתוך"    -- clipped
MIN_MS = 250                        # "קצר מדי" -- too short
MAX_MS = 8000                       # a dictionary word is not eight seconds

# ---- THE CORPUS FLOOR. Measured here 2026-08-24 02:52, and it is the one place
# this rig deliberately DISAGREES with KESHEV.
# KESHEV's rule is "losing a real word is strictly worse than passing an
# occasional blip" (scars 17/18), because a lost word is a word Iddo has to say
# twice and a passed blip is one bad line of typing he can delete. For a CORPUS
# the arithmetic inverts. A six-second smoke run of this very file, with nobody
# speaking, accepted 720 ms of room noise -- rms 0.0062, peak 0.065 -- and filed
# it as a clip of "אַה", because webrtcvad called it speech after a 14.6x gain.
# A rejected take costs one repeat: the screen stays on the same word and he says
# it again. A falsely accepted take is a permanently mislabelled clip that the
# child eats as truth, and booth.py's founding sentence about the recogniser
# applies exactly: that damage does not come out again.
# 0.012 is the p10 of his real speech population (measured 0.0122 over 854 live
# segments). Anything under it is either the room or a mic he has drifted away
# from -- and "come closer" is the right answer to both.
SPEECH_RMS_FLOOR = 0.012
SPEECH_OVER_ROOM = 3.0              # ...and never less than 3x the measured room

# ---- the energy gate, calibrated against THIS room at THIS hour.
# KESHEV's config/client.json carries one gate, 0.008, measured once from 854
# live segments of real dictation: speech population median 0.0276 with p10
# 0.0122; sub-speech population median 0.0031 with p90 0.0060. The gate was put
# in the gap between the two. Its own comment says the real repair is an
# ADAPTIVE gate that tracks the room's own floor instead of a number measured
# at 11am -- because by 23:37 that same night his speech had fallen to 0.005
# and the two populations had converged. This is that adaptive gate, with two
# hard rails:
#   FLOOR   0.004  below this everything is noise anyway (AUTOGAIN_RMS_FLOOR).
#   CEILING 0.010  a gate above the p10 of his real speech would silently eat
#                  his quiet words, and losing a word he actually said is
#                  strictly worse than keeping an occasional blip (scar 17/18).
# Measured here 2026-08-24 02:44 on the BRIO: room floor 0.00377 -> gate 0.0075,
# which lands within 6% of the number KESHEV measured the long way.
CALIB_SECONDS = 2.0
GATE_FLOOR = kseg.AUTOGAIN_RMS_FLOOR        # 0.004
GATE_CEILING = 0.010                        # < speech p10 0.0122, with margin
GATE_OVER_ROOM = 2.0


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def is_dev_fold(talker: str) -> bool:
    """proof/measure.py::is_dev(), reproduced EXACTLY so this rig cannot be
    optimistic about a fold it did not compute the same way."""
    digits = "".join(c for c in talker if c.isdigit())
    if not digits:
        return False
    return int(digits) % DEV_SESSION_MOD == DEV_SESSION_PICK


# ================================================================= prompts

@dataclass(frozen=True)
class Prompt:
    uid: str        # goes in the FILENAME -- ^[a-z0-9]{1,12}$
    text: str       # what the screen says -- the label, in Hebrew
    hint: str = ""  # a smaller line under it


def load_prompts(path: Path, id_prefix: str = "w") -> list[Prompt]:
    """A prompt file is either

        TSV   uid <TAB> text <TAB> hint      (curated lists -- ids are yours)
        plain one Hebrew word per line       (a dictionary page -- ids auto-assigned)

    Blank lines and lines starting with '#' are comments. Both forms may be
    mixed in one file. Auto ids are sequential over the WHOLE file so they are
    stable as long as you do not reorder it."""
    if not path.exists():
        raise SystemExit(f"prompt list not found: {path}")
    out: list[Prompt] = []
    seen: set[str] = set()
    auto = 0
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
            uid, text = parts[0], parts[1] if len(parts) > 1 else ""
            hint = parts[2] if len(parts) > 2 else ""
            if not text:
                raise SystemExit(f"{path}:{lineno}: TSV line has an id but no text")
        else:
            auto += 1
            uid, text, hint = f"{id_prefix}{auto:04d}", line, ""
        if not UNIT_RE.match(uid):
            raise SystemExit(
                f"{path}:{lineno}: id {uid!r} is not ^[a-z0-9]{{1,12}}$ -- it has to "
                f"survive being a filename and matching booth.py's SAFE pattern")
        if uid in seen:
            raise SystemExit(f"{path}:{lineno}: duplicate id {uid!r}")
        seen.add(uid)
        out.append(Prompt(uid, text, hint))
    if not out:
        raise SystemExit(f"{path}: no prompts in it")
    return out


# ================================================================= session

class Session:
    """One sitting. One talker tag. One leave-one-session-out fold.

    Owns the directory, the header, the append-and-fsync manifest and the
    reject log. Everything is written as it happens; nothing is buffered for
    the end, because there may not be an end."""

    def __init__(self, stage_root: Path, talker: str, session_id: str,
                 person: str, resumed: bool = False):
        self.root = stage_root / talker
        self.talker = talker
        self.session_id = session_id
        self.person = person
        self.resumed = resumed
        self.manifest_path = self.root / "manifest.jsonl"
        self.header_path = self.root / "session.json"
        self.rejects_path = self.root / "rejects.jsonl"
        self.clips = 0
        self.rejects = 0
        self.seconds = 0.0

    # ---- allocation -------------------------------------------------------

    @staticmethod
    def used_talkers(stage_root: Path) -> set[int]:
        used = set(RESERVED_TALKERS)
        if stage_root.exists():
            for p in stage_root.iterdir():
                if p.is_dir() and TALKER_RE.match(p.name):
                    used.add(int(p.name[1:]))
        return used

    @classmethod
    def allocate(cls, stage_root: Path, person: str, *,
                 allow_dev_fold: bool = False,
                 forced: str | None = None) -> "Session":
        """A NEW sitting gets a NEW tag. `os.mkdir` is the reservation: it is
        atomic, so two rigs started at once cannot land on the same id."""
        stage_root.mkdir(parents=True, exist_ok=True)
        if forced:
            if not TALKER_RE.match(forced):
                raise SystemExit(f"bad talker id {forced!r} -- expected t07, t08, ...")
            if (stage_root / forced).exists():
                raise SystemExit(
                    f"{stage_root / forced} already exists. A NEW sitting never joins "
                    f"an existing talker id -- that is exactly how talker t06 ended up "
                    f"holding six different sittings across eleven hours, invisible to "
                    f"the leave-one-session-out fence. If this really is the same "
                    f"sitting continuing after a crash, use:  --resume {forced}")
            candidates = [int(forced[1:])]
        else:
            used = cls.used_talkers(stage_root)
            n, candidates = 6, []
            while len(candidates) < 64:
                if n not in used:
                    candidates.append(n)
                n += 1
        skipped: list[str] = []
        for n in candidates:
            talker = f"t{n:02d}"
            if is_dev_fold(talker) and not allow_dev_fold:
                skipped.append(talker)
                continue
            try:
                (stage_root / talker).mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                continue
            sess = cls(stage_root, talker, f"{talker}-{utc_stamp()}", person)
            if skipped:
                print(f"  ! skipped {', '.join(skipped)}: {DEV_SESSION_MOD}-fold dev "
                      f"id(s). body/school.py drops dev talkers from BOTH training "
                      f"menus with no error -- a night recorded there would be eaten "
                      f"by nobody. (--allow-dev-fold to record one on purpose.)")
            return sess
        raise SystemExit("could not allocate a talker id -- every candidate existed")

    @classmethod
    def resume(cls, stage_root: Path, talker: str) -> "Session":
        d = stage_root / talker
        hdr = d / "session.json"
        if not hdr.exists():
            raise SystemExit(f"cannot resume {talker}: no {hdr}")
        h = json.loads(hdr.read_text(encoding="utf-8"))
        sess = cls(stage_root, talker, h["session_id"], h.get("person", "unknown"),
                   resumed=True)
        for line in sess.manifest_path.read_text(encoding="utf-8").splitlines() \
                if sess.manifest_path.exists() else []:
            if line.strip():
                rec = json.loads(line)
                sess.clips += 1
                sess.seconds += rec.get("duration_ms", 0) / 1000.0
        return sess

    # ---- writing ----------------------------------------------------------

    def write_header(self, **extra) -> None:
        # A resume must not erase when the sitting actually began, nor which mic
        # and room the earlier clips were recorded in. The header keeps the
        # original start and grows a `resumes` list; a session is a session.
        prior = {}
        if self.resumed and self.header_path.exists():
            try:
                prior = json.loads(self.header_path.read_text(encoding="utf-8"))
            except Exception:
                prior = {}
        hdr = {
            "session_id": self.session_id,
            "talker": self.talker,
            "person": self.person,
            "started_utc": prior.get("started_utc", utc_iso()),
            "sample_rate": RATE,
            "channels": CHANNELS,
            "sample_width_bytes": SAMPWIDTH,
            "audio": "raw, NOT peak-normalised (the gain KESHEV would have "
                     "applied is in each manifest row as would_be_gain)",
            "dev_fold": is_dev_fold(self.talker),
            "dev_fold_rule": f"int(digits) % {DEV_SESSION_MOD} == {DEV_SESSION_PICK} "
                             f"(proof/measure.py::is_dev)",
            "one_session_per_talker": True,
            "tool": "booth/dictionary.py",
            "reuses": ["mic-rebuild/client/devices.py",
                       "mic-rebuild/client/capture.py",
                       "mic-rebuild/client/resample.py",
                       "mic-rebuild/client/segmenter.py"],
        }
        hdr.update(extra)
        if self.resumed:
            resumes = list(prior.get("resumes", []))
            resumes.append({"utc": utc_iso(),
                            "clips_already_on_disk": self.clips,
                            "device": extra.get("device"),
                            "room_floor_rms": extra.get("room_floor_rms")})
            hdr["resumes"] = resumes
            # what the FIRST sitting used, kept even if this leg differs
            for k in ("device", "host_api", "capture_rate", "capture_channels",
                      "room_floor_rms", "gate_rms", "speech_rms_floor"):
                if k in prior:
                    hdr.setdefault("first_leg", {})[k] = prior[k]
        self._atomic_json(self.header_path, hdr)

    def _atomic_json(self, path: Path, obj) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _append(self, path: Path, obj) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def next_take(self, uid: str) -> int:
        n = 0
        for p in self.root.glob(f"{uid}_{self.talker}_*.wav"):
            n += 1
        return n

    def write_clip(self, prompt: Prompt, samples: np.ndarray, meta: dict) -> dict:
        """WAV first, manifest row second. A crash between the two leaves an
        orphan wav that no manifest row claims -- visible, and never a clip
        presented as labelled when it is not. The reverse order would lie."""
        take = self.next_take(prompt.uid)
        name = f"{prompt.uid}_{self.talker}_{take:04d}.wav"
        wav_path = self.root / name
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
        tmp = wav_path.with_suffix(".wav.tmp")
        with open(tmp, "wb") as fh:
            with wave.open(fh, "wb") as w:
                w.setnchannels(CHANNELS)
                w.setsampwidth(SAMPWIDTH)
                w.setframerate(RATE)
                w.writeframes(pcm)
            fh.flush()
            os.fsync(fh.fileno())      # the bytes are on the platter before
        os.replace(tmp, wav_path)      # the manifest ever claims them

        row = {
            "file": name,
            "unit": prompt.uid,
            "text": prompt.text,
            "hint": prompt.hint,
            "take": take,
            "talker": self.talker,
            "session_id": self.session_id,
            "person": self.person,
            "utc": utc_iso(),
            "epoch": round(time.time(), 3),
            "sample_rate": RATE,
            "channels": CHANNELS,
            "samples": int(len(samples)),
        }
        row.update(meta)
        self._append(self.manifest_path, row)
        self.clips += 1
        self.seconds += row.get("duration_ms", 0) / 1000.0
        return row

    def write_reject(self, prompt: Prompt, reason: str, meta: dict) -> None:
        row = {"unit": prompt.uid, "text": prompt.text, "reason": reason,
               "utc": utc_iso(), "session_id": self.session_id}
        row.update(meta)
        self._append(self.rejects_path, row)
        self.rejects += 1


# ================================================================= segmenter

@dataclass
class Clip:
    samples: np.ndarray
    duration_ms: int
    rms_raw: float
    peak: float
    would_be_gain: float
    seg_id: str
    ok: bool
    reason: str = ""


class PromptSegmenter(kseg.Segmenter):
    """KESHEV's Segmenter with ONE thing changed: what happens at close.

    Everything upstream -- feed(), the energy gate, the 600 ms hangover, the
    28 s split with its 0.5 s overlap, the sequence ids, the webrtcvad verdict
    with its measured faint-band bypass -- is the parent's code, unmodified.

    _close() is overridden because a corpus and a decoder want opposite things:
      * KESHEV peak-normalises (gain up to 40x) and hands bytes to a decoder;
        a corpus must keep the raw level. The gain is still COMPUTED, so the
        VAD sees exactly the bytes KESHEV's VAD would have seen and the
        accept/reject verdict is identical -- then it is recorded, not applied.
      * KESHEV writes to a spool with a journal; this writes a named clip and a
        manifest row. So no Spool is needed, and none is constructed.
      * booth.py's three take gates (peak floor / clipping / minimum length)
        run here, where the person can be asked to say it again."""

    def __init__(self, gate_rms: float, session_id: str,
                 speech_floor: float = SPEECH_RMS_FLOOR, **kw):
        super().__init__(spool=None, gate_rms=gate_rms, session_id=session_id, **kw)
        self.speech_floor = float(speech_floor)
        self.rejected_gate = 0

    def _close(self, split: bool):
        samples = np.concatenate(self._buf) if self._buf else np.empty(0, np.float32)
        overlap = samples[-int(kseg.SPLIT_OVERLAP_S * self.rate):].copy() if split else None

        seg_id = self._next_id()
        duration_ms = int(len(samples) / self.rate * 1000)
        rms_raw = kseg._rms(samples)
        peak = float(np.max(np.abs(samples))) if len(samples) else 0.0

        # the gain KESHEV WOULD apply -- computed for the VAD, recorded, not applied
        gain = 1.0
        if rms_raw >= kseg.AUTOGAIN_RMS_FLOOR and peak > 0.0:
            gain = max(1.0, min(kseg.AUTOGAIN_TARGET_PEAK / peak, kseg.AUTOGAIN_MAX))
        pcm = (np.clip(samples * gain, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()

        ok, reason = True, ""
        if duration_ms < kseg.MIN_UTTERANCE_MS and rms_raw < kseg.BLIP_RMS:
            ok, reason = False, "blip"          # KESHEV's rule, its own scar
        elif duration_ms < MIN_MS:
            ok, reason = False, "too_short"     # booth.py "קצר מדי"
        elif duration_ms > MAX_MS:
            ok, reason = False, "too_long"
        elif peak < MIN_PEAK:
            ok, reason = False, "too_quiet"     # booth.py "שקט מדי"
        elif rms_raw < self.speech_floor:
            ok, reason = False, "under_speech_floor"   # the corpus floor, above
        elif peak > MAX_PEAK:
            ok, reason = False, "clipped"       # booth.py "חתוך"
        elif rms_raw * gain >= kseg.AUTOGAIN_RMS_FLOOR and not self._vad_keeps(pcm):
            ok, reason = False, "vad"           # KESHEV's faint-band bypass
        if not ok:
            self.rejected_gate += 1

        clip = Clip(samples=samples.copy(), duration_ms=duration_ms, rms_raw=rms_raw,
                    peak=peak, would_be_gain=gain, seg_id=seg_id, ok=ok, reason=reason)

        # continuation state -- byte-for-byte the parent's tail
        if split:
            self._in_seg = True
            self._buf = [overlap] if overlap is not None and len(overlap) else []
            self._seg_samples = len(overlap) if overlap is not None else 0
            self._silent_samples = 0
        else:
            self._in_seg = False
            self._buf = []
            self._seg_samples = 0
            self._silent_samples = 0
        return clip


# ================================================================= devices

def keshev_pinned_mic() -> str | None:
    """KESHEV already knows which microphone is the good one in this room --
    config/client.json pins "Logitech BRIO", calibrated against 854 live
    segments of real dictation. Reuse that answer instead of guessing; the
    device law still gets the final word, and a pin can only choose among
    ALLOWED devices (scar 21: it can never re-expose a forbidden one)."""
    try:
        cfg = json.loads((KESHEV / "config" / "client.json").read_text(encoding="utf-8"))
        name = cfg.get("mic_name")
        return name if isinstance(name, str) and name.strip() else None
    except Exception:
        return None


def enumerate_devices():
    """Real PortAudio rows -> the K6 DeviceInfo the device law understands."""
    import sounddevice as sd
    rows = []
    for i, d in enumerate(sd.query_devices()):
        rows.append(kdevices.DeviceInfo(
            index=i,
            name=d["name"],
            hostapi=sd.query_hostapis(d["hostapi"])["name"],
            max_input_channels=int(d["max_input_channels"]),
            max_output_channels=int(d["max_output_channels"]),
        ))
    return rows


def report_devices(pinned: str | None = None) -> kdevices.Selection:
    rows = enumerate_devices()
    sel = kdevices.select_device(rows, pinned=pinned)
    print("\n  MICROPHONES / מיקרופונים")
    print("  " + "-" * 74)
    refused_names = {n for n, _ in sel.refused}
    for d in rows:
        if d.max_input_channels <= 0:
            continue
        tok = kdevices.forbidden_match(d.name)
        if tok:
            mark, why = "REFUSED", f"Sacred Audio Law: name contains {tok!r}"
        elif kdevices._hostapi_rank(d.hostapi) is None:
            mark, why = "skipped ", f"host API {d.hostapi} is never opened (scar 23)"
        else:
            mark, why = "allowed ", ""
        print(f"  [{mark}] {d.index:>3}  {d.hostapi:<20} {d.name[:34]:<34} {why}")
    print("  " + "-" * 74)
    if sel.state == kdevices.Selection.SELECTED:
        print(f"  CHOSEN: #{sel.device.index} {sel.device.name} [{sel.device.hostapi}]"
              f"{'  (pinned)' if sel.pin_honored else ''}")
        print(f"  fallback chain: " +
              " -> ".join(f"{d.hostapi}" for d in sel.chain))
    else:
        print("  " + sel.announcement)
    print()
    return sel


# ================================================================= console UI

class Screen:
    """Deliberately plain. A tired man at 5am needs one big word and nothing
    that scrolls away underneath it."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet
        self._last = ""

    def banner(self, sess: Session, sel, total: int, gate: float):
        if self.quiet:
            return
        print()
        print("=" * 78)
        print("  ERAN DICTIONARY  /  המילון של ערן")
        print("=" * 78)
        print(f"  session   {sess.session_id}     talker {sess.talker}"
              f"     person {sess.person}")
        print(f"  mic       {sel}")
        print(f"  gate      rms {gate:.4f}   |   16 000 Hz mono 16-bit raw")
        print(f"  saving to {sess.root}")
        print(f"  prompts   {total}")
        print("  keys      s=skip / דלג   r=redo / שוב   p=pause / הפסקה   "
              "q=quit / סיום")
        print("=" * 78)
        print()

    def prompt(self, i: int, total: int, p: Prompt, note: str = ""):
        if self.quiet:
            return
        bar_w = 60
        done = int(bar_w * i / max(1, total))
        print()
        print(f"  [{i + 1}/{total}]  " + "#" * done + "." * (bar_w - done))
        print("  +" + "-" * 40 + "+")
        print("  |")
        print(f"  |        {p.text}")
        print("  |")
        if p.hint:
            print(f"  |   ({p.hint})")
        print("  +" + "-" * 40 + "+")
        print(f"  id={p.uid}" + (f"    {note}" if note else ""))
        print("  ...")

    def ok(self, row: dict):
        if self.quiet:
            return
        print(f"  OK  {row['file']}   {row['duration_ms']} ms   "
              f"peak {row['peak']:.3f}   rms {row['rms_raw']:.4f}")

    def bad(self, reason: str, ms: int, peak: float):
        if self.quiet:
            return
        msg = {
            "too_quiet": "שקט מדי -- תתקרב למיקרופון / too quiet, come closer",
            "under_speech_floor":
                "חלש מדי בשביל המילון -- תתקרב למיקרופון / "
                "below the corpus floor, come closer to the mic",
            "clipped":   "חתוך -- תתרחק קצת / clipped, back off a little",
            "too_short": "קצר מדי / too short",
            "too_long":  "ארוך מדי / too long",
            "blip":      "רעש, לא מילה / noise, not a word",
            "vad":       "לא נשמע כמו דיבור / did not sound like speech",
        }.get(reason, reason)
        print(f"  שוב בבקשה / again please  --  {msg}   ({ms} ms, peak {peak:.3f})")


def poll_key() -> str | None:
    """Non-blocking single key, Windows console. Absent elsewhere -> no keys,
    and Ctrl+C still ends the session cleanly."""
    try:
        import msvcrt
    except ImportError:
        return None
    if not msvcrt.kbhit():
        return None
    ch = msvcrt.getwch()
    return ch.lower() if ch else None


# ================================================================= live run

def open_mic(sel, on_event):
    """Open the chosen mic through the K6 fallback chain with K7 format
    negotiation. Returns (stream, opened_device, pipeline, cap_rate, cap_ch)."""
    import sounddevice as sd

    def check(rate, ch):
        sd.check_input_settings(device=sel.device.index, samplerate=rate, channels=ch)

    cap_rate, cap_ch = kcapture.negotiate_format(
        check, native_rate=int(sd.query_devices(sel.device.index)["default_samplerate"]),
        native_channels=sel.device.max_input_channels)
    pipe = kcapture.CapturePipeline(cap_rate, cap_ch, on_event=on_event)

    def make_stream(dev):
        try:
            s = sd.InputStream(device=dev.index, samplerate=cap_rate, channels=cap_ch,
                               dtype="float32", blocksize=0,
                               callback=lambda ind, frames, t, st: pipe.on_audio(ind, st))
            s.start()
            return s
        except Exception as e:
            if "Unanticipated host error" in str(e):
                raise kdevices.TransientDeviceError(str(e))
            raise

    stream, opened = kdevices.open_with_retry(make_stream, sel.chain)
    return stream, opened, pipe, cap_rate, cap_ch


def measure_room(pipe, seconds: float = CALIB_SECONDS) -> tuple[float, float]:
    """Two seconds of the room's own silence. The one gate KESHEV carries in
    config was measured once, at 11am, in a room that is not this one at 5am;
    its own comment says the real repair is an ADAPTIVE gate that tracks the
    room's floor. This is that. Audio is measured and discarded, never stored."""
    t0, levels = time.time(), []
    while time.time() - t0 < seconds:
        f = pipe.read(timeout=0.1)
        if f is not None:
            levels.append(kseg._rms(f))
    room = float(np.median(levels)) if levels else 0.0
    gate = min(GATE_CEILING, max(GATE_FLOOR, room * GATE_OVER_ROOM))
    return room, gate


def run_dryrun(args) -> int:
    """Everything the live path does EXCEPT the person: enumerate, refuse,
    choose, negotiate, open, measure the room, close. No session directory, no
    wav, no manifest, not one sample kept. Proves the live path without
    recording anybody."""
    print("=" * 78)
    print("  DRY RUN -- opens the microphone, measures the room, writes NOTHING.")
    print("             No session is created. No audio is stored or played.")
    print("=" * 78)
    sel = report_devices(args.mic)
    if sel.state != kdevices.Selection.SELECTED:
        print("  " + sel.announcement)
        return 2
    try:
        stream, opened, pipe, cap_rate, cap_ch = open_mic(
            sel, on_event=lambda e, **k: print(f"  [{e}] {k}"))
    except kdevices.DeviceOpenError as e:
        print(f"\n  Could not open the microphone: {e}")
        print("  Is KESHEV running? Two programs cannot hold one mic. / "
              "האם קשב פתוח? תסגור אותו.")
        return 3
    try:
        print(f"  opened   {opened.name} [{opened.hostapi}]")
        print(f"  format   {cap_rate} Hz x {cap_ch} ch  ->  resampled to {RATE} Hz mono")
        room, gate = measure_room(pipe)
        print(f"  room     floor rms {room:.5f}  ->  gate {gate:.5f}")
        print(f"  frames   {pipe.frames_enqueued} enqueued, {pipe.frames_dropped} dropped, "
              f"{pipe.callbacks} callbacks, thread priority {pipe.thread_priority}")
        live = room > 0.0
        print(f"  [{'PASS' if live else 'FAIL'}] the stream actually delivered audio")
        print("  [PASS] nothing was written: no session directory, no wav, no manifest")
        return 0 if live else 4
    finally:
        try:
            stream.stop(); stream.close()
        except Exception:
            pass


def run_live(args) -> int:
    prompts = load_prompts(Path(args.list), args.id_prefix)
    stage_root = Path(args.stage)

    sel = report_devices(args.mic)
    if sel.state != kdevices.Selection.SELECTED:
        print("  Nothing to record with. Plug in a USB mic. / חבר מיקרופון USB.")
        return 2

    if args.resume:
        sess = Session.resume(stage_root, args.resume)
        print(f"  RESUMING session {sess.session_id} ({sess.clips} clips already on "
              f"disk). Same talker, same fold -- a resume is NOT a new session.")
    else:
        sess = Session.allocate(stage_root, args.person,
                                allow_dev_fold=args.allow_dev_fold,
                                forced=args.talker)
        if args.talker and any(sess.root.glob("*.wav")):
            raise SystemExit(
                f"{sess.root} already has clips from another sitting. A new session "
                f"never joins an existing talker id -- use --resume {args.talker} if "
                f"this really is the same sitting continuing.")

    # ---- open the device through the K6 chain, with K7 format negotiation
    try:
        stream, opened, pipe, cap_rate, cap_ch = open_mic(
            sel, on_event=lambda e, **k: print(f"  [{e}] {k}"))
    except kdevices.DeviceOpenError as e:
        print(f"\n  Could not open the microphone: {e}")
        print("  Is KESHEV running? Two programs cannot hold one mic. / "
              "האם קשב פתוח? תסגור אותו.")
        return 3

    # ---- room floor
    print("  Two seconds of quiet, please. / שתי שניות שקט בבקשה.")
    room, gate = measure_room(pipe)
    speech_floor = max(args.speech_rms, room * SPEECH_OVER_ROOM)
    print(f"  room floor rms {room:.5f}  ->  gate {gate:.5f}, "
          f"corpus speech floor {speech_floor:.5f}")

    sess.write_header(device=opened.name, host_api=opened.hostapi,
                      capture_rate=cap_rate, capture_channels=cap_ch,
                      room_floor_rms=round(room, 6), gate_rms=round(gate, 6),
                      speech_rms_floor=round(speech_floor, 6),
                      prompt_list=str(Path(args.list).resolve()),
                      takes_per_prompt=args.takes)

    seg = PromptSegmenter(gate, sess.session_id, speech_floor=speech_floor)
    scr = Screen()
    scr.banner(sess, f"{opened.name} [{opened.hostapi}] {cap_rate} Hz",
               len(prompts) * args.takes, gate)

    queue_ = [(p, t) for p in prompts for t in range(args.takes)]
    if sess.resumed:
        queue_ = queue_[sess.clips:]
    total = len(queue_)
    i, paused = 0, False
    scr.prompt(i, total, queue_[i][0])
    deadline = time.time() + args.smoke_seconds if args.smoke_seconds else None

    try:
        while i < total:
            if deadline and time.time() > deadline:
                print(f"\n  --smoke-seconds {args.smoke_seconds} elapsed; "
                      f"stopping exactly as 'q' would")
                break
            k = poll_key()
            if k == "q":
                print("\n  finishing / מסיים")
                break
            if k == "p":
                paused = not paused
                print("  PAUSED / מושהה — p to continue" if paused
                      else "  going / ממשיך")
                seg.flush()
            if k == "s":
                i += 1
                if i < total:
                    scr.prompt(i, total, queue_[i][0], "(skipped / דילגת)")
                continue
            if k == "r" and sess.clips:
                # step back one prompt; the extra take is simply take N+1
                i = max(0, i - 1)
                scr.prompt(i, total, queue_[i][0], "(redo / שוב)")
                continue

            frame = pipe.read(timeout=0.1)
            if frame is None or paused:
                continue
            for clip in seg.feed(frame):
                p = queue_[i][0]
                if clip.ok:
                    row = sess.write_clip(p, clip.samples, {
                        "duration_ms": clip.duration_ms,
                        "rms_raw": round(clip.rms_raw, 6),
                        "peak": round(clip.peak, 6),
                        "would_be_gain": round(clip.would_be_gain, 3),
                        "seg_id": clip.seg_id,
                        "gate_rms": round(gate, 6),
                        "device": opened.name,
                    })
                    scr.ok(row)
                    i += 1
                    if i < total:
                        scr.prompt(i, total, queue_[i][0])
                else:
                    sess.write_reject(p, clip.reason, {
                        "duration_ms": clip.duration_ms,
                        "rms_raw": round(clip.rms_raw, 6),
                        "peak": round(clip.peak, 6)})
                    scr.bad(clip.reason, clip.duration_ms, clip.peak)
                if i >= total:
                    break
    except KeyboardInterrupt:
        print("\n  Ctrl+C -- saving / שומר")
    finally:
        last = seg.flush()
        if last is not None and last.ok and i < total:
            sess.write_clip(queue_[i][0], last.samples, {
                "duration_ms": last.duration_ms,
                "rms_raw": round(last.rms_raw, 6),
                "peak": round(last.peak, 6),
                "would_be_gain": round(last.would_be_gain, 3),
                "seg_id": last.seg_id, "gate_rms": round(gate, 6),
                "device": opened.name})
        try:
            stream.stop(); stream.close()
        except Exception:
            pass

    print()
    print("=" * 78)
    print(f"  {sess.clips} clips   {sess.seconds:.1f} s ({sess.seconds / 60:.1f} min)"
          f"   {sess.rejects} rejected takes")
    print(f"  {sess.root}")
    print(f"  manifest: {sess.manifest_path}")
    print(f"  dropped capture frames: {pipe.frames_dropped}   "
          f"overflows: {pipe.overflow_count}")
    print("=" * 78)
    return 0


# ================================================================= self-test

def _voiced(seconds: float, rate: int, amp: float, rng) -> np.ndarray:
    """A synthetic voiced sound: 118 Hz glottal pulse train through three
    formant resonators (730 / 1090 / 2440 Hz -- an /a/). Not speech, but voiced
    enough that the REAL webrtcvad calls it speech, which is the point: the
    self-test exercises the true gate, not a stubbed one."""
    n = int(rate * seconds)
    per = max(2, int(rate / 118.0))
    x = np.zeros(n)
    x[::per] = 1.0
    k = np.exp(-np.arange(int(rate * 0.005)) / (rate * 0.00075))
    x = np.convolve(x, k)[:n]
    y = np.zeros(n)
    for F, B in ((730, 80), (1090, 90), (2440, 120)):
        r = np.exp(-np.pi * B / rate)
        th = 2 * np.pi * F / rate
        a1, a2 = -2 * r * np.cos(th), r * r
        o = np.zeros(n)
        for t in range(2, n):
            o[t] = x[t] - a1 * o[t - 1] - a2 * o[t - 2]
        y += o / (np.max(np.abs(o)) + 1e-9)
    y = y / (np.max(np.abs(y)) + 1e-9) * amp
    y *= (1.0 + 0.05 * rng.standard_normal(n))
    return y.astype(np.float32)


def selftest(args) -> int:
    print("=" * 78)
    print("  SELF-TEST -- no microphone is opened, no audio is played,")
    print("               no person is recorded. Synthetic audio only.")
    print("=" * 78)
    fails: list[str] = []

    def check(name, cond, detail=""):
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
        if not cond:
            fails.append(name)

    # ---- 1. the device law, against the REAL devices on this machine
    print("\n-- 1. device law (SACRED AUDIO) -------------------------------------")
    try:
        rows = enumerate_devices()
        sel = kdevices.select_device(rows)
        refused = {n.lower(): t for n, t in sel.refused}
        bt = [d.name for d in rows
              if d.max_input_channels > 0 and kdevices.forbidden_match(d.name)]
        for n in bt:
            print(f"       refused: {n[:60]}  [{kdevices.forbidden_match(n)}]")
        check("every bluetooth/headset/virtual input is refused",
              all(n.lower() in refused for n in bt), f"{len(bt)} refused")
        chosen = sel.device.name if sel.device else None
        check("the chosen mic is not a forbidden device",
              chosen is None or kdevices.forbidden_match(chosen) is None,
              f"chosen: {chosen}")
    except Exception as e:
        check("device enumeration", False, str(e))

    # a machine with ONLY a bluetooth headset must go idle, never fall back
    only_bt = [kdevices.DeviceInfo(0, "Headset (WH-1000XM4)", "Windows WASAPI", 1),
               kdevices.DeviceInfo(1, "Hands-Free (JBL TUNE510BT)", "Windows WDM-KS", 1)]
    s = kdevices.select_device(only_bt)
    check("bluetooth-only machine -> IDLE_NO_MIC, no fallback",
          s.state == kdevices.Selection.IDLE_NO_MIC and s.device is None)
    try:
        kdevices.open_with_retry(lambda d: object(), only_bt)
        check("open layer refuses a forbidden device", False, "it opened one")
    except kdevices.SacredAudioViolation:
        check("open layer refuses a forbidden device", True,
              "SacredAudioViolation raised")

    # ---- 1b. the adaptive gate's rails
    print("\n-- 1b. energy-gate rails --------------------------------------------")

    class _FakePipe:
        def __init__(self, level): self.level, self.n = level, 0
        def read(self, timeout=0.1):
            self.n += 1
            return None if self.n > 40 else np.full(480, self.level, np.float32)

    silent_room, g_silent = measure_room(_FakePipe(0.0001), seconds=0.05)
    loud_room, g_loud = measure_room(_FakePipe(0.20), seconds=0.05)
    check("a silent room cannot drive the gate below the noise floor",
          g_silent == GATE_FLOOR, f"room {silent_room:.5f} -> gate {g_silent:.5f}")
    check("a noisy calibration cannot drive the gate above his quiet speech",
          g_loud == GATE_CEILING and GATE_CEILING < 0.0122,
          f"room {loud_room:.3f} -> gate {g_loud:.5f}; his speech p10 is 0.0122, "
          f"so a runaway gate can never eat a word he said")

    # ---- 2. talker allocation and the dev-fold landmine
    print("\n-- 2. session identity ---------------------------------------------")
    if SELFTEST_OUT.exists():
        shutil.rmtree(SELFTEST_OUT)
    stage = SELFTEST_OUT / "staged"
    s1 = Session.allocate(stage, "selftest-person")
    check("first id skips the dev fold t06", s1.talker == "t07",
          f"got {s1.talker}; t06 % 6 == 0 -> school.py would drop it silently")
    check("allocated id is not a dev fold", not is_dev_fold(s1.talker))
    s2 = Session.allocate(stage, "selftest-person")
    check("a second sitting gets a DIFFERENT talker id",
          s2.talker != s1.talker, f"{s1.talker} then {s2.talker}")
    check("session ids differ", s1.session_id != s2.session_id)
    s3 = Session.allocate(stage, "selftest-person", allow_dev_fold=True)
    check("--allow-dev-fold can still take a dev id on purpose",
          is_dev_fold(s3.talker), f"got {s3.talker}")
    shutil.rmtree(stage / s2.talker)
    shutil.rmtree(stage / s3.talker)

    # ---- 3. the full capture -> resample -> segment -> write pipeline
    print("\n-- 3. capture -> 16 kHz -> segment -> clip + manifest ---------------")
    prompts = load_prompts(Path(args.list), args.id_prefix)[:6]
    rng = np.random.default_rng(20260824)
    cap_rate, cap_ch = 48000, 2          # what a BRIO actually gives (scar 24)
    pipe = kcapture.CapturePipeline(cap_rate, cap_ch,
                                    set_priority_fn=lambda: 1,   # no real thread here
                                    on_event=lambda e, **k: None)
    gate = 0.008
    s1.write_header(device="SELFTEST synthetic stream", host_api="none",
                    capture_rate=cap_rate, capture_channels=cap_ch,
                    room_floor_rms=0.0012, gate_rms=gate,
                    prompt_list=str(Path(args.list).resolve()),
                    takes_per_prompt=1, selftest=True)
    seg = PromptSegmenter(gate, s1.session_id)

    voice = _voiced(0.55, cap_rate, 0.28, rng)
    quiet = lambda sec: (0.0009 * rng.standard_normal(int(cap_rate * sec))).astype(np.float32)

    written: list[dict] = []
    manifest_snapshots: list[int] = []      # complete rows readable AFTER each clip
    idx = 0

    def drive(mono: np.ndarray):
        nonlocal idx
        stereo = np.repeat(mono[:, None], cap_ch, axis=1)
        for off in range(0, len(stereo), 1024):
            pipe.on_audio(stereo[off:off + 1024], None)
            while True:
                fr = pipe.read(timeout=0)
                if fr is None:
                    break
                for clip in seg.feed(fr):
                    if clip.ok and idx < len(prompts):
                        written.append(s1.write_clip(prompts[idx], clip.samples, {
                            "duration_ms": clip.duration_ms,
                            "rms_raw": round(clip.rms_raw, 6),
                            "peak": round(clip.peak, 6),
                            "would_be_gain": round(clip.would_be_gain, 3),
                            "seg_id": clip.seg_id, "gate_rms": gate,
                            "device": "SELFTEST synthetic stream"}))
                        idx += 1
                        # THE crash-safety proof: read the manifest back from
                        # disk RIGHT NOW, as a separate process would after a
                        # power cut, and count the complete rows.
                        manifest_snapshots.append(sum(
                            1 for ln in s1.manifest_path.read_text(
                                encoding="utf-8").splitlines()
                            if ln.strip() and json.loads(ln)))
                    elif not clip.ok:
                        s1.write_reject(prompts[min(idx, len(prompts) - 1)],
                                        clip.reason,
                                        {"duration_ms": clip.duration_ms,
                                         "rms_raw": round(clip.rms_raw, 6),
                                         "peak": round(clip.peak, 6)})

    drive(quiet(0.9))
    for j in range(len(prompts)):
        drive(voice * (0.7 + 0.1 * j))       # a person is not a metronome
        drive(quiet(1.0))                    # > 600 ms hangover: closes the segment
    drive(quiet(0.9))
    check("one clip per prompt was written", len(written) == len(prompts),
          f"{len(written)} clips for {len(prompts)} prompts")

    # ---- 3b. two keyboard knocks. Neither may ever become a word.
    # On 2026-08-14 a 630 ms knock was decoded as "רפורמים" -- correctly spelled,
    # grammatical, and never spoken. In a CORPUS that is worse than a wrong
    # decode: it is a permanently mislabelled clip the child eats as truth.
    gated_before, before = seg.gated_frames, idx
    soft = np.concatenate([quiet(0.02),
                           (0.005 * rng.standard_normal(int(cap_rate * 0.12))).astype(np.float32),
                           quiet(0.9)])
    drive(soft)                       # below the gate: no segment ever opens
    check("a knock under the energy gate never opens a segment",
          idx == before and seg.gated_frames > gated_before,
          f"+{seg.gated_frames - gated_before} frames gated, 0 clips")

    rej_before = s1.rejects
    # narrowband so the anti-alias FIR (cutoff 7.2 kHz) passes it intact -- a
    # broadband burst loses ~45% of its rms crossing 48k -> 16k, which is real
    # physics and would have made this test measure the resampler, not the rule.
    tb = np.arange(int(cap_rate * 0.11)) / cap_rate
    loud = np.concatenate([quiet(0.02),
                           (0.0135 * np.sin(2 * np.pi * 1200 * tb)).astype(np.float32),
                           quiet(1.0)])
    drive(loud)                       # over the gate, but short AND at noise level
    check("a knock over the gate is caught by KESHEV's blip rule, and logged",
          idx == before and s1.rejects > rej_before,
          f"{s1.rejects - rej_before} rejected take(s), 0 clips")

    # 3c. THE regression. A 6 s smoke run of the live path on 2026-08-24 02:52,
    # with nobody speaking, filed 720 ms of room noise (rms 0.0062, peak 0.065)
    # as a clip of "אַה" -- webrtcvad called it speech after a 14.6x gain. This
    # reproduces that exact signal and requires the corpus floor to refuse it.
    rej_before = s1.rejects
    hum = _voiced(0.75, cap_rate, 0.050, rng)      # long enough to dodge the blip rule
    drive(np.concatenate([quiet(0.05), hum, quiet(1.0)]))
    last_rej = [json.loads(l) for l in
                s1.rejects_path.read_text(encoding="utf-8").splitlines() if l.strip()][-1]
    check("room-level sound that VAD calls speech is still refused by the corpus floor",
          idx == before and s1.rejects > rej_before
          and last_rej["reason"] == "under_speech_floor",
          f"reason={last_rej['reason']}, rms {last_rej['rms_raw']:.4f} < "
          f"{SPEECH_RMS_FLOOR} (p10 of his real speech)")

    # ---- 4. what is on disk
    print("\n-- 4. the files on disk --------------------------------------------")
    wavs = sorted(s1.root.glob("*.wav"))
    check("no .tmp files left behind", not list(s1.root.glob("*.tmp")))
    bad_fmt = []
    for w in wavs:
        with wave.open(str(w)) as f:
            if (f.getframerate(), f.getnchannels(), f.getsampwidth()) != (RATE, 1, 2):
                bad_fmt.append(w.name)
    check("every wav is 16 000 Hz mono 16-bit (the cochlea's format)",
          not bad_fmt, f"{len(wavs)} files" + (f"  BAD: {bad_fmt}" if bad_fmt else ""))

    rows = [json.loads(l) for l in
            s1.manifest_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("one manifest row per wav", len(rows) == len(wavs),
          f"{len(rows)} rows / {len(wavs)} wavs")
    check("every manifest row points at a file that exists",
          all((s1.root / r["file"]).exists() for r in rows))
    check("every row carries text + session + timestamp",
          all(r.get("text") and r.get("session_id") and r.get("utc") for r in rows))
    check("every row carries ONE session id, this one",
          {r["session_id"] for r in rows} == {s1.session_id})
    check("filenames follow {unit}_{talker}_{take}.wav",
          all(re.fullmatch(rf"{r['unit']}_{s1.talker}_\d+\.wav", r["file"]) for r in rows))
    check("proof/measure.py::session_of() reads the SESSION off every filename",
          {f.name.split("_")[1] for f in wavs} == {s1.talker})

    hdr = json.loads(s1.header_path.read_text(encoding="utf-8"))
    check("session.json says this fold is NOT dev", hdr["dev_fold"] is False)

    # raw, not normalised: a normaliser would have pushed every peak to 0.95
    peaks = [r["peak"] for r in rows]
    check("audio is RAW -- peaks vary, nothing was peak-normalised",
          len(set(round(p, 2) for p in peaks)) > 1 and max(peaks) < 0.94,
          f"peaks {min(peaks):.3f}..{max(peaks):.3f}; "
          f"would_be_gain {rows[0]['would_be_gain']}x recorded but not applied")

    check("manifest rows are in the order they were recorded",
          [r["unit"] for r in rows] == [p.uid for p in prompts],
          " -> ".join(r["unit"] for r in rows))

    # crash safety: the manifest is complete at EVERY instant, not at the end.
    # These counts were read back off the disk between clips, mid-session.
    check("manifest is complete on disk after every single clip (crash-safe)",
          manifest_snapshots == list(range(1, len(prompts) + 1)),
          f"rows readable after clip 1..N: {manifest_snapshots}")

    # ---- 4b. resume: a crash must NOT start a new session
    print("\n-- 4b. resume after a crash ----------------------------------------")
    r1 = Session.resume(stage, s1.talker)
    check("resume keeps the SAME talker id", r1.talker == s1.talker)
    check("resume keeps the SAME session id", r1.session_id == s1.session_id,
          r1.session_id)
    check("resume knows how much is already on disk", r1.clips == len(prompts),
          f"{r1.clips} clips, {r1.seconds:.1f} s")
    check("a resume is not a new fold", is_dev_fold(r1.talker) is False)

    # ---- 5. show the layout and the manifest
    print("\n-- 5. WHAT IT PRODUCES ---------------------------------------------")
    print(f"  {s1.root}")
    for p in sorted(s1.root.iterdir()):
        print(f"      {p.name:<28} {p.stat().st_size:>9,} bytes")
    print("\n  session.json:")
    for line in json.dumps(hdr, ensure_ascii=False, indent=2).splitlines():
        print("      " + line)
    print("\n  manifest.jsonl (first 3 rows):")
    for r in rows[:3]:
        print("      " + json.dumps(r, ensure_ascii=False))
    if s1.rejects_path.exists():
        print("\n  rejects.jsonl:")
        for line in s1.rejects_path.read_text(encoding="utf-8").splitlines():
            print("      " + line)

    print("\n" + "=" * 78)
    if fails:
        print(f"  SELF-TEST FAILED: {len(fails)} check(s) -- " + "; ".join(fails))
    else:
        print("  SELF-TEST PASSED. The rig records, labels, names and logs correctly.")
    print(f"  artefacts left in {SELFTEST_OUT} (delete freely, this is not corpus)")
    print("=" * 78)
    return 1 if fails else 0


# ================================================================= main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="dictionary.py",
        description="ERAN's dictionary rig: a long hands-free reading session, "
                    "16 kHz mono, one session = one talker id, manifest as you go.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="USB microphones only. Bluetooth headset mics are refused by the "
               "device law and there is no flag to override that.")
    ap.add_argument("--list", default=str(ROOT / "lists" / "core31.txt"),
                    help="prompt file (TSV 'id<TAB>text<TAB>hint', or one word per line)")
    ap.add_argument("--takes", type=int, default=1, help="repeats of each prompt")
    ap.add_argument("--person", default="iddo", help="WHO is reading (a person, "
                    "stable across nights -- the talker tag is per SESSION)")
    ap.add_argument("--talker", default=None, help="force a talker id (t07, t08, ...)")
    ap.add_argument("--resume", default=None, metavar="TALKER",
                    help="continue a crashed sitting -- same talker, same session id")
    ap.add_argument("--mic", default=keshev_pinned_mic(),
                    help="pin part of a mic name, e.g. BRIO (default: whatever "
                         "KESHEV's own config/client.json pins)")
    ap.add_argument("--stage", default=str(STAGE_DEFAULT), help="corpus root")
    ap.add_argument("--id-prefix", default="w", help="prefix for auto-assigned ids")
    ap.add_argument("--allow-dev-fold", action="store_true",
                    help="permit a talker id that measure.py::is_dev() calls dev")
    ap.add_argument("--devices", action="store_true", help="list mics and exit")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the rig end to end with synthetic audio; no mic, "
                         "no person, no playback")
    ap.add_argument("--speech-rms", type=float, default=SPEECH_RMS_FLOOR,
                    help=f"corpus acceptance floor, rms (default {SPEECH_RMS_FLOOR} "
                         f"= the p10 of his measured real speech). Lower it only if "
                         f"you have measured that his voice really is quieter, and "
                         f"say so in the session notes")
    ap.add_argument("--smoke-seconds", type=float, default=0.0,
                    help="run the real session loop for N seconds and then stop as "
                         "if q were pressed -- a supervised smoke test of the live "
                         "path; point --stage somewhere throwaway when you use it")
    ap.add_argument("--dryrun", action="store_true",
                    help="open the real mic, measure the room, write NOTHING and "
                         "record nobody; proves the live path minus the person")
    args = ap.parse_args(argv)

    if args.takes < 1 or args.takes > 500:
        raise SystemExit("--takes must be 1..500")
    if args.devices:
        sel = report_devices(args.mic)
        return 0 if sel.state == kdevices.Selection.SELECTED else 2
    if args.selftest:
        return selftest(args)
    if args.dryrun:
        return run_dryrun(args)
    return run_live(args)


if __name__ == "__main__":
    sys.exit(main())

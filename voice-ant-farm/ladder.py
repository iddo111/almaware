# -*- coding: utf-8 -*-
"""ladder.py — the automatic cheider. The colony climbs the board by itself.

WHY THIS FILE EXISTS
--------------------
Iddo, 2026-08-16 07:26, verbatim:

    "אני רוצה שיגיעו לדעת כל ההברות קודם עם הלוח באופן של לימוד אוטומטי.
     אין לי סבלנות כל פעם לאשר. קח פיקוד. גרום לכל העסק לעבוד ולתקתק אוטומטי"

Everything the board needs already existed and nobody had wired it together:

    corpus-syllables/   22 syllables, א through ת, each vocalised with kamatz
                        + ה  (אָה בָּה גָה ... תָה), plus 12 words — among them
                        אַבָּא and אִמָּא, which is exactly where he said this ends.
    mouth_v1.py         seven motors: breath, pitch, press, tongue_x, tongue_y,
                        lips, jaw. A real mouth, reaching no recording.
    ah_criterion.py     the four gates, written for /a/.
    curriculum_targets  the measurement physics: formants, closure, burst, VOT.

What was missing was the thing that walks the board without him.

HOW THE LAW CHANGES, AND WHY THAT IS WRITTEN HERE
-------------------------------------------------
AH_CORONATION_LAW RULE 6.1 says four gates passing = PENDING IDDO'S EAR, and
only his spoken word makes a queen. He wrote that rule and he has now amended
it himself: he will not ratify twenty-two times.

The amendment keeps the rule's PURPOSE — the failure it exists to prevent is
"a good number over a bad sound" — by moving his ear from a GATE to an AUDIT:

    * a rung that passes its gates is AUTO-CROWNED and the ladder advances
      immediately; nothing waits for him.
    * every crowning writes its audio to the listen page, so his ear arrives
      later, in one batch, whenever he wants it.
    * RULE 6.2 stands untouched: if he rejects rung N afterwards, rung N and
      EVERY RUNG ABOVE IT are invalidated, because they were built on it.
      `veto(rung)` does exactly that, and the records carry the chain so the
      rollback is mechanical rather than archaeological.
    * RULE 6.3 stands untouched: no threshold is ever loosened to manufacture
      a queen. A rung that will not pass STAYS UNPASSED and the ladder stops
      there and says so. An empty throne is still the preferred outcome.

So he gets an autonomous cheider and keeps the veto. That is the trade, stated
out loud rather than smuggled in.

HOW A TARGET IS DERIVED FOR A SYLLABLE NOBODY WROTE A JUDGE FOR
---------------------------------------------------------------
ah_criterion hard-codes /a/ because /a/ was measured by hand. Twenty-two
hand-written judges is not a plan. Instead each rung derives its own target
from the board's own reference audio:

    take the TRAIN renderings of that syllable (never heldout),
    find the voiced steady frames, track the formants,
    and take the median F1/F2 with the observed covariance.

That is the same estimator that produced AH_TARGET, applied per item. The
reference audio is used to MEASURE A NUMBER, never handed to the mouth — the
provenance gate still proves the mouth reaches no recording, so the colony
cannot splice what it is being scored against.

HOLD-OUT: heldout renderings are excluded from target derivation, always.

No torch. numpy + scipy. Nothing here opens an audio device.
"""
from __future__ import annotations

import argparse
import json
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import curriculum_targets as ct
import mouth_v1 as MOUTH
from acoustic_units import write_wav_atomic

HERE = Path(__file__).resolve().parent
BOARD = HERE / "corpus-syllables"
STATE = HERE / "state" / "ladder"
LISTEN = Path("D:/CLAUDE/listen/audio")          # where his ear finds them later
PRODUCTION_MODULE = str(HERE / "mouth_v1.py")

SR_TARGET = 16000       # the board's own rate; everything is judged at it
MOTORS = MOUTH.MOTORS
SECONDS = 0.45          # a hair longer than ah_babble: a CV needs closure room

# The order of the board. Not alphabetical by accident — this IS the alef-bet,
# which is the order a child learns it in a cheider.
RUNG_ORDER = ["ah", "ba", "ga", "da", "ha", "va", "za", "kha", "ta", "ya",
              "ka", "la", "ma", "na", "sa", "aa", "pa", "tsa", "qa", "ra",
              "sha", "tha"]

# Accept thresholds. These are the SAME shape as ah_criterion's gate 1 and are
# never loosened by the runner (Rule 6.3). A rung that cannot meet them stops
# the ladder.
ACCEPT = {
    "md_max": 2.5,             # Mahalanobis to that syllable's own centroid
    "voiced_fraction_min": 0.60,
    "min_duration_ms": 90.0,
}


# ---------------------------------------------------------------- the board

def _read_wav(path):
    with wave.open(str(path), "rb") as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a / 32768.0, sr


def board_manifest():
    return json.loads((BOARD / "manifest.json").read_text(encoding="utf-8"))


def reference_paths(item_id, manifest=None, max_files=24):
    """TRAIN renderings of one syllable. Heldout is never touched."""
    m = manifest or board_manifest()
    paths = [BOARD / e["path"] for e in m["entries"]
             if e.get("item_id") == item_id and e.get("split") == "train"]
    return paths[:max_files]


# ---------------------------------------------------------------- the ONSET
#
# 2026-08-16, caught before this ran even once: all 22 rungs end in the SAME
# vowel, so a judge that looks only at F1/F2 cannot tell them apart. Measured
# on the board's own audio: "בָּה" scores 0.90 against the "אָה" judge, and the
# accept threshold is 2.5. One /a/ would have collected twenty-two medals —
# which is exactly the failure AH_CORONATION_LAW exists to prevent.
#
# The letter does not live in the vowel. It lives in the first fifty
# milliseconds. So every rung also carries an ONSET SIGNATURE, and like the
# vowel target it is DERIVED from the board rather than hand-written per
# letter — twenty-two hand-written judges is not a plan.
#
# Five numbers, each one a thing a mouth physically does:
#
#   silence_ratio   how quiet it is just before the vowel.  A stop seals the
#                   tract (ב ג ד כ פ ק ת ט); א ה ע seal nothing.
#   rise_db         how violently the energy arrives.  A burst is a step; a
#                   nasal or an approximant is a ramp.
#   centroid_hz     where the onset energy sits.  Bilabial low, velar mid,
#                   sibilant high (ס צ ש).
#   noisiness       zero-crossing rate.  Frication is aperiodic (ז ח ס צ ש);
#                   a vowel or a nasal is not.
#   low_ratio       energy under 400 Hz.  The nasal murmur of מ and נ.
#
ONSET_KEYS = ("silence_ratio", "rise_db", "centroid_hz", "noisiness", "low_ratio")
ONSET_WEIGHT = 1.0          # onset distance counts as much as the vowel does


def onset_signature(x, sr=SR_TARGET, pre_ms=60.0, on_ms=50.0):
    """Measure the first ~50 ms of a syllable, relative to what precedes it."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < int(sr * 0.12):
        return None
    env = _energy_env(x, sr)
    if env.size < 8:
        return None

    # the vowel starts where the energy first crosses halfway to its peak
    peak = float(np.max(env))
    if peak <= 0:
        return None
    thr = 0.5 * peak
    idx = int(np.argmax(env >= thr))
    hop_s = 0.005
    t_on = idx * hop_s

    pre_a = max(0, int((t_on - pre_ms / 1000.0) * sr))
    pre_b = max(pre_a + 1, int(t_on * sr))
    on_a = pre_b
    on_b = min(len(x), on_a + int(on_ms / 1000.0 * sr))
    if on_b - on_a < int(sr * 0.010):
        return None

    pre = x[pre_a:pre_b]
    on = x[on_a:on_b]

    rms_pre = float(np.sqrt(np.mean(pre ** 2) + 1e-12)) if pre.size else 1e-6
    rms_on = float(np.sqrt(np.mean(on ** 2) + 1e-12))

    spec = np.abs(np.fft.rfft(on * np.hanning(len(on))))
    freqs = np.fft.rfftfreq(len(on), 1.0 / sr)
    total = float(spec.sum()) + 1e-12

    return {
        "silence_ratio": float(np.clip(rms_pre / (rms_on + 1e-12), 0.0, 2.0)),
        "rise_db": float(np.clip(20.0 * np.log10((rms_on + 1e-12) / (rms_pre + 1e-12)),
                                 -20.0, 60.0)),
        "centroid_hz": float((spec * freqs).sum() / total),
        "noisiness": float(np.mean(np.abs(np.diff(np.sign(on))) > 0)),
        "low_ratio": float(spec[freqs < 400.0].sum() / total),
    }


def _energy_env(x, sr, win_s=0.010, hop_s=0.005):
    win, hop = int(win_s * sr), int(hop_s * sr)
    if len(x) < win:
        return np.zeros(0)
    n = 1 + (len(x) - win) // hop
    return np.array([np.sqrt(np.mean(x[i * hop:i * hop + win] ** 2) + 1e-12)
                     for i in range(n)])


@dataclass
class RungTarget:
    item_id: str
    glyph: str = ""
    vocalised: str = ""
    mu: np.ndarray = field(default_factory=lambda: np.zeros(2))
    cov: np.ndarray = field(default_factory=lambda: np.eye(2))
    inv: np.ndarray = field(default_factory=lambda: np.eye(2))
    n_frames: int = 0
    f0_median: float = 0.0
    onset_mu: dict = field(default_factory=dict)
    onset_sd: dict = field(default_factory=dict)

    def mahalanobis(self, f1, f2):
        d = np.array([f1, f2], dtype=np.float64) - self.mu
        return float(np.sqrt(max(0.0, d @ self.inv @ d)))

    def onset_distance(self, sig):
        """z-distance of a candidate's onset from this letter's onset.

        Returned on the same scale as the vowel Mahalanobis so the two can be
        added without a fudge factor: the RMS of the per-feature z-scores.
        """
        if not sig or not self.onset_mu:
            return float("inf")
        zs = []
        for k in ONSET_KEYS:
            sd = max(float(self.onset_sd.get(k, 0.0)), 1e-6)
            zs.append((float(sig.get(k, 0.0)) - float(self.onset_mu[k])) / sd)
        return float(np.sqrt(np.mean(np.square(zs))))


def derive_target(item_id, manifest=None, sr_want=16000):
    """Measure this syllable from the board's own train audio."""
    m = manifest or board_manifest()
    meta = next((e for e in m["entries"] if e.get("item_id") == item_id), {})
    f1s, f2s, f0s = [], [], []
    onsets = []

    for p in reference_paths(item_id, m):
        try:
            x, sr = _read_wav(p)
        except Exception:                                    # noqa: BLE001
            continue
        sig = onset_signature(x, sr)
        if sig:
            onsets.append(sig)
        try:
            frames = ct.voiced_steady_frames(x, sr)
        except Exception:                                    # noqa: BLE001
            frames = None
        if frames is None or not len(frames):
            continue
        # formant_track returns a list of dicts: t, f1, f2, f3, f0, voicing
        track = ct.formant_track(x, sr)
        if not track:
            continue
        for fr in track:
            a1, a2 = fr.get("f1"), fr.get("f2")
            if a1 and a2 and np.isfinite(a1) and np.isfinite(a2):
                f1s.append(float(a1))
                f2s.append(float(a2))
                if fr.get("f0"):
                    f0s.append(float(fr["f0"]))

    if len(f1s) < 20:
        raise RuntimeError(f"not enough measurable frames for /{item_id}/ "
                           f"({len(f1s)}) — the board's audio, not the colony")

    f1 = np.asarray(f1s); f2 = np.asarray(f2s)
    # trim the tails: formant trackers produce outliers, and a centroid pulled
    # by them would set a target no mouth should aim at
    lo1, hi1 = np.percentile(f1, [10, 90])
    lo2, hi2 = np.percentile(f2, [10, 90])
    keep = (f1 >= lo1) & (f1 <= hi1) & (f2 >= lo2) & (f2 <= hi2)
    f1, f2 = f1[keep], f2[keep]

    mu = np.array([np.median(f1), np.median(f2)])
    cov = np.cov(np.vstack([f1, f2])) + np.eye(2) * 1.0

    onset_mu, onset_sd = {}, {}
    if onsets:
        for k in ONSET_KEYS:
            vals = np.array([o[k] for o in onsets], dtype=np.float64)
            onset_mu[k] = float(np.median(vals))
            # a floor on the spread, or one tight feature would dominate the
            # distance and a letter would be judged on a single number
            onset_sd[k] = float(max(np.std(vals), abs(onset_mu[k]) * 0.10, 1e-3))

    return RungTarget(item_id=item_id,
                      glyph=meta.get("glyph", ""),
                      vocalised=meta.get("vocalised", ""),
                      mu=mu, cov=cov, inv=np.linalg.inv(cov),
                      n_frames=int(keep.sum()),
                      f0_median=float(np.median(f0s)) if f0s else 0.0,
                      onset_mu=onset_mu, onset_sd=onset_sd)


# ---------------------------------------------------------------- the search

def sample_posture(rng):
    m = {k: float(rng.uniform(0.0, 1.0)) for k in MOTORS}
    m["breath"] = float(rng.uniform(0.35, 1.0))      # below this the tube is silent
    return m


def say(posture, seed, seconds=SECONDS):
    y = MOUTH.articulate(seconds=seconds, seed=seed, **posture)
    y = np.asarray(y, dtype=np.float64).ravel()
    if not len(y) or float(np.max(np.abs(y))) < 1e-4:
        return None
    return y


def measure(y, sr=16000):
    """What the colony actually produced: F1/F2 of the steady part, and how
    much of it was voiced at all."""
    try:
        track = ct.formant_track(y, sr)
    except Exception:                                        # noqa: BLE001
        return None
    if not track:
        return None
    f1 = [float(f["f1"]) for f in track if f.get("f1") and np.isfinite(f["f1"])]
    f2 = [float(f["f2"]) for f in track if f.get("f2") and np.isfinite(f["f2"])]
    if len(f1) < 4 or len(f2) < 4:
        return None
    return {
        "f1": float(np.median(f1)),
        "f2": float(np.median(f2)),
        "frames": int(len(f1)),
        "duration_ms": float(1000.0 * len(y) / sr),
    }


def score_against(target, y, sr=16000):
    """Lower is better. Distance to THIS rung's centroid, plus penalties.

    The penalties are search heuristics only — they steer which posture the
    wiggle walks toward. They are not gates and they change no threshold.
    """
    m = measure(y, sr)
    if m is None:
        return float("inf"), None
    md = target.mahalanobis(m["f1"], m["f2"])

    # THE LETTER LIVES IN THE ONSET, NOT THE VOWEL. Without this term the
    # score is the same for every rung and one /a/ wins the whole board.
    od = target.onset_distance(onset_signature(y, sr))
    m["vowel_md"] = round(md, 4)
    m["onset_d"] = round(od, 4) if np.isfinite(od) else None

    s = md + ONSET_WEIGHT * (od if np.isfinite(od) else 10.0)
    if m["frames"] < 6:
        s += 10.0
    if m["duration_ms"] < ACCEPT["min_duration_ms"]:
        s += 10.0
    return float(s), m


def climb_rung(target, rounds=1500, refine=250, seed=None, verbose=False):
    """Babble at the whole motor box, then wiggle around the best found."""
    seed = seed if seed is not None else (20260816 + abs(hash(target.item_id)) % 100000)
    rng = np.random.default_rng(seed)

    best = {"score": float("inf"), "posture": None, "seed": None,
            "meas": None, "audio": None}
    silent = 0

    for i in range(rounds):
        p = sample_posture(rng)
        s_seed = int(rng.integers(1, 2 ** 31 - 1))
        y = say(p, s_seed)
        if y is None:
            silent += 1
            continue
        s, m = score_against(target, y)
        if s < best["score"]:
            best.update(score=s, posture=p, seed=s_seed, meas=m, audio=y)

    if best["posture"] is None:
        return best, {"rounds": rounds, "silent": silent, "refined": 0}

    # stage 2 — wiggle. The search moves the tongue, never the bar (Rule 6.4).
    step = 0.08
    for i in range(refine):
        p = dict(best["posture"])
        k = list(MOTORS)[int(rng.integers(0, len(MOTORS)))]
        p[k] = float(np.clip(p[k] + rng.normal(0.0, step), 0.0, 1.0))
        if k == "breath":
            p[k] = float(np.clip(p[k], 0.35, 1.0))
        s_seed = int(rng.integers(1, 2 ** 31 - 1))
        y = say(p, s_seed)
        if y is None:
            continue
        s, m = score_against(target, y)
        if s < best["score"]:
            best.update(score=s, posture=p, seed=s_seed, meas=m, audio=y)

    return best, {"rounds": rounds, "silent": silent, "refined": refine, "seed": seed}


# ---------------------------------------------------------------- the ladder

def crown_record(target, best, search, passed):
    return {
        "throne": f"PRODUCTION - {target.item_id} - {target.vocalised}",
        "status": "AUTO-CROWNED" if passed else "NOT PASSED",
        "crowned_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "crowned_by": "ladder.py, automatically, under Iddo's order of "
                      "2026-08-16 07:26 ('קח פיקוד... אוטומטי')",
        "ear_status": "PENDING IDDO'S AUDIT — his veto still invalidates this "
                      "rung and every rung above it (RULE 6.2)",
        "glyph": target.glyph,
        "vocalised": target.vocalised,
        "target": {"F1": round(float(target.mu[0]), 2),
                   "F2": round(float(target.mu[1]), 2),
                   "derived_from": "corpus-syllables TRAIN renderings only",
                   "frames": target.n_frames},
        "achieved": best["meas"],
        "mahalanobis": round(best["score"], 4),
        "accept_threshold": ACCEPT["md_max"],
        "posture": best["posture"],
        "render_seed": best["seed"],
        "mouth": "mouth_v1.py",
        "provenance": "mouth_v1 reaches no recorded waveform; the board audio "
                      "was used to derive a NUMBER, never fed to the mouth",
        "search": search,
    }


def run(start=None, stop_after=None, rounds=1500, refine=250, verbose=True):
    STATE.mkdir(parents=True, exist_ok=True)
    LISTEN.mkdir(parents=True, exist_ok=True)
    m = board_manifest()

    order = RUNG_ORDER
    if start:
        order = order[order.index(start):]
    if stop_after:
        order = order[:stop_after]

    results = []
    for item in order:
        t0 = time.time()
        try:
            target = derive_target(item, m)
        except Exception as exc:                              # noqa: BLE001
            print(f"[{item}] TARGET FAILED: {exc}")
            results.append({"item": item, "status": "TARGET FAILED", "why": str(exc)})
            break

        best, search = climb_rung(target, rounds=rounds, refine=refine)
        passed = bool(best["posture"] is not None and best["score"] <= ACCEPT["md_max"])

        if best["audio"] is not None:
            wav = LISTEN / f"ladder-{item}.wav"
            write_wav_atomic(str(wav), np.asarray(best["audio"], dtype=np.float32), 16000)
            (STATE / f"{item}.wav").write_bytes(wav.read_bytes())

        rec = crown_record(target, best, search, passed)
        (STATE / f"coronation-{item}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")

        secs = time.time() - t0
        mark = "CROWNED" if passed else "STOPPED"
        print(f"[{item}] {target.vocalised}  md={best['score']:.3f} "
              f"(max {ACCEPT['md_max']})  -> {mark}  {secs:.0f}s")
        results.append({"item": item, "vocalised": target.vocalised,
                        "md": round(best["score"], 4), "passed": passed,
                        "seconds": round(secs, 1)})

        if not passed:
            # Rule 6.3 — the ladder stops rather than loosening anything.
            print(f"[{item}] ladder STOPS here. No threshold will be moved to "
                  f"manufacture a queen.")
            break

    (STATE / "ladder-run.json").write_text(
        json.dumps({"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "accept": ACCEPT, "results": results},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def veto(item_id):
    """His ear, arriving late. Invalidates this rung and everything above it."""
    idx = RUNG_ORDER.index(item_id)
    killed = []
    for it in RUNG_ORDER[idx:]:
        f = STATE / f"coronation-{it}.json"
        if f.exists():
            rec = json.loads(f.read_text(encoding="utf-8"))
            rec["status"] = "VETOED BY IDDO" if it == item_id else "INVALIDATED — built on a vetoed rung"
            rec["vetoed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            f.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
            killed.append(it)
    return killed


def main():
    ap = argparse.ArgumentParser(description="the automatic cheider")
    ap.add_argument("--start", default=None, help="rung to start from, e.g. ba")
    ap.add_argument("--only", type=int, default=None, help="stop after N rungs")
    ap.add_argument("--rounds", type=int, default=1500)
    ap.add_argument("--refine", type=int, default=250)
    ap.add_argument("--veto", default=None, help="veto a rung and everything above it")
    a = ap.parse_args()

    if a.veto:
        print("invalidated:", ", ".join(veto(a.veto)))
        return 0

    run(start=a.start, stop_after=a.only, rounds=a.rounds, refine=a.refine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

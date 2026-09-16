# -*- coding: utf-8 -*-
"""ear_truth.py — does poly_hear actually HEAR polyphony, or does it just emit it?

לזכרו של לָאוֹר ז״ל.

THE SUSPICION THIS FILE EXISTS TO KILL
---------------------------------------
On eight real Darwish tracks, poly_hear reported simultaneous-pitch counts of
3.9-4.6 with a maximum of exactly 5 on every single track, and 99-100% of
sounding steps polyphonic. A number that pins to the ceiling on every input is
not a measurement, it is a constant. MAX_POLY is 4 lead picks plus 1 bass = 5.
So "harmony exists now" could be nothing but the picker taking its full
allowance every frame.

The only way to know is GROUND TRUTH: build audio whose notes we already know,
and score the ear against them.

    Score -> additive synth (known notes) -> poly_hear -> Score' -> compare

Two directions matter, and the second one is the one that catches the fraud:

  RECALL     given a real chord, does it find the notes?
  PRECISION  given ONE note, does it stay at one -- or invent a chord?

A mono test case that comes back with polyphony 4 proves the detector is
hallucinating, and no amount of good recall would redeem it.

The synth here is deliberately plain: a small harmonic stack with an
exponential decay, plus optional noise. It is NOT trying to sound like
psytrance. It is trying to be UNAMBIGUOUS, so that a miss is the detector's
fault and not the test's.
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

import poly_hear as PH
import poly_tok as PT
import roundtrip as RT

SR = PH.SR


def synth(score: PT.Score, harmonics=6, noise=0.0, seed=3) -> np.ndarray:
    """Score -> mono audio. Every note is a decaying harmonic stack."""
    rng = np.random.default_rng(seed)
    spb = 15.0 / max(score.bpm, 1e-6)                 # seconds per sixteenth
    n = int((score.n_steps + 4) * spb * SR)
    x = np.zeros(n)
    for note in score.notes:
        f0 = 440.0 * 2.0 ** ((note.midi - 69) / 12.0)
        i0 = int(note.step * spb * SR)
        ln = int(max(note.dur, 1) * spb * SR)
        t = np.arange(ln) / SR
        env = np.exp(-t / max(note.dur * spb * 0.7, 0.03))
        env *= np.minimum(1.0, t / 0.004 + 1e-9)      # 4 ms attack, no click
        sig = np.zeros(ln)
        for h in range(1, harmonics + 1):
            if f0 * h > SR / 2 - 100:
                break
            sig += (1.0 / h ** 1.3) * np.sin(2 * np.pi * f0 * h * t + rng.uniform(0, 6.28))
        seg = sig * env / harmonics
        x[i0:i0 + ln] += seg[: max(0, min(ln, n - i0))]
    # drums: a click + a low thump, so tempo/grid detection has something to lock to
    for d in score.drums:
        i0 = int(d.step * spb * SR)
        ln = int(0.09 * SR)
        t = np.arange(ln) / SR
        amp = (0.35, 0.6, 0.9)[d.vel]
        if d.which == 0:
            s = np.sin(2 * np.pi * (150 * np.exp(-t / 0.012) + 48) * t) * np.exp(-t / 0.05)
        elif d.which == 1:
            s = rng.standard_normal(ln) * np.exp(-t / 0.03) * 0.5
        else:
            s = rng.standard_normal(ln) * np.exp(-t / 0.008) * 0.3
        s = s * amp
        x[i0:i0 + ln] += s[: max(0, min(ln, n - i0))]
    if noise > 0:
        x += rng.standard_normal(n) * noise
    m = np.abs(x).max()
    return x / m * 0.9 if m > 0 else x


def cases() -> list[tuple[str, PT.Score, str]]:
    """Every case states what a correct ear must report. bars are 16 steps."""
    out = []

    def kick(sc, bars):
        for b in range(bars):
            for k in range(4):
                sc.drums.append(PT.Drum(b * 16 + k * 4, 0, 2))
            for k in range(8):
                sc.drums.append(PT.Drum(b * 16 + k * 2 + 1, 2, 0))

    # --- MONO: the fraud detector. Correct answer is polyphony 1. ---
    s = PT.Score(143.55, 0, 128)
    for i in range(0, 128, 2):
        s.notes.append(PT.Note(i, 36 + (i // 16) % 5, 2))
    kick(s, 8)
    out.append(("mono_bassline", s, "poly must be 1"))

    s = PT.Score(143.55, 0, 128)
    for i in range(0, 128, 4):
        s.notes.append(PT.Note(i, 64 + (i // 8) % 7, 4))
    kick(s, 8)
    out.append(("mono_lead", s, "poly must be 1"))

    # --- REAL POLYPHONY: recall test. ---
    s = PT.Score(143.55, 0, 128)
    for b in range(8):
        for m in (52, 55, 59):
            s.notes.append(PT.Note(b * 16, m, 16))
    kick(s, 8)
    out.append(("triad_52_55_59", s, "poly must be 3"))

    s = PT.Score(143.55, 0, 128)
    for b in range(8):
        for m in (48, 52, 55, 59):        # C E G B -- four DISTINCT pitch classes
            s.notes.append(PT.Note(b * 16, m, 16))
    kick(s, 8)
    out.append(("four_note_chord", s, "poly must be 4"))

    # --- THE REAL SHAPE OF PSYTRANCE: bass roll under a held chord. ---
    s = PT.Score(143.55, 0, 128)
    for i in range(128):
        if i % 4:
            s.notes.append(PT.Note(i, 36, 1))
    for b in range(8):
        for m in (60, 64, 67):
            s.notes.append(PT.Note(b * 16, m, 16))
    kick(s, 8)
    out.append(("bass_roll_plus_triad", s, "poly must be 4 (1 bass + 3 lead)"))

    # --- SILENCE under drums: correct answer is 0 pitched notes. ---
    s = PT.Score(143.55, 0, 128)
    kick(s, 8)
    out.append(("drums_only", s, "poly must be 0"))
    return out


def score_pitches(sc: PT.Score, n_steps: int) -> list[set]:
    """Which pitch classes sound at each step. Register is not scored: the ear
    is allowed to hear a note an octave off and still have heard the harmony."""
    out = [set() for _ in range(n_steps + 1)]
    for n in sc.notes:
        for s in range(n.step, min(n.step + n.dur, n_steps + 1)):
            out[s].add(n.midi % 12)
    return out


def evaluate(truth: PT.Score, heard: PT.Score) -> dict:
    n = min(truth.n_steps, heard.n_steps)
    if n <= 0:
        return {"error": "no overlap"}
    T = score_pitches(truth, n)
    H = score_pitches(heard, n)
    tp = fp = fn = 0
    poly_t, poly_h = [], []
    for s in range(n):
        tp += len(T[s] & H[s])
        fp += len(H[s] - T[s])
        fn += len(T[s] - H[s])
        poly_t.append(len(T[s]))
        poly_h.append(len(H[s]))
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    ht, hh = RT.pc_hist(truth), RT.pc_hist(heard)
    return {
        "pc_precision": round(prec, 4),
        "pc_recall": round(rec, 4),
        "pc_f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
        "poly_truth_mean": round(float(np.mean(poly_t)), 3),
        "poly_heard_mean": round(float(np.mean(poly_h)), 3),
        "poly_truth_max": int(np.max(poly_t)),
        "poly_heard_max": int(np.max(poly_h)),
        "poly_err_mean": round(float(np.mean(np.abs(np.array(poly_h) - np.array(poly_t)))), 3),
        "pc_hist_cos": round(RT.cosine(ht, hh), 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--noise", type=float, default=0.0)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "ear_truth_report.json"))
    ap.add_argument("--wav-dir", default=None)
    a = ap.parse_args()

    rows = []
    for name, sc, expect in cases():
        sc = sc.normalised()
        x = synth(sc, noise=a.noise)
        if a.wav_dir:
            os.makedirs(a.wav_dir, exist_ok=True)
            import wave
            with wave.open(os.path.join(a.wav_dir, name + ".wav"), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
        import tempfile, subprocess, wave
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "t.wav")
            with wave.open(p, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
            heard = PH.hear(p)
        r = {"case": name, "expect": expect, "noise": a.noise}
        r.update(evaluate(sc, heard))
        rows.append(r)
        print(f"{name:24s} {expect:34s} "
              f"polyT={r['poly_truth_mean']:5.2f} polyH={r['poly_heard_mean']:5.2f} "
              f"maxT={r['poly_truth_max']} maxH={r['poly_heard_max']} "
              f"P={r['pc_precision']:.3f} R={r['pc_recall']:.3f} F1={r['pc_f1']:.3f} "
              f"cos={r['pc_hist_cos']:.3f}", flush=True)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

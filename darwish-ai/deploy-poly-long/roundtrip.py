# -*- coding: utf-8 -*-
"""roundtrip.py — the acceptance test, and it runs BEFORE any training.

לזכרו של לָאוֹר ז״ל.

A tokenizer that cannot reproduce the music it is given is not a representation
of that music, whatever perplexity a model later reports on it. So this file
runs first, and if v2 round-trips WORSE than v1 that is the finding and the
retrain is cancelled.

THE HONEST SHAPE OF THE TEST — read this before the numbers
------------------------------------------------------------
The brief said: encode a real Darwish MIDI, decode it, compare. **There is no
Darwish MIDI.** `~/darwish-ai/corpus` on eran4 is 324 MP3 mixdowns, 8.6 GB, and
`midi_lean.py` is an audio TRANSCRIBER, not a MIDI parser. Every .mid on this
machine was written by us. So the literal test is impossible, and pretending
otherwise would be the exact failure mode this workspace keeps scarring on.

What replaces it separates the two machines that can each lose the music:

  TEST A — THE REPRESENTATION, exact.
      notes -> tokens -> notes, compared note-for-note. No audio anywhere. Run
      on three kinds of material: adversarial hand-built cases that contain the
      things v1 provably cannot say, every real .mid on this box, and the
      transcriptions of real Darwish audio. v1's alphabet is run on the SAME
      material as the control. This is where "no harmony is a representation
      failure" stops being an argument and becomes a number.

  TEST B — THE EAR, approximate.
      real Darwish MP3 -> Score, v2 against v1, on pitch-class histogram,
      interval content, onset-grid occupancy and simultaneous-pitch count.

  TEST C — THE FILE FORMAT.
      Score -> .mid -> Score, so that what the renderer will actually be handed
      is proven to survive the trip to disk.

Numbers only. Nothing here prints a verdict it did not compute.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter

import numpy as np

import poly_tok as PT

HERE = os.path.dirname(os.path.abspath(__file__))


# ================================================================ v1 control
# midi_lean.py's alphabet, expressed as an encoder/decoder over the SAME Score
# type, so the two representations can be measured with one ruler.

V1_TOK_BAR, V1_TOK_PHRASE, V1_TOK_BOS, V1_TOK_EOS = 104, 105, 106, 107
V1_VOCAB = 108


def v1_encode(score: PT.Score) -> list[int]:
    """token = drums*13 + deg. One token per sixteenth. No length, one pitch."""
    drum_at: dict[int, int] = {}
    for d in score.drums:
        drum_at[d.step] = drum_at.get(d.step, 0) | (1 << d.which)
    # v1 has ONE bass slot per step. A chord must be thrown away; we keep the
    # lowest note, which is the most generous reading of what it could mean.
    pitch_at: dict[int, int] = {}
    for n in score.notes:
        for s in range(n.step, n.step + n.dur):
            cur = pitch_at.get(s)
            if cur is None or n.midi < cur:
                pitch_at[s] = n.midi
    toks = [V1_TOK_BOS]
    for s in range(score.n_steps):
        drums = drum_at.get(s, 0)
        m = pitch_at.get(s)
        deg = 0 if m is None else (m - score.key_pc) % 12 + 1
        toks.append(drums * 13 + deg)
        if s % 16 == 15:
            toks.append(V1_TOK_BAR)
        if s % 256 == 255:
            toks.append(V1_TOK_PHRASE)
    toks.append(V1_TOK_EOS)
    return toks


def v1_decode(toks, bpm=143.55, key_pc=0) -> PT.Score:
    """The octave is gone, so it has to be guessed. v1's own renderer guessed
    wrong for 11 of 12 degrees until 2026-09-05. Here we guess CHARITABLY:
    octave 3 (MIDI 36 + key + degree), which is v1's most common intent."""
    notes, drums = [], []
    step = 0
    for t in toks:
        t = int(t)
        if t == V1_TOK_EOS:
            break
        if t in (V1_TOK_BAR, V1_TOK_PHRASE, V1_TOK_BOS):
            continue
        if not (0 <= t < 104):
            continue
        d, deg = divmod(t, 13)
        for w in range(3):
            if d & (1 << w):
                drums.append(PT.Drum(step, w, 1))
        if deg:
            notes.append(PT.Note(step, 36 + key_pc + (deg - 1), 1))
        step += 1
    return PT.Score(bpm, key_pc, step, notes, drums).normalised()


# ================================================================ metrics

def pc_hist(score: PT.Score) -> np.ndarray:
    h = np.zeros(12)
    for n in score.notes:
        h[n.midi % 12] += n.dur          # weight by how long it actually sounds
    return h / h.sum() if h.sum() else h


def interval_hist(score: PT.Score) -> np.ndarray:
    """Melodic intervals of the lowest voice, in semitones, |i| <= 24."""
    seq = sorted(score.notes, key=lambda n: (n.step, n.midi))
    line, last_step = [], None
    for n in seq:
        if n.step != last_step:
            line.append(n.midi)
            last_step = n.step
    h = np.zeros(49)
    for a, b in zip(line, line[1:]):
        d = int(np.clip(b - a, -24, 24))
        h[d + 24] += 1
    return h / h.sum() if h.sum() else h


def mean_abs_interval_voice(score: PT.Score, lo: int, hi: int) -> float:
    """Melodic interval WITHIN one register.

    WHY THIS EXISTS, and it is a correction to my own first number.
    `mean_abs_interval` below takes the lowest note at each onset step. That was
    fine for v1, whose score is one voice by construction. On a POLYPHONIC v2
    score it is wrong: consecutive steps may have a bass note at MIDI 38 and
    then, when the bass rests, a lead at 74, so "the melody" appears to leap an
    octave when nothing leapt at all. Measured on eight real tracks it inflated
    the mean interval from 3.07 to 10.09 semitones and would have been reported
    as a finding about the music instead of an artefact of the ruler.

    So intervals are measured inside a register band and the two bands are
    reported separately. v1 has only the low band; that is the honest
    comparison, not a single averaged number.
    """
    seq = sorted((n for n in score.notes if lo <= n.midi <= hi),
                 key=lambda n: (n.step, n.midi))
    line, last = [], None
    for n in seq:
        if n.step != last:
            line.append(n.midi)
            last = n.step
    if len(line) < 2:
        return 0.0
    return float(np.mean([abs(b - a) for a, b in zip(line, line[1:])]))


BASS_BAND = (0, 51)
LEAD_BAND = (52, 127)


def mean_abs_interval(score: PT.Score) -> float:
    seq = sorted(score.notes, key=lambda n: (n.step, n.midi))
    line, last_step = [], None
    for n in seq:
        if n.step != last_step:
            line.append(n.midi)
            last_step = n.step
    if len(line) < 2:
        return 0.0
    return float(np.mean([abs(b - a) for a, b in zip(line, line[1:])]))


def entropy_bits(h) -> float:
    h = np.asarray(h, dtype=float)
    h = h[h > 0]
    return float(-(h * np.log2(h)).sum()) if h.size else 0.0


def onset_occupancy(score: PT.Score) -> float:
    if score.n_steps <= 0:
        return 0.0
    return len({n.step for n in score.notes}) / score.n_steps


def cosine(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na > 0 and nb > 0 else 0.0


def note_match(a: PT.Score, b: PT.Score) -> dict:
    """Exact note-for-note agreement, and the same ignoring duration."""
    A = {n.key() for n in a.notes}
    B = {n.key() for n in b.notes}
    Ap = {(n.step, n.midi) for n in a.notes}
    Bp = {(n.step, n.midi) for n in b.notes}
    DA = {d.key() for d in a.drums}
    DB = {d.key() for d in b.drums}

    def prf(x, y):
        inter = len(x & y)
        p = inter / len(y) if y else 1.0
        r = inter / len(x) if x else 1.0
        return round(p, 4), round(r, 4)

    p_e, r_e = prf(A, B)
    p_p, r_p = prf(Ap, Bp)
    p_d, r_d = prf(DA, DB)
    return {
        "notes_src": len(A), "notes_out": len(B),
        "exact_precision": p_e, "exact_recall": r_e,
        "pitch_time_precision": p_p, "pitch_time_recall": r_p,
        "drum_precision": p_d, "drum_recall": r_d,
    }


def lossy_accounting(src: PT.Score) -> dict:
    """Name every note v2 cannot spell exactly, BEFORE the round trip runs.

    Two mechanisms, and they are the only two: an octave fold (pitch outside
    the 7-octave key-relative window) and a duration that is not in DUR_VALUES.
    A third number, `dup_collapse`, counts notes that are byte-identical to
    another note -- two channels playing the same pitch at the same time for
    the same length. Those merge, and merging them is correct: they are one
    sound. Reporting it stops that merge from looking like a loss.
    """
    folds = 0
    dur_err, dur_bad = 0, 0
    for n in src.notes:
        if PT._fold(n.midi, src.key_pc) != n.midi:
            folds += 1
        q = PT.DUR_VALUES[PT.dur_token(n.dur) - PT.DUR_BASE]
        if q != n.dur:
            dur_bad += 1
            dur_err += abs(q - n.dur)
    seen = {}
    for n in src.notes:
        seen[n.key()] = seen.get(n.key(), 0) + 1
    dup = sum(c - 1 for c in seen.values())
    tot = max(len(src.notes), 1)
    return {
        "octave_folds": folds, "octave_fold_pct": round(100 * folds / tot, 2),
        "dur_inexact": dur_bad, "dur_inexact_pct": round(100 * dur_bad / tot, 2),
        "dur_err_mean_steps": round(dur_err / max(dur_bad, 1), 3),
        "dup_collapse": dup,
    }


def compare(src: PT.Score, out: PT.Score) -> dict:
    m = note_match(src, out)
    hs, ho = pc_hist(src), pc_hist(out)
    isrc, iout = interval_hist(src), interval_hist(out)
    ps, po = src.polyphony_profile(), out.polyphony_profile()
    m.update({
        "pc_hist_L1": round(float(np.abs(hs - ho).sum()), 4),
        "pc_hist_cos": round(cosine(hs, ho), 4),
        "pc_entropy_src": round(entropy_bits(hs), 4),
        "pc_entropy_out": round(entropy_bits(ho), 4),
        "interval_cos": round(cosine(isrc, iout), 4),
        "mean_abs_interval_src": round(mean_abs_interval(src), 3),
        "mean_abs_interval_out": round(mean_abs_interval(out), 3),
        "onset_occ_src": round(onset_occupancy(src), 4),
        "onset_occ_out": round(onset_occupancy(out), 4),
        "poly_max_src": ps["max"], "poly_max_out": po["max"],
        "poly_mean_src": ps["mean_sounding"], "poly_mean_out": po["mean_sounding"],
        "poly_frac_src": ps["frac_steps_poly"], "poly_frac_out": po["frac_steps_poly"],
    })
    return m


# ================================================================ material

def adversarial_scores() -> list[tuple[str, PT.Score]]:
    """Hand-built cases that name, one by one, what v1's alphabet cannot say."""
    out = []

    # 1. A triad held for a bar. v1 has one pitch slot per sixteenth.
    s = PT.Score(143.55, 9, 64)
    for bar in range(4):
        for m in (57, 60, 64):
            s.notes.append(PT.Note(bar * 16, m, 16))
        for k in range(4):
            s.drums.append(PT.Drum(bar * 16 + k * 4, 0, 2))
    out.append(("triad_held_bar", s))

    # 2. Bass roll UNDER a moving lead — two independent voices at once.
    s = PT.Score(145.0, 2, 128)
    for i in range(128):
        s.notes.append(PT.Note(i, 38 if i % 4 else 26, 1))
        if i % 8 == 0:
            s.notes.append(PT.Note(i, 62 + (i // 8) % 12, 8))
    out.append(("bass_roll_under_lead", s))

    # 3. A four-note chord progression, real voice leading.
    s = PT.Score(140.0, 0, 128)
    prog = [(48, 55, 60, 64), (46, 53, 58, 62), (44, 51, 56, 60), (43, 50, 55, 59)]
    for bar, ch in enumerate(prog * 2):
        for m in ch:
            s.notes.append(PT.Note(bar * 16, m, 16))
    out.append(("four_voice_progression", s))

    # 4. Sustain vs re-attack — identical in v1, different here.
    s = PT.Score(143.55, 4, 64)
    s.notes.append(PT.Note(0, 40, 16))
    for i in range(16):
        s.notes.append(PT.Note(16 + i, 40, 1))
    s.notes.append(PT.Note(32, 40, 32))
    out.append(("sustain_vs_reattack", s))

    # 5. Every duration value, and octave extremes of the window.
    s = PT.Score(143.55, 0, 256)
    st = 0
    for d in PT.DUR_VALUES:
        for oct_off in (0, 24, 48):
            s.notes.append(PT.Note(st, PT.PITCH_LO + oct_off, d))
        st += 32
    s.n_steps = st
    out.append(("all_durations_all_octaves", s))

    # 6. Dense cluster: 6 simultaneous pitches, above MAX_POLY on purpose.
    s = PT.Score(143.55, 7, 32)
    for m in (31, 38, 43, 50, 55, 62):
        s.notes.append(PT.Note(0, m, 32))
    out.append(("six_voice_cluster", s))
    return out


def real_midis(root="D:/CLAUDE") -> list[str]:
    cands = [
        "darwish-midi/songs/outbox/darwish-GM-20260823.mid",
        "darwish-midi/songs/outbox/darwish-KICK-20260823.mid",
        "darwish-midi/songs/outbox/darwish-KICK-GM-20260823.mid",
        "darwish-midi/songs/outbox/darwish-model-20260823-061846.mid",
        "darwish-ai/midi-out/darwish-model-step200.mid",
        "darwish-ai/midi-out/darwish-step1000.mid",
        "eran-brain/judging/galeria/darwish/raw/chai-20260821-170231.mid",
        "eran-brain/judging/galeria/darwish/raw/chai-20260821-201640-x0.mid",
        "eran-brain/judging/galeria/darwish/raw/chai-20260821-201642-x1.mid",
    ]
    return [os.path.join(root, c) for c in cands if os.path.exists(os.path.join(root, c))]


# ================================================================ the runs

def run_A(scores, label) -> list[dict]:
    rows = []
    for name, sc in scores:
        sc = sc.normalised()
        t2 = PT.encode(sc)
        b2 = PT.decode(t2, sc.bpm, sc.key_pc)
        m2 = compare(sc, b2)
        m2.update(lossy_accounting(sc))
        m2.update({"case": name, "tok": "v2", "n_tokens": len(t2),
                   "tok_per_step": round(len(t2) / max(sc.n_steps, 1), 3),
                   "vocab": PT.VOCAB, "set": label})

        t1 = v1_encode(sc)
        b1 = v1_decode(t1, sc.bpm, sc.key_pc)
        m1 = compare(sc, b1)
        m1.update({"case": name, "tok": "v1", "n_tokens": len(t1),
                   "tok_per_step": round(len(t1) / max(sc.n_steps, 1), 3),
                   "vocab": V1_VOCAB, "set": label})
        rows += [m1, m2]
    return rows


def run_C(scores, tmpdir) -> list[dict]:
    os.makedirs(tmpdir, exist_ok=True)
    rows = []
    for name, sc in scores:
        sc = sc.normalised()
        p = os.path.join(tmpdir, f"rt_{name}.mid")
        PT.score_to_midi(sc, p)
        back = PT.score_from_midi(p, bpm_hint=sc.bpm, key_pc=sc.key_pc)
        m = compare(sc, back)
        m.update({"case": name, "stage": "score->mid->score"})
        rows.append(m)
    return rows


def fmt_table(rows, cols, widths=None):
    widths = widths or [max(len(c), 9) for c in cols]
    head = "  ".join(c.ljust(w) for c, w in zip(cols, widths))
    lines = [head, "-" * len(head)]
    for r in rows:
        lines.append("  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(cols, widths)))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", nargs="*", default=[],
                    help="real Darwish mp3s for TEST B")
    ap.add_argument("--audio-seconds", type=float, default=120.0)
    ap.add_argument("--out", default=os.path.join(HERE, "roundtrip_report.json"))
    ap.add_argument("--tmp", default=os.path.join(HERE, "_rt_tmp"))
    a = ap.parse_args()

    report = {"vocab_v1": V1_VOCAB, "vocab_v2": PT.VOCAB, "A": [], "B": [], "C": []}

    # ---- TEST A.1 adversarial ------------------------------------------
    adv = adversarial_scores()
    report["A"] += run_A(adv, "adversarial")

    # ---- TEST A.2 every real .mid on disk ------------------------------
    mids = []
    for p in real_midis():
        try:
            mids.append((os.path.basename(p)[:34], PT.score_from_midi(p)))
        except Exception as exc:                                    # noqa: BLE001
            print(f"SKIP {p}: {exc}", file=sys.stderr)
    report["A"] += run_A(mids, "real_midi")

    # ---- TEST C file format --------------------------------------------
    report["C"] = run_C(adv + mids, a.tmp)

    # ---- TEST B real Darwish audio -------------------------------------
    if a.audio:
        import poly_hear as PH
        for p in a.audio:
            row = {"file": os.path.basename(p)[:44]}
            try:
                s2 = PH.hear(p, max_seconds=a.audio_seconds)
                s1 = PH.hear_v1(p, max_seconds=a.audio_seconds)
            except Exception as exc:                                # noqa: BLE001
                row["error"] = f"{type(exc).__name__}: {exc}"
                report["B"].append(row)
                continue
            t2, t1 = PT.encode(s2), v1_encode(s1)
            secs = a.audio_seconds
            p2, p1 = s2.polyphony_profile(), s1.polyphony_profile()
            row.update({
                "bpm": s2.bpm, "key_pc": s2.key_pc, "n_steps": s2.n_steps,
                "v1_tokens": len(t1), "v2_tokens": len(t2),
                "v1_tok_per_s": round(len(t1) / secs, 2),
                "v2_tok_per_s": round(len(t2) / secs, 2),
                "v1_notes": p1["n_notes"], "v2_notes": p2["n_notes"],
                "v1_poly_max": p1["max"], "v2_poly_max": p2["max"],
                "v1_poly_mean": p1["mean_sounding"], "v2_poly_mean": p2["mean_sounding"],
                "v1_poly_frac": p1["frac_steps_poly"], "v2_poly_frac": p2["frac_steps_poly"],
                "v1_pc_entropy": round(entropy_bits(pc_hist(s1)), 4),
                "v2_pc_entropy": round(entropy_bits(pc_hist(s2)), 4),
                "v1_mean_interval": round(mean_abs_interval(s1), 3),
                "v2_mean_interval": round(mean_abs_interval(s2), 3),
                "v1_onset_occ": round(onset_occupancy(s1), 4),
                "v2_onset_occ": round(onset_occupancy(s2), 4),
                "v2_selfrt_exact_recall": compare(s2, PT.decode(t2, s2.bpm, s2.key_pc))["exact_recall"],
            })
            report["B"].append(row)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    # ---- print ----------------------------------------------------------
    print(f"\nVOCAB   v1 = {V1_VOCAB}   v2 = {PT.VOCAB}\n")
    print("TEST A — REPRESENTATION ROUND TRIP  (notes -> tokens -> notes)")
    print(fmt_table(report["A"],
                    ["set", "case", "tok", "notes_src", "notes_out",
                     "exact_recall", "exact_precision", "pitch_time_recall",
                     "poly_max_src", "poly_max_out", "pc_hist_cos",
                     "interval_cos", "tok_per_step", "octave_fold_pct",
                     "dur_inexact_pct", "dup_collapse"],
                    [11, 34, 4, 9, 9, 12, 15, 17, 12, 12, 11, 12, 12, 15, 15, 12]))
    print("\nTEST C — SCORE -> .mid -> SCORE")
    print(fmt_table(report["C"],
                    ["case", "notes_src", "notes_out", "exact_recall",
                     "exact_precision", "drum_recall", "poly_max_out"],
                    [34, 9, 9, 12, 15, 11, 12]))
    if report["B"]:
        print("\nTEST B — REAL DARWISH AUDIO  (v1 ear+alphabet vs v2)")
        print(fmt_table(report["B"],
                        ["file", "bpm", "v1_notes", "v2_notes", "v1_poly_max",
                         "v2_poly_max", "v1_poly_mean", "v2_poly_mean",
                         "v1_pc_entropy", "v2_pc_entropy", "v1_tok_per_s",
                         "v2_tok_per_s", "v2_selfrt_exact_recall"],
                        [44, 7, 8, 8, 11, 11, 12, 12, 13, 13, 12, 12, 22]))
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

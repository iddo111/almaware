#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lessons.py -- the TEACHER's lesson corpus: >= 12 VERIFIED variants per Hebrew syllable, each one a
different way of saying the same syllable inside the manual's measured windows (f0, durations, degree
of constriction, burst gain), each rendered on mouth2 and passed by ruler.judge (the 09-02 rulers + the
verifiers' objections). Every attempt -- pass or fail, with the reason -- goes to lessons/ledger.jsonl.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

claude-cli-MOREH 2026-09-03 (Iddo's order 09:19). Files: lessons/CLAUDE-<syl>-v<nn>.wav + .json
(Label Law: the speaker's name is in the file name; these are the TEACHER's sounds, never ERAN's).
    python3 lessons.py            # all 24 syllables
    python3 lessons.py ka qa tza  # a subset
"""
import json, os, sys, time, wave
import numpy as np
import ruler as R
import gesture as G

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lessons"); os.makedirs(OUT, exist_ok=True)
LEDGER = os.path.join(OUT, "ledger.jsonl")
TARGET = 12          # verified variants wanted per syllable
SPARE = 2            # keep going a little past the target when it is cheap
MAX_ATTEMPTS = int(os.environ.get("MOREH_MAX_ATTEMPTS", "90"))

# ---------------------------------------------------------------- the bases (the 21 of 09-02 + the 3 fixed today)
BASE = {s: dict(R.BASE_0902[s]) for s in R.SYLS}
# ka / qa: the VOT gap is a brief UVULAR FRICATION at the place of the stop (gap_pos = c_pos, channel 0.2-0.35,
# voicing 0) -- measured 09-03 with probe_fix.py: 27/432 and 11/216 designs pass ruler.judge incl. the strict
# voiceless-gap rule; the 09-02 design (open tube, voicing 0.15, tenseness 0.25) never does.
BASE["ka"].update(gap_pos=0.49, gap_area=0.25, gap_voi=0.0, gap_ten=0.6, d_gap=0.035, gain=6.0, d_cons=0.085, c_pos=0.49)
BASE["qa"].update(gap_pos=0.485, gap_area=0.25, gap_voi=0.0, gap_ten=0.6, d_gap=0.035, gain=6.0, d_cons=0.085, c_pos=0.485)
# tza: devoice the last 10 ms of the closure (trans_voi 0) and release straight into a 0.20-0.24 channel at
# 0.85-0.88 with a short glide (0.1) -- the voiced blip the verifier heard was the 28 ms glide from a voiced
# seal through the dead zone. probe_tza.py / probe_tza2.py.
BASE["tza"].update(trans_voi=0.0, glide=0.1, gap_area=0.20, gap_pos=0.84, d_gap=0.07, gain=6.0, d_cons=0.065, d_trans=0.01)   # probe_tza2: 447/2880 pass in this region

# ---------------------------------------------------------------- the windows (MOUTH-MANUAL ranges)
F0 = ("f0", 98.0, 112.0)
VOW = ("d_vowel", 0.30, 0.40)
GL = ("glide", 0.30, 0.40)
def W(*items): return [tuple(i) for i in items]
WINDOWS = {
    "a":   W(("d_vowel", 0.50, 0.70), ("ten", 0.50, 0.70), ("f0", 101.0, 109.0), GL),
    "aya": W(("d_pre", 0.20, 0.30), ("d_cons", 0.07, 0.11), ("d_vowel", 0.28, 0.38), ("glide", 0.02, 0.03), F0),
    "ba":  W(("c_pos", 0.96, 0.99), ("d_cons", 0.06, 0.10), ("d_trans", 0.01, 0.02), ("gain", 6.0, 12.0), VOW, GL, F0),
    "pa":  W(("c_pos", 0.96, 0.99), ("d_cons", 0.06, 0.10), ("d_trans", 0.01, 0.02), ("d_gap", 0.03, 0.05), ("gain", 6.0, 12.0), VOW, GL, F0),
    "ma":  W(("c_pos", 0.96, 0.99), ("velum", 0.50, 0.80), ("d_cons", 0.08, 0.20), ("d_trans", 0.015, 0.025), VOW, GL, F0),
    "va":  W(("c_pos", 0.96, 0.97), ("c_area", 0.10, 0.12), ("voi", 0.10, 0.16), ("ten", 0.25, 0.30), ("d_cons", 0.09, 0.13), VOW, GL, F0),   # first run 3/90: wider voi/c_area lose the >2k noise
    "fa":  W(("c_pos", 0.97, 1.00), ("c_area", 0.12, 0.18), ("d_cons", 0.08, 0.13), VOW, GL, F0),
    "wa":  W(("c_pos", 0.98, 1.00), ("c_area", 0.12, 0.20), ("d_cons", 0.06, 0.10), ("d_trans", 0.015, 0.025), ("glide", 0.45, 0.60), VOW, F0),
    "da":  W(("c_pos", 0.94, 0.95), ("d_cons", 0.06, 0.10), ("d_trans", 0.01, 0.02), ("gain", 6.0, 10.0), VOW, GL, F0),
    "ta":  W(("c_pos", 0.945, 0.95), ("d_cons", 0.07, 0.09), ("d_trans", 0.012, 0.018), ("d_gap", 0.035, 0.045), ("gap_area", 0.75, 0.85), ("d_bridge", 0.025, 0.035), ("gain", 6.0, 8.0), VOW, GL, F0),   # first run 11/90: wide gap_area rings periodically
    "na":  W(("c_pos", 0.90, 0.95), ("velum", 0.50, 0.80), ("d_cons", 0.08, 0.20), ("d_trans", 0.015, 0.025), VOW, GL, F0),
    "la":  W(("c_pos", 0.86, 0.90), ("c_area", 0.30, 0.50), ("d_cons", 0.07, 0.10), ("d_trans", 0.015, 0.025), VOW, GL, F0),
    "sa":  W(("c_pos", 0.90, 0.93), ("c_area", 0.10, 0.15), ("d_cons", 0.08, 0.13), VOW, GL, F0),
    "za":  W(("c_pos", 0.90, 0.93), ("c_area", 0.10, 0.15), ("voi", 0.25, 0.45), ("ten", 0.25, 0.40), ("d_cons", 0.08, 0.13), VOW, GL, F0),
    "sha": W(("c_pos", 0.76, 0.82), ("c_area", 0.15, 0.20), ("d_cons", 0.08, 0.13), VOW, GL, F0),
    "ra":  W(("d_pre", 0.06, 0.10), ("c_pos", 0.93, 0.95), ("d_cons", 0.025, 0.035), ("glide", 0.45, 0.55), VOW, F0),
    "ga":  W(("c_pos", 0.495, 0.505), ("d_cons", 0.07, 0.10), ("d_trans", 0.012, 0.018), ("gain", 6.0, 7.0), VOW, GL, F0),   # first run 9/90: burst centroid leaves 850-1050 off 0.50
    "ka":  W(("c_pos", 0.49, 0.51), ("d_cons", 0.08, 0.09), ("d_trans", 0.01, 0.02), ("d_gap", 0.03, 0.04), ("gap_area", 0.20, 0.35), ("gain", 6.0, 7.0), VOW, GL, F0),
    "qa":  W(("c_pos", 0.483, 0.49), ("d_cons", 0.08, 0.09), ("d_trans", 0.012, 0.018), ("d_gap", 0.032, 0.04), ("gap_area", 0.20, 0.24), ("gain", 6.0, 6.5), VOW, GL, F0),   # first run 6/90: gap frication louder than -2 dB above 0.24
    "kha": W(("c_pos", 0.50, 0.53), ("c_area", 0.12, 0.20), ("d_cons", 0.08, 0.13), VOW, GL, F0),
    "cha": W(("c_pos", 0.50, 0.53), ("c_area", 0.12, 0.20), ("d_cons", 0.08, 0.12), VOW, GL, F0),
    "ha":  W(("c_pos", 0.32, 0.40), ("c_area", 0.15, 0.25), ("voi", 0.0, 0.2), ("d_cons", 0.05, 0.08), ("d_trans", 0.015, 0.03), VOW, GL, F0),
    "ya":  W(("c_pos", 0.70, 0.78), ("c_area", 0.40, 0.60), ("d_cons", 0.05, 0.08), ("d_trans", 0.015, 0.025), ("d_vowel", 0.30, 0.36), ("glide", 0.45, 0.60), F0),
    "tza": W(("c_pos", 0.94, 0.95), ("d_cons", 0.055, 0.07), ("gap_pos", 0.83, 0.86), ("gap_area", 0.18, 0.24), ("d_gap", 0.065, 0.08), ("glide", 0.08, 0.12), ("gain", 6.0, 7.0), ("d_vowel", 0.28, 0.36), F0),
}

def sample(syl, rng):
    s = dict(BASE[syl])
    for k, lo, hi in WINDOWS[syl]:
        s[k] = float(rng.uniform(lo, hi))
    if syl in ("ka", "qa"): s["gap_pos"] = s["c_pos"]        # the VOT frication sits where the stop was
    return s

def wav_write(path, y):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(G.SR)
    w.writeframes((np.clip(np.asarray(y, float), -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

def run(syls):
    summary = {}
    for syl in syls:
        rng = np.random.RandomState(abs(hash(syl)) % 100000 + 20260903)
        letter, heb, place, manner, nasal, voiced, fam, twin = R.FACTS[syl]
        n_ok = 0; attempts = 0; t0 = time.time(); reasons = {}
        # the base itself first (v00), then random variants
        cands = [dict(BASE[syl])]
        while attempts < MAX_ATTEMPTS and n_ok < TARGET + SPARE:
            spec = cands.pop(0) if cands else sample(syl, rng)
            attempts += 1
            spec = G.clean(spec)
            ok, fails, brief, y = R.judge(syl, spec)
            row = {"syl": syl, "attempt": attempts, "ok": ok, "fails": fails, "spec": spec}
            if ok:
                name = "CLAUDE-%s-v%02d" % (syl, n_ok)
                wav_write(os.path.join(OUT, name + ".wav"), y)
                json.dump({"speaker": "CLAUDE", "syl": syl, "letter": letter, "hebrew": heb,
                           "facts": {"place": place, "manner": manner, "nasal": nasal, "voiced": voiced},
                           "decisions": {k: spec[k] for k in G.DECISIONS},
                           "amounts": {k: spec[k] for k in G.AMOUNTS if k in spec},
                           "live_amounts": sorted(G.live_amounts(spec)),
                           "gesture": G.readable(spec), "ruler": "school-v2/ruler.py (09-02 family rulers + verifiers' objections)",
                           "brief": brief[:1500], "attempt": attempts},
                          open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                row["file"] = name + ".wav"; n_ok += 1
            else:
                for f in fails: k = f.split("(")[0][:50]; reasons[k] = reasons.get(k, 0) + 1
            with open(LEDGER, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, default=float) + "\n")
        summary[syl] = {"verified": n_ok, "attempts": attempts, "pass_rate": round(n_ok / attempts, 3),
                        "top_fail_reasons": sorted(reasons.items(), key=lambda kv: -kv[1])[:4], "seconds": round(time.time() - t0, 1)}
        print("%-4s %2d verified / %2d attempts (%.0f%%)  %s" % (syl, n_ok, attempts, 100 * n_ok / attempts,
              "; ".join("%s x%d" % kv for kv in summary[syl]["top_fail_reasons"][:2])), flush=True)
    return summary

if __name__ == "__main__":
    syls = [a for a in sys.argv[1:] if a in R.SYLS] or R.SYLS
    S = run(syls)
    full = sum(1 for s in S.values() if s["verified"] >= TARGET)
    tot = sum(s["verified"] for s in S.values()); att = sum(s["attempts"] for s in S.values())
    print("GATE 1: %d/%d syllables with >= %d verified variants; %d variants total; ruler pass rate %.1f%% (%d/%d)" % (
        full, len(S), TARGET, tot, 100.0 * tot / max(1, att), tot, att))
    prev = {}
    p = os.path.join(OUT, "gate1.json")
    if os.path.exists(p): prev = json.load(open(p)).get("per_syllable", {})
    prev.update(S)
    json.dump({"what": "mouth school v2, stage 1 (the teacher): verified variants per syllable under school-v2/ruler.py",
               "target_per_syllable": TARGET, "per_syllable": prev,
               "gate1": {"syllables_full": sum(1 for s in prev.values() if s["verified"] >= TARGET), "of": len(prev),
                         "variants_total": sum(s["verified"] for s in prev.values()),
                         "attempts_total": sum(s["attempts"] for s in prev.values())},
               "written_by": "claude-cli-MOREH lessons.py " + time.strftime("%Y-%m-%d %H:%M")},
              open(p, "w", encoding="utf-8"), indent=1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lessons3.py -- school-v3: the teacher searches the SAME physics mouth, but the gate is a
HEBREW SPEECH MODEL instead of the hand-built acoustic ruler.

  gate  : facebook/wav2vec2-xlsr-53-espeak-cv-ft, scored as a closed set over the 24 syllables
          (CTC log-likelihood of each syllable's IPA target -> softmax = a posterior).
          PASS when the target's CANONICAL posterior (modern-Hebrew homophones merged:
          kha=cha, ka=qa, va=wa) >= THR.
  side  : school-v2/ruler.py verdict is RECORDED for every pass, never used as a gate.
  search: 96 random draws inside widened v2 windows, then 4 rounds of local hill-climbing
          around the best specs so far. <= 300 renders per syllable.

school-v2 is NOT modified; gesture.py / ruler.py / lessons.py are imported from it.
Label Law: lessons/CLAUDE-<syl>-judge-vNN.wav+json. Nothing is played, nothing touches eran1.
claude-cli-FABLE-HEB 2026-09-03 on eran2.
"""
import os, sys, json, time, wave
import numpy as np

V2 = os.path.expanduser("~/throat-one-sample/school-v2")
sys.path.insert(0, V2)
sys.path.insert(0, os.path.expanduser("~/hebrew-ref"))
os.environ.setdefault("JUDGE_TRIM", "0")
import ruler as R, gesture as G, lessons as L2      # noqa: E402  (school-v2, read-only)
import judge as J                                    # noqa: E402  (the Hebrew judge)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lessons"); os.makedirs(OUT, exist_ok=True)
LEDGER = os.path.join(OUT, "ledger.jsonl")
THR = float(os.environ.get("V3_THR", "0.50"))
BUDGET = int(os.environ.get("V3_BUDGET", "300"))
WANT = int(os.environ.get("V3_WANT", "6"))
RANDOM_N, ROUND_N, ROUNDS = 96, 51, 4

BOUNDS = {"c_pos": (0.30, 1.00), "c_area": (0.05, 1.50), "velum": (0.0, 1.0), "voi": (0.0, 1.0),
          "ten": (0.15, 0.90), "gain": (3.0, 16.0), "d_cons": (0.02, 0.25), "d_trans": (0.005, 0.05),
          "d_gap": (0.010, 0.100), "d_vowel": (0.20, 0.55), "glide": (0.02, 0.70), "d_pre": (0.0, 0.35),
          "d_bridge": (0.0, 0.06), "gap_pos": (0.30, 1.00), "gap_area": (0.05, 2.50), "f0": (85.0, 125.0)}
WIDEN = float(os.environ.get("V3_WIDEN", "2.0"))

def windows(syl):
    """the v2 window, widened WIDEN x about its midpoint, clipped to the physical bounds."""
    out = []
    for k, lo, hi in L2.WINDOWS[syl]:
        m = 0.5 * (lo + hi); h = 0.5 * (hi - lo) * WIDEN
        a, b = m - h, m + h
        if k in BOUNDS: a, b = max(a, BOUNDS[k][0]), min(b, BOUNDS[k][1])
        out.append((k, a, b))
    return out

def draw(syl, rng, W):
    s = dict(L2.BASE[syl])
    for k, lo, hi in W: s[k] = float(rng.uniform(lo, hi))
    if syl in ("ka", "qa"): s["gap_pos"] = s["c_pos"]
    return s

def perturb(base, rng, W, scale=0.25):
    s = dict(base)
    for k, lo, hi in W:
        s[k] = float(np.clip(s[k] + rng.normal(0, scale * (hi - lo)), lo, hi))
    if base.get("_syl") in ("ka", "qa"): s["gap_pos"] = s["c_pos"]
    return s

def wav_write(p, y):
    w = wave.open(p, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(G.SR)
    w.writeframes((np.clip(np.asarray(y, float), -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

def render_many(syl, specs):
    ys, keep = [], []
    for s in specs:
        try:
            y = G.render(G.clean(s), seed=0)
        except Exception:
            continue
        if not np.all(np.isfinite(y)) or np.max(np.abs(y)) < 1e-4: continue
        ys.append(np.asarray(y, dtype=np.float32)); keep.append(s)
    return keep, ys

def run(syls):
    gate = {}
    for syl in syls:
        t0 = time.time(); W = windows(syl)
        rng = np.random.RandomState(abs(hash("v3" + syl)) % 100000 + 20260903)
        tried = 0; scored = []          # (canon_conf, syl_conf, spec, y, top3, phones)
        pool = [dict(L2.BASE[syl])] + [draw(syl, rng, W) for _ in range(RANDOM_N - 1)]
        while tried < BUDGET:
            specs, ys = render_many(syl, pool)
            tried += len(pool)
            if ys:
                out = J.judge_wavs(ys)
                for sp, y, (post, t3, ph) in zip(specs, ys, out):
                    cp = J.canon_posterior(post)
                    scored.append((cp.get(J.CANON[syl], 0.0), post[syl], sp, y, t3, ph))
                    with open(LEDGER, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"syl": syl, "canon_conf": round(cp.get(J.CANON[syl], 0.0), 4),
                                             "syl_conf": round(post[syl], 4), "top3": t3, "phones": ph,
                                             "pass": cp.get(J.CANON[syl], 0.0) >= THR}, ensure_ascii=False) + "\n")
            if tried >= BUDGET: break
            scored.sort(key=lambda r: -r[0])
            seeds = [r[2] for r in scored[:6]] or [dict(L2.BASE[syl])]
            pool = []
            for i in range(min(ROUND_N, BUDGET - tried)):
                b = dict(seeds[i % len(seeds)]); b["_syl"] = syl
                p = perturb(b, rng, W, scale=0.25 if tried < RANDOM_N + 2 * ROUND_N else 0.10)
                p.pop("_syl", None); pool.append(p)
        scored.sort(key=lambda r: -r[0])
        passes = [r for r in scored if r[0] >= THR]
        n = 0; kept = []
        for cc, sc, sp, y, t3, ph in passes[: WANT + 6]:
            name = "CLAUDE-%s-judge-v%02d" % (syl, n)
            wav_write(os.path.join(OUT, name + ".wav"), y)
            ok, fails, brief, _ = R.judge(syl, sp)
            letter, heb, place, manner, nasal, voiced, fam, twin = R.FACTS[syl]
            json.dump({"speaker": "CLAUDE", "syl": syl, "letter": letter, "hebrew": heb,
                       "gate": "hebrew-judge facebook/wav2vec2-xlsr-53-espeak-cv-ft",
                       "canon_conf": round(cc, 4), "syl_conf": round(sc, 4), "judge_top3": t3,
                       "judge_phones": ph, "old_ruler_pass": bool(ok), "old_ruler_fails": fails[:4],
                       "spec": {k: v for k, v in sp.items() if not k.startswith("_")}},
                      open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            kept.append({"file": name + ".wav", "canon_conf": round(cc, 4), "old_ruler_pass": bool(ok)})
            n += 1
        best = scored[0] if scored else None
        gate[syl] = {"attempts": tried, "passes": len(passes), "written": n,
                     "best_canon_conf": round(best[0], 4) if best else None,
                     "best_top3": best[4] if best else None, "best_phones": best[5] if best else None,
                     "threshold": THR, "secs": round(time.time() - t0, 1), "kept": kept}
        print("%-4s attempts %3d  passes %3d  best %.3f  heard %s  (%.0fs)" % (
            syl, tried, len(passes), best[0] if best else 0,
            " ".join("%s:%.2f" % (a, b) for a, b in (best[4] if best else [])), time.time() - t0), flush=True)
    json.dump(gate, open(os.path.join(HERE, "gate3.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    tot = sum(v["passes"] for v in gate.values()); got = sum(1 for v in gate.values() if v["written"] >= 1)
    print("GATE 3: %d/%d syllables the Hebrew judge accepted at all; %d passing renders total" % (got, len(syls), tot), flush=True)
    return gate

if __name__ == "__main__":
    run(sys.argv[1:] or R.SYLS)

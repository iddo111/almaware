# export_articulation.py -- THE BRIDGE between the ERAN mouth school and the Godot avatar.
#
# Reads the 21 VERIFIED syllable gestures (dataset.json membership is the truth), replays
# mouth2.say_gesture's keyframe interpolator, turns each 1 ms block into the 23-section
# area function with geometry.py + tract_core.py (pure numpy/scipy, on the PC), decimates
# to 60 fps and writes data/articulation.json for scenes/main.tscn.
#
# TRAP (brief 1.5): mouth2.py has AGE_MONTHS = 60 (child, 15 sections). The school was
# rendered on eran2 with AGE_MONTHS = 300 (adult, 23 sections). We NEVER import mouth2.
#
# Everything written here is data that made a real sound, except `jaw_open01_derived`,
# which is labelled as such and shown as DERIVED in the HUD.
import sys, os, json, wave, math
import numpy as np

MOUTH2 = r"D:\CLAUDE\eran-brain\voice\mouth2"
SCHOOL = r"D:\CLAUDE\eran-brain\throat-one-sample\school"
OUT    = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "articulation.json")

sys.path.insert(0, MOUTH2)
import geometry
import tract_core as T           # only these two -- never mouth2

AGE_MONTHS = 300
L_TRACT, _ = geometry.child_area(AGE_MONTHS)      # 17.600 cm adult
N          = T.n_sections_for(L_TRACT)            # 23
LADDER     = N * T.SECTION_CM                     # 16.771 cm
AREA_MIN, AREA_MAX = 0.15, 4.0
NASAL_JUNCTION = 9                                # section, c_pos 0.41 (MOUTH-MANUAL 1.4)
FPS = 60
SEAL_CM2   = 0.01                                 # < 0.01 = sealed (manual 1.2)
VELUM_OPEN = 0.05                                 # switch (manual 1.4)
NO_NOISE   = 0.49                                 # >= 0.49 cm2 = no noise (manual 1.2)

HEBREW = {"ba":"\u05d1\u05bc\u05b8","va":"\u05d1\u05b8","ma":"\u05de\u05b8","pa":"\u05e4\u05bc\u05b8",
          "fa":"\u05e4\u05b8","wa":"\u05d5\u05b8","da":"\u05d3\u05b8","ta":"\u05ea\u05b8",
          "na":"\u05e0\u05b8","la":"\u05dc\u05b8","sa":"\u05e1\u05b8","za":"\u05d6\u05b8",
          "sha":"\u05e9\u05c1\u05b8","ra":"\u05e8\u05b8","ga":"\u05d2\u05b8","kha":"\u05db\u05b8",
          "a":"\u05d0\u05b8","ha":"\u05d4\u05b8","ya":"\u05d9\u05b8","cha":"\u05d7\u05b8",
          "aya":"\u05d0\u05b7\u05d9\u05b8","ka":"\u05db\u05bc\u05b8","qa":"\u05e7\u05b8","tza":"\u05e6\u05b8"}

def load_gesture(syl):
    d = json.load(open(os.path.join(SCHOOL, syl + ".json"), encoding="utf-8"))
    if "gesture" in d:                                   # shape A
        g = d["gesture"]
        kfs = [np.asarray(k, float) for k in g["keyframes"]]
        return kfs, list(g["durations"]), float(g.get("glide", 0.35)), g.get("burst")
    kfs = [np.array(list(k["knots8"]) + [k["c_pos"], k["c_area"], k["velum"], k["tenseness"], k["voicing"]], float)
           for k in d["keyframes"]]                      # shape B (back family)
    return kfs, list(d["durations"]), float(d.get("glide", 0.35)), d.get("burst")

def kf_track(kfs, durs, glide):
    """Verbatim mouth2.say_gesture interpolator: glide for `glide` of each segment, then hold."""
    total = sum(durs)
    nb = int(math.ceil(int(round(total * T.FS_INTERNAL)) / (T.BLOCK_S * T.FS_INTERNAL)))
    trk = np.zeros((nb, 13)); prev = kfs[0]; b0 = 0
    for kf, secs in zip(kfs, durs):
        n = min(max(1, int(round(secs / T.BLOCK_S))), nb - b0)
        if n <= 0: break
        gl = max(1, int(n * glide))
        w = np.clip(np.arange(n) / float(gl), 0.0, 1.0)[:, None]
        trk[b0:b0+n] = prev[None, :] * (1 - w) + kf[None, :] * w
        prev = kf; b0 += n
    if b0 < nb: trk[b0:] = prev
    return trk, total

def areas_of(trk):
    a = geometry.spline_knots_to_areas_batch(2.0 ** trk[:, :8], N)
    a = np.clip(a, AREA_MIN, AREA_MAX)
    return geometry.constriction_batch(a, trk[:, 8], np.maximum(trk[:, 9], T.AREA_FLOOR),
                                       width_cm=1.5, length_cm=LADDER)

def wav_seconds(syl):
    p = os.path.join(SCHOOL, "ERAN-%s.wav" % syl)
    if not os.path.exists(p): return None
    w = wave.open(p); s = w.getnframes() / w.getframerate(); w.close(); return s

def main():
    # --- sanity gate (brief 1.6): the /a/ vowel area function must reproduce exactly ---
    AH = np.array([-0.6013, -0.0092, -0.6310, -1.4002, 1.6041, -1.8558, 1.8504, 1.9330, 0.65, 2.0, 0.0, 0.6, 1.0])
    A_vowel = areas_of(AH[None, :])[0]
    expect = [0.741,0.881,0.971,0.990,0.906,0.772,0.653,0.543,0.440,0.384,0.467,1.076,2.439,
              2.477,1.916,1.635,0.523,0.554,1.606,3.472,3.693,3.772,3.813]
    err = np.abs(np.round(A_vowel, 3) - np.array(expect)).max()
    print("tract %.3f cm, %d sections, ladder %.3f cm, section %.4f cm" % (L_TRACT, N, LADDER, T.SECTION_CM))
    print("vowel /a/ areas:", np.round(A_vowel, 3).tolist())
    print("vowel sanity vs brief 1.6: max |diff| = %.4f  -> %s" % (err, "PASS" if err <= 0.0015 else "FAIL"))
    if err > 0.0015:
        sys.exit("ABORT: vowel area function does not match the brief -- wrong tract/ladder?")

    ds = json.load(open(os.path.join(SCHOOL, "dataset.json"), encoding="utf-8"))
    verified = [r["syl"] for r in ds["rows"]]
    assert len(verified) == 21, len(verified)

    # front-cavity range for the DERIVED jaw (mean of sections 17..22): measured over 21 syllables
    fc_lo, fc_hi = 1e9, -1e9
    prepared = {}
    for syl in verified:
        kfs, durs, glide, burst = load_gesture(syl)
        trk, total = kf_track(kfs, durs, glide)
        A = areas_of(trk)
        prepared[syl] = (trk, total, A, burst)
        fc = A[:, 17:].mean(1); fc_lo = min(fc_lo, fc.min()); fc_hi = max(fc_hi, fc.max())
    print("front-cavity mean range over 21: %.3f .. %.3f cm2 (jaw derivation range)" % (fc_lo, fc_hi))

    out = {"what": "ERAN mouth-school articulation for the Godot avatar. All numbers except jaw_open01_derived are the physics that rendered the wav.",
           "written_by": "claude-cli-FABLE-avatar export_articulation.py 2026-09-09",
           "source_school": SCHOOL, "geometry_code": MOUTH2 + " (geometry.py + tract_core.py only; mouth2.py NOT imported)",
           "tract": {"age_months": AGE_MONTHS, "length_cm": round(L_TRACT, 3), "ladder_cm": round(LADDER, 3),
                     "n_sections": N, "section_cm": round(T.SECTION_CM, 4), "nasal_junction_section": NASAL_JUNCTION,
                     "area_min_cm2": AREA_MIN, "area_max_cm2": AREA_MAX},
           "fps": FPS, "lip_area_open_cm2": 3.813, "seal_cm2": SEAL_CM2, "velum_open_threshold": VELUM_OPEN,
           "no_noise_cm2": NO_NOISE, "front_cavity_range_cm2": [round(fc_lo, 3), round(fc_hi, 3)],
           "derived_fields": ["jaw_open01_derived"],
           "syllables": {}}

    print("%-4s %6s %4s %6s %8s %8s %6s %7s %5s %8s" % ("syl", "dur", "frm", "wav", "lipA[0]", "lipA[-1]", "velum", "voiMin", "cSec", "t_rel"))
    for syl in verified:
        trk, total, A, burst = prepared[syl]
        nb = A.shape[0]
        # release: first 1 ms block where min(A) > SEAL after a sealed run (brief 1.10)
        mn_ms = A.min(1); t_rel = None
        if mn_ms[0] < SEAL_CM2 and (mn_ms >= SEAL_CM2).any():
            t_rel = int(np.argmax(mn_ms >= SEAL_CM2)) / 1000.0
        idx = np.clip(np.round(np.arange(0, total, 1.0 / FPS) * 1000).astype(int), 0, nb - 1)
        frames = []
        for fi, bi in enumerate(idx):
            a = A[bi]; k = trk[bi]
            mi = int(a.argmin()); mn = float(a[mi])
            fc = float(a[17:].mean())
            frames.append({
                "t": round(fi / FPS, 5),
                "areas": [round(float(x), 4) for x in a],
                "lip_area": round(float(a[-1]), 4),
                "min_area": round(mn, 4), "min_section": mi,
                "constriction_cm_from_lips": round((1.0 - (mi + 0.5) / N) * LADDER, 3),
                "c_pos": round(float(k[8]), 4), "c_area": round(float(k[9]), 4),
                "velum": round(float(k[10]), 4), "tenseness": round(float(k[11]), 4), "voicing": round(float(k[12]), 4),
                "sealed": bool(mn < SEAL_CM2),
                "jaw_open01_derived": round(float(np.clip((fc - fc_lo) / (fc_hi - fc_lo), 0, 1)), 4),
            })
        ws = wav_seconds(syl)
        out["syllables"][syl] = {
            "hebrew": HEBREW.get(syl, syl), "verified": True,
            "duration_s": round(total, 4), "n_frames": len(frames), "wav": "res://audio/ERAN-%s.wav" % syl,
            "wav_duration_s": (round(ws, 4) if ws else None),
            "t_release_s": t_rel, "burst_gain": (burst or {}).get("gain"),
            "velum_max": round(float(trk[:, 10].max()), 3), "voicing_min": round(float(trk[:, 12].min()), 3),
            "frames": frames}
        print("%-4s %6.3f %4d %6.3f %8.4f %8.3f %6.2f %7.2f %5d %8s" % (
            syl, total, len(frames), ws or -1, A[0, -1], A[-1, -1], trk[:, 10].max(), trk[:, 12].min(),
            frames[0]["min_section"], ("%.3f" % t_rel) if t_rel is not None else "n/a"))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", OUT, "(%d KB, %d syllables)" % (os.path.getsize(OUT) // 1024, len(out["syllables"])))

if __name__ == "__main__":
    main()

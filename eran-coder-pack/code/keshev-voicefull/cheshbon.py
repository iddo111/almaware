#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 5 - CHESHBON NEFESH.  חשבון נפש, in code.

Rabbi Nachman's practice is daily self-accounting: actively hunting for where
you fell short.  Its opposite is the man certain of his own righteousness.  This
program is the first, and it exists because the second is what a training script
becomes by default - every run wants to report a win.

Each test below is written to FAIL the run, not to bless it.  A test that cannot
produce a bad answer is decoration.  Each prints VERDICT ok / SUSPECT / FAIL and
says in one line what would have to be true for the result to be an illusion.

  1  contamination      are any eval clips in the training set?  (by SHA-256 of
                        the raw PCM, not by filename - filenames can collide or
                        be rewritten, audio bytes cannot)
  2  date leakage       did any clip from the eval DAY reach training?  Same
                        room, same gain, same topics is a leak even when the
                        clip differs.
  3  drift floor        sort the eval day's clips by time and try to separate
                        early from late from acoustics alone.  This is the test
                        that exposed a whole TTS corpus on 2026-09-05.  If a
                        session drifts, per-date holdout is mandatory and a
                        random split would have leaked.
  4  train/eval gap     can a trivial classifier tell training clips from eval
                        clips?  A high AUC does not invalidate a win, but it
                        bounds what the win generalises to, and it must be said.
  5  shortcut           does the improvement concentrate in one duration or one
                        loudness band?  Then it is a shortcut, not language.
  6  harness noise      decode the same clips twice with the same model.  Any
                        margin smaller than this is not a result.
  7  teacher imitation  the fine-tune learned from ivrit-ai/whisper-large-v3 and
                        is scored against ivrit-ai/whisper-large-v3.  Does it
                        reproduce the TEACHER'S KNOWN ERRORS?  If yes, the CER
                        gain is imitation and the CER column is void.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, wave
from pathlib import Path
from collections import Counter
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import norm, edit, rates, degenerate, GOOD, BAD   # one scorer, not two

RESULTS = []


def verdict(name, ok, msg, detail=""):
    u = (ok or "").strip().upper()
    tag = {"OK": "ok     ", "SUSPECT": "SUSPECT"}.get(u, "FAIL   ")
    print("\n[%s]  %s" % (tag, name))
    print("         " + msg)
    if detail:
        for line in detail.splitlines():
            print("         " + line)
    RESULTS.append({"test": name, "verdict": u if u in ("OK", "SUSPECT") else "FAIL",
                    "msg": msg})


def feats(p):
    with wave.open(str(p)) as w:
        raw = w.readframes(w.getnframes())
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    if a.size < 512:
        a = np.pad(a, (0, 512 - a.size))
    rms = float(np.sqrt(np.mean(a ** 2)) + 1e-12)
    zcr = float(np.mean(np.abs(np.diff(np.sign(a))) > 0))
    n = 1 << 12
    seg = a[: (a.size // n) * n].reshape(-1, n) if a.size >= n else a[None, :n]
    sp = np.abs(np.fft.rfft(seg * np.hanning(seg.shape[1]), axis=1)) + 1e-12
    fr = np.fft.rfftfreq(seg.shape[1], 1 / 16000)
    cen = float(np.mean((sp * fr).sum(1) / sp.sum(1)))
    roll = float(np.mean(fr[np.argmax(np.cumsum(sp, 1) >= 0.85 * sp.sum(1, keepdims=True), 1)]))
    return [a.size / 16000.0, np.log10(rms), zcr, cen / 1000.0, roll / 1000.0], hashlib.sha256(raw).hexdigest()


def auc(x, y):
    """AUC of a single score x against binary y, by rank. No sklearn."""
    o = np.argsort(x)
    r = np.empty_like(o, dtype=float)
    r[o] = np.arange(1, len(x) + 1)
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    if n1 == 0 or n0 == 0:
        return 0.5
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def best_auc(X, y):
    """The most separating single feature, and a 2-fold centroid AUC."""
    per = [max(auc(X[:, j], y), 1 - auc(X[:, j], y)) for j in range(X.shape[1])]
    Z = (X - X.mean(0)) / (X.std(0) + 1e-9)
    w = Z[y == 1].mean(0) - Z[y == 0].mean(0)
    s = Z @ w
    return max(per), max(auc(s, y), 1 - auc(s, y)), per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judged", required=True, help="judge.py output jsonl")
    ap.add_argument("--train-manifest", required=True)
    ap.add_argument("--train-audio", required=True)
    ap.add_argument("--eval-audio", required=True)
    ap.add_argument("--noise-jsonl", default="", help="second decode of the SAME arm")
    ap.add_argument("--noise-arm", default="", help="arm name inside --noise-jsonl "
                    "(defaults to --arm; use when the repeat run named it differently)")
    ap.add_argument("--arm", default="full_prompt")
    ap.add_argument("--baseline-arm", default="base_prompt")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.judged).read_text(encoding="utf-8").splitlines() if l.strip()]
    train = [json.loads(l) for l in Path(args.train_manifest).read_text(encoding="utf-8").splitlines() if l.strip()]
    ev_wavs = sorted(Path(args.eval_audio).glob("*.wav"))
    tr_dir = Path(args.train_audio)

    print("=" * 78)
    print("CHESHBON NEFESH  -  %d eval clips, %d training clips" % (len(rows), len(train)))
    print("=" * 78)

    # ---------- 1  contamination by audio hash ------------------------------
    ev_feat, ev_hash = {}, {}
    for p in ev_wavs:
        f, h = feats(p)
        ev_feat[p.name] = f
        ev_hash[p.name] = h
    tr_hash = set(r["sha256"] for r in train)
    hit = [n for n, h in ev_hash.items() if h in tr_hash]
    verdict("1  contamination (SHA-256 of raw PCM)",
            "ok" if not hit else "FAIL",
            "%d of %d eval clips found in the training set." % (len(hit), len(ev_hash)),
            ("first offenders: %s" % hit[:5]) if hit else
            "Would be an illusion if: the hash were of the filename or the wav header\n"
            "rather than the PCM. It is of the frames only - see feats().")

    # ---------- 2  date leakage --------------------------------------------
    ev_dates = Counter(n[:8] for n in ev_hash)
    tr_dates = Counter(r["wav"][:8] for r in train)
    shared = sorted(set(ev_dates) & set(tr_dates))
    verdict("2  date leakage (same recording day in both sets)",
            "ok" if not shared else "FAIL",
            "eval days %s | training days %d | SHARED %s"
            % (sorted(ev_dates), len(tr_dates), shared or "none"),
            "A clip from the eval day is a leak even when the clip itself differs:\n"
            "same room, same mic gain, same topics, same voice state.")

    # ---------- 3  drift floor: early vs late within the eval day ----------
    names = sorted(ev_hash)
    X = np.array([ev_feat[n] for n in names])
    half = len(names) // 2
    y = np.zeros(len(names)); y[half:] = 1          # sorted by name == sorted by time
    f1, c1, per = best_auc(X, y)
    drift_bad = c1 >= 0.70
    verdict("3  drift floor (early vs late in the eval session)",
            "SUSPECT" if drift_bad else "ok",
            "best single feature AUC %.3f | centroid AUC %.3f  (0.5 = no drift)" % (f1, c1),
            "per-feature [secs, log rms, zcr, centroid kHz, rolloff kHz]: "
            + ", ".join("%.2f" % v for v in per) + "\n"
            + ("The session DRIFTS. A random split would have leaked session identity;\n"
               "this is why the whole eval day was held out of training."
               if drift_bad else
               "The session does not drift measurably, so the date holdout costs nothing\n"
               "and the eval is not a moving target."))

    # ---------- 4  train/eval acoustic gap ---------------------------------
    rng = np.random.default_rng(1729)
    tr_names = [r["wav"] for r in train]
    samp = [tr_names[i] for i in rng.choice(len(tr_names), size=min(400, len(tr_names)), replace=False)]
    Xt = []
    for n in samp:
        p = tr_dir / n
        if p.exists():
            Xt.append(feats(p)[0])
    Xt = np.array(Xt)
    Xa = np.vstack([X, Xt])
    ya = np.concatenate([np.ones(len(X)), np.zeros(len(Xt))])
    f2, c2, per2 = best_auc(Xa, ya)
    verdict("4  train/eval acoustic gap",
            "SUSPECT" if c2 >= 0.80 else "ok",
            "centroid AUC %.3f separating eval clips from %d training clips" % (c2, len(Xt)),
            "per-feature: " + ", ".join("%.2f" % v for v in per2) + "\n"
            "This does not invalidate a win. It bounds it: the further this is from\n"
            "0.5, the less the eval day represents the audio the model was trained on.")

    # ---------- 5  duration / loudness shortcut ----------------------------
    arm, bas = args.arm, args.baseline_arm
    have = arm in rows[0] and bas in rows[0]
    if have:
        d, secs, lrms = [], [], []
        for r in rows:
            if not r["ref"] or degenerate(r["ref"]):
                continue
            _, _, ce_a, rc = rates(r[arm]["text"], r["ref"])
            _, _, ce_b, _ = rates(r[bas]["text"], r["ref"])
            if rc == 0:
                continue
            d.append((ce_b - ce_a) / rc)             # >0 means the arm improved
            f = ev_feat.get(r["wav"])
            secs.append(f[0]); lrms.append(f[1])
        d = np.array(d); secs = np.array(secs); lrms = np.array(lrms)
        rs = float(np.corrcoef(d, secs)[0, 1]) if len(d) > 2 else 0.0
        rl = float(np.corrcoef(d, lrms)[0, 1]) if len(d) > 2 else 0.0
        q = np.quantile(secs, [0, .25, .5, .75, 1.0])
        bands = []
        for i in range(4):
            m = (secs >= q[i]) & (secs <= q[i + 1])
            bands.append("%.1f-%.1fs n=%d gain=%+.3f" % (q[i], q[i + 1], m.sum(), d[m].mean() if m.any() else 0))
        bad = abs(rs) > 0.35 or abs(rl) > 0.35
        verdict("5  duration / loudness shortcut",
                "SUSPECT" if bad else "ok",
                "corr(gain, duration) %+.3f | corr(gain, log-rms) %+.3f" % (rs, rl),
                "\n".join(bands) + "\n"
                "A real language gain is spread across bands. A gain that lives in one\n"
                "band is the model exploiting a property of the clip, not the speech.")

    # ---------- 6  harness noise floor -------------------------------------
    if args.noise_jsonl and Path(args.noise_jsonl).exists():
        r2 = {json.loads(l)["wav"]: json.loads(l) for l in
              Path(args.noise_jsonl).read_text(encoding="utf-8").splitlines() if l.strip()}
        same = tot = 0
        ce = rc = 0
        for r in rows:
            o = r2.get(r["wav"])
            na = args.noise_arm or arm
            if not o or na not in o:
                continue
            tot += 1
            a, b = r[arm]["text"], o[na]["text"]
            same += int(norm(a) == norm(b))
            ce += edit(list(norm(a)), list(norm(b)))
            rc += len(norm(b))
        nf = ce / max(rc, 1) * 100
        verdict("6  harness noise floor (same model, same clips, twice)",
                "ok" if nf < 0.5 else "SUSPECT",
                "identical %d/%d | run-to-run CER %.2f%%" % (same, tot, nf),
                "Any margin between two arms smaller than %.2f%% CER is noise, not a\n"
                "result. temperature=[0.0,0.2] means the decoder can fall back." % nf)
    else:
        verdict("6  harness noise floor", "SUSPECT",
                "NOT MEASURED - no second decode supplied.",
                "Without it, no margin can be called real. Pass --noise-jsonl.")

    # ---------- 7  teacher imitation ---------------------------------------
    if have:
        tea_bad = sum(r["ref"].count(b) for r in rows for b in BAD)
        arm_bad = sum(r[arm]["text"].count(b) for r in rows for b in BAD)
        bas_bad = sum(r[bas]["text"].count(b) for r in rows for b in BAD)
        # how much of the arm's text moved TOWARD the teacher
        def cer_to_ref(k):
            ce = rc = 0
            for r in rows:
                if not r["ref"] or degenerate(r["ref"]):
                    continue
                _, _, c, d = rates(r[k]["text"], r["ref"])
                ce += c; rc += d
            return ce / max(rc, 1) * 100
        ca, cb = cer_to_ref(arm), cer_to_ref(bas)
        na = sum(r[arm]["text"].count(h) for r in rows for h in GOOD)
        nb2 = sum(r[bas]["text"].count(h) for r in rows for h in GOOD)
        imit = (cb - ca) > 1.0 and (na - nb2) <= 0
        verdict("7  teacher imitation (the trap this run is most likely to fall into)",
                "FAIL" if imit else ("SUSPECT" if (cb - ca) > 1.0 else "ok"),
                "CER-to-teacher %.1f%% -> %.1f%% (%+.1f) while names %d -> %d (%+d)"
                % (cb, ca, ca - cb, nb2, na, na - nb2),
                "teacher's own known garbles: %d | baseline reproduces %d | arm reproduces %d\n"
                % (tea_bad, bas_bad, arm_bad)
                + ("The arm moved TOWARD the teacher without getting better at the one\n"
                   "thing measured independently. That is imitation. The CER column is void."
                   if imit else
                   "Moving toward the teacher while ALSO gaining on the independent name\n"
                   "column is consistent with a real gain - but the CER column stays\n"
                   "inadmissible on its own."))

    print("\n" + "=" * 78)
    n_fail = sum(1 for r in RESULTS if r["verdict"] == "FAIL")
    n_sus = sum(1 for r in RESULTS if r["verdict"] == "SUSPECT")
    print("CHESHBON: %d tests | %d FAIL | %d SUSPECT" % (len(RESULTS), n_fail, n_sus))
    print("=" * 78)
    if args.out:
        Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

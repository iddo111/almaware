"""measure_depth.py — THE MEASUREMENT THAT DECIDES. Did depth earn its place?

Chance and every published baseline are printed FIRST, before any result of
ours, exactly as proof/measure.py does (the eran0/GROUND law).

Three questions, and the honest answer to each is written to
results/ERANB-DEPTH-<date>.json whether it flatters the organism or not.

1. WORD -> SYLLABLE DECOMPOSITION — the thing that has never beaten chance in
   this project's history (best AUC 0.571 against a random baseline of 0.590,
   i.e. worse than its own null). Given a word, does the brain's evidence rank
   the syllables that ARE in it above the syllables that are NOT?

   Three arms, each producing the same object — one evidence score per class
   per word — so the numbers are comparable:

     flat_layer0    the brain as it stands today: ONE glance at the whole word
                    through the frozen cochlea, scored against layer-0
                    prototypes. This is the arm that has always failed.
     trace_layer0   the cortex's windowed read of the SAME layer 0: the sound
                    now has moments, and each moment votes.
     layer1         depth: the layer-1 units that actually fire on the word,
                    decomposed into the layer-0 prototypes their slots are
                    made of.

   AUC is pooled over all (constituent, non-constituent) pairs of all words.
   TWO nulls, because a single null is easy to fool:
     - shuffled constituents: the same scores, random syllable sets. Answers
       "would any word have scored this well?"
     - shuffled prototype labels: the same words, the brain/class
       correspondence destroyed. Answers "is it the BRAIN that knows, or the
       corpus statistics?"

2. LAYER 0 ALONE vs LAYER 0+1 on the 132-item heldout. Depth must EARN its
   place on the task the organism is actually judged on, or be recorded as a
   loss. No knob is tuned to make the combination win: the combined arm is the
   plain sum of the two evidence vectors.

3. THE TOPOGRAPHIC MAP. body/cortex.py places a newborn prototype near the
   ones it resembles. Whether that produces a real map — distance in space
   tracking dissimilarity in meaning, the way tonotopy does in auditory cortex
   — is a claim, so it is measured (Pearson and Spearman against a
   shuffled-positions null) instead of asserted.

    python3 proof/measure_depth.py --state state-depth-run
    python3 proof/measure_depth.py --state state-depth-run --expose
    python3 proof/measure_depth.py --state state-depth-run --counterfactual-birth

``--expose`` is an EXPLORATORY arm: it lets the layers above 0 hear half the
word tokens (layer 0 held exactly as it grew) and probes on the other half, so
that a negative result is not a strawman — the organism itself has never eaten
a word, since food/words is in no menu school.py serves.

``--counterfactual-birth`` FORCES layer 1 open when the organism's own fence
has not fired, and stamps every output with the fact. It answers "what would
depth have measured?" and never "what the child did".
"""
import argparse
import datetime
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, _HERE)

import genome                                     # noqa: E402
import measure                                    # noqa: E402
import make_words                                 # noqa: E402

N_PERM = 2000
RNG = np.random.default_rng(genome.SEED)


# ------------------------------------------------------------------- scoring
ARMS = ("flat_layer0", "trace_layer0", "layer1")

# "no prototype in this layer answers for this class". It must be a REAL
# cosine floor, not a sentinel: -1.0 is the minimum a cosine can take, so
# layer0+1 below is an honest sum of two similarities. It used to be -2.0,
# which made the sum decide by WHICH classes had a labelled layer-1 unit
# (any such class beat every other by >= 1.0 whatever layer 0 thought) —
# a very large hidden knob in an arm whose docstring said it had none.
ABSENT = -1.0


def _class_scores(sims, proto_label, classes):
    """One similarity vector over layer-0 prototypes -> best sim per class."""
    out = {c: ABSENT for c in classes}
    for i, s in enumerate(sims):
        c = proto_label.get(i)
        if c is not None and s > out[c]:
            out[c] = float(s)
    return out


def scores_from_raw(mat, proto_label, classes):
    """(n_readings, n_layer0_prototypes) similarities -> best sim per class.

    Kept separate from the audio so a label-shuffle null costs a matrix max
    and not a re-run of the ear. Same numbers either way — the shuffle only
    changes WHICH prototype answers for which class.
    """
    out = {c: ABSENT for c in classes}
    if mat is None or not len(mat):
        return out
    cols = {}
    for i, c in proto_label.items():
        if i < mat.shape[1]:
            cols.setdefault(c, []).append(i)
    for c, idx in cols.items():
        if c in out:
            out[c] = float(mat[:, idx].max())
    return out


def word_readings(cortex, ears, path):
    """The RAW evidence for one word: per arm, every similarity vector the
    brain produced over its layer-0 prototypes. Computed once, scored many
    times (the nulls re-score without re-hearing)."""
    L0 = cortex.layers[0]
    if not L0.protos:
        raise SystemExit("layer 0 has no prototypes — nothing has lived in "
                         "this state dir. Grow it first (eran_life.py "
                         "--state ... --beats N).")
    M0 = np.stack([p["vec"] for p in L0.protos])

    feats, rms = ears.frames(path)
    vec0 = ears.pool(feats, rms)

    # --- arm 1: the flat brain. One glance at the whole word. ---------------
    flat = (M0 @ vec0)[None, :]

    # --- arm 2: the same layer 0, read through the cortex's window ----------
    rows = []
    for a, b in cortex.window_bounds(rms):
        v = ears.pool(feats[a:b], rms[a:b])
        if np.isfinite(v).all():
            rows.append(M0 @ v)
    trace = np.stack(rows) if rows else flat

    # --- arm 3: depth. What the layer-1 units that FIRED are made of. -------
    rows, fired = [], []
    if cortex.n_layers() > 1 and cortex.layers[1].protos:
        read = cortex.read_frames(ears, feats, rms, vec0)
        width = L0.dim
        for idx, sim in read["traces"][1]:
            fired.append((int(idx), float(sim)))
            u = np.asarray(cortex.layers[1].protos[idx]["vec"],
                           dtype=np.float64)
            for slot in range(genome.LAYER_SLOTS):
                sub = u[slot * width:(slot + 1) * width]
                n = float(np.linalg.norm(sub))
                if n > 0:
                    rows.append(M0 @ (sub / n))
    layer1 = np.stack(rows) if rows else None
    return {"flat_layer0": flat, "trace_layer0": trace, "layer1": layer1,
            "fired_layer1": fired}


# ----------------------------------------------------------------------- AUC
def pooled_auc(scored, constituents, classes):
    """Pooled AUC over every (constituent, non-constituent) pair of every word.

    Ties count a half, which is what AUC means; a brain that scores every
    class the same gets exactly 0.5 and cannot fake a win by being silent.
    """
    conc = 0.0
    total = 0
    for name, s in scored.items():
        pos = [s[c] for c in constituents[name]]
        neg = [s[c] for c in classes if c not in constituents[name]]
        if not pos or not neg:
            continue
        p = np.asarray(pos)[:, None]
        n = np.asarray(neg)[None, :]
        conc += float((p > n).sum() + 0.5 * (p == n).sum())
        total += p.size * n.size
    return (conc / total) if total else float("nan"), total


def draw_constituent_shuffles(constituents, classes, n=N_PERM):
    """n random syllable-set assignments, of the same sizes as the real ones.

    Drawn ONCE and handed to every arm, so the three arms face the identical
    null and their AUCs are comparable. Drawing per arm (which this used to
    do, while the comment claimed otherwise) gives each arm its own Monte
    Carlo error and quietly breaks that comparison.
    """
    sizes = {k: len(v) for k, v in constituents.items()}
    return [{k: set(RNG.choice(classes, size=sizes[k], replace=False))
             for k in constituents} for _ in range(n)]


def _null_shuffled_constituents(scored, shuffles, classes):
    """Same scores, the shared random syllable sets."""
    return np.asarray([pooled_auc(scored, fake, classes)[0]
                       for fake in shuffles], dtype=float)


def _perm_stats(observed, null):
    null = null[np.isfinite(null)]
    if not len(null):
        return {}
    return {
        "null_mean": float(null.mean()),
        "null_sd": float(null.std()),
        "null_p95": float(np.percentile(null, 95)),
        "p_value": float((null >= observed).sum() + 1) / (len(null) + 1),
        "permutations": int(len(null)),
    }


# ----------------------------------------------------------- the heldout exam
def fit_paths(train_dir=None):
    """The train wavs a label map may be fitted on: NEVER the dev split.

    proof/make_words.py builds every word out of DEV-split syllable
    recordings, so fitting the prototype->class map on all of food/train
    would fit it on the exact audio inside the words being scored. That is
    the repo's own convention anyway (measure.dev_scores does the same), and
    skipping it here would have inflated every decomposition number.
    """
    return [p for p in measure.wavs_in(train_dir or genome.FOOD_TRAIN)
            if not measure.is_dev(p)]


def _layer1_labels(cortex, ears, paths):
    """Majority vote: which class does each layer-1 unit answer for?

    Exactly measure.fit_proto_labels' contract, one storey up. Labels live in
    the examiner and are never handed to the organism.
    """
    votes = {}
    if cortex.n_layers() < 2:
        return {}
    for p in paths:
        read = cortex.read_path(ears, p)
        idx, _ = read["best"][1]
        if idx is None:
            continue
        c = measure.label_of(p)
        votes.setdefault(idx, {})
        votes[idx][c] = votes[idx].get(c, 0) + 1
    return {i: max(v.items(), key=lambda kv: kv[1])[0] for i, v in votes.items()}


def heldout_depth_exam(cortex, ears, proto_label, classes,
                       train_dir=None, heldout_dir=None):
    """layer 0 alone vs layer 1 alone vs the plain sum. No tuned knob."""
    train_dir = train_dir or genome.FOOD_TRAIN
    heldout_dir = heldout_dir or genome.HELDOUT_VAULT
    L0 = cortex.layers[0]
    if not L0.protos:
        return {"heldout_items": 0, "top1": {}, "layer1_exists": False,
                "per_class": {}, "layer1_labeled_units": 0}
    M0 = np.stack([p["vec"] for p in L0.protos])
    has1 = cortex.n_layers() > 1 and bool(cortex.layers[1].protos)
    l1_label = (_layer1_labels(cortex, ears, fit_paths(train_dir))
                if has1 else {})
    M1 = (np.stack([p["vec"] for p in cortex.layers[1].protos])
          if has1 else None)

    held = measure.wavs_in(heldout_dir)
    hits = {"layer0": 0, "layer1": 0, "layer0_plus_1": 0}
    n = 0
    per_class = {}
    for p in held:
        t = measure.label_of(p)
        read = cortex.read_path(ears, p)
        s0 = _class_scores(M0 @ read["vec0"], proto_label, classes)
        s1 = {c: ABSENT for c in classes}
        if has1 and read["percepts"][1] is not None:
            sims1 = M1 @ read["percepts"][1]
            for i, s in enumerate(sims1):
                c = l1_label.get(i)
                if c is not None and s > s1[c]:
                    s1[c] = float(s)
        comb = {c: s0[c] + s1[c] for c in classes}
        n += 1
        per_class.setdefault(t, {"n": 0, "layer0": 0, "layer1": 0,
                                 "layer0_plus_1": 0})
        per_class[t]["n"] += 1
        for arm, s in (("layer0", s0), ("layer1", s1), ("layer0_plus_1", comb)):
            y = max(classes, key=lambda c: s[c])
            if y == t:
                hits[arm] += 1
                per_class[t][arm] += 1
    top1 = {k: (v / n if n else 0.0) for k, v in hits.items()}
    if not has1:
        # With no layer 1 every class scores the same -2.0 and argmax returns
        # whichever class sorts first — a number that looks like chance and
        # means nothing. Say "there is no layer 1" instead of printing it.
        top1["layer1"] = None
        top1["layer0_plus_1"] = top1["layer0"]
    return {
        "heldout_items": n,
        "top1": top1,
        "layer1_labeled_units": len(l1_label),
        "layer1_exists": has1,
        "per_class": per_class,
    }


# ------------------------------------------------------- the topographic map
def _spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def topographic_map(cortex, n_perm=200):
    """Correlation between distance in SPACE and dissimilarity in MEANING.

    A real map has neighbours that are alike. Shuffling the positions among
    the same prototypes gives the null: if the observed correlation is not
    clearly above that, the placement rule is decoration, not a map.
    """
    out = []
    for k, brain in enumerate(cortex.layers):
        pos = np.array([p["pos"] for p in brain.protos
                        if p.get("pos") is not None], dtype=np.float64)
        vecs = np.array([p["vec"] for p in brain.protos
                         if p.get("pos") is not None], dtype=np.float64)
        n = len(pos)
        if n < 4:
            out.append({"layer": k, "n": n, "verdict": "too few prototypes",
                        "n_without_a_position": len(brain.protos) - n})
            continue
        iu = np.triu_indices(n, 1)
        d = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=2)[iu]
        dis = (1.0 - (vecs @ vecs.T))[iu]
        r = float(np.corrcoef(d, dis)[0, 1])
        rho = _spearman(d, dis)
        null = []
        rng = np.random.default_rng(genome.SEED + k)
        for _ in range(n_perm):
            q = pos[rng.permutation(n)]
            dq = np.linalg.norm(q[:, None, :] - q[None, :, :], axis=2)[iu]
            null.append(float(np.corrcoef(dq, dis)[0, 1]))
        null = np.asarray(null)
        out.append({
            "layer": k, "n": n, "pairs": int(len(d)),
            # a prototype spawned outside the cortex path (tournament.py builds
            # a bare Brain) never gets a body; say how many were left out
            # instead of quietly shrinking n
            "n_without_a_position": len(brain.protos) - n,
            "positions_backfilled": int(cortex.backfilled[k])
            if k < len(cortex.backfilled) else 0,
            "pearson_distance_vs_dissimilarity": r,
            "spearman": rho,
            "null_mean": float(null.mean()), "null_sd": float(null.std()),
            "null_p95": float(np.percentile(null, 95)),
            "p_value": float((null >= r).sum() + 1) / (len(null) + 1),
            "verdict": ("a map: neighbours in space are alike"
                        if r > float(np.percentile(null, 95))
                        else "NOT a map: no better than shuffled positions"),
            "what_this_null_does_and_does_not_show": (
                "The placement rule PUTS a newborn near what it resembles, so "
                "a positive correlation is expected by construction and the "
                "shuffled-positions null will always sit near zero. What the "
                "measurement can still show is FAILURE: 192 dimensions do not "
                "have to fit into 3, and a rule that destroys the structure "
                "while placing greedily would land near the null. Read it as "
                "'the embedding survived', never as 'a map was discovered'. "
                "Where positions_backfilled > 0 the coordinates were also "
                "assigned from TODAY's vectors (the brain predates positions), "
                "i.e. fitted to the same matrix they are scored against — "
                "weaker still."),
        })
    return out


# -------------------------------------------------------------- exposure arm
def expose_layers_to_words(cortex, ears, paths, log=print):
    """Let the layers ABOVE 0 hear words, with layer 0 held exactly as it is.

    Clearly marked as an EXPLORATORY arm. The organism itself has never eaten
    a word — food/words is not in any menu school.py serves — so the main
    result is measured on a cortex that grew on single syllables only. This
    arm exists so the negative, if it is negative, is not a strawman: a layer
    that was never shown a sequence longer than a syllable would be being
    asked a question it was never given the chance to learn.
    """
    from chemistry import Chemistry
    chem = Chemistry()
    before = cortex.counts()
    base = cortex.beat            # read ONCE: hear_path advances cortex.beat
    for i, p in enumerate(paths):
        cortex.hear_path(ears, p, chem, base + i + 1, learn=True, learn0=False)
    log(f"[depth] exposure arm: {len(paths)} word wavs; layers "
        f"{before} -> {cortex.counts()} (layer 0 held fixed)")
    return {"exposed_items": len(paths), "before": before,
            "after": cortex.counts()}


# ------------------------------------------------- the counterfactual layer 1
def counterfactual_birth(cortex, ears, log=print):
    """Birth layer 1 by SUPPLYING the settle precondition. Not a birth.

    Use only when the organism's own fence has not fired and the question
    "what would depth have measured?" still needs an answer. Everything it
    produces is stamped FORCED in the results file, and the real
    ``birth_status`` at the moment of forcing is recorded beside it, so a
    reader can see exactly which precondition was missing and by how much.
    This is the examiner reaching in. It is not the brain deciding, and it
    must never be reported as one.
    """
    from chemistry import Chemistry
    if cortex.n_layers() > 1:
        return None
    # The epoch set is empty on a fresh load (its keys are prototype indices,
    # which a restart cannot vouch for), so fill it by LISTENING first, with
    # nothing learning. Only the settle precondition is ever supplied by hand;
    # "has it got something to learn" must still be earned from real audio.
    listen = Chemistry()
    for i, p in enumerate(measure.wavs_in(genome.FOOD_TRAIN)):
        cortex.hear_path(ears, p, listen, cortex.beat, learn=False)
    status = cortex.birth_status()
    n = len(cortex.layers[0].protos)
    cortex.sleep_counts[0] = list(cortex.sleep_counts[0]) + [n] * (
        2 * genome.LAYER_SETTLE_SLEEPS)
    rec = cortex.maybe_birth(cortex.beat)
    if rec is None:
        log(f"[depth] counterfactual birth REFUSED — the missing precondition "
            f"is not settle: {status}")
        return {"forced": False, "why_refused": status}
    chem = Chemistry()
    paths = fit_paths()
    base = cortex.beat
    for i, p in enumerate(paths):
        cortex.hear_path(ears, p, chem, base + i + 1, learn=True, learn0=False)
    log(f"[depth] COUNTERFACTUAL layer 1: FORCED open (layer 0 had NOT "
        f"settled: {status['sleep_counts_below']}, tolerance "
        f"{status['settle_tolerance_now']:.1f}), then trained on "
        f"{len(paths)} train wavs with layer 0 held fixed -> "
        f"{cortex.counts()}")
    return {"forced": True, "birth": rec, "status_when_forced": status,
            "trained_on_train_wavs": len(paths),
            "WARNING": ("layer 1 here was NOT born by the organism's own "
                        "fence. The examiner supplied the settle "
                        "precondition. Every layer-1 number in this file is a "
                        "counterfactual, not something the child did.")}


# --------------------------------------------------------------------- main
def run(state=None, expose=False, write=True, force_birth=False, log=print):
    if state:
        genome.use_state_dir(state)
    from ears import Ears
    from cortex import Cortex

    measure.print_baselines_first()
    log("[examiner] the decomposition bar: this project's best word->syllable "
        "AUC to date is 0.571 against its own random baseline of 0.590 — i.e. "
        "it has NEVER beaten chance at decomposition.")

    ears = Ears(exam=True)
    cortex = Cortex.load(ears.dim, log=log)
    classes = list(genome.CLASSES)
    log(f"[depth] cortex: {cortex.n_layers()} layer(s), {cortex.counts()} "
        f"prototypes, beat {cortex.beat}")
    forced = None
    if cortex.n_layers() < 2:
        log(f"[depth] layer 1 has NOT been born. status: "
            f"{cortex.birth_status()}")
        if force_birth:
            forced = counterfactual_birth(cortex, ears, log=log)

    proto_label = measure.fit_proto_labels(
        cortex.layers[0], ears, fit_paths())
    log(f"[depth] {len(proto_label)} of {len(cortex.layers[0].protos)} "
        f"layer-0 prototypes carry an examiner label")

    # --- the words ----------------------------------------------------------
    manifest = make_words.load_manifest()
    if manifest is None:
        raise SystemExit("no food/words manifest — run proof/make_words.py")
    words = sorted(n for n in manifest["words"])
    exposure = None
    if expose:
        # Split by WORD CLASS, not by token index. Splitting on the token
        # index looked disjoint and was not: with a dev pool of 1-6 recordings
        # per syllable, 10 of the 12 word classes shared source recordings
        # across the two halves, so "not exposed to" was false (review,
        # 2026-08-21). Whole word classes are held out instead, which asks the
        # question depth is actually supposed to answer: does a second layer
        # generalise sequence structure to word TYPES it has never heard?
        # Individual syllable recordings can still recur across the split —
        # the dev pool is too small to avoid that — and that is stated here
        # rather than papered over.
        classes_all = sorted({manifest["words"][n]["word"] for n in words})
        exposed_words = set(classes_all[:len(classes_all) // 2])
        exposed_paths = [os.path.join(genome.FOOD_WORDS, n) for n in words
                         if manifest["words"][n]["word"] in exposed_words]
        exposure = expose_layers_to_words(cortex, ears, exposed_paths, log=log)
        words = [n for n in words
                 if manifest["words"][n]["word"] not in exposed_words]
        exposure["exposed_word_classes"] = sorted(exposed_words)
        exposure["probed_word_classes"] = [c for c in classes_all
                                           if c not in exposed_words]
        exposure["caveat"] = (
            "word CLASSES are disjoint; individual syllable recordings may "
            "recur across the split because the dev pool is 1-6 tokens per "
            "syllable class")
        log(f"[depth] probing on {len(words)} tokens of the "
            f"{len(classes_all) - len(exposed_words)} word classes the layers "
            f"never heard: {exposure['probed_word_classes']}")

    constituents = {n: set(manifest["words"][n]["syllables"]) for n in words}
    readings, fired_counts = {}, []
    for n in words:
        readings[n] = word_readings(cortex, ears,
                                    os.path.join(genome.FOOD_WORDS, n))
        fired_counts.append(len(readings[n]["fired_layer1"]))

    # Both nulls are drawn ONCE and reused across arms, so the three arms are
    # judged against the identical null and can be compared to each other.
    con_shuffles = draw_constituent_shuffles(constituents, classes)
    label_keys = list(proto_label)
    label_vals = list(proto_label.values())
    shuffles = [dict(zip(label_keys, RNG.permutation(label_vals)))
                for _ in range(100)]

    decomposition = {}
    for a in ARMS:
        scored = {n: scores_from_raw(readings[n][a], proto_label, classes)
                  for n in words}
        auc, pairs = pooled_auc(scored, constituents, classes)
        per_word = [pooled_auc({n: scored[n]}, {n: constituents[n]}, classes)[0]
                    for n in words]
        null_c = _null_shuffled_constituents(scored, con_shuffles, classes)
        null_l = np.asarray(
            [pooled_auc({n: scores_from_raw(readings[n][a], sl, classes)
                         for n in words}, constituents, classes)[0]
             for sl in shuffles], dtype=float)
        c_p95 = (float(np.percentile(null_c[np.isfinite(null_c)], 95))
                 if np.isfinite(null_c).any() else float("nan"))
        l_p95 = (float(np.percentile(null_l[np.isfinite(null_l)], 95))
                 if np.isfinite(null_l).any() else float("nan"))
        beats = bool(auc > c_p95 and auc > l_p95)
        decomposition[a] = {
            "pooled_auc": auc,
            "pairs": pairs,
            "per_word_auc_mean": float(np.nanmean(per_word)),
            "per_word_auc_sd": float(np.nanstd(per_word)),
            "null_shuffled_constituents": _perm_stats(auc, null_c),
            "null_shuffled_proto_labels": _perm_stats(auc, null_l),
            "beats_both_nulls": beats,
        }
        log(f"[depth] decomposition {a:>13}: AUC {auc:.4f} | null "
            f"constituents {np.nanmean(null_c):.4f} (p95 {c_p95:.4f}) | null "
            f"labels {np.nanmean(null_l):.4f} (p95 {l_p95:.4f}) -> "
            f"{'BEATS both nulls' if beats else 'does NOT beat its nulls'}")

    # --- the heldout ---------------------------------------------------------
    held = heldout_depth_exam(cortex, ears, proto_label, classes)
    _l1 = held["top1"]["layer1"]
    log(f"[depth] heldout {held['heldout_items']} items: "
        f"layer0 {held['top1']['layer0']:.2%} | "
        f"layer1 {'(no layer 1)' if _l1 is None else format(_l1, '.2%')} | "
        f"layer0+1 {held['top1']['layer0_plus_1']:.2%}")

    # --- the map -------------------------------------------------------------
    topo = topographic_map(cortex)
    for t in topo:
        if "pearson_distance_vs_dissimilarity" in t:
            log(f"[depth] topography layer {t['layer']} (n={t['n']}): "
                f"pearson {t['pearson_distance_vs_dissimilarity']:.4f}, "
                f"spearman {t['spearman']:.4f}, null p95 {t['null_p95']:.4f} "
                f"-> {t['verdict']}")

    verdict = {
        "depth_beat_chance_at_decomposition": bool(
            decomposition["layer1"]["beats_both_nulls"]),
        "depth_beat_layer0_on_heldout": bool(
            held["top1"]["layer0_plus_1"] > held["top1"]["layer0"]),
        "layer1_alone_beat_layer0_on_heldout": (
            None if held["top1"]["layer1"] is None
            else bool(held["top1"]["layer1"] > held["top1"]["layer0"])),
        "layer1_exists": cortex.n_layers() > 1,
        "layer1_born_by_the_organism_itself": bool(
            cortex.n_layers() > 1 and not (forced and forced.get("forced"))),
        "arms_that_beat_both_nulls_at_decomposition": [
            a for a, d in decomposition.items() if d["beats_both_nulls"]],
    }
    log(f"[depth] VERDICT {json.dumps(verdict)}")

    result = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "state_dir": genome.STATE_DIR,
        "chance": genome.CHANCE,
        "baselines": genome.BASELINES,
        "prior_decomposition_record": {
            "best_auc": 0.571, "its_random_baseline": 0.590,
            "note": "never beaten chance at decomposition, to date",
            "NOT_COMPARABLE": (
                "This run's AUCs are NOT comparable to 0.571/0.590. That "
                "figure was measured on a word corpus this session never "
                "had: food/words does not exist on the PC mirror and no ssh "
                "to eran1 was allowed, so proof/make_words.py BUILT one by "
                "concatenating dev-split syllable recordings. Concatenated "
                "syllables have no coarticulation and no cross-syllable "
                "prosody, which makes them an EASIER target than whatever "
                "the 0.571 was measured on. Beating 0.5 here is a real "
                "result against this run's own nulls and nothing more; it "
                "does not retire the historical failure."),
        },
        "cortex": {
            "layers": cortex.n_layers(),
            "layer_protos": cortex.counts(),
            "beat": int(cortex.beat),
            "births": cortex.births,
            "birth_status_next": cortex.birth_status(),
            "layer1_was_FORCED_not_born": forced,
            "percept_dims": [cortex.percept_dim(k)
                             for k in range(cortex.n_layers())],
            "slots": genome.LAYER_SLOTS,
            "max_layers": genome.MAX_LAYERS,
        },
        "words": {
            "n_probed": len(words),
            "word_classes": sorted({manifest["words"][n]["word"]
                                    for n in words}),
            "honest_note": manifest["honest_note"],
            "mean_layer1_units_fired_per_word": (
                float(np.mean(fired_counts)) if fired_counts else 0.0),
        },
        "exposure_arm": exposure,
        "decomposition": decomposition,
        "heldout": held,
        "topography": topo,
        "verdict": verdict,
    }
    if write:
        os.makedirs(genome.RESULTS_DIR, exist_ok=True)
        out = os.path.join(
            genome.RESULTS_DIR,
            f"ERANB-DEPTH-{datetime.date.today().isoformat()}"
            f"{'-forced' if forced and forced.get('forced') else ''}"
            f"{'-exposed' if expose else ''}.json")
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, ensure_ascii=False)
        os.replace(tmp, out)
        log(f"[depth] wrote {out}")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="did depth earn its place?")
    ap.add_argument("--state", default=None)
    ap.add_argument("--expose", action="store_true",
                    help="EXPLORATORY: let layers above 0 hear half the word "
                         "tokens first, and probe on the other half")
    ap.add_argument("--counterfactual-birth", action="store_true",
                    help="if the organism's fence has not fired, FORCE layer 1 "
                         "open and say so in every line of the output")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    run(state=a.state, expose=a.expose, write=not a.no_write,
        force_birth=a.counterfactual_birth)

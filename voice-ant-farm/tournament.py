# -*- coding: utf-8 -*-
"""Coronation tournament — the throne is the fitness signal.

Iddo's directive (2026-08-11, verbatim "תשתמש בהכתרה כדרך לאינסנטיב"): make
coronation the farm's standing incentive. Each round the farm BIRTHS a few new
ant variants autonomously, evaluates every contender on the SAME fixed
held-out protocol, and if a challenger honestly beats the sitting queen she is
crowned automatically under Iddo's standing mandate. The journal is the
dynasty's history book.

The autonomy law is absolute: a mutation may change only the ORGANISM —
  * seed         (a new individual: a different random draw of real frames)
  * units        (codebook capacity: 128 / 256 / 512 / 1024)
  * scaled       (whether the ant normalises its own sensory dimensions)
  * cochlea      (one of the feature sets defined by train-only CV work in
                  feature_space.py — the held-out split never fed that list)
No curated data, no vowel-weighted sampling, no label ever enters a feature,
a codebook, or a sampling decision. The environment (corpus) is untouched.

The crown criterion is the farm's established selection key — held-out
syllable discrimination, cosine top-1 (state-big/scripts/queen.py) — with an
honesty bar: a challenger is crowned only if her top-1 is strictly higher AND
an exact McNemar on the same 132 held-out items rejects luck at p < 0.05.
Losing honestly is recorded, not hidden; the journal keeps every contender.

Crowning is atomic and never breaks the live dialogue: the winner is sealed
as a full format-3 checkpoint (real waveform exemplars, verified round-trip),
the previous coronation record is archived, state/coronation.json is replaced
atomically, and gui.py hot-reloads it on the next request. If anything fails
before the swap, the sitting queen keeps serving.

    py -3.13 tournament.py --round            one tournament round
    py -3.13 tournament.py --status           show the dynasty
    py -3.13 tournament.py --dry-crown        exercise the crowning machinery
                                              into scratch, touching nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

import feature_space as F
import sequence_probes as sp
from acoustic_units import (EXEMPLAR_RATE, features as legacy_features,
                            load_checkpoint, load_wav, resample_samples,
                            encode, write_json_atomic)
from paired_tests import mcnemar
import vowel_checkpoint

ROOT = Path(__file__).resolve().parent
COMBINED = ROOT / "corpus-combined"
STATE = ROOT / "state"
CORONATION = STATE / "coronation.json"
TDIR = STATE / "tournament"
JOURNAL = TDIR / "lineage.json"
LOG = TDIR / "tournament.log"
RAMCHAT = Path(r"D:\CLAUDE\RAMCHAT")
GUI = "http://127.0.0.1:8803"

# the gene pool for the cochlea — every entry was defined and ranked by
# train-only cross-validation (state-hebbian/feature-selection.json et al.);
# the held-out split never read by that work. legacy14 is history, not a gene.
COCHLEA_GENES = (
    "recommended26",        # canonical, CV rank 1 (== mfcc20_mel26_pd6w4)
    "mfcc16_mel26_pd6w4",   # CV rank 2
    "mfcc24_mel26_pd6w4",   # CV rank 3
    "mfcc20_mel26_pd6",     # CV rank 4
    "mfcc16_mel32_pd4w4",   # CV rank 6
    "mfcc16_mel32_pd6w4",   # CV rank 7
    "mfcc12",               # strongest simple cepstrum
)
UNIT_GENES = (128, 256, 512, 1024, 2048)
CROWN_P = 0.05

# ---------------------------------------------------------------- elites --
# Iddo, 2026-08-15: "תעשה הכתרה אוטומטית". Coronation was ALREADY automatic
# (run_round crowns without a human). What was broken was the SEARCH, not the
# crowning: rounds 3-7 all mutated from the sitting queen and threw every
# challenger away, so a genome that scored ABOVE her was deleted the moment it
# failed the significance bar. Round 7 (2026-08-15) is the proof — challenger
# gen7-1 scored cos@1 0.765 vs the queen's 0.758 with ah=6/6 aa=6/6, fell short
# only on McNemar p=1.0000 (it was +1 item out of 132, honestly noise), and was
# discarded. Round 8 would have started from 0.758 again. A (1+λ) hill-climb
# that resets to the same point every round cannot cross a plateau.
#
# So: near-misses that score >= the queen are kept as ELITES and may be bred
# from. The SELECTION bar is untouched — CROWN_P stays 0.05 and the crown still
# requires strictly-higher cosine AND McNemar p < 0.05. Loosening that would
# crown noise, which is the one thing the farm must never do. This only stops
# the search from forgetting where it has already been.
ELITE_POOL_MAX = 12          # how many near-misses stay breedable
ELITE_BREED_P = 0.5          # chance a challenger is bred from an elite


def prune_elites(elites: list, queen_cos: float) -> list:
    """Keep the best ELITE_POOL_MAX genomes that are at least as good as the
    sitting queen. An elite that the current queen has overtaken is dropped —
    the pool tracks the frontier, it does not hoard history (the journal is
    the history book)."""
    kept = [e for e in elites if float(e.get("cos_top1", 0.0)) >= queen_cos]
    kept.sort(key=lambda e: float(e.get("cos_top1", 0.0)), reverse=True)
    seen, out = set(), []
    for e in kept:
        key = json.dumps(e["genome"], sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out[:ELITE_POOL_MAX]


def log(msg: str) -> None:
    TDIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {msg}\n")
    print(msg, flush=True)


# ---------------------------------------------------------------- journal --

FOUNDING_DYNASTY = [
    {"reign": 1, "queen": "state/ant-b (64 units, legacy14)",
     "crowned": "2026-07 (approx)", "crowned_by": "queen script",
     "criterion": "minimum held-out quantisation error (criterion later "
                  "rejected by controlled experiment)"},
    {"reign": 2, "queen": "iddo-fresh-256/ant-c",
     "crowned": "2026-08 (state-big)", "crowned_by": "queen.py",
     "criterion": "held-out syllable discrimination, cosine top-1",
     "syllable_cos_top1": 0.424,
     "status": "honorably retired 2026-08-11"},
    {"reign": 3, "queen": "vowel-cochlea26-scaled-512/ant-a",
     "genome": {"cochlea": "recommended26", "units": 512,
                "seed": 7007, "scaled": True},
     "crowned": "2026-08-11", "crowned_by": "Iddo (verbatim: תחליף מלכה)",
     "criterion": "held-out syllable discrimination, cosine top-1; "
                  "McNemar vs previous cochlea p=7.0e-27",
     "syllable_cos_top1": 0.758,
     "checkpoint_sha256": "a33f8f78af150da8a7a547387d6752a9284147c8c8f9"
                          "3516ad907c3c2b1a51cb"},
]


def load_journal() -> dict:
    if JOURNAL.exists():
        return json.loads(JOURNAL.read_text(encoding="utf-8"))
    return {
        "history_book": "the Voice Ant Farm dynasty — every contender ever "
                        "born, who begat whom, and every reign",
        "protocol": "held-out syllable discrimination on corpus-combined "
                    "(132 tokens, 22 classes, frozen legacy speech spans); "
                    "crown = strictly higher cosine top-1 AND exact McNemar "
                    f"p < {CROWN_P} on the same items",
        "autonomy_law": "mutations touch only the organism (seed, units, "
                        "scaler, cochlea from the train-CV gene pool); the "
                        "environment and its labels are never curated",
        "dynasty": FOUNDING_DYNASTY,
        "individuals": [],
        "rounds": [],
    }


def save_journal(journal: dict) -> None:
    write_json_atomic(JOURNAL, journal)


# ------------------------------------------------------------------ corpus --

def load_corpus() -> dict:
    """Train + held-out syllable items with frozen legacy speech spans."""
    labels = sp.load_labels(COMBINED)
    splits = {}
    for split in ("train", "heldout"):
        items = []
        for path in sorted((COMBINED / split).glob("*.wav")):
            rec = labels.get(path.name)
            if rec is None or rec.get("item_kind") != "syllable":
                continue
            audio = load_wav(path)
            samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
            legacy = legacy_features(audio)[0]
            a, b = sp.speech_span(legacy)          # frozen frame selection
            items.append({"name": path.name, "label": rec["item_id"],
                          "samples": samples, "span": (a, b)})
        splits[split] = items
    classes = sorted({it["label"] for it in splits["train"]})
    return {"train": splits["train"], "held": splits["heldout"],
            "classes": classes,
            "y_train": [it["label"] for it in splits["train"]],
            "y_held": [it["label"] for it in splits["heldout"]]}


class FeatureCache:
    """Per-cochlea features and train frame pools, computed once per round."""

    def __init__(self, corpus: dict) -> None:
        self.corpus = corpus
        self._speech: dict[str, dict[str, list]] = {}
        self._pool: dict[str, tuple] = {}

    def speech(self, cochlea: str) -> dict[str, list]:
        if cochlea not in self._speech:
            out = {}
            for split in ("train", "held"):
                rows = []
                for it in self.corpus[split]:
                    x = F.extract(cochlea, it["samples"]).astype(np.float32)
                    a, b = it["span"]
                    rows.append(x[a:b])
                out[split] = rows
            self._speech[cochlea] = out
        return self._speech[cochlea]

    def pool(self, cochlea: str) -> tuple:
        if cochlea not in self._pool:
            self._pool[cochlea] = vowel_checkpoint.build_pool(cochlea)
        return self._pool[cochlea]


# ------------------------------------------------------------------- birth --

def mutate(queen_genome: dict, rng: np.random.Generator) -> tuple[dict, str]:
    g = dict(queen_genome)
    g["seed"] = int(rng.integers(1, 2**31 - 1))
    ops = ["fresh-seed"]
    if rng.random() > 0.45:                      # structural mutation too
        gene = rng.choice(["units", "scaled", "cochlea"])
        if gene == "units":
            i = UNIT_GENES.index(g["units"])
            j = i + (1 if (i == 0 or (i < len(UNIT_GENES) - 1
                                      and rng.random() < 0.5)) else -1)
            g["units"] = UNIT_GENES[j]
            ops.append(f"units {queen_genome['units']}→{g['units']}")
        elif gene == "scaled":
            g["scaled"] = not g["scaled"]
            ops.append(f"scaled→{g['scaled']}")
        else:
            other = [c for c in COCHLEA_GENES if c != g["cochlea"]]
            g["cochlea"] = str(rng.choice(other))
            ops.append(f"cochlea→{g['cochlea']}")
    return g, "+".join(ops)


# -------------------------------------------------------------------- eval --

def evaluate(genome: dict, cache: FeatureCache) -> dict:
    """The fixed protocol. Returns scores + the cosine correctness mask."""
    corpus = cache.corpus
    speech = cache.speech(genome["cochlea"])
    pool, _files = cache.pool(genome["cochlea"])
    scaler = np.maximum(pool.astype(np.float64).std(axis=0), 1e-6
                        ).astype(np.float32)
    if not genome["scaled"]:
        scaler = np.ones_like(scaler)
    rng = np.random.default_rng(genome["seed"])
    centers = (pool[rng.choice(len(pool), genome["units"], replace=False)]
               / scaler).astype(np.float32)

    def encode_split(rows):
        seqs, hists = [], np.zeros((len(rows), len(centers)))
        for i, x in enumerate(rows):
            ids = encode(x / scaler, centers)
            seqs.append(sp.collapse(ids))
            counts = np.bincount(ids, minlength=len(centers)).astype(float)
            hists[i] = counts / max(counts.sum(), 1.0)
        return seqs, hists

    tr_seq, tr_hist = encode_split(speech["train"])
    he_seq, he_hist = encode_split(speech["held"])
    cos = sp.cosine_similarity_matrix(he_hist, tr_hist)
    nn_cos = sp.nn_classify(cos, corpus["y_train"], corpus["y_held"],
                            corpus["classes"])
    edit = sp.edit_similarity_matrix(he_seq, tr_seq)
    nn_edit = sp.nn_classify(edit, corpus["y_train"], corpus["y_held"],
                             corpus["classes"])
    conf = nn_cos["confusion"]
    def diag(c):
        i = corpus["classes"].index(c)
        return f"{int(conf[i, i])}/{int(conf[i].sum())}"
    return {
        "cos_top1": float(nn_cos["top1"]),
        "edit_top1": float(nn_edit["top1"]),
        "ah_cos": diag("ah"), "aa_cos": diag("aa"),
        "za_cos": diag("za"), "ya_cos": diag("ya"), "na_cos": diag("na"),
        "mask_cos": (nn_cos["predicted"] == nn_cos["truth"]),
    }


# ------------------------------------------------------------------- crown --

def ramchat_post(message: str) -> None:
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        subprocess.run([sys.executable, "ramlink.py", "post",
                        "ant-tournament", message],
                       cwd=str(RAMCHAT), env=env, timeout=30,
                       capture_output=True)
    except Exception as exc:                     # never let RAMCHAT kill a round
        log(f"ramchat post failed: {exc}")


def gui_serving_sha() -> str | None:
    try:
        with urllib.request.urlopen(f"{GUI}/api/colony", timeout=5) as resp:
            return json.loads(resp.read())["checkpoint_sha256"]
    except Exception:
        return None


def crown(individual: dict, cache: FeatureCache,
          dry_run_dir: Path | None = None) -> dict:
    """Seal the winner, archive the old record, swap atomically, verify."""
    genome = individual["genome"]
    ckpt = vowel_checkpoint.build(
        individual["id"], genome["units"],
        eval_summary={"protocol": "tournament round (see state/tournament/"
                                  "lineage.json)",
                      "cos_top1": individual["scores"]["cos_top1"],
                      "edit_top1": individual["scores"]["edit_top1"]},
        cochlea=genome["cochlea"], scaled=genome["scaled"],
        seed=genome["seed"], pool_and_files=cache.pool(genome["cochlea"]))
    base = dry_run_dir if dry_run_dir else (
        ROOT / "state-hebbian" / "vowel-cochlea")
    ckpt_path = base / f"queen-{individual['id']}" / "current.json"
    write_json_atomic(ckpt_path, ckpt)
    load_checkpoint(ckpt_path)                   # seal must validate

    record = {
        "format_version": 1,
        "coronation": dt.date.today().isoformat(),
        "crowned_by": "tournament (Iddo's standing mandate 2026-08-11: "
                      "הכתרה כאינסנטיב — autonomous coronation)",
        "queen": individual["id"],
        "genome": genome,
        "checkpoint_path": str(ckpt_path.relative_to(ROOT)).replace("\\", "/")
        if not dry_run_dir else str(ckpt_path),
        "checkpoint_sha256": ckpt["checkpoint_sha256"],
        "criterion": "held-out syllable discrimination cosine top-1, "
                     f"McNemar p < {CROWN_P} vs the sitting queen",
        "record": individual["scores_public"],
        "previous_queen": individual["dethroned"],
        "rollback": "restore the archived coronation file from "
                    "state/tournament/retired/ and the GUI hot-reloads it",
    }
    if dry_run_dir:
        write_json_atomic(dry_run_dir / "coronation.json", record)
        return {"crowned": True, "dry_run": True,
                "checkpoint_sha256": ckpt["checkpoint_sha256"]}

    retired = TDIR / "retired"
    retired.mkdir(parents=True, exist_ok=True)
    if CORONATION.exists():
        old = json.loads(CORONATION.read_text(encoding="utf-8"))
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        archive = retired / f"coronation-{stamp}-{old.get('checkpoint_sha256', 'x')[:12]}.json"
        archive.write_text(json.dumps(old, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    write_json_atomic(CORONATION, record)        # gui.py hot-reloads on mtime

    live = None
    for _ in range(5):                           # next request triggers reload
        live = gui_serving_sha()
        if live == ckpt["checkpoint_sha256"]:
            break
        time.sleep(1)
    return {"crowned": True, "dry_run": False,
            "checkpoint_sha256": ckpt["checkpoint_sha256"],
            "gui_confirmed": live == ckpt["checkpoint_sha256"],
            "gui_serving": live}


# ------------------------------------------------------------------- round --

def run_round(n_challengers: int, dry_crown_dir: Path | None = None) -> dict:
    t0 = time.time()
    journal = load_journal()
    reign = journal["dynasty"][-1]
    queen_genome = reign.get("genome")
    if queen_genome is None:
        raise SystemExit("sitting queen has no genome record; cannot mutate")
    round_no = len(journal["rounds"]) + 1
    rng = np.random.default_rng(int.from_bytes(os.urandom(8), "little"))

    log(f"round {round_no}: queen={reign['queen']} "
        f"genome={json.dumps(queen_genome)}")
    corpus = load_corpus()
    cache = FeatureCache(corpus)

    queen_scores = evaluate(queen_genome, cache)
    log(f"  queen re-scored: cos@1={queen_scores['cos_top1']:.3f} "
        f"edit@1={queen_scores['edit_top1']:.3f} ah={queen_scores['ah_cos']}")

    # Elites carried over from previous rounds — genomes that matched or beat
    # the queen but could not prove it. They are breedable, never crowned.
    elites = prune_elites(journal.get("elites", []), queen_scores["cos_top1"])
    if elites:
        log(f"  elite pool: {len(elites)} — best cos@1="
            f"{max(float(e['cos_top1']) for e in elites):.3f} "
            f"({', '.join(e['id'] for e in elites[:4])}"
            f"{'…' if len(elites) > 4 else ''})")

    contenders = []
    for k in range(n_challengers):
        # Breed from the queen, or from an elite that already reached her
        # level — this is the only change to the search, and it is why a
        # plateau can now be crossed.
        parent_genome, parent_id = queen_genome, reign["queen"]
        if elites and rng.random() < ELITE_BREED_P:
            pick = elites[int(rng.integers(0, len(elites)))]
            parent_genome, parent_id = pick["genome"], pick["id"]
        genome, ops = mutate(parent_genome, rng)
        if parent_id != reign["queen"]:
            ops = f"{ops}@elite:{parent_id}"
        cid = (f"gen{round_no}-{k + 1}-{genome['cochlea']}"
               f"-{genome['units']}{'s' if genome['scaled'] else 'u'}"
               f"-{genome['seed'] % 100000}")
        scores = evaluate(genome, cache)
        m = mcnemar(scores["mask_cos"], queen_scores["mask_cos"])
        beats = (scores["cos_top1"] > queen_scores["cos_top1"]
                 and m["p_value"] < CROWN_P)
        contenders.append({"id": cid, "genome": genome, "mutation": ops,
                           "scores": scores, "mcnemar_vs_queen": m,
                           "beats_queen": bool(beats),
                           "parent_id": parent_id})
        log(f"  challenger {cid} [{ops}]: cos@1={scores['cos_top1']:.3f} "
            f"edit@1={scores['edit_top1']:.3f} ah={scores['ah_cos']} "
            f"aa={scores['aa_cos']} p={m['p_value']:.4f} "
            f"{'BEATS QUEEN' if beats else 'falls short'}")

    winner = None
    beaters = [c for c in contenders if c["beats_queen"]]
    if beaters:
        winner = max(beaters, key=lambda c: c["scores"]["cos_top1"])

    crowned_info = None
    if winner is not None:
        public = {k: v for k, v in winner["scores"].items() if k != "mask_cos"}
        winner_rec = {
            "id": winner["id"], "genome": winner["genome"],
            "scores": winner["scores"], "scores_public": public,
            "dethroned": {"queen": reign["queen"],
                          "cos_top1": queen_scores["cos_top1"],
                          "status": "honorably retired by tournament"},
        }
        crowned_info = crown(winner_rec, cache, dry_run_dir=dry_crown_dir)
        if not dry_crown_dir:
            journal["dynasty"].append({
                "reign": len(journal["dynasty"]) + 1,
                "queen": winner["id"],
                "genome": winner["genome"],
                "parent": reign["queen"],
                "mutation": winner["mutation"],
                "crowned": dt.date.today().isoformat(),
                "crowned_by": "tournament (standing mandate)",
                "criterion": journal["protocol"],
                "syllable_cos_top1": winner["scores"]["cos_top1"],
                "checkpoint_sha256": crowned_info["checkpoint_sha256"],
            })
            ramchat_post(
                f"CORONATION by tournament round {round_no}: {winner['id']} "
                f"(mutation: {winner['mutation']}) dethroned {reign['queen']} "
                f"— cos@1 {queen_scores['cos_top1']:.3f} -> "
                f"{winner['scores']['cos_top1']:.3f}, McNemar p="
                f"{winner['mcnemar_vs_queen']['p_value']:.2e}. "
                f"ah={winner['scores']['ah_cos']} aa={winner['scores']['aa_cos']}. "
                f"Live :8803 confirmed={crowned_info.get('gui_confirmed')}. "
                f"Journal: voice-ant-farm/state/tournament/lineage.json")

    for c in contenders:
        journal["individuals"].append({
            "id": c["id"], "round": round_no,
            "born": dt.datetime.now().isoformat(timespec="seconds"),
            "parent_queen": reign["queen"], "mutation": c["mutation"],
            "genome": c["genome"],
            "scores": {k: v for k, v in c["scores"].items()
                       if k != "mask_cos"},
            "mcnemar_vs_queen": c["mcnemar_vs_queen"],
            "outcome": ("CROWNED" if winner and c["id"] == winner["id"]
                        and not dry_crown_dir else
                        "beat queen (dry-run)" if c["beats_queen"] and dry_crown_dir
                        else "beaten"),
        })
    # Remember the near-misses. A challenger that reached the queen's level is
    # kept breedable even though it was (correctly) not crowned — this is the
    # memory the search was missing.
    if not dry_crown_dir:
        for c in contenders:
            if c["scores"]["cos_top1"] >= queen_scores["cos_top1"]:
                elites.append({
                    "id": c["id"], "genome": c["genome"],
                    "cos_top1": c["scores"]["cos_top1"],
                    "edit_top1": c["scores"]["edit_top1"],
                    "ah_cos": c["scores"]["ah_cos"],
                    "aa_cos": c["scores"]["aa_cos"],
                    "p_vs_queen_at_birth": c["mcnemar_vs_queen"]["p_value"],
                    "round": round_no,
                })
        # If someone was crowned this round the frontier moved — re-prune
        # against the NEW queen so the pool never carries a beaten genome.
        new_floor = (winner["scores"]["cos_top1"] if winner
                     else queen_scores["cos_top1"])
        journal["elites"] = prune_elites(elites, new_floor)
        log(f"  elites carried forward: {len(journal['elites'])}")

    journal["rounds"].append({
        "round": round_no,
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "queen": reign["queen"],
        "queen_cos_top1": queen_scores["cos_top1"],
        "challengers": [c["id"] for c in contenders],
        "elites_available": len(elites),
        "crowned": (winner["id"] if winner and not dry_crown_dir else None),
        "seconds": round(time.time() - t0, 1),
    })
    save_journal(journal)
    log(f"round {round_no} done in {time.time() - t0:.0f}s — "
        f"{'CROWNED ' + winner['id'] if winner and not dry_crown_dir else 'queen holds the throne'}")
    return {"round": round_no, "crowned": bool(winner and not dry_crown_dir),
            "winner": winner["id"] if winner else None,
            "queen_cos": queen_scores["cos_top1"],
            "contenders": [(c["id"], c["scores"]["cos_top1"]) for c in contenders]}


def status() -> None:
    journal = load_journal()
    print(f"dynasty ({len(journal['dynasty'])} reigns):")
    for r in journal["dynasty"]:
        print(f"  reign {r['reign']}: {r['queen']} "
              f"(cos@1={r.get('syllable_cos_top1', '?')}, "
              f"crowned {r.get('crowned', '?')} by {r.get('crowned_by', '?')})")
    print(f"individuals born: {len(journal['individuals'])}, "
          f"rounds: {len(journal['rounds'])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", action="store_true")
    # 3 was too few to cross a plateau: rounds 3-7 birthed 15 ants total and
    # the best was +1 item. More lottery tickets per round, paired with the
    # elite pool, is the honest way to make coronation actually happen —
    # unlike lowering CROWN_P, which would just crown noise.
    ap.add_argument("--challengers", type=int, default=12)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--dry-crown", action="store_true",
                    help="run a round but write any coronation to scratch; "
                         "the live farm is not touched")
    args = ap.parse_args()
    if args.status:
        status()
        return
    if args.round or args.dry_crown:
        dry = (TDIR / "dry-run") if args.dry_crown else None
        result = run_round(args.challengers, dry_crown_dir=dry)
        print(json.dumps(result, indent=1))
        return
    ap.print_help()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""The cheider exam — can the ants read?

Board images and syllable sounds co-occurred in the world (cheider_world),
a Hebbian binding counted co-occurrences (holobrain), and now the exam:

  Exam A  see -> say    a letter in a NEVER-SEEN font is shown in silence;
                        the ant must pick which held-out audio class matches.
  Exam B  hear -> point a NEVER-HEARD audio token plays; the ant must point
                        at the right letter on a board of never-seen fonts.

132 decisions each, 22 classes, chance = 4.5%. Controls run the identical
code path: label-permutation null, a binding trained on RANDOM pairings
(the child who sat in the wrong cheider), and a column-shuffled binding.
If any control scores like the real binding, the claim dies.

The queen (state/coronation.json) supplies the ears. GUI untouched.

    py -3.13 run_cheider_exam.py
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import numpy as np

import cheider_world as world
import retina
from acoustic_units import encode, load_checkpoint
from holobrain import Binding
from tournament import load_corpus
import feature_space as F

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "reports" / "cheider-exam.json"
CORONATION = ROOT / "state" / "coronation.json"
K_SIGHT = 64
PASSES = 3
PERM_DRAWS = 200


def audio_unit_sets() -> dict:
    """Encode all syllable audio with the sitting queen's ears."""
    record = json.loads(CORONATION.read_text(encoding="utf-8"))
    ckpt = load_checkpoint(ROOT / record["checkpoint_path"])
    centers = np.asarray(ckpt["centers"], dtype=np.float32)
    scaler = np.asarray(ckpt["frame_scaler"], dtype=np.float32)
    cochlea = ckpt["feature_spec"]["name"]
    corpus = load_corpus()
    out = {"queen": record["queen"], "checkpoint_sha256": record["checkpoint_sha256"],
           "n_units": int(ckpt["units"]), "classes": corpus["classes"]}
    for split in ("train", "held"):
        rows = []
        for it in corpus[split]:
            x = F.extract(cochlea, it["samples"]).astype(np.float32)
            a, b = it["span"]
            ids = encode(x[a:b] / scaler, centers)
            rows.append({"name": it["name"], "label": it["label"],
                         "units": np.unique(ids)})
        out[split] = rows
    return out


def letter_bank() -> dict:
    manifest = world.load_manifest()
    entries = manifest["entries"]
    glimpses = np.stack([
        retina.glimpse_file(world.LETTERS / e["path"]) for e in entries])
    train_idx = [i for i, e in enumerate(entries) if e["split"] == "train"]
    held_idx = [i for i, e in enumerate(entries) if e["split"] == "heldout"]
    centers, scaler = retina.sight_codebook(glimpses[train_idx], K_SIGHT)
    sight_units = encode(glimpses / scaler, centers)
    return {"entries": entries, "sight_units": sight_units,
            "train_idx": train_idx, "held_idx": held_idx,
            "sight_codebook_kind": f"random-real-glimpses-{K_SIGHT}",
            "units_used_train": int(len(set(sight_units[train_idx].tolist()))),
            "units_used_heldout": int(len(set(sight_units[held_idx].tolist())))}


def train_binding(audio: dict, bank: dict, class_to_imageclass: dict,
                  seed: int = 50_050) -> Binding:
    """Run the co-presence stream; class_to_imageclass is world architecture
    (identity for the real cheider, a derangement for the control)."""
    names_by_class: dict[str, list] = {}
    token_by_name = {}
    for row in audio["train"]:
        names_by_class.setdefault(row["label"], []).append(row["name"])
        token_by_name[row["name"]] = row
    images_by_class: dict[str, list[int]] = {}
    for i in bank["train_idx"]:
        images_by_class.setdefault(bank["entries"][i]["syllable"], []).append(i)
    paired_images = {c: images_by_class[class_to_imageclass[c]]
                     for c in names_by_class}
    binding = Binding(audio["n_units"], K_SIGHT)
    for kind, name, img in world.co_presence_stream(
            names_by_class, paired_images, passes=PASSES, seed=seed):
        if kind == "both":
            binding.observe_both(token_by_name[name]["units"],
                                 int(bank["sight_units"][img]))
        elif kind == "sound":
            binding.observe_sound(token_by_name[name]["units"])
        else:
            binding.observe_sight(int(bank["sight_units"][img]))
    return binding


def class_sight_scores(pmi: np.ndarray, bank: dict, classes: list[str]) -> dict:
    """For every class: its held-out images' sight units (the exam board)."""
    board = {}
    for c in classes:
        idx = [i for i in bank["held_idx"]
               if bank["entries"][i]["syllable"] == c]
        board[c] = np.asarray([int(bank["sight_units"][i]) for i in idx])
    return board


def run_exams(pmi: np.ndarray, audio: dict, bank: dict) -> dict:
    classes = audio["classes"]
    board = class_sight_scores(pmi, bank, classes)
    held_by_class = {}
    for row in audio["held"]:
        held_by_class.setdefault(row["label"], []).append(row["units"])

    # Exam A: see (held-out font) -> pick the audio class
    a_truth, a_pred = [], []
    for i in bank["held_idx"]:
        e = bank["entries"][i]
        v = int(bank["sight_units"][i])
        scores = [np.mean([pmi[t, v].mean() for t in held_by_class[c]])
                  for c in classes]
        a_truth.append(classes.index(e["syllable"]))
        a_pred.append(int(np.argmax(scores)))

    # Exam B: hear (held-out audio) -> point at the letter
    b_truth, b_pred = [], []
    for row in audio["held"]:
        s = row["units"]
        scores = [float(np.mean(pmi[np.ix_(s, board[c])])) for c in classes]
        b_truth.append(classes.index(row["label"]))
        b_pred.append(int(np.argmax(scores)))

    def summarise(truth, pred):
        truth = np.asarray(truth); pred = np.asarray(pred)
        per_class = {}
        for k, c in enumerate(classes):
            m = truth == k
            per_class[c] = f"{int((pred[m] == k).sum())}/{int(m.sum())}"
        return {"top1": float((truth == pred).mean()),
                "items": int(len(truth)), "per_class": per_class,
                "_truth": truth, "_pred": pred}

    return {"exam_a_see_to_say": summarise(a_truth, a_pred),
            "exam_b_hear_to_point": summarise(b_truth, b_pred)}


def permutation_null(truth: np.ndarray, pred: np.ndarray,
                     seed: int = 7007) -> dict:
    rng = np.random.default_rng(seed)
    scores = [float((rng.permutation(truth) == pred).mean())
              for _ in range(PERM_DRAWS)]
    return {"draws": PERM_DRAWS, "mean": float(np.mean(scores)),
            "p95": float(np.quantile(scores, 0.95)),
            "max": float(np.max(scores))}


def main() -> None:
    t0 = time.time()
    if not world.MANIFEST.exists():
        world.build()
    audio = audio_unit_sets()
    bank = letter_bank()
    classes = audio["classes"]
    print(f"ears: {audio['queen']} ({audio['n_units']} sound-units) | "
          f"eyes: {bank['sight_codebook_kind']} "
          f"(train uses {bank['units_used_train']}, heldout uses "
          f"{bank['units_used_heldout']})", flush=True)

    identity = {c: c for c in classes}
    binding = train_binding(audio, bank, identity)
    pmi = binding.pmi()
    real = run_exams(pmi, audio, bank)

    # control 1: the wrong cheider — letters deranged w.r.t. sounds
    shifted = dict(zip(sorted(classes), np.roll(sorted(classes), 1)))
    wrong = run_exams(train_binding(audio, bank, shifted).pmi(), audio, bank)

    # control 2: column-shuffled binding
    rng = np.random.default_rng(4242)
    shuffled = pmi[:, rng.permutation(pmi.shape[1])]
    shuf = run_exams(shuffled, audio, bank)

    report = {
        "question": "did the ants learn to READ — bind never-seen letter "
                    "images to never-heard syllable sounds",
        "chance": 1 / len(classes),
        "protocol": "22 classes, 132 held-out decisions per exam; letter "
                    "images in fonts never seen in training; audio tokens "
                    "from the published held-out split; binding = Hebbian "
                    "PMI over co-presence moments only",
        "world": {"passes": PASSES,
                  "moments_total": int(binding.moments),
                  "moments_co_presence": int(binding.co_moments),
                  "train_fonts": world.TRAIN_FONTS,
                  "heldout_fonts": world.HELDOUT_FONTS},
        "ears": {k: audio[k] for k in ("queen", "checkpoint_sha256",
                                       "n_units")},
        "eyes": {k: bank[k] for k in ("sight_codebook_kind",
                                      "units_used_train",
                                      "units_used_heldout")},
        "results": {},
        "controls": {},
        "date": dt.datetime.now().isoformat(timespec="seconds"),
    }
    for exam in ("exam_a_see_to_say", "exam_b_hear_to_point"):
        r = real[exam]
        report["results"][exam] = {
            "top1": r["top1"], "items": r["items"],
            "per_class": r["per_class"],
            "permutation_null": permutation_null(r["_truth"], r["_pred"]),
        }
        report["controls"][exam] = {
            "wrong_cheider_deranged_pairing_top1": wrong[exam]["top1"],
            "column_shuffled_binding_top1": shuf[exam]["top1"],
        }
        print(f"{exam}: top1={r['top1']*100:.1f}% (chance 4.5%) | "
              f"wrong-cheider={wrong[exam]['top1']*100:.1f}% | "
              f"shuffled={shuf[exam]['top1']*100:.1f}% | "
              f"ah={r['per_class']['ah']} aa={r['per_class']['aa']} "
              f"za={r['per_class']['za']}", flush=True)

    report["seconds"] = round(time.time() - t0, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"wrote {OUT} ({report['seconds']}s)")


if __name__ == "__main__":
    main()

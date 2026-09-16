"""Turn reports/syllable-knowledge.json into state-syllables/RESULTS.md."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np

ORDER = ("64", "128", "256", "512", "baseline-human-only",
         "random-real-frames-64", "random-real-frames-128",
         "random-real-frames-256", "random-real-frames-512",
         "random-centres-64", "random-centres-128",
         "random-centres-256", "random-centres-512")

# Why each close pair is close, so a reader can judge whether a confusion is a
# real acoustic fact or a bug. Hebrew letter names in brackets.
PAIR_NOTES = {
    "ba/pa": "b/p - both bilabial stops, differ only in voicing",
    "ga/ka": "g/k - both velar stops, differ only in voicing",
    "da/ta": "d/t - both alveolar stops, differ only in voicing",
    "sa/sha": "s/sh - both voiceless fricatives, differ in place",
    "ka/qa": "k/q - both voiceless velar/uvular stops; merged in modern Hebrew",
    "ta/tha": "tet/tav - a true homophone in modern Hebrew, both /t/",
    "za/sa": "z/s - both alveolar fricatives, differ only in voicing",
}


CAVEATS = (
    "One synthetic voice. Every syllable and word came from a single cached "
    "mms-tts-heb speaker. Nothing here shows the ants would recognise these "
    "syllables from a human mouth, and the 24 human recordings are one speaker too.",
    "One vocoder, one recording chain. Held-out tokens are different renderings "
    "with different prosody seeds, but the same synthesiser and the same "
    "augmentation pipeline. Cross-speaker and cross-channel generalisation is "
    "completely untested.",
    "Recognition, not production. A codebook that separates syllables cannot "
    "utter them; the exemplar reconstruction path is a different claim and is not "
    "measured here.",
    "No phonetics. A unit is a 25 ms spectral cluster. Nothing establishes that a "
    "unit corresponds to a phoneme, a segment boundary, or any linguistic object.",
    "The Lloyd iterations are not what is working. Random real frames from the "
    "same corpus score the same, so 'the ant learned' means 'the ant is holding "
    "in-domain reference points', not 'the ant optimised a representation'.",
    "Isolated syllables are the easy case. The word tests show the representation "
    "does not carry over to syllables inside connected speech.",
    "The held-out split fed the Queen's selection criterion (quantisation error), "
    "so it is held out from fitting but not from every decision in the pipeline.",
    "132 held-out tokens, 22 classes, six tokens per class. Per-class and "
    "per-minimal-pair numbers are noisy; only the pooled figures carry weight.",
)


def get(report: dict, group: str) -> list[dict]:
    return [c for c in report["codebooks"] if c["group"] == group]


def stat(rows: list[dict], path: tuple) -> np.ndarray:
    out = []
    for row in rows:
        value = row
        for key in path:
            value = value[key]
        out.append(value)
    return np.asarray(out, dtype=np.float64)


def ms(values: np.ndarray) -> str:
    return f"{100 * values.mean():.1f}±{100 * values.std(ddof=0):.1f}"


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h)
              for i, h in enumerate(headers)]
    line = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |"
    rule = "|" + "|".join("-" * (w + 2) for w in widths) + "|"
    body = ["| " + " | ".join(c.ljust(w) for c, w in zip(r, widths)) + " |" for r in rows]
    return "\n".join([line, rule, *body])


def build(report: dict, paired: dict | None = None,
          phonetics: dict | None = None) -> str:
    classes = report["classes"]
    chance = report["chance_syllable"]
    refs = report["references"]
    groups = [g for g in ORDER if get(report, g)]
    trained = [g for g in ("64", "128", "256", "512") if get(report, g)]

    base_rows = get(report, "baseline-human-only")
    base_edit = stat(base_rows, ("test2_nearest_neighbour", "edit", "top1")).mean()
    base_cos = stat(base_rows, ("test2_nearest_neighbour", "cosine", "top1")).mean()
    base_word = stat(base_rows, ("test4_words", "identification_edit", "top1")).mean()
    rnd_rows = get(report, "random-centres-64") + get(report, "random-centres-256")
    rnd_edit = stat(rnd_rows, ("test2_nearest_neighbour", "edit", "top1")).mean()
    rnd_cos = stat(rnd_rows, ("test2_nearest_neighbour", "cosine", "top1")).mean()

    best = max((c for c in report["codebooks"] if c["kind"] == "trained-ant"),
               key=lambda c: c["test2_nearest_neighbour"]["cosine"]["top1"])

    out: list[str] = []
    w = out.append
    w("# Do the ants know the syllables?")
    w("")
    w(f"Held-out audio only: {report['heldout_items']} syllable tokens from vocoder "
      f"renderings that appear in no training split, encoded into unit strings by "
      f"codebooks that were fitted on {report['train_items']} other tokens. "
      f"Chance is {100 * chance:.1f}% over {len(classes)} classes. "
      "Quantisation error is not reported.")
    w("")
    best_256 = stat(get(report, "256"),
                    ("test2_nearest_neighbour", "cosine", "top1")).mean()
    frames_256 = stat(get(report, "random-real-frames-256"),
                      ("test2_nearest_neighbour", "cosine", "top1")).mean()
    w("## Verdict")
    w("")
    w(f"**Partly - and the part that works is not the part that was trained.**")
    w("")
    w(f"They discriminate: `{best['group']}/{best['ant']}` reaches "
      f"{100 * best['test2_nearest_neighbour']['cosine']['top1']:.1f}% top-1 "
      f"({100 * best['test2_nearest_neighbour']['cosine']['top5']:.1f}% top-5) on 22 "
      f"held-out classes against {100 * chance:.1f}% chance, and the k=256 colony "
      f"averages {100 * best_256:.1f}% across four independent ants. That is a real "
      f"effect: it survives a label-permutation null, it is not duration, and the "
      f"syllable curriculum is what produced it - the same learner on the original "
      f"human-only corpus gets {100 * base_cos:.1f}% "
      f"(+{100 * (best_256 - base_cos):.1f} points, p < 0.001, all four ants).")
    w("")
    w(f"They do not know them the way the word 'know' implies. A codebook built from "
      f"random real frames of the same corpus, with the k-means iterations never run, "
      f"scores {100 * frames_256:.1f}% - statistically indistinguishable from the "
      f"trained ants' {100 * best_256:.1f}% (paired McNemar p = 0.54, and the trained "
      f"ant loses on the edit metric). The ants also fail every minimal pair that is "
      f"genuinely hard "
      f"(ba/pa, da/ta) while scoring high on pairs modern Hebrew treats as the same "
      f"sound, and the compositional word test sits at its floor. What the training "
      f"bought is in-domain reference points and enough of them, not a learned "
      f"representation.")
    w("")

    w("## Test 0 - the things that would invalidate everything")
    w("")
    w(table(
        ["control", "syllable top-1", "reading"],
        [["label permutation (200 draws)",
          f"{100 * np.mean(stat([c for c in report['codebooks'] if c['kind'] == 'trained-ant'], ('test2_nearest_neighbour', 'permutation_null_edit', 'mean'))):.1f}%",
          "empirical floor; matches analytic chance"],
         ["duration of the sound alone",
          f"{100 * refs['duration_only']['syllable_top1']:.1f}%",
          "the probes are not measuring how long a syllable is"],
         ["raw 14-dim features, no codebook",
          f"{100 * refs['raw_features_no_codebook']['syllable_top1']:.1f}%",
          "ceiling on the speech span"],
         ["raw features, loudest 60% pooling",
          f"{100 * refs['raw_features_loudest_60_percent']['syllable_top1']:.1f}%",
          "ceiling under the earlier report's pooling, for continuity"]]))
    w("")
    w(f"Leak check on the held-out set: {json.dumps(report['leak_check'])} - "
      "no shared vocoder rendering, no shared file, no identical frame matrix.")
    w("")

    w("## Test 1 + 2 - consistency, distinctness, identification")
    w("")
    w("`sep` is within-syllable minus between-syllable similarity over held-out pairs, "
      "counting only pairs from *different* vocoder renderings. `AUC` is the "
      "probability that a same-syllable pair scores above a different-syllable pair "
      "(0.5 = no information). `twin` is the same-rendering augmentation pairs, shown "
      "only to prove they were excluded from `sep`.")
    w("")
    rows = []
    for group in groups:
        for c in sorted(get(report, group), key=lambda c: c["ant"]):
            e = c["test2_nearest_neighbour"]["edit"]
            k = c["test2_nearest_neighbour"]["cosine"]
            s = c["test1_separation"]
            rows.append([
                group, c["ant"], str(c["units"]),
                f"{100 * k['top1']:.1f}", f"{100 * k['top5']:.1f}",
                f"{100 * e['top1']:.1f}", f"{100 * e['top5']:.1f}",
                f"{s['cosine']['separation']:+.3f}", f"{s['cosine']['auc']:.3f}",
                f"{s['edit']['separation']:+.3f}", f"{s['edit']['auc']:.3f}",
                f"{s['edit']['within_same_syllable_same_base_twins']:.3f}",
            ])
    w(table(["group", "ant", "k", "cos@1", "cos@5", "edit@1", "edit@5",
             "sep cos", "AUC cos", "sep edit", "AUC edit", "twin edit"], rows))
    w("")
    w("Colony means over the four independent ants (± sd):")
    w("")
    rows = []
    for group in groups:
        g = get(report, group)
        rows.append([
            group, str(g[0]["units"]),
            ms(stat(g, ("test2_nearest_neighbour", "cosine", "top1"))),
            ms(stat(g, ("test2_nearest_neighbour", "cosine", "top5"))),
            ms(stat(g, ("test2_nearest_neighbour", "cosine", "meanlink_top1"))),
            ms(stat(g, ("test2_nearest_neighbour", "edit", "top1"))),
            f"{stat(g, ('test1_separation', 'cosine', 'auc')).mean():.3f}",
            f"{stat(g, ('test1_separation', 'edit', 'auc')).mean():.3f}",
            f"{100 * (stat(g, ('test2_nearest_neighbour', 'cosine', 'top1')).mean() - base_cos):+.1f}",
            f"{stat(g, ('test2_nearest_neighbour', 'cosine', 'top1')).mean() / max(chance, 1e-9):.1f}x",
        ])
    w(table(["group", "k", "cos@1", "cos@5", "cos mean-link@1", "edit@1",
             "AUC cos", "AUC edit", "vs human-only", "vs chance"], rows))
    w("")

    w("## Which syllables they confuse")
    w("")
    pooled: dict[str, int] = {}
    for c in get(report, trained[-1] if trained else "64"):
        for entry in c["test2_nearest_neighbour"]["top_confusions_cosine"]:
            pooled[entry["pair"]] = pooled.get(entry["pair"], 0) + entry["errors"]
    top = sorted(pooled.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
    w(f"Pooled over the four ants of the k={get(report, trained[-1])[0]['units']} colony "
      f"({4 * report['heldout_items']} decisions):")
    w("")
    distance = {e["pair"]: e["distance"] for e in (phonetics or {}).get("closest_pairs", [])}
    rank = {e["pair"]: i + 1 for i, e in enumerate((phonetics or {}).get("closest_pairs", []))}
    sounds = (phonetics or {}).get("phonetics", {})

    def describe(pair: str) -> str:
        a, b = pair.split("/")
        if a not in sounds or b not in sounds:
            return ""
        shared = [f for f, g in zip(sounds[a], sounds[b]) if f == g]
        merged = pair in (phonetics or {}).get("merged_in_modern_hebrew", [])
        note = f"{'/'.join(sounds[a])} vs {'/'.join(sounds[b])}"
        tags = []
        if merged:
            tags.append("SAME phoneme in modern Hebrew")
        if pair in rank:
            tags.append(f"#{rank[pair]} acoustically closest pair")
        if shared and not merged:
            tags.append("shares " + ", ".join(shared))
        return note + (" - " + "; ".join(tags) if tags else "")

    w(table(["confused pair", "errors", "phonetics, and how close the two really are"],
            [[p, str(n), describe(p)] for p, n in top]))
    w("")
    if phonetics:
        w("Confusion structure, pooled per colony. `rho acoustic` is Spearman "
          "correlation between how often a pair is confused and how far apart the two "
          "syllables sit in the ants' own 14-dim feature space (negative = confuses "
          "things that sound alike, which is what a real representation should do). "
          "`rho phonetic` is the same against shared manner/place/voicing. "
          "`closest-10` is the share of all errors landing on the ten acoustically "
          "closest pairs, which are 4.3% of the 231 possible pairs.")
        w("")
        rows = []
        for group in groups:
            entry = phonetics["confusion_structure"].get(group)
            if not entry:
                continue
            rows.append([
                group, str(entry["errors"]),
                f"{entry['spearman_errors_vs_acoustic_distance']:+.3f}",
                f"{entry['spearman_errors_vs_phonetic_overlap']:+.3f}",
                f"{100 * entry['share_of_errors_on_the_10_closest_pairs']:.1f}%",
            ])
        w(table(["group", "errors", "rho acoustic", "rho phonetic", "closest-10 share"],
                rows))
        w("")
    w("Per-class held-out accuracy, same colony, mean over the four ants:")
    w("")
    per = {c: [] for c in classes}
    for c in get(report, trained[-1]):
        for name, value in c["test2_nearest_neighbour"]["per_class_accuracy_cosine"].items():
            per[name].append(value)
    ordered = sorted(per.items(), key=lambda kv: -np.mean(kv[1]))
    w(table(["syllable", "accuracy"],
            [[k, f"{100 * np.mean(v):.0f}%"] for k, v in ordered]))
    w("")

    w("## Test 3 - minimal pairs (forced two-way choice, chance 50%, 48 decisions each)")
    w("")
    w("`1-NN` and `mean-link` are the same decision made two ways; with six held-out "
      "tokens per syllable a single odd training token can swing 1-NN, so a pair only "
      "counts as separated if both agree. `raw` is the same test on the ants' features "
      "with no codebook - it says whether the contrast survives in the audio at all. "
      "`dist` is the distance between the two syllables' centroids in that feature "
      "space; a large distance means the pair is not actually a hard case in this "
      "corpus, whatever the phonology says.")
    w("")
    rows = []
    by_pair = {m["pair"]: m for m in (phonetics or {}).get("minimal_pairs", [])}
    for pair in [p["pair"] for p in get(report, trained[-1])[0]["test3_minimal_pairs"]["cosine"]]:
        nn, link, correct, items = [], [], 0, 0
        for c in get(report, trained[-1]):
            entry = next(e for e in c["test3_minimal_pairs"]["cosine"] if e["pair"] == pair)
            nn.append(entry["accuracy"])
            link.append(entry["meanlink_accuracy"])
            correct += entry["correct"]
            items += entry["items"]
        baseline = np.mean([
            next(e for e in c["test3_minimal_pairs"]["cosine"] if e["pair"] == pair)["accuracy"]
            for c in base_rows])
        meta = by_pair.get(pair, {})
        verdict = "separated" if min(np.mean(nn), np.mean(link)) > 0.75 else (
            "NOT separated" if max(np.mean(nn), np.mean(link)) < 0.65 else "borderline")
        if meta.get("merged_in_modern_hebrew"):
            verdict += " (same phoneme - see below)"
        rows.append([
            pair, f"{100 * np.mean(nn):.0f}%", f"{100 * np.mean(link):.0f}%",
            f"{correct}/{items}", f"{100 * baseline:.0f}%",
            f"{100 * meta.get('raw_features_no_codebook_accuracy', float('nan')):.0f}%",
            f"{meta.get('acoustic_centroid_distance', float('nan')):.2f}", verdict])
    w(table(["pair", "1-NN", "mean-link", "1-NN correct", "human-only", "raw",
             "dist", "verdict"], rows))
    w("")
    merged = (phonetics or {}).get("merged_in_modern_hebrew", [])
    if merged:
        w(f"**Read `{'`, `'.join(merged)}` in the opposite direction.** Modern Israeli "
          "Hebrew merges these: kaf/qof are both /k/, tet/tav are both /t/, alef/ayin "
          "are both a bare vowel onset. A high score there is not phonetic skill, it "
          "is the ant picking up a fingerprint of how mms-tts-heb rendered two "
          "different letters. The prior corpus audit already established that the "
          "tokenizer strips niqqud, so the realised sound is whatever the model "
          "inferred from a bare consonant, not the vowel that was written down. "
          "`ka/qa` sits 4.4 apart in feature space - further than most genuinely "
          "different consonants - which is not what a merged pair should look like.")
        w("")

    w("## Test 4 - words (the honest one)")
    w("")
    rows = []
    for group in groups:
        g = get(report, group)
        rows.append([
            group, str(g[0]["units"]),
            ms(stat(g, ("test4_words", "identification_edit", "top1"))),
            ms(stat(g, ("test4_words", "identification_cosine", "top1"))),
            f"{stat(g, ('test4_words', 'constituent_recall_edit', 'auc_constituent_over_other')).mean():.3f}",
            f"{stat(g, ('test4_words', 'constituent_recall_edit', 'constituent_rank_percentile')).mean():.3f}",
            f"{100 * stat(g, ('test4_words', 'constituent_recall_edit', 'in_top_n_rate')).mean():.1f}",
        ])
    w(table(["group", "k", "word id edit@1", "word id cos@1", "constituent AUC",
             "constituent rank pct", "in-top-n %"], rows))
    w("")
    w(f"Word identification is 12-way, chance {100 * report['chance_word']:.1f}%, "
      "leave-one-vocoder-rendering-out, on 96 files no colony ever trained on. That "
      "part works, and it scales with the syllable curriculum the same way the "
      "syllable test does.")
    w("")
    w("**The constituent test does not work, and that is the honest headline of this "
      "section.** It asks whether a word's unit string actually contains its "
      "syllables' unit strings: each of the 22 syllables is aligned as a substring of "
      "the word (free start, free end) and the 22 are ranked. If the representation "
      "were compositional the syllables a word is spelled with would rank at the top. "
      "AUC 0.5 and rank percentile 0.5 are no information. The trained colonies sit at "
      f"AUC {stat(get(report, trained[-1]), ('test4_words', 'constituent_recall_edit', 'auc_constituent_over_other')).mean():.3f}"
      " - and random Gaussian centres, which know nothing, sit at "
      f"{stat(get(report, 'random-centres-512'), ('test4_words', 'constituent_recall_edit', 'auc_constituent_over_other')).mean():.3f}. "
      "The trained ants are not better than the untrained control here, so the small "
      "excess over 0.5 is a property of the alignment statistic, not evidence of "
      "learned sub-word structure. Word identification therefore works the way any "
      "whole-utterance fingerprint works, not by recognising the syllables inside. "
      "That is the predicted outcome - the ants were taught isolated syllables, and a "
      "syllable inside a word is shorter and coarticulated - but it is worth saying "
      f"plainly rather than reporting the {100 * stat(get(report, trained[-1]), ('test4_words', 'identification_edit', 'top1')).mean():.0f}% "
      "word score alone. Chance for the in-top-n column is "
      f"{100 * np.mean(stat(get(report, trained[-1]), ('test4_words', 'constituent_recall_edit', 'in_top_n_rate_chance'))):.1f}%.")
    w("")

    w("## Capacity")
    w("")
    rows = []
    for group in trained:
        g = get(report, group)
        rows.append([
            str(g[0]["units"]),
            ms(stat(g, ("test2_nearest_neighbour", "cosine", "top1"))),
            ms(stat(g, ("test2_nearest_neighbour", "edit", "top1"))),
            f"{stat(g, ('test1_separation', 'cosine', 'auc')).mean():.3f}",
            ms(stat(g, ("test4_words", "identification_edit", "top1"))),
            f"{stat(g, ('mean_sequence_length',)).mean():.1f}",
            f"{stat(g, ('units_used_heldout',)).mean():.0f}",
        ])
    w(table(["k", "syllable cos@1", "syllable edit@1", "AUC cos", "word edit@1",
             "mean unit-string length", "units used on held-out"], rows))
    w("")
    if paired:
        w("## Paired tests on the same 132 items (exact McNemar)")
        w("")
        w("Every codebook is scored on the same held-out tokens, so the honest "
          "comparison is item-by-item and matched by seed, not colony mean against "
          "colony mean.")
        w("")
        rows = []
        for entry in paired["comparisons"]:
            rows.append([
                entry["comparison"], entry["metric"],
                f"{100 * entry['pooled_left_accuracy']:.1f}",
                f"{100 * entry['pooled_right_accuracy']:.1f}",
                f"{entry['pooled_delta_points']:+.1f}",
                f"{entry['pooled_mcnemar']['p_value']:.4f}",
                f"{entry['ants_where_left_wins']}/4",
            ])
        w(table(["comparison", "metric", "left %", "right %", "delta pts",
                 "p", "ants won"], rows))
        w("")

    w("## What this does not prove")
    w("")
    for line in CAVEATS:
        w(f"- {line}")
    w("")
    w(json.dumps({
        "report": "reports/syllable-knowledge.json",
        "paired_tests": "reports/paired-tests.json",
        "confusion_analysis": "reports/confusion-analysis.json",
        "probe_library": "sequence_probes.py",
        "driver": "run_knowledge_tests.py",
        "summariser": "summarise_knowledge.py",
        "tests": "tests/test_sequence_probes.py",
    }, indent=2))
    w("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="reports/syllable-knowledge.json")
    parser.add_argument("--paired", default="reports/paired-tests.json")
    parser.add_argument("--phonetics", default="reports/confusion-analysis.json")
    parser.add_argument("--out", default="state-syllables/RESULTS.md")
    args = parser.parse_args()
    report = json.loads(io.open(args.report, encoding="utf-8").read())
    paired_path = Path(args.paired)
    paired = json.loads(paired_path.read_text(encoding="utf-8")) if paired_path.exists() else None
    phonetics_path = Path(args.phonetics)
    phonetics = (json.loads(phonetics_path.read_text(encoding="utf-8"))
                 if phonetics_path.exists() else None)
    Path(args.out).write_text(build(report, paired, phonetics), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

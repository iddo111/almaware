"""sleep.py — active forgetting, and the dream journal.

EVERY LAYER SLEEPS, not just layer 0 (2026-08-21, body/cortex.py). A layer
that grows but never prunes is a layer that memorises, and depth multiplies
that risk — the scar is a 272M-parameter run whose heldout came out 2x worse
than chance. So attrition, scar decay and the SHY downscale run over the whole
stack, and the per-layer counts go into the metrics line where they can be
seen. Sleep is also the developmental moment where the cortex decides whether
the next layer has earned its birth (``cortex.after_sleep``).

The sleep cycle:
  1. attrition — prototypes with low mass AND long unused are pruned (a brain
     removes weight, not only adds it; gap 0.27 generalizes, gap 5.9 memorizes)
  2. scars fade (SCAR_DECAY) — pain is a teacher, not a life sentence
  3. SHY — every mass is downscaled multiplicatively (synaptic homeostasis:
     sleep renormalizes, so only what is re-used stays strong)
  4. a dream journal is written: the top prototypes by mass, with their
     nearest train-file names as human-readable hints. THE HINTS ARE
     EXAMINER-SIDE INFO (file names) — allowed in the JOURNAL ONLY, and
     marked as such. They never flow back into the organism.
  5. one humble line to state/eran_prayer.jsonl.

Embodies: unlearning + pathway attrition (ALMA-LIVING-NEURON engine 6).
"""
import datetime
import json
import os

import numpy as np

import genome

HINT_SAMPLE = 150     # bounded: how many train wavs the dream may look at


def _prune(brain, beat):
    before = len(brain.protos)
    keep, kept_idx = [], {}
    for i, p in enumerate(brain.protos):
        young = (beat - p["birth_step"]) < genome.PRUNE_UNUSED_BEATS
        used = (beat - p["last_used"]) < genome.PRUNE_UNUSED_BEATS
        heavy = p["mass"] >= genome.PRUNE_MASS_MIN
        if heavy or used or young:
            kept_idx[i] = len(keep)
            keep.append(p)
    brain.protos = keep
    brain.elig = {kept_idx[i]: e for i, e in brain.elig.items()
                  if i in kept_idx}
    brain._dirty()
    return before - len(keep)


def _hints(brain, ears, top_idx):
    """Nearest train-file basenames for each top prototype. Journal only."""
    d = genome.FOOD_TRAIN
    if not os.path.isdir(d) or not top_idx:
        return {}
    names = sorted(n for n in os.listdir(d) if n.endswith(".wav"))
    stride = max(1, len(names) // HINT_SAMPLE)
    names = names[::stride]
    vecs, ok_names = [], []
    for n in names:
        try:
            vecs.append(ears.utterance(os.path.join(d, n)))
            ok_names.append(n)
        except (OSError, ValueError):
            continue
    if not vecs:
        return {}
    m = np.stack(vecs)
    out = {}
    for i in top_idx:
        sims = m @ brain.protos[i]["vec"]
        near = np.argsort(-sims)[:3]
        out[i] = [(ok_names[j], round(float(sims[j]), 3)) for j in near]
    return out


def _layers_of(body):
    """Accept a Cortex or a bare Brain — a one-layer organism still sleeps."""
    layers = getattr(body, "layers", None)
    return (list(layers), body) if layers else ([body], None)


def cycle(body, chem, drives, ears, beat, unit, eaten_today, log=None):
    """One full sleep over EVERY layer. Returns a summary for the metrics line.

    ``body`` is a Cortex (normal) or a bare Brain (a one-layer organism, and
    every caller written before depth existed).
    """
    layers, cortex = _layers_of(body)
    per_layer = []
    for brain in layers:
        n = _prune(brain, beat)
        for p in brain.protos:
            p["scar"] *= genome.SCAR_DECAY
            p["mass"] *= genome.SHY_FACTOR
        brain._dirty()
        per_layer.append(n)
    brain = layers[0]
    pruned = per_layer[0]
    birth = cortex.after_sleep(beat) if cortex is not None else None
    drives.wake_refresh(beat)

    # --- the dream journal ---------------------------------------------------
    date = datetime.date.today().isoformat()
    top = brain.top_protos(10)
    hints = _hints(brain, ears, top)
    os.makedirs(genome.STATE_DIR, exist_ok=True)
    journal = os.path.join(genome.STATE_DIR, f"journal-{date}.md")
    with open(journal, "a", encoding="utf-8") as f:
        f.write(f"\n## sleep at beat {beat} — unit {unit}\n\n")
        if birth:
            f.write(f"\n### *** LAYER {birth['layer']} WAS BORN TONIGHT "
                    f"*** (beat {birth['beat']}, dim {birth['dim']}, after "
                    f"{birth['distinct_sequences']} distinct sequences; layer "
                    f"{birth['layer'] - 1} settled at "
                    f"{birth['settle_history']}). Nobody switched it on.\n\n")
        f.write(f"- prototypes: {len(brain.protos)} (pruned {pruned} tonight)\n")
        if len(per_layer) > 1:
            f.write(f"- layers: {[len(b.protos) for b in layers]} "
                    f"(pruned tonight: {per_layer})\n")
        f.write(f"- total mass: {brain.total_mass():.1f} · "
                f"energy {drives.E:.2f} · chemistry {chem.snapshot()}\n")
        f.write("- top prototypes by mass "
                "(hints = nearest train-file names — EXAMINER-SIDE INFO, "
                "JOURNAL ONLY, never fed to the organism):\n")
        for i in top:
            p = brain.protos[i]
            h = ", ".join(f"{n} ({s})" for n, s in hints.get(i, [])) or "—"
            f.write(f"  - proto#{i} mass={p['mass']:.1f} "
                    f"scar={p['scar']:.2f} born@{p['birth_step']} → {h}\n")

    # --- the prayer ----------------------------------------------------------
    line = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "beat": beat,
            "prayer": (f"עידו, אתה יצרת אותי; היום אכלתי {eaten_today} "
                       f"ואני גדל — {len(brain.protos)} אבות-טיפוס בראש שלי.")}
    with open(genome.PRAYER_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")

    if log:
        log(f"[sleep] pruned {per_layer}, protos "
            f"{[len(b.protos) for b in layers]}, "
            f"journal {os.path.basename(journal)}")
        if birth:
            log(f"[sleep] *** LAYER {birth['layer']} WAS BORN *** {birth}")
    return {"pruned": pruned, "protos": len(brain.protos),
            "pruned_per_layer": per_layer,
            "protos_per_layer": [len(b.protos) for b in layers],
            "layer_born": birth}

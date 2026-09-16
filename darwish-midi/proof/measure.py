"""measure.py — the v0 proof (DESIGN.md §12). Numbers in a file, or it did not
happen. Every part that needs data or tools not present on this machine is
marked "not-run" with an honest reason — never faked, never guessed.

Prints the uniform (chance) baseline FIRST, as the floor of honesty, then runs
whatever is measurable here and writes results/results-v0-<date>.json (and,
if this is the PC mirror, that file already sits where DESIGN.md expects it —
D:\\CLAUDE\\darwish-midi\\proof\\).

Sections:
  PASS-1  heldout bits/16th-step vs an independent unigram baseline
  PASS-2  DA-gating ON vs OFF, matched shard budget, whichever wins is recorded
  PASS-3  the newest song: valid MThd/MTrk, nonzero-RMS wav, kick-on-downbeat %
  PASS-4  one synthetic -1 tap through a real saved trace: motif p before/after
  PASS-5  archive respected: no darwish-* (archived) unit is active
"""
import datetime
import glob
import json
import math
import os
import shutil
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):           # Hebrew/emoji-safe console
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, ROOT)

import genome                                     # noqa: E402
from brain import Brain                           # noqa: E402
from chemistry import Chemistry                   # noqa: E402
from ears import Ears                              # noqa: E402
import critic as critic_mod                        # noqa: E402
from darwish_life import assert_not_archive         # noqa: E402

FOOD_DIR = os.path.join(ROOT, "food")
SPLIT_PATH = os.path.join(FOOD_DIR, "split.json")
STATE_DIR = os.path.join(ROOT, "state")
BRAIN_FILE = os.path.join(STATE_DIR, "brain.json.gz")
SETPOINTS_PATH = os.path.join(STATE_DIR, "setpoints.json")
OUTBOX_DIR = os.path.join(ROOT, "songs", "outbox")
RESULTS_DIR = os.path.join(ROOT, "results")

UNIFORM_BPT = math.log2(genome.VOCAB)             # the floor of honesty (~6.7549)
TORCH_REF_BPT = 3.52                              # archived torch run, inferred nats->bits
ABLATION_SHARDS = 20                              # matched-budget A/B, kept small on purpose


def _log(msg):
    print(msg, flush=True)


# ------------------------------------------------------------------ PASS-1 --
def heldout_bits(brain, ears, names):
    """Teacher-forced (learn=False) cross-entropy. Steps = non-structural
    tokens only (one token per 16th note); structural tokens still feed the
    context so bar/phrase phase stays honest, they just aren't counted as
    a 'step'. Returns (bits_per_step, bits_per_token, n_steps)."""
    saved_hist = list(brain.history)
    brain.history = [genome.TOK_BOS]
    total_step_bits, n_steps = 0.0, 0
    total_tok_bits, n_tok = 0.0, 0
    for name in names:
        for tok, phase in ears.feed(name):
            p = brain.p_of(tok, phase)
            bits = -math.log2(p)
            total_tok_bits += bits
            n_tok += 1
            if tok not in genome.STRUCTURAL:
                total_step_bits += bits
                n_steps += 1
            brain.history.append(tok)
            if len(brain.history) > genome.ORDER_MAX:
                brain.history.pop(0)
    brain.history = saved_hist
    bpt_step = total_step_bits / max(1, n_steps)
    bpt_tok = total_tok_bits / max(1, n_tok)
    return bpt_step, bpt_tok, n_steps


def unigram_baseline_bpt(ears, train_names, heldout_names):
    """An independent unigram model fit on TRAIN, evaluated on HELDOUT —
    honest cross-entropy, not the live brain's online unigram floor."""
    counts = [1.0] * genome.VOCAB                # add-one smoothing
    for name in train_names:
        for tok in ears.load(name)["tokens"]:
            counts[tok] += 1.0
    total = sum(counts)
    bits, n = 0.0, 0
    for name in heldout_names:
        for tok in ears.load(name)["tokens"]:
            if tok in genome.STRUCTURAL:
                continue
            bits += -math.log2(counts[tok] / total)
            n += 1
    return bits / max(1, n)


# ------------------------------------------------------------------ PASS-2 --
def da_ablation(ears):
    """Matched-budget A/B on a FIXED shard order (same data both arms):
    DA-gated (normal) vs DA neutralized (flat Hebbian counts, i.e. the
    ablated lattice — plasticity_gain() == ach*(1+0), constant). Whichever
    wins on heldout bits/step is recorded — a negative result for DA is a
    result, not a failure."""
    shards = ears.train[:ABLATION_SHARDS]
    if not shards or not ears.heldout:
        return {"status": "not-run", "reason": "not enough train/heldout shards"}

    def run(ablate_da):
        b, chem = Brain(), Chemistry()
        if ablate_da:
            chem.observe_surprise = lambda bits: None    # DA never updates
        for name in shards:
            for tok, phase in ears.feed(name):
                b.digest(tok, phase, chem, learn=True)
        return b

    b_on, b_off = run(False), run(True)
    bpt_on, _, _ = heldout_bits(b_on, ears, ears.heldout)
    bpt_off, _, _ = heldout_bits(b_off, ears, ears.heldout)
    winner = "on" if bpt_on < bpt_off else "off"
    return {"status": "measured", "on": round(bpt_on, 4), "off": round(bpt_off, 4),
            "shards_used": len(shards), "winner": winner}


# ------------------------------------------------------------------ PASS-3 --
def voice_checks():
    """The newest song triplet: valid MThd/MTrk bytes, nonzero WAV RMS,
    kick-on-downbeat % next to the corpus value."""
    wavs = sorted(glob.glob(os.path.join(OUTBOX_DIR, "*.wav")))
    if not wavs:
        return {"status": "not-run", "reason": "no song in songs/outbox yet"}
    wav_path = wavs[-1]
    song_id = os.path.splitext(os.path.basename(wav_path))[0]
    mid_path = os.path.join(OUTBOX_DIR, song_id + ".mid")
    tok_path = os.path.join(OUTBOX_DIR, song_id + ".tokens.json")

    midi_valid = False
    if os.path.exists(mid_path):
        with open(mid_path, "rb") as f:
            head = f.read(64)
        midi_valid = head[:4] == b"MThd" and b"MTrk" in head
    midi_size = os.path.getsize(mid_path) if os.path.exists(mid_path) else 0

    with open(wav_path, "rb") as f:
        wav_bytes = f.read()
    rms = _wav_rms(wav_bytes)

    kick_pct = corpus_kick_pct = None
    if os.path.exists(tok_path):
        with open(tok_path, "r", encoding="utf-8") as f:
            tokens = json.load(f)["tokens"]
        stats = critic_mod._stats(tokens)
        if stats and os.path.exists(SETPOINTS_PATH):
            critic = critic_mod.Critic(SETPOINTS_PATH)
            kick_pct = round(100.0 * stats["downbeat_affinity"][critic.kick_bit], 1)
            corpus_kick_pct = round(100.0 * critic.sp["downbeat_affinity"][critic.kick_bit], 1)

    return {"status": "measured", "song": f"songs/outbox/{song_id}.mid",
            "midi_header_valid": midi_valid, "midi_bytes": midi_size,
            "wav_rms_nonzero": rms > 0.0, "wav_rms": round(rms, 4),
            "kick_on_downbeat_pct": kick_pct, "corpus_kick_on_downbeat_pct": corpus_kick_pct}


def _wav_rms(wav_bytes):
    import struct
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        return 0.0
    i, data = 12, None
    while i + 8 <= len(wav_bytes):
        cid, csize = wav_bytes[i:i + 4], int.from_bytes(wav_bytes[i + 4:i + 8], "little")
        if cid == b"data":
            data = wav_bytes[i + 8:i + 8 + csize]
            break
        i += 8 + csize + (csize % 2)
    if not data:
        return 0.0
    n = len(data) // 2
    if n == 0:
        return 0.0
    total = 0
    for k in range(0, n * 2, 2):
        s = struct.unpack_from("<h", data, k)[0]
        total += s * s
    return math.sqrt(total / n) / 32768.0


# ------------------------------------------------------------------ PASS-4 --
def unlearning_smoke(ears):
    """One synthetic 👎 through the newest song's REAL saved trace, using the
    real payout path (brain.pay_trace at ACh=ACH_PARENT, eta=ETA_PARENT) —
    motif re-emission probability before/after, plus heldout collateral."""
    if not os.path.exists(BRAIN_FILE):
        return {"status": "not-run", "reason": "no trained brain (state/brain.json.gz) yet"}
    traces = sorted(glob.glob(os.path.join(OUTBOX_DIR, "*.trace.json")))
    if not traces:
        return {"status": "not-run", "reason": "no song trace yet"}
    trace_path = traces[-1]
    song_id = os.path.basename(trace_path)[:-len(".trace.json")]
    tok_path = os.path.join(OUTBOX_DIR, song_id + ".tokens.json")
    if not os.path.exists(tok_path):
        return {"status": "not-run", "reason": f"no tokens.json for {song_id}"}

    with open(trace_path, "r", encoding="utf-8") as f:
        trace = json.load(f)["trace"]
    with open(tok_path, "r", encoding="utf-8") as f:
        tokens = json.load(f)["tokens"]

    motif = [t for t in tokens if t not in genome.STRUCTURAL][:8]
    if len(motif) < 2:
        return {"status": "not-run", "reason": "song too short for a motif"}
    ctx, target = motif[:-1], motif[-1]

    brain = Brain.load(BRAIN_FILE)
    chem = Chemistry()

    collateral_pct = None
    bpt_before = None
    if ears is not None and ears.heldout:
        bpt_before, _, _ = heldout_bits(brain, ears, ears.heldout)

    brain.history = ctx[-genome.ORDER_MAX:]
    p_before = brain.p_of(target, 0)

    chem.mode(genome.ACH_PARENT)
    paid, missing = brain.pay_trace(trace, -1.0 * genome.V_TAP, genome.ETA_PARENT, chem)

    brain.history = ctx[-genome.ORDER_MAX:]
    p_after = brain.p_of(target, 0)

    if bpt_before is not None:
        bpt_after, _, _ = heldout_bits(brain, ears, ears.heldout)
        collateral_pct = round(100.0 * abs(bpt_after - bpt_before) / max(bpt_before, 1e-9), 3)

    drop_pct = round(100.0 * (p_before - p_after) / max(p_before, 1e-12), 2)
    return {"status": "measured", "song_id": song_id,
            "motif_p_before": round(p_before, 6), "motif_p_after": round(p_after, 6),
            "drop_pct": drop_pct, "paid_synapses": paid, "missing_synapses": missing,
            "collateral_heldout_delta_pct": collateral_pct}


# ------------------------------------------------------------------ PASS-5 --
def archive_untouched_check():
    if not shutil.which("systemctl"):
        return {"status": "not-run", "reason": "systemctl unavailable on this OS (PC mirror)"}
    try:
        out = subprocess.run(
            ["systemctl", "--user", "list-units", "darwish-*", "--all", "--no-legend"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        return {"status": "not-run", "reason": f"systemctl call failed: {e}"}
    active = [ln for ln in out.stdout.splitlines() if " active " in ln or " running " in ln]
    return {"status": "measured", "archive_untouched": len(active) == 0,
            "active_darwish_units": active}


# --------------------------------------------------------------------- main
def main():
    _log(f"uniform (chance) bits/step: {UNIFORM_BPT:.4f}  (log2 of VOCAB={genome.VOCAB})")

    results = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "uniform_bpt": round(UNIFORM_BPT, 4),
        "torch_ref_bpt": TORCH_REF_BPT,
        "torch_ref_units": "inferred nats->bits (2.4407 nats CE), external reference only",
    }

    ears = None
    if os.path.exists(SPLIT_PATH):
        ears = Ears(FOOD_DIR, SPLIT_PATH)
    else:
        _log(f"[measure] no {SPLIT_PATH} — run prep/adopt_archive.sh on eran4 first")

    # PASS-1 -------------------------------------------------------------
    brain = Brain.load(BRAIN_FILE) if os.path.exists(BRAIN_FILE) else None
    if brain is not None:
        results["synapses"] = brain.mass
        results["brain_gz_mb"] = round(os.path.getsize(BRAIN_FILE) / 1e6, 3)
    else:
        results["synapses"] = "not-run"
        results["brain_gz_mb"] = "not-run"

    if brain is not None and ears is not None and ears.heldout:
        bpt_step, bpt_tok, n_steps = heldout_bits(brain, ears, ears.heldout)
        uni_bpt = unigram_baseline_bpt(ears, ears.train, ears.heldout)
        results["heldout_bits_per_step"] = round(bpt_step, 4)
        results["heldout_bpt"] = round(bpt_tok, 4)
        results["unigram_bpt"] = round(uni_bpt, 4)
        results["heldout_steps_measured"] = n_steps
        pass1 = bpt_step < 0.8 * uni_bpt
    else:
        results["heldout_bits_per_step"] = "not-run"
        results["heldout_bpt"] = "not-run"
        results["unigram_bpt"] = "not-run"
        pass1 = "not-run"

    # tokens_eaten from organs.json if present -----------------------------
    organs_path = os.path.join(STATE_DIR, "organs.json")
    if os.path.exists(organs_path):
        with open(organs_path, "r", encoding="utf-8") as f:
            results["tokens_eaten"] = json.load(f).get("tokens_eaten", "not-run")
    else:
        results["tokens_eaten"] = "not-run"

    # PASS-2 ---------------------------------------------------------------
    if ears is not None:
        da = da_ablation(ears)
    else:
        da = {"status": "not-run", "reason": "no corpus adopted yet"}
    results["da_ablation_bits_per_step"] = da
    pass2 = True if da.get("status") == "measured" else "not-run"

    # PASS-3 ---------------------------------------------------------------
    voice = voice_checks()
    results.update({k: v for k, v in voice.items() if k != "status"})
    if voice["status"] == "measured":
        pass3 = (voice["midi_header_valid"] and voice["midi_bytes"] > 1000
                 and voice["wav_rms_nonzero"]
                 and (voice["kick_on_downbeat_pct"] is None
                      or voice["kick_on_downbeat_pct"] >= 90))
    else:
        pass3 = "not-run"
        results["song"] = "not-run"

    # PASS-4 ---------------------------------------------------------------
    smoke = unlearning_smoke(ears)
    results["unlearning_smoke"] = smoke
    if smoke["status"] == "measured":
        results["motif_p_before"] = smoke["motif_p_before"]
        results["motif_p_after"] = smoke["motif_p_after"]
        results["collateral_heldout_delta_pct"] = smoke["collateral_heldout_delta_pct"]
        collateral_ok = (smoke["collateral_heldout_delta_pct"] is None
                          or smoke["collateral_heldout_delta_pct"] < 5.0)
        pass4 = smoke["drop_pct"] >= 50.0 and collateral_ok
    else:
        results["motif_p_before"] = "not-run"
        results["motif_p_after"] = "not-run"
        results["collateral_heldout_delta_pct"] = "not-run"
        pass4 = "not-run"

    # PASS-5 ---------------------------------------------------------------
    archive_check = archive_untouched_check()
    results["archive_untouched"] = archive_check.get("archive_untouched", "not-run")
    results["archive_check_detail"] = archive_check
    pass5 = archive_check.get("archive_untouched", "not-run")

    results["pass"] = {"PASS-1_fluency": pass1, "PASS-2_da_ablation_measured": pass2,
                       "PASS-3_voice": pass3, "PASS-4_unlearning_smoke": pass4,
                       "PASS-5_respect": pass5}
    results["notes"] = [
        "Any field reading 'not-run' means the data/tool needed was not present on THIS "
        "machine — it is an honest gap, never a fabricated number.",
        "DA ablation uses a fixed matched budget of the first "
        f"{ABLATION_SHARDS} train shards (both arms see identical data in identical "
        "order) for tractability, not the full 156-shard corpus.",
    ]

    os.makedirs(RESULTS_DIR, exist_ok=True)
    assert_not_archive(RESULTS_DIR)
    date = datetime.datetime.now().strftime("%Y%m%d")
    out_path = os.path.join(RESULTS_DIR, f"results-v0-{date}.json")
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    os.replace(tmp, out_path)
    _log(f"[measure] wrote {out_path}")
    _log(json.dumps(results["pass"], indent=1))
    return results


if __name__ == "__main__":
    main()

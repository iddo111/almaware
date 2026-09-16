"""Does sociality actually help, or does any extra audio help?

A four-condition experiment harness for the tribal-fire hypothesis
("many ants forming social bonds increases learning exponentially").
It imports the production modules and never modifies them.

    SOLO       real training audio only                      (baseline)
    SELF_ECHO  real audio + the ant's OWN synthesized audio   (critical control)
    SOCIAL     real audio + OTHER ants' synthesized audio     (the hypothesis)
    NOISE      real audio + phase-randomised audio            (structure destroyed)

The design rests on three invariants, each asserted in code:

1. VOLUME MATCHING. SELF_ECHO, SOCIAL and NOISE add exactly the same number of
   audio samples to every ant, every round. The added audio is built from a
   condition-independent "segment plan": a fixed list of real training-audio
   windows, one per slot. A reconstruction's length depends only on the length
   of its source window, never on the codebook that produced it, so slot k
   contributes an identical sample count in every condition and for every ant.
   If SOCIAL beats SOLO but SELF_ECHO and NOISE do too, the effect was data
   quantity, not sociality.

2. VOLUME IS ALSO MATCHED ACROSS COLONY SIZES. The total added budget is a
   fixed proportion of the real training audio, split into (colony_size - 1)
   slots. A colony of 8 therefore hears the same NUMBER OF SAMPLES as a colony
   of 2, from more distinct voices. Colony size varies sociality, not diet.

3. HELD-OUT ERROR IS ALWAYS MEASURED ON REAL HUMAN RECORDINGS ONLY. The
   held-out folder is verified against the corpus manifest before every single
   measurement, and every synthesized sample is checked never to collide with
   a held-out or evaluation recording. Synthesized audio exists only inside the
   work directory and only ever enters a training mix.

Round 0 is a real-audio-only bootstrap and is identical across conditions for a
given replicate; rounds 1..N are the treatment rounds. Each round retrains from
scratch on that round's mix, exactly as fire.run_cycle does, so added audio does
not accumulate across rounds.

CLI:
    python experiments/sociality/run_experiment.py \
        --recordings recordings --manifest recordings/manifest.json \
        --condition SOCIAL --colony-size 4 --rounds 5 --replicate 0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from acoustic_units import (  # noqa: E402
    EXEMPLAR_RATE, build_checkpoint, frame_geometry, load_wav, reconstruct,
    resample_samples, write_json_atomic, write_wav_atomic,
)
from corpus import validate_manifest  # noqa: E402

EXPERIMENT_FORMAT = 1
CONDITIONS = ("SOLO", "SELF_ECHO", "SOCIAL", "NOISE")
MATCHED_CONDITIONS = ("SELF_ECHO", "SOCIAL", "NOISE")
COLONY_SIZES = (2, 4, 8)
DEFAULT_ROUNDS = 5
DEFAULT_UNITS = 64
DEFAULT_SYNTHETIC_PROPORTION = 0.3
VOLUME_TOLERANCE = 0.03
NOISE_PRODUCER = "phase-randomised-noise"


# --------------------------------------------------------------------------
# seeds
# --------------------------------------------------------------------------

def ant_seed(replicate: int, index: int) -> int:
    """Deterministic per-ant seed. Depends on replicate and colony index only.

    Two ants in the same colony therefore never share a seed, and the same ant
    index carries the same seed across all four conditions so the conditions
    stay comparable.
    """
    if replicate < 0 or index < 0:
        raise ValueError("replicate and ant index must be non-negative")
    key = f"voice-ant-farm/sociality/replicate={replicate}/ant={index}"
    digest = hashlib.sha256(key.encode()).digest()
    return int.from_bytes(digest[:4], "big") % 2_147_483_647


def colony_seeds(replicate: int, colony_size: int) -> list[int]:
    seeds = [ant_seed(replicate, index) for index in range(colony_size)]
    if len(set(seeds)) != colony_size:
        raise ValueError("every ant in a colony requires a distinct random seed")
    return seeds


def colony_ants(colony_size: int) -> list[str]:
    return [f"ant-{index:02d}" for index in range(colony_size)]


def noise_seed(replicate: int, ant_index: int, round_index: int, slot: int) -> int:
    key = (
        f"voice-ant-farm/sociality/noise/replicate={replicate}"
        f"/ant={ant_index}/round={round_index}/slot={slot}"
    )
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")


# --------------------------------------------------------------------------
# volume-matched segment plan
# --------------------------------------------------------------------------

def reconstruction_sample_count(audio) -> int:
    """Length of reconstruct()'s output, which depends only on the source.

    This is what makes volume matching exact: no codebook, no ant and no
    condition can change how many samples a given source window synthesizes to.
    """
    samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    frame, hop = frame_geometry(EXEMPLAR_RATE)
    if len(samples) < frame:
        raise ValueError("source is shorter than one analysis frame")
    frames = 1 + (len(samples) - frame) // hop
    return (frames - 1) * hop + frame


def real_training_timeline(train_folder: Path) -> np.ndarray:
    paths = sorted(train_folder.glob("*.wav"))
    if not paths:
        raise ValueError(f"no real training audio in {train_folder}")
    pieces = []
    for path in paths:
        audio = load_wav(path)
        pieces.append(resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE))
    return np.concatenate(pieces)


def segment_lengths(timeline_samples: int, slots: int, proportion: float) -> tuple[list[int], bool]:
    """Split a fixed added-audio budget into `slots` windows of distinct length.

    Distinct lengths guarantee distinct synthesized PCM, which matters because
    acoustic_units.dataset() de-duplicates a training folder by PCM hash: two
    identical added files would silently halve one condition's real volume.
    """
    if slots < 1:
        raise ValueError("a colony needs at least one donation slot")
    if not 0.0 < proportion < 1.0:
        raise ValueError("synthetic proportion must be in (0, 1)")
    frame, _ = frame_geometry(EXEMPLAR_RATE)
    minimum = EXEMPLAR_RATE // 4 + frame
    step = frame
    budget = round(timeline_samples * proportion / (1.0 - proportion))
    base = round(budget / slots - (slots - 1) * step / 2)
    clamped = base < minimum
    base = max(base, minimum)
    lengths = [base + index * step for index in range(slots)]
    if max(lengths) > timeline_samples:
        raise ValueError(
            "real training audio is too short for this colony size and "
            "synthetic proportion; lower --synthetic-proportion or add audio"
        )
    return lengths, clamped


def build_segment_plan(
    train_folder: Path, segment_root: Path, slots: int, proportion: float,
    timeline: np.ndarray | None = None,
) -> list[dict]:
    """One real-audio window per donation slot, shared by every condition.

    The windows are cut from the concatenated real training audio, so they are
    real human speech; only their reconstructions ever reach a training mix.
    """
    if timeline is None:
        timeline = real_training_timeline(train_folder)
    lengths, clamped = segment_lengths(len(timeline), slots, proportion)
    segment_root.mkdir(parents=True, exist_ok=True)
    plan = []
    cursor = 0
    for slot, length in enumerate(lengths):
        indexes = (np.arange(cursor, cursor + length) % len(timeline))
        window = timeline[indexes]
        cursor = (cursor + length) % len(timeline)
        path = segment_root / f"segment-{slot:02d}.wav"
        if not path.exists():
            write_wav_atomic(path, window, EXEMPLAR_RATE)
        segment = load_wav(path)
        if len(segment.samples) != length:
            raise ValueError(f"segment {slot} was not written at its planned length")
        plan.append({
            "slot": slot,
            "path": path,
            "segment_samples": int(length),
            "segment_pcm_sha256": segment.pcm_sha256,
            "synthetic_samples": reconstruction_sample_count(segment),
            "clamped": clamped,
        })
    counts = [item["synthetic_samples"] for item in plan]
    if len(set(counts)) != len(counts):
        raise ValueError("donation slots must synthesize distinct sample counts")
    return plan


def plan_total_samples(plan: list[dict]) -> int:
    return sum(item["synthetic_samples"] for item in plan)


def serialisable_plan(plan: list[dict]) -> list[dict]:
    return [
        {k: v for k, v in item.items() if k != "path"} | {"segment": item["path"].name}
        for item in plan
    ]


# --------------------------------------------------------------------------
# synthesis
# --------------------------------------------------------------------------

def speak_segment(checkpoint: dict, segment_path: Path, out_path: Path) -> dict:
    """One ant reconstructs one real segment through its own codebook."""
    source = load_wav(segment_path)
    samples, _unit_ids = reconstruct(source, checkpoint)
    write_wav_atomic(out_path, samples, checkpoint["exemplar_rate"])
    audio = load_wav(out_path)
    return {
        "pcm_sha256": audio.pcm_sha256,
        "sample_count": int(len(audio.samples)),
        "sample_rate": audio.rate,
    }


def phase_randomised(samples: np.ndarray, target_samples: int, seed: int) -> np.ndarray:
    """Destroy temporal structure, keep the magnitude spectrum (and so the RMS).

    The control for "is it the structure of another voice, or just spectrally
    similar extra audio?"
    """
    x = np.asarray(samples[:target_samples], dtype=np.float64)
    if len(x) != target_samples:
        raise ValueError("not enough source samples to build volume-matched noise")
    spectrum = np.fft.rfft(x)
    magnitude = np.abs(spectrum)
    rng = np.random.default_rng(seed)
    phase = rng.uniform(-np.pi, np.pi, size=magnitude.shape)
    phase[0] = 0.0
    if len(x) % 2 == 0:
        phase[-1] = 0.0
    scrambled = np.fft.irfft(magnitude * np.exp(1j * phase), n=len(x))
    source_rms = float(np.sqrt(np.mean(x * x)))
    scrambled_rms = float(np.sqrt(np.mean(scrambled * scrambled)))
    if scrambled_rms > 0.0:
        scrambled *= source_rms / scrambled_rms
    return np.clip(scrambled, -1.0, 1.0).astype(np.float32)


def scramble_segment(
    segment_path: Path, target_samples: int, seed: int, out_path: Path,
) -> dict:
    segment = load_wav(segment_path)
    canonical = resample_samples(segment.samples, segment.rate, EXEMPLAR_RATE)
    write_wav_atomic(out_path, phase_randomised(canonical, target_samples, seed), EXEMPLAR_RATE)
    audio = load_wav(out_path)
    return {
        "pcm_sha256": audio.pcm_sha256,
        "sample_count": int(len(audio.samples)),
        "sample_rate": audio.rate,
    }


# --------------------------------------------------------------------------
# held-out purity
# --------------------------------------------------------------------------

def folder_pcm_hashes(folder: Path) -> set[str]:
    return {load_wav(path).pcm_sha256 for path in sorted(folder.glob("*.wav"))}


def manifest_split_hashes(manifest: dict, split: str) -> set[str]:
    return {
        entry["pcm_sha256"] for entry in manifest.get("entries", [])
        if entry.get("split") == split
    }


def assert_heldout_is_real(heldout_folder: Path, allowed_pcm_sha256: set[str]) -> set[str]:
    """The measurement rule, enforced before every single measurement."""
    if not allowed_pcm_sha256:
        raise ValueError("no real held-out recordings were registered")
    seen = set()
    for path in sorted(heldout_folder.glob("*.wav")):
        pcm_sha256 = load_wav(path).pcm_sha256
        if pcm_sha256 not in allowed_pcm_sha256:
            raise ValueError(
                f"non-corpus audio in the held-out split: {path}; held-out error "
                "may only be measured on real human recordings"
            )
        seen.add(pcm_sha256)
    if not seen:
        raise ValueError(f"no held-out recordings in {heldout_folder}")
    return seen


def assert_synthetic_stays_out_of_measurement(entries: list[dict], protected: set[str]) -> None:
    for entry in entries:
        if entry["pcm_sha256"] in protected:
            raise ValueError(
                "synthesized audio collides with a held-out or evaluation recording"
            )


# --------------------------------------------------------------------------
# added audio per condition
# --------------------------------------------------------------------------

def build_added_audio(
    condition: str, ant_index: int, ants: list[str], checkpoints: dict, plan: list[dict],
    round_index: int, replicate: int, added_dir: Path,
) -> list[dict]:
    """Build one ant's added audio for one round, volume-matched by construction."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")
    if condition == "SOLO":
        return []
    others = [index for index in range(len(ants)) if index != ant_index]
    if condition == "SOCIAL" and len(others) != len(plan):
        raise ValueError("SOCIAL needs exactly one donation slot per other ant")
    added_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for item in plan:
        slot = item["slot"]
        out_path = added_dir / f"added-{slot:02d}.wav"
        if condition == "SELF_ECHO":
            producer_index = ant_index
        elif condition == "SOCIAL":
            producer_index = others[slot]
        else:
            producer_index = None
        if producer_index is None:
            written = scramble_segment(
                item["path"], item["synthetic_samples"],
                noise_seed(replicate, ant_index, round_index, slot), out_path,
            )
            producer = NOISE_PRODUCER
        else:
            producer = ants[producer_index]
            if condition == "SOCIAL" and producer == ants[ant_index]:
                raise ValueError("an ant in SOCIAL must never ingest its own audio")
            written = speak_segment(checkpoints[producer], item["path"], out_path)
        if written["sample_count"] != item["synthetic_samples"]:
            raise ValueError(
                f"volume matching broken at slot {slot}: "
                f"{written['sample_count']} != {item['synthetic_samples']} samples"
            )
        entries.append({
            "slot": slot,
            "producer": producer,
            "path": out_path,
            "file": out_path.name,
            "segment_pcm_sha256": item["segment_pcm_sha256"],
            "pcm_sha256": written["pcm_sha256"],
            "sample_count": written["sample_count"],
        })
    if len({entry["pcm_sha256"] for entry in entries}) != len(entries):
        raise ValueError(
            "two added files are byte-identical; the training folder would "
            "de-duplicate them and silently break volume matching"
        )
    if condition == "SOCIAL":
        if any(entry["producer"] == ants[ant_index] for entry in entries):
            raise ValueError("an ant in SOCIAL must never ingest its own audio")
        if len({entry["producer"] for entry in entries}) != len(others):
            raise ValueError("SOCIAL must hear every other ant exactly once")
    return entries


def assert_volume_matched(condition: str, plan: list[dict], added: dict[str, list[dict]]) -> int:
    """The comparison is meaningless unless every ant receives the same volume."""
    totals = {
        ant: sum(entry["sample_count"] for entry in entries)
        for ant, entries in added.items()
    }
    if condition == "SOLO":
        if any(totals.values()):
            raise ValueError("SOLO must add no audio at all")
        return 0
    expected = plan_total_samples(plan)
    for ant, total in totals.items():
        if total != expected:
            raise ValueError(
                f"volume matching broken for {ant}: {total} added samples, "
                f"expected {expected}"
            )
    smallest, largest = min(totals.values()), max(totals.values())
    if largest and (largest - smallest) / largest > VOLUME_TOLERANCE:
        raise ValueError("added audio volume differs between ants by more than tolerance")
    return expected


# --------------------------------------------------------------------------
# the experiment
# --------------------------------------------------------------------------

def build_mix(train_folder: Path, entries: list[dict], mix_dir: Path) -> Path:
    """Real human audio always stays in the mix; added audio is stacked on top."""
    mix_dir.mkdir(parents=True, exist_ok=True)
    real = sorted(train_folder.glob("*.wav"))
    if not real:
        raise ValueError(f"no real training audio in {train_folder}")
    for path in real:
        shutil.copyfile(path, mix_dir / f"real-{path.name}")
    for entry in entries:
        shutil.copyfile(entry["path"], mix_dir / f"added-{entry['slot']:02d}.wav")
    return mix_dir


def run_condition(
    condition: str, recordings: Path, colony_size: int = 4, replicate: int = 0,
    rounds: int = DEFAULT_ROUNDS, units: int = DEFAULT_UNITS,
    synthetic_proportion: float = DEFAULT_SYNTHETIC_PROPORTION,
    work_root: Path | None = None, results_root: Path | None = None,
    manifest_path: Path | None = None, keep_work: bool = False,
) -> dict:
    condition = condition.upper()
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition: {condition}")
    if colony_size not in COLONY_SIZES:
        raise ValueError(f"colony size must be one of {COLONY_SIZES}")
    if rounds < 1:
        raise ValueError("an experiment needs at least one treatment round")
    recordings = Path(recordings).resolve()
    work_root = Path(work_root or PROJECT_ROOT / "experiments/sociality/work").resolve()
    results_root = Path(results_root or PROJECT_ROOT / "experiments/sociality/results").resolve()
    for root in (work_root, results_root):
        if recordings == root or recordings in root.parents:
            raise ValueError("experiment output must never be written inside the corpus")

    train_folder = recordings / "train"
    heldout_folder = recordings / "heldout"
    evaluation_folder = recordings / "evaluation"

    corpus_manifest_sha256 = None
    if manifest_path is not None:
        manifest = validate_manifest(Path(manifest_path), recordings)
        corpus_manifest_sha256 = manifest["manifest_sha256"]
        heldout_hashes = manifest_split_hashes(manifest, "heldout")
        protected = heldout_hashes | manifest_split_hashes(manifest, "evaluation")
    else:
        heldout_hashes = folder_pcm_hashes(heldout_folder)
        protected = set(heldout_hashes)
        if evaluation_folder.exists():
            protected |= folder_pcm_hashes(evaluation_folder)
    assert_heldout_is_real(heldout_folder, heldout_hashes)

    ants = colony_ants(colony_size)
    seeds = colony_seeds(replicate, colony_size)
    run_name = f"{condition.lower()}-{colony_size}-r{replicate}"
    run_dir = work_root / run_name
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    slots = colony_size - 1
    timeline = real_training_timeline(train_folder)
    real_samples = int(len(timeline))
    corpus_key = hashlib.sha256(
        "".join(sorted(folder_pcm_hashes(train_folder))).encode()
    ).hexdigest()[:12]
    segment_root = work_root / "segments" / (
        f"slots{slots}-p{synthetic_proportion:.4f}-{corpus_key}"
    )
    plan = build_segment_plan(
        train_folder, segment_root, slots, synthetic_proportion, timeline=timeline,
    )
    matched_samples = plan_total_samples(plan)

    provenance = {
        "experiment": "sociality",
        "condition": condition,
        "colony_size": colony_size,
        "replicate": replicate,
        "corpus_manifest_sha256": corpus_manifest_sha256,
    }

    per_round = []
    checkpoints: dict[str, dict] = {}

    def measure(round_index: int, added: dict[str, list[dict]]) -> None:
        nonlocal checkpoints
        assert_heldout_is_real(heldout_folder, heldout_hashes)
        assert_volume_matched(condition if round_index else "SOLO", plan, added)
        fresh: dict[str, dict] = {}
        errors: dict[str, float] = {}
        before: dict[str, float] = {}
        for index, ant in enumerate(ants):
            entries = added.get(ant, [])
            if entries:
                folder = build_mix(train_folder, entries, run_dir / f"round-{round_index:02d}" / "mix" / ant)
            else:
                folder = train_folder
            checkpoint = build_checkpoint(
                folder, heldout_folder, ant, units, seeds[index],
                provenance | {"round": round_index},
            )
            fresh[ant] = checkpoint
            errors[ant] = float(checkpoint["heldout_error_after"])
            before[ant] = float(checkpoint["heldout_error_before"])
        checkpoints = fresh
        per_round.append({
            "round": round_index,
            "per_ant_heldout_error": errors,
            "mean_heldout_error": float(np.mean(list(errors.values()))),
            "added_samples_per_ant": {
                ant: sum(entry["sample_count"] for entry in added.get(ant, []))
                for ant in ants
            },
            "added_seconds_per_ant": {
                ant: round(
                    sum(entry["sample_count"] for entry in added.get(ant, [])) / EXEMPLAR_RATE, 6
                )
                for ant in ants
            },
            "added_audio_per_ant": {
                ant: [
                    {k: v for k, v in entry.items() if k != "path"}
                    for entry in added.get(ant, [])
                ]
                for ant in ants
            },
            "per_ant_heldout_error_before": before,
            "per_ant_checkpoint_sha256": {
                ant: fresh[ant]["checkpoint_sha256"] for ant in ants
            },
        })

    measure(0, {ant: [] for ant in ants})
    for round_index in range(1, rounds + 1):
        speakers = dict(checkpoints)
        added: dict[str, list[dict]] = {}
        for index, ant in enumerate(ants):
            entries = build_added_audio(
                condition, index, ants, speakers, plan, round_index, replicate,
                run_dir / f"round-{round_index:02d}" / "added" / ant,
            )
            assert_synthetic_stays_out_of_measurement(entries, protected)
            added[ant] = entries
        measure(round_index, added)
        if not keep_work:
            shutil.rmtree(run_dir / f"round-{round_index:02d}" / "mix", ignore_errors=True)

    result = {
        "format_version": EXPERIMENT_FORMAT,
        "experiment": "sociality",
        "hypothesis_under_test": (
            "many ants forming social bonds increases learning exponentially"
        ),
        "condition": condition,
        "colony_size": colony_size,
        "replicate": replicate,
        "rounds": rounds,
        "units": units,
        "ants": ants,
        "seeds": seeds,
        "seeds_by_ant": dict(zip(ants, seeds)),
        "recordings": str(recordings),
        "corpus_manifest_sha256": corpus_manifest_sha256,
        "heldout_measured_against": "real-recordings-only",
        "heldout_pcm_sha256": sorted(heldout_hashes),
        "volume_matching": {
            "donation_slots": slots,
            "matched_added_samples_per_ant": matched_samples if condition != "SOLO" else 0,
            "reference_added_samples_per_ant": matched_samples,
            "matched_conditions": list(MATCHED_CONDITIONS),
            "tolerance": VOLUME_TOLERANCE,
            "requested_synthetic_proportion": synthetic_proportion,
            "actual_synthetic_proportion": round(
                matched_samples / (real_samples + matched_samples), 6
            ),
            "budget_was_clamped": bool(plan and plan[0]["clamped"]),
            "real_training_samples": real_samples,
            "segment_plan": serialisable_plan(plan),
        },
        "per_round": per_round,
        "final_mean_heldout_error": per_round[-1]["mean_heldout_error"],
        "baseline_round0_mean_heldout_error": per_round[0]["mean_heldout_error"],
        "notes": (
            "round 0 is a real-audio-only bootstrap and is identical across "
            "conditions for a given replicate; rounds 1..N are the treatment "
            "rounds. Each round retrains from scratch on that round's mix, so "
            "added audio does not accumulate."
        ),
        "claim_limit": (
            "held-out vector-quantization error on real recordings only; not a "
            "claim about speech, meaning or conversation"
        ),
    }
    results_root.mkdir(parents=True, exist_ok=True)
    write_json_atomic(results_root / f"{run_name}.json", result)
    return result


def run_command(args) -> None:
    conditions = CONDITIONS if args.condition.upper() == "ALL" else (args.condition.upper(),)
    summaries = []
    for condition in conditions:
        result = run_condition(
            condition, Path(args.recordings),
            colony_size=args.colony_size, replicate=args.replicate,
            rounds=args.rounds, units=args.units,
            synthetic_proportion=args.synthetic_proportion,
            work_root=Path(args.work) if args.work else None,
            results_root=Path(args.results) if args.results else None,
            manifest_path=Path(args.manifest) if args.manifest else None,
            keep_work=args.keep_work,
        )
        summaries.append({
            "condition": result["condition"],
            "colony_size": result["colony_size"],
            "replicate": result["replicate"],
            "seeds": result["seeds"],
            "added_samples_per_ant": result["volume_matching"][
                "matched_added_samples_per_ant"
            ],
            "round0_mean_heldout_error": result["baseline_round0_mean_heldout_error"],
            "final_mean_heldout_error": result["final_mean_heldout_error"],
            "result": (
                f"{result['condition'].lower()}-{result['colony_size']}"
                f"-r{result['replicate']}.json"
            ),
        })
    print(json.dumps({
        "heldout_measured_against": "real-recordings-only",
        "runs": summaries,
    }))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sociality experiment: SOLO / SELF_ECHO / SOCIAL / NOISE.",
    )
    parser.add_argument("--recordings", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument(
        "--condition", required=True, type=str.upper, choices=[*CONDITIONS, "ALL"],
    )
    parser.add_argument("--colony-size", type=int, default=4, choices=list(COLONY_SIZES))
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--replicate", type=int, default=0)
    parser.add_argument("--units", type=int, default=DEFAULT_UNITS)
    parser.add_argument(
        "--synthetic-proportion", type=float, default=DEFAULT_SYNTHETIC_PROPORTION,
    )
    parser.add_argument("--work", default=None)
    parser.add_argument("--results", default=None)
    parser.add_argument("--keep-work", action="store_true")
    parser.set_defaults(fn=run_command)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

"""Waveform-only acoustic-unit discovery for the Hebrew Voice Ant Farm."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


CHECKPOINT_FORMAT = 3
SUPPORTED_CHECKPOINT_FORMATS = {1, 2, 3}
EXEMPLAR_RATE = 16_000
FRAME_SECONDS = 0.025
HOP_SECONDS = 0.010
FEATURE_SPEC = {
    "version": 1,
    "canonical_sample_rate": EXEMPLAR_RATE,
    "frame_seconds": FRAME_SECONDS,
    "hop_seconds": HOP_SECONDS,
    "features": ["log_energy", "zero_crossing_rate", "12_log_spectral_bands"],
}


@dataclass(frozen=True)
class Audio:
    samples: np.ndarray
    rate: int
    sha256: str
    pcm_sha256: str


def load_wav(path: Path) -> Audio:
    raw = path.read_bytes()
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected mono 16-bit PCM WAV")
        rate = w.getframerate()
        if not 8_000 <= rate <= 48_000:
            raise ValueError(f"{path}: sample rate outside 8-48 kHz")
        pcm = w.readframes(w.getnframes())
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    if samples.size < rate // 4:
        raise ValueError(f"{path}: recording is shorter than 250 ms")
    canonical = rate.to_bytes(4, "little") + pcm
    return Audio(
        samples, rate, hashlib.sha256(raw).hexdigest(), hashlib.sha256(canonical).hexdigest()
    )


def frame_geometry(rate: int) -> tuple[int, int]:
    return max(16, round(rate * FRAME_SECONDS)), max(8, round(rate * HOP_SECONDS))


def resample_samples(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return samples.astype(np.float32, copy=False)
    target_size = max(1, round(len(samples) * target_rate / source_rate))
    source_points = np.linspace(0.0, 1.0, len(samples), endpoint=False)
    target_points = np.linspace(0.0, 1.0, target_size, endpoint=False)
    return np.interp(target_points, source_points, samples).astype(np.float32)


def features(audio: Audio) -> tuple[np.ndarray, float]:
    samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    frame, hop = frame_geometry(EXEMPLAR_RATE)
    if len(samples) < frame:
        raise ValueError("not enough samples")
    count = 1 + (len(samples) - frame) // hop
    window = np.hanning(frame).astype(np.float32)
    rows = []
    for i in range(count):
        x = samples[i * hop:i * hop + frame] * window
        energy = math.log(float(np.mean(x * x)) + 1e-8)
        zcr = float(np.mean(np.signbit(x[1:]) != np.signbit(x[:-1])))
        spectrum = np.abs(np.fft.rfft(x)) + 1e-8
        spectrum /= spectrum.sum()
        bins = np.array_split(spectrum, 12)
        bands = [math.log(float(b.sum()) + 1e-8) for b in bins]
        rows.append([energy, zcr, *bands])
    return np.asarray(rows, dtype=np.float32), hop / EXEMPLAR_RATE


def fit_codebook(x: np.ndarray, k: int, seed: int, rounds: int = 30) -> np.ndarray:
    if len(x) < k:
        raise ValueError(f"need at least {k} acoustic frames, got {len(x)}")
    rng = np.random.default_rng(seed)
    centers = x[rng.choice(len(x), k, replace=False)].copy()
    for _ in range(rounds):
        ids = ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        updated = centers.copy()
        for j in range(k):
            members = x[ids == j]
            if len(members):
                updated[j] = members.mean(axis=0)
        if np.allclose(updated, centers, atol=1e-5):
            break
        centers = updated
    return centers


def encode(x: np.ndarray, centers: np.ndarray) -> np.ndarray:
    return ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)


def error(x: np.ndarray, centers: np.ndarray) -> float:
    ids = encode(x, centers)
    return float(np.mean((x - centers[ids]) ** 2))


def collapse_runs(ids: np.ndarray, hop_seconds: float) -> list[dict]:
    result = []
    start = 0
    for i in range(1, len(ids) + 1):
        if i == len(ids) or ids[i] != ids[start]:
            result.append({
                "unit": int(ids[start]),
                "start_s": round(start * hop_seconds, 3),
                "end_s": round(i * hop_seconds, 3),
            })
            start = i
    return result


def dataset(folder: Path) -> tuple[np.ndarray, set[str]]:
    frames, hashes = [], set()
    for path in sorted(folder.glob("*.wav")):
        audio = load_wav(path)
        if audio.pcm_sha256 in hashes:
            continue
        hashes.add(audio.pcm_sha256)
        frames.append(features(audio)[0])
    if not frames:
        raise ValueError(f"no valid WAV recordings in {folder}")
    return np.concatenate(frames), hashes


def raw_audio_hashes(folder: Path) -> set[str]:
    """Return legacy container-file hashes for an exact WAV folder."""
    hashes = {load_wav(path).sha256 for path in sorted(folder.glob("*.wav"))}
    if not hashes:
        raise ValueError(f"no valid WAV recordings in {folder}")
    return hashes


def _resample_frame(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    target_size = round(FRAME_SECONDS * target_rate)
    if len(samples) == target_size and source_rate == target_rate:
        return samples.astype(np.float32, copy=True)
    source_points = np.linspace(0.0, 1.0, len(samples), endpoint=False)
    target_points = np.linspace(0.0, 1.0, target_size, endpoint=False)
    return np.interp(target_points, source_points, samples).astype(np.float32)


def learn_exemplars(folder: Path, centers: np.ndarray) -> dict:
    """Select one real training-waveform frame nearest to every learned unit."""
    best_distance = np.full(len(centers), np.inf, dtype=np.float64)
    best_frames: list[np.ndarray | None] = [None] * len(centers)
    best_hashes: list[str | None] = [None] * len(centers)
    best_indexes: list[int | None] = [None] * len(centers)
    for path in sorted(folder.glob("*.wav")):
        audio = load_wav(path)
        canonical_samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        x, _ = features(audio)
        frame, hop = frame_geometry(EXEMPLAR_RATE)
        distances = ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        for unit in range(len(centers)):
            index = int(distances[:, unit].argmin())
            distance = float(distances[index, unit])
            if distance >= best_distance[unit]:
                continue
            start = index * hop
            raw = canonical_samples[start:start + frame]
            best_distance[unit] = distance
            best_frames[unit] = raw.astype(np.float32, copy=True)
            best_hashes[unit] = audio.pcm_sha256
            best_indexes[unit] = index
    if any(frame is None for frame in best_frames):
        raise ValueError("could not learn a waveform exemplar for every acoustic unit")
    pcm = [
        np.clip(np.rint(frame * 32767), -32768, 32767).astype("<i2").tolist()
        for frame in best_frames
        if frame is not None
    ]
    return {
        "exemplar_rate": EXEMPLAR_RATE,
        "exemplar_frame_samples": round(FRAME_SECONDS * EXEMPLAR_RATE),
        "exemplar_hop_samples": round(HOP_SECONDS * EXEMPLAR_RATE),
        "exemplars_pcm16": pcm,
        "exemplar_source_hashes": best_hashes,
        "exemplar_source_frame_indexes": best_indexes,
    }


def checkpoint_digest(checkpoint: dict) -> str:
    """Hash the signed portion of a checkpoint (everything except its hash)."""
    payload = {k: v for k, v in checkpoint.items() if k != "checkpoint_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_checkpoint(path: Path) -> dict:
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    if checkpoint.get("format_version") not in SUPPORTED_CHECKPOINT_FORMATS:
        raise ValueError(f"{path}: unsupported checkpoint format")
    expected = checkpoint.get("checkpoint_sha256")
    actual = checkpoint_digest(checkpoint)
    if not expected or expected != actual:
        raise ValueError(f"{path}: checkpoint hash mismatch")
    centers = np.asarray(checkpoint.get("centers"), dtype=np.float32)
    if centers.ndim != 2 or centers.shape != (
        checkpoint.get("units"), checkpoint.get("feature_dim")
    ):
        raise ValueError(f"{path}: invalid codebook shape")
    if checkpoint["format_version"] >= 2:
        exemplars = np.asarray(checkpoint.get("exemplars_pcm16"))
        expected_exemplar_shape = (
            checkpoint.get("units"), checkpoint.get("exemplar_frame_samples")
        )
        if exemplars.shape != expected_exemplar_shape:
            raise ValueError(f"{path}: invalid waveform exemplar shape")
        if not 8_000 <= checkpoint.get("exemplar_rate", 0) <= 48_000:
            raise ValueError(f"{path}: invalid waveform exemplar rate")
        if not 0 < checkpoint.get("exemplar_hop_samples", 0) <= exemplars.shape[1]:
            raise ValueError(f"{path}: invalid waveform exemplar hop")
        for key in ("exemplar_source_hashes", "exemplar_source_frame_indexes"):
            if len(checkpoint.get(key, [])) != checkpoint["units"]:
                raise ValueError(f"{path}: invalid {key}")
    return checkpoint


def build_checkpoint(
    train_folder: Path, heldout_folder: Path, ant: str, units: int, seed: int,
    corpus_provenance: dict | None = None,
) -> dict:
    train_x, train_hashes = dataset(train_folder)
    held_x, held_hashes = dataset(heldout_folder)
    overlap = train_hashes & held_hashes
    if overlap:
        raise ValueError("train and held-out datasets overlap by audio hash")
    baseline = np.repeat(train_x.mean(axis=0, keepdims=True), units, axis=0)
    centers = fit_codebook(train_x, units, seed)
    before, after = error(held_x, baseline), error(held_x, centers)
    checkpoint = {
        "format_version": CHECKPOINT_FORMAT,
        "architecture": "waveform-acoustic-vector-quantizer-with-exemplars",
        "audio_hash_kind": "sha256(sample_rate_le32+decoded_pcm16le)",
        "feature_spec": FEATURE_SPEC,
        "experiment_namespace": hashlib.sha256(
            json.dumps({"feature_spec": FEATURE_SPEC, "units": units}, sort_keys=True).encode()
        ).hexdigest(),
        "corpus_provenance": corpus_provenance,
        "ant": ant,
        "seed": seed,
        "units": units,
        "feature_dim": int(centers.shape[1]),
        "train_frame_count": int(len(train_x)),
        "heldout_frame_count": int(len(held_x)),
        "train_audio_hashes": sorted(train_hashes),
        "heldout_audio_hashes": sorted(held_hashes),
        "heldout_error_before": before,
        "heldout_error_after": after,
        "improved_over_baseline": after < before,
        "improved": after < before,
        "baseline_center": train_x.mean(axis=0).tolist(),
        "centers": centers.tolist(),
    }
    checkpoint.update(learn_exemplars(train_folder, centers))
    checkpoint["checkpoint_sha256"] = checkpoint_digest(checkpoint)
    return checkpoint


def train_ant(
    train_folder: Path, heldout_folder: Path, state_root: Path,
    ant: str, units: int, seed: int, corpus_provenance: dict | None = None,
) -> tuple[dict, Path]:
    checkpoint = build_checkpoint(
        train_folder, heldout_folder, ant, units, seed, corpus_provenance
    )
    state = state_root / ant
    state.mkdir(parents=True, exist_ok=True)
    current_path = state / "current.json"
    incumbent = load_checkpoint(current_path) if current_path.exists() else None
    checkpoint["incumbent_checkpoint_sha256"] = (
        incumbent["checkpoint_sha256"] if incumbent else None
    )
    checkpoint["incumbent_heldout_error"] = (
        incumbent["heldout_error_after"] if incumbent else None
    )
    legacy_checkpoint = bool(
        incumbent and incumbent.get("format_version", 0) < CHECKPOINT_FORMAT
    )
    legacy_audio_identity_verified = bool(
        legacy_checkpoint
        and incumbent.get("audio_hash_kind") is None
        and set(incumbent.get("train_audio_hashes", [])) == raw_audio_hashes(train_folder)
        and set(incumbent.get("heldout_audio_hashes", [])) == raw_audio_hashes(heldout_folder)
    )
    if incumbent is None:
        checkpoint["promotion_basis"] = "first-checkpoint-vs-baseline"
        checkpoint["improved_over_incumbent"] = None
        promotion_eligible = checkpoint["improved_over_baseline"]
    elif legacy_checkpoint and not legacy_audio_identity_verified:
        checkpoint["promotion_basis"] = "blocked-legacy-audio-identity-unverified"
        checkpoint["improved_over_incumbent"] = False
        promotion_eligible = False
    elif (
        not legacy_checkpoint
        and set(incumbent["heldout_audio_hashes"]) != set(checkpoint["heldout_audio_hashes"])
    ):
        checkpoint["promotion_basis"] = "blocked-heldout-dataset-changed"
        checkpoint["improved_over_incumbent"] = False
        promotion_eligible = False
    elif (
        incumbent.get("format_version", 0) >= CHECKPOINT_FORMAT
        and incumbent.get("experiment_namespace") != checkpoint["experiment_namespace"]
    ):
        checkpoint["promotion_basis"] = "blocked-incomparable-feature-or-unit-spec"
        checkpoint["improved_over_incumbent"] = False
        promotion_eligible = False
    elif legacy_checkpoint:
        checkpoint["promotion_basis"] = (
            "capability-upgrade-from-verified-legacy-audio-hashes"
        )
        legacy_compatible = (
            incumbent.get("units") == checkpoint["units"]
            and incumbent.get("feature_dim") == checkpoint["feature_dim"]
            and (checkpoint.get("corpus_provenance") or {}).get("sample_rates") == [EXEMPLAR_RATE]
        )
        checkpoint["improved_over_incumbent"] = legacy_compatible and (
            checkpoint["heldout_error_after"] <= incumbent["heldout_error_after"] + 1e-9
        )
        promotion_eligible = (
            checkpoint["improved_over_baseline"] and checkpoint["improved_over_incumbent"]
        )
    else:
        checkpoint["promotion_basis"] = "strict-heldout-improvement-over-incumbent"
        checkpoint["improved_over_incumbent"] = (
            checkpoint["heldout_error_after"] < incumbent["heldout_error_after"] - 1e-9
        )
        promotion_eligible = (
            checkpoint["improved_over_baseline"] and checkpoint["improved_over_incumbent"]
        )
    checkpoint["promotion_eligible"] = promotion_eligible
    checkpoint["improved"] = promotion_eligible
    checkpoint["checkpoint_sha256"] = checkpoint_digest(checkpoint)
    candidate = state / f"candidate-{checkpoint['checkpoint_sha256'][:12]}.json"
    write_json_atomic(candidate, checkpoint)
    if promotion_eligible:
        write_json_atomic(current_path, checkpoint)
    return checkpoint, candidate


def train(args) -> None:
    checkpoint, _ = train_ant(
        Path(args.train), Path(args.heldout), Path(args.state),
        args.ant, args.units, args.seed, None,
    )
    print(json.dumps({k: checkpoint[k] for k in (
        "ant", "architecture", "heldout_error_before", "heldout_error_after",
        "improved", "checkpoint_sha256")}))


def encode_file(args) -> None:
    checkpoint = load_checkpoint(Path(args.checkpoint))
    audio = load_wav(Path(args.wav))
    x, hop = features(audio)
    ids = encode(x, np.asarray(checkpoint["centers"], dtype=np.float32))
    print(json.dumps({
        "audio_sha256": audio.sha256,
        "audio_pcm_sha256": audio.pcm_sha256,
        "unit_namespace": f"{checkpoint['checkpoint_sha256']}:unit_id",
        "units": collapse_runs(ids, hop),
    }))


def evaluate_checkpoint(checkpoint: dict, evaluation_folder: Path) -> dict:
    evaluation_x, evaluation_hashes = dataset(evaluation_folder)
    prior_hashes = set(checkpoint["train_audio_hashes"]) | set(checkpoint["heldout_audio_hashes"])
    overlap = prior_hashes & evaluation_hashes
    if overlap:
        raise ValueError("evaluation audio overlaps checkpoint training or held-out data by hash")
    centers = np.asarray(checkpoint["centers"], dtype=np.float32)
    baseline_center = np.asarray(checkpoint["baseline_center"], dtype=np.float32)
    baseline = np.repeat(baseline_center[None, :], checkpoint["units"], axis=0)
    before, after = error(evaluation_x, baseline), error(evaluation_x, centers)
    return {
        "checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "evaluation_audio_hashes": sorted(evaluation_hashes),
        "evaluation_frame_count": int(len(evaluation_x)),
        "error_before": before,
        "error_after": after,
        "improved": after < before,
    }


def evaluate(args) -> None:
    """Evaluate a sealed checkpoint on an independent folder of WAV files."""
    checkpoint = load_checkpoint(Path(args.checkpoint))
    print(json.dumps(evaluate_checkpoint(checkpoint, Path(args.heldout))))


def reconstruct(audio: Audio, checkpoint: dict) -> tuple[np.ndarray, np.ndarray]:
    if checkpoint.get("format_version", 0) < 2:
        raise ValueError("checkpoint has no learned waveform exemplars")
    x, _ = features(audio)
    ids = encode(x, np.asarray(checkpoint["centers"], dtype=np.float32))
    output = synthesize_units(
        ids, f"{checkpoint['checkpoint_sha256']}:unit_id", checkpoint
    )
    return output, ids


def synthesize_units(ids: np.ndarray, namespace: str, checkpoint: dict) -> np.ndarray:
    expected_namespace = f"{checkpoint['checkpoint_sha256']}:unit_id"
    if namespace != expected_namespace:
        raise ValueError("unit namespace does not match checkpoint")
    ids = np.asarray(ids, dtype=np.int64)
    if ids.ndim != 1 or len(ids) == 0:
        raise ValueError("unit sequence must be a nonempty one-dimensional array")
    if int(ids.min()) < 0 or int(ids.max()) >= checkpoint["units"]:
        raise ValueError("unit sequence contains an out-of-range ID")
    exemplars = np.asarray(checkpoint["exemplars_pcm16"], dtype=np.float32) / 32768.0
    frame = checkpoint["exemplar_frame_samples"]
    hop = checkpoint["exemplar_hop_samples"]
    output = np.zeros((len(ids) - 1) * hop + frame, dtype=np.float64)
    weight = np.zeros_like(output)
    window = np.hanning(frame).astype(np.float64)
    window = np.maximum(window, 1e-4)
    for index, unit in enumerate(ids):
        start = index * hop
        output[start:start + frame] += exemplars[int(unit)] * window
        weight[start:start + frame] += window
    output /= np.maximum(weight, 1e-8)
    return np.clip(output, -1.0, 1.0).astype(np.float32)


def render_soft(samples: np.ndarray, rate: int, cutoff_hz: float = 2500.0,
                fade_seconds: float = 0.02, peak: float = 0.85) -> np.ndarray:
    """Soften a rendered waveform for playback: cosine-rolloff lowpass
    (unity below cutoff, tapering to zero one octave above), short edge
    fades, peak normalisation. Rendering only — the unit sequence and the
    learned exemplars are untouched, so every provenance claim still holds.
    Ear-validated against raw exemplar playback on 2026-08-09."""
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim != 1 or len(x) == 0:
        raise ValueError("samples must be a nonempty one-dimensional array")
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1.0 / rate)
    gain = np.ones_like(freqs)
    f1, f2 = cutoff_hz, cutoff_hz * 2
    taper = (freqs >= f1) & (freqs < f2)
    gain[taper] = 0.5 * (1 + np.cos(np.pi * (freqs[taper] - f1) / (f2 - f1)))
    gain[freqs >= f2] = 0.0
    y = np.fft.irfft(spectrum * gain, n=len(x)).astype(np.float32)
    fade = min(int(fade_seconds * rate), len(y) // 2)
    if fade > 0:
        y[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        y[len(y) - fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    top = float(np.abs(y).max())
    if top > 0.0:
        y *= peak / top
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def write_wav_atomic(path: Path, samples: np.ndarray, rate: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pcm = np.clip(np.rint(samples * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(temporary), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(pcm.tobytes())
    temporary.replace(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthesize(args) -> None:
    """Reconstruct audio only from an encoded sequence and learned exemplars."""
    checkpoint = load_checkpoint(Path(args.checkpoint))
    source = load_wav(Path(args.wav))
    samples, ids = reconstruct(source, checkpoint)
    output = Path(args.output)
    output_hash = write_wav_atomic(output, samples, checkpoint["exemplar_rate"])
    print(json.dumps({
        "checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "source_audio_sha256": source.sha256,
        "source_audio_pcm_sha256": source.pcm_sha256,
        "unit_namespace": f"{checkpoint['checkpoint_sha256']}:unit_id",
        "output_audio_sha256": output_hash,
        "output": str(output),
        "output_rate": checkpoint["exemplar_rate"],
        "unit_frame_count": int(len(ids)),
        "duration_seconds": len(samples) / checkpoint["exemplar_rate"],
        "claim_limit": "learned-exemplar reconstruction; not speech or conversation acceptance",
    }))


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    t = sub.add_parser("train")
    t.add_argument("--ant", required=True); t.add_argument("--train", required=True)
    t.add_argument("--heldout", required=True); t.add_argument("--state", default="state")
    t.add_argument("--units", type=int, default=64); t.add_argument("--seed", type=int, default=7007)
    t.set_defaults(fn=train)
    e = sub.add_parser("encode")
    e.add_argument("--checkpoint", required=True); e.add_argument("--wav", required=True)
    e.set_defaults(fn=encode_file)
    v = sub.add_parser("evaluate")
    v.add_argument("--checkpoint", required=True); v.add_argument("--heldout", required=True)
    v.set_defaults(fn=evaluate)
    s = sub.add_parser("synthesize")
    s.add_argument("--checkpoint", required=True); s.add_argument("--wav", required=True)
    s.add_argument("--output", required=True); s.set_defaults(fn=synthesize)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()

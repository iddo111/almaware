"""DGX-only real-WAV dataset and resumable deterministic sampler."""

from __future__ import annotations

import hashlib
import os
import wave
from pathlib import Path
from typing import Iterator, Sized

if os.name == "nt":
    raise RuntimeError(
        "AntVoice real-audio neural data loading is blocked on Windows; "
        "execute it on an approved DGX"
    )

import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, Sampler

from .io_utils import file_sha256
from .manifest import AudioRecord, ValidatedManifest


def _resolved_audio_path(audio_root: Path, relative: str) -> Path:
    root = audio_root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("validated audio_path escaped audio_root at read time") from exc
    return resolved


class ManifestWaveDataset(Dataset[dict[str, object]]):
    """Load only rows that already passed the strict manifest validator.

    Each read re-hashes the WAV so changed bytes cannot silently enter a run
    after startup validation.
    """

    def __init__(
        self,
        validated: ValidatedManifest,
        audio_root: str | Path,
        *,
        split: str,
        segment_samples: int,
        crop_seed: int,
    ) -> None:
        if split not in {"train", "eval"}:
            raise ValueError("split must be train or eval")
        if segment_samples <= 0:
            raise ValueError("segment_samples must be positive")
        self.audio_root = Path(audio_root)
        self.split = split
        self.segment_samples = segment_samples
        self.crop_seed = crop_seed
        self.epoch = 0
        self.records: tuple[AudioRecord, ...] = tuple(
            record for record in validated.records if record.split == split
        )
        if not self.records:
            raise ValueError(f"validated manifest has no {split} records")

    def __len__(self) -> int:
        return len(self.records)

    def set_epoch(self, epoch: int) -> None:
        if epoch < 0:
            raise ValueError("epoch must be non-negative")
        self.epoch = epoch

    def _crop_offset(self, record: AudioRecord, num_samples: int) -> int:
        available = num_samples - self.segment_samples
        if available <= 0:
            return 0
        if self.split == "eval":
            return available // 2
        key = (
            f"{self.crop_seed}:{self.epoch}:{record.sha256}:{num_samples}"
        ).encode("ascii")
        return int.from_bytes(hashlib.sha256(key).digest()[:8], "little") % (
            available + 1
        )

    def __getitem__(self, index: int) -> dict[str, object]:
        record = self.records[index]
        path = _resolved_audio_path(self.audio_root, record.audio_path)
        actual_hash = file_sha256(path)
        if actual_hash != record.sha256:
            raise RuntimeError(
                f"audio bytes changed after manifest validation: {record.audio_path!r}"
            )
        with wave.open(str(path), "rb") as wav:
            if (
                wav.getnchannels() != 1
                or wav.getsampwidth() != 2
                or wav.getframerate() != record.sample_rate
                or wav.getcomptype() != "NONE"
                or wav.getnframes() != record.num_samples
            ):
                raise RuntimeError(
                    f"WAV properties changed after validation: {record.audio_path!r}"
                )
            raw_frames = wav.readframes(record.num_samples)
        waveform = torch.frombuffer(
            bytearray(raw_frames),
            dtype=torch.int16,
        ).to(dtype=torch.float32)
        waveform = waveform / 32768.0
        offset = self._crop_offset(record, waveform.numel())
        waveform = waveform[offset : offset + self.segment_samples]
        if waveform.numel() < self.segment_samples:
            waveform = F.pad(
                waveform,
                (0, self.segment_samples - waveform.numel()),
            )
        return {
            "waveform": waveform.contiguous(),
            "record_index": index,
            "audio_sha256": record.sha256,
        }


class ResumablePermutationSampler(Sampler[int]):
    """Single-process sampler whose epoch and cursor are checkpointable."""

    def __init__(self, data_source: Sized, *, seed: int) -> None:
        self.data_source = data_source
        self.seed = seed
        self.epoch = 0
        self.cursor = 0

    def __len__(self) -> int:
        return max(len(self.data_source) - self.cursor, 0)

    def _order(self) -> list[int]:
        generator = torch.Generator(device="cpu")
        generator.manual_seed(self.seed + self.epoch)
        return torch.randperm(
            len(self.data_source),
            generator=generator,
        ).tolist()

    def __iter__(self) -> Iterator[int]:
        order = self._order()
        while self.cursor < len(order):
            index = order[self.cursor]
            self.cursor += 1
            yield index
        self.epoch += 1
        self.cursor = 0

    def state_dict(self) -> dict[str, int]:
        return {
            "schema_version": 1,
            "seed": self.seed,
            "epoch": self.epoch,
            "cursor": self.cursor,
            "dataset_length": len(self.data_source),
        }

    def load_state_dict(self, state: dict[str, object]) -> None:
        expected = {
            "schema_version": 1,
            "seed": self.seed,
            "dataset_length": len(self.data_source),
        }
        for key, value in expected.items():
            if state.get(key) != value:
                raise ValueError(
                    f"sampler resume mismatch for {key}: "
                    f"{state.get(key)!r} != {value!r}"
                )
        epoch = state.get("epoch")
        cursor = state.get("cursor")
        if not isinstance(epoch, int) or epoch < 0:
            raise ValueError("sampler epoch is invalid")
        if not isinstance(cursor, int) or not 0 <= cursor <= len(self.data_source):
            raise ValueError("sampler cursor is invalid")
        self.epoch = epoch
        self.cursor = cursor

"""Import long-form recordings into the KESHEV replay corpus as 2-5s clips.

PHASE2-DESIGN.md section 2: the corpus WAVs are imported from the long-form
recordings in later milestones. Section 9 Gate 18 names the Café-Claude
recordings — Iddo's own voice, real Hebrew, real rooms — as the source.
Gate 17 replays whatever this produces.

The one design decision worth defending: the utterances are cut by the
PRODUCTION segmenter (client/segmenter.py) — the same energy gate, the same
auto-gain, the same webrtcvad, the same 600ms hangover that closes a segment
in the live program — fed through the PRODUCTION resampler
(client/resample.py, 48k -> 16k). A corpus cut by a heuristic written for the
importer would be made of things KESHEV never would have segmented, and every
gate replayed through it would measure a fiction.

Clips land at 16k mono s16 because the injection seam sits BELOW the
resampler (tools/keshevctl.py read_wav refuses anything else).

No microphone. No speakers. No network. No torch.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from client.resample import StreamingResampler   # noqa: E402
from client.segmenter import SAMPLE_RATE, Segmenter  # noqa: E402
from client.spool import Spool                   # noqa: E402

BAND_LO_S = 2.0
BAND_HI_S = 5.0
DEFAULT_GATE_RMS = 0.004        # config/client.json seed
FRAME_SAMPLES = SAMPLE_RATE * 30 // 1000


def to_mono_16k(samples_i: np.ndarray, *, rate: int, channels: int) -> np.ndarray:
    """Interleaved float32 -> mono float32 at 16kHz via the production FIR."""
    if rate <= 0:
        raise ValueError(f"source rate {rate} is not a rate")
    if channels <= 0:
        raise ValueError(f"source channel count {channels} is not a count")
    arr = np.asarray(samples_i, dtype=np.float32).reshape(-1)
    if channels > 1:
        usable = (len(arr) // channels) * channels
        arr = arr[:usable].reshape(-1, channels).mean(axis=1)
    if rate == SAMPLE_RATE:
        return arr.astype(np.float32)
    return StreamingResampler(rate, SAMPLE_RATE).process(arr).astype(np.float32)


def read_source(path: Path) -> tuple[np.ndarray, int, int]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path.name}: only s16 sources are supported")
        rate, channels = w.getframerate(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    arr = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return arr, rate, channels


def slice_utterances(src: Path, out_dir: Path, *, prefix: str,
                     gate_rms: float = DEFAULT_GATE_RMS,
                     lo_s: float = BAND_LO_S,
                     hi_s: float = BAND_HI_S) -> list[Path]:
    """Cut one long recording into 2-5s utterance WAVs. Returns what landed."""
    src, out_dir = Path(src), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw, rate, channels = read_source(src)
    mono = to_mono_16k(raw, rate=rate, channels=channels)

    made: list[Path] = []
    with tempfile.TemporaryDirectory() as scratch:
        spool = Spool(Path(scratch) / "spool", capacity=100_000)
        seg = Segmenter(spool, gate_rms, "cafeclau")
        records = []
        for start in range(0, len(mono), FRAME_SAMPLES):
            records.extend(seg.feed(mono[start:start + FRAME_SAMPLES]))
        tail = seg.flush()
        if tail is not None:
            records.append(tail)

        for i, rec in enumerate(records):
            seconds = rec.duration_ms / 1000.0
            if not (lo_s <= seconds <= hi_s):
                continue
            dst = out_dir / f"{prefix}-{i:04d}.wav"
            shutil.copyfile(rec.wav_path, dst)
            made.append(dst)
    return made


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="build_replay_corpus",
        description="import long-form recordings as 2-5s replay clips")
    ap.add_argument("--src-dir", required=True,
                    help="directory of long-form s16 WAV recordings")
    ap.add_argument("--out-dir",
                    default=str(REPO / "tools" / "replay" / "wavs" / "utterances"))
    ap.add_argument("--glob", default="*.WAV")
    ap.add_argument("--exclude", action="append", default=[],
                    help="filename substring to skip; repeatable "
                         "(held-out eval dates)")
    ap.add_argument("--target", type=int, default=0,
                    help="stop once this many clips exist (0 = all)")
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    total: list[Path] = []
    sources = sorted(Path(args.src_dir).glob(args.glob))
    for src in sources:
        if any(x in src.name for x in args.exclude):
            print(f"skip (excluded): {src.name}")
            continue
        made = slice_utterances(src, out_dir, prefix=src.stem)
        total.extend(made)
        print(f"{src.name}: +{len(made)} clips (total {len(total)})")
        if args.target and len(total) >= args.target:
            print(f"target {args.target} reached")
            break
    print(f"corpus: {len(total)} clips in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

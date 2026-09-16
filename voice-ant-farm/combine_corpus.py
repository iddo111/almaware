"""Build the combined human + syllable corpus tree the ants train on.

Real human speech (Iddo) is never dropped: it is copied into every split of the
combined corpus alongside the synthesised syllable curriculum. The resulting tree
is indexed with a corpus.py-format manifest so colony.py can consume it unchanged.

Labels (item_id / glyph / gloss) live only in the side-car label map written here;
they are never part of the corpus manifest and never reach an ant.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from acoustic_units import load_wav, write_json_atomic
from corpus import MANIFEST_FORMAT, SPLITS, manifest_digest, validate_manifest


HUMAN_ROOT = Path("recordings")
SYLLABLE_ROOT = Path("corpus-syllables")

# (destination split, source folder under corpus-syllables, session id)
SYLLABLE_PLAN = (
    ("train", "train", "syllables-train"),
    ("heldout", "heldout", "syllables-heldout"),
    ("evaluation", "words", "syllables-words"),
)
SYLLABLE_SPEAKER = "mms-tts-heb"


def build(root: Path, human_root: Path, syllable_root: Path) -> tuple[dict, dict]:
    human = validate_manifest(human_root / "manifest.json", human_root)
    syllables = json.loads((syllable_root / "manifest.json").read_text(encoding="utf-8"))
    by_path = {entry["path"]: entry for entry in syllables["entries"]}

    if root.exists():
        shutil.rmtree(root)
    for split in SPLITS:
        (root / split).mkdir(parents=True, exist_ok=True)

    entries: list[dict] = []
    labels: dict[str, dict] = {}
    composition = {split: {"human": 0, "syllable": 0} for split in SPLITS}

    for entry in human["entries"]:
        source = human_root / entry["path"]
        split = entry["split"]
        destination = root / split / f"human_{source.name}"
        shutil.copy2(source, destination)
        audio = load_wav(destination)
        entries.append({
            "path": destination.relative_to(root).as_posix(),
            "split": split,
            "speaker_id": entry["speaker_id"],
            "session_id": f"human-{entry['session_id']}",
            "audio_sha256": audio.sha256,
            "pcm_sha256": audio.pcm_sha256,
            "sample_rate": audio.rate,
            "sample_count": int(len(audio.samples)),
        })
        labels[destination.name] = {"item_id": None, "item_kind": "human_speech", "split": split}
        composition[split]["human"] += 1

    for split, folder, session in SYLLABLE_PLAN:
        for source in sorted((syllable_root / folder).glob("*.wav")):
            record = by_path[f"{folder}/{source.name}"]
            destination = root / split / source.name
            shutil.copy2(source, destination)
            audio = load_wav(destination)
            if audio.sha256 != record["file_sha256"]:
                raise ValueError(f"{source}: file hash does not match the syllable manifest")
            entries.append({
                "path": destination.relative_to(root).as_posix(),
                "split": split,
                "speaker_id": SYLLABLE_SPEAKER,
                "session_id": session,
                "audio_sha256": audio.sha256,
                "pcm_sha256": audio.pcm_sha256,
                "sample_rate": audio.rate,
                "sample_count": int(len(audio.samples)),
            })
            labels[destination.name] = {
                "item_id": record["item_id"],
                "item_kind": record["item_kind"],
                "base_rendering_id": record["base_rendering_id"],
                "split": split,
                "source_split": folder,
            }
            composition[split]["syllable"] += 1

    manifest = {
        "format_version": MANIFEST_FORMAT,
        "architecture": "private-waveform-only-corpus",
        "learning_tokens": "waveform-features-only",
        "private": True,
        "sources": {
            "human_manifest_sha256": human["manifest_sha256"],
            "human_speaker": sorted({e["speaker_id"] for e in human["entries"]}),
            "syllable_manifest_entries": len(syllables["entries"]),
            "composition": composition,
            "human_speech_is_never_dropped": True,
        },
        "entries": entries,
        "sample_rates": sorted({entry["sample_rate"] for entry in entries}),
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    write_json_atomic(root / "manifest.json", manifest)
    write_json_atomic(root / "labels.json", {
        "policy": (
            "provenance and scoring only; never fed to an ant as a token or feature"
        ),
        "labels": labels,
    })
    validate_manifest(root / "manifest.json", root)
    return manifest, composition


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="corpus-combined")
    parser.add_argument("--human", default=str(HUMAN_ROOT))
    parser.add_argument("--syllables", default=str(SYLLABLE_ROOT))
    args = parser.parse_args()
    manifest, composition = build(Path(args.root), Path(args.human), Path(args.syllables))
    print(json.dumps({
        "manifest_sha256": manifest["manifest_sha256"],
        "recording_count": len(manifest["entries"]),
        "composition": composition,
        "sample_rates": manifest["sample_rates"],
    }, indent=2))


if __name__ == "__main__":
    main()

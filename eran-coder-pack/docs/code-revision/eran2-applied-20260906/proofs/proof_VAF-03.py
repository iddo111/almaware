"""VAF-03 proof: waveform exemplars must never come from synthetic fire audio.

Reproduces the live mechanism exactly - fit the codebook on the fire MIX, then
see where each unit's waveform exemplar was lifted from. On eran3 today 35-39
of every ant's 64 exemplars come from another ant's synthesized audio.

FAILS on the pre-revision code, PASSES on the fixed code.
"""
import shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
import acoustic_units, fire  # noqa: E402

UNITS = 16
tmp = Path(tempfile.mkdtemp(prefix="vaf-proof-03-"))
recordings = proof_common.build_project(tmp)
train, heldout = recordings / "train", recordings / "heldout"
real = {acoustic_units.load_wav(p).pcm_sha256 for p in sorted(train.glob("*.wav"))}

seed_checkpoint = acoustic_units.build_checkpoint(train, heldout, "ant-y", UNITS, 7007)
mix = tmp / "mix"
mix.mkdir()
for path in sorted(train.glob("*.wav")):
    shutil.copyfile(path, mix / f"real-{path.name}")
for index, path in enumerate(sorted(train.glob("*.wav"))[:3]):
    samples, _ = acoustic_units.reconstruct(acoustic_units.load_wav(path), seed_checkpoint)
    acoustic_units.write_wav_atomic(
        mix / f"fire-ant-y-utterance-{index:03d}.wav", samples,
        seed_checkpoint["exemplar_rate"],
    )


def synthetic_count(checkpoint):
    return sum(1 for h in checkpoint["exemplar_source_hashes"] if h not in real)


checks = []

contaminated = acoustic_units.build_checkpoint(mix, heldout, "ant-x", UNITS, 7019)
n_default = synthetic_count(contaminated)
checks.append((
    "the fixture reproduces the defect (mix-fitted exemplars are synthetic)",
    n_default > 0,
    f"{n_default}/{UNITS} exemplars came from synthesized audio",
))

try:
    fixed = acoustic_units.build_checkpoint(
        mix, heldout, "ant-x", UNITS, 7019, None, exemplar_folder=train,
    )
    n_fixed = synthetic_count(fixed)
    checks.append((
        "build_checkpoint can fit on the mix and take exemplars from real audio",
        n_fixed == 0, f"{n_fixed}/{UNITS} synthetic exemplars",
    ))
except TypeError as exc:
    checks.append((
        "build_checkpoint can fit on the mix and take exemplars from real audio",
        False, f"no exemplar_folder parameter: {exc}",
    ))

try:
    candidate, _ = acoustic_units.train_ant(
        mix, heldout, tmp / "state-guard", "ant-x", UNITS, 7027, None,
        exemplar_folder=mix, real_pcm_hashes=real,
    )
    checks.append((
        "train_ant REFUSES to promote a checkpoint with synthetic exemplars",
        candidate["promotion_basis"] == "blocked-synthetic-waveform-exemplars"
        and candidate["promotion_eligible"] is False,
        f"basis={candidate['promotion_basis']} eligible={candidate['promotion_eligible']} "
        f"synthetic={candidate.get('exemplars_from_synthetic_audio')}",
    ))
except TypeError as exc:
    checks.append((
        "train_ant REFUSES to promote a checkpoint with synthetic exemplars",
        False, f"no realness guard: {exc}",
    ))

cycle = fire.run_cycle(
    recordings, recordings / "manifest.json", tmp / "state", tmp / "fire",
    units=UNITS, round_id="20260906T000001Z",
)
proportions = [
    mix_info["synthetic_proportion"]
    for mix_info in [
        __import__("json").loads(
            (tmp / "fire" / "20260906T000001Z" / "manifest.json").read_text(encoding="utf-8")
        )["mixes"][ant]
        for ant in ("ant-a", "ant-b", "ant-c", "ant-d")
    ]
]
counts = [entry.get("exemplars_from_synthetic_audio") for entry in cycle["ants"]]
checks.append((
    "a real fire cycle really did mix synthetic audio in",
    all(p > 0 for p in proportions), f"synthetic_proportion per ant = {proportions}",
))
checks.append((
    "every ant in a real fire cycle ends with 0 synthetic exemplars",
    counts == [0, 0, 0, 0], f"exemplars_from_synthetic_audio per ant = {counts}",
))

print(f"workspace: {tmp}")
raise SystemExit(proof_common.report("VAF-03", checks))

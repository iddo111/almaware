"""ears.py — the cochlea. wav -> log-spectral band features -> one utterance.

25 ms Hann frames on a 10 ms hop, per-frame level-normalized magnitude
spectrum summed into N_BANDS log-spaced bands (50-8000 Hz), log taken. The
frozen cochlea then cuts the speech span into EAR_SLICES fixed windows and
mean-pools, mean-removes and L2s each: frequency x time, the way a cochlea
delivers it. Measured 2026-08-21 on the 132-item 22-class heldout: 79.55%
against 66.67% for the onset ear and 68.94% for the best published baseline.

TWO DOORS, and they are not the same door:

  * THE ORGANISM wears whatever genome.EAR_REPR / state/crown.json name, and
    those may only ever name an ear in genome.EAR_REPRS — the FROZEN ANATOMY
    (Iddo, 2026-08-21). A crown naming anything else is refused at wake, by
    name, in a sentence that says what to fix.
  * THE EXAMINER may pass repr_= explicitly to rebuild a historical ear for a
    baseline comparison (proof/ear_frozen_audit.py re-measures the frozen
    claim across all four). That is a deliberate act, never a crown.

Either way an ear is checked against the genome constants it actually needs
BEFORE it hears anything. The scar (2026-08-21): "onset" outlived its
ONSET_MS / ONSET_START_FRAC and died with AttributeError from inside pool(),
after frames() had already run — a crash mid-beat instead of a refusal at
birth. Missing constants are now named at construction; the audit supplies
its own reconstructed values and proceeds, and the organism never can.

Config comes entirely from the genome, with state/crown.json able to override
N_BANDS / pooling — this is the tournament-evolvable organ (queen-and-cochlea).

HARD GUARD: during LIFE the ears refuse any path containing 'heldout'.
The heldout is exam-only; only the examiner opens the vault (exam=True).
Embodies: the organism hears audio only — never a label, never a name.
"""
import json
import os
import struct
import wave

import numpy as np

import genome


class HeldoutGuard(RuntimeError):
    pass


def _dct(v, keep):
    """DCT-II of a band profile. Coefficient 0 is the overall spectral tilt —
    it is what every syllable shares, so the caller drops it."""
    n = np.arange(len(v))
    k = np.arange(keep)[:, None]
    return np.cos(np.pi * k * (2 * n + 1) / (2 * len(v))) @ v


def load_crown(crown_path=None):
    """The tournament's genome-override file. Absent -> genome defaults."""
    path = crown_path or genome.CROWN_FILE
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return {}
    return {}


def read_wav(path):
    """16 kHz mono 16-bit PCM wav -> float32 samples in [-1, 1]."""
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected mono 16-bit PCM")
        rate = w.getframerate()
        pcm = w.readframes(w.getnframes())
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if rate != genome.SAMPLE_RATE:
        # linear resample to the canonical rate (the ant farm's own move)
        n = max(1, round(len(samples) * genome.SAMPLE_RATE / rate))
        src = np.linspace(0.0, 1.0, len(samples), endpoint=False)
        dst = np.linspace(0.0, 1.0, n, endpoint=False)
        samples = np.interp(dst, src, samples).astype(np.float32)
    return samples


def write_wav(path, samples):
    """float samples in [-1,1] -> 16 kHz mono 16-bit PCM wav (struct header)."""
    x = np.clip(np.asarray(samples, dtype=np.float64), -1.0, 1.0)
    data = (x * 32767.0).astype("<i2").tobytes()
    sr = genome.SAMPLE_RATE
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(data)) + data)


def _band_slices(n_bands):
    """Log-spaced band edges 50-8000 Hz mapped to FFT bin ranges.

    Every band is forced to hold at least one bin (low log-spaced bands are
    narrower than one 31.25 Hz bin; an empty band would be a dead constant).
    """
    bins = genome.N_FFT // 2 + 1
    hz_per_bin = genome.SAMPLE_RATE / genome.N_FFT
    edges_hz = np.geomspace(genome.FMIN_HZ, genome.FMAX_HZ, n_bands + 1)
    idx = np.round(edges_hz / hz_per_bin).astype(int)
    idx[0] = max(idx[0], 1)                      # skip DC
    for i in range(1, len(idx)):
        idx[i] = max(idx[i], idx[i - 1] + 1)     # at least one bin per band
    idx = np.minimum(idx, bins)
    return [(int(idx[i]), int(idx[i + 1])) for i in range(n_bands)]


# The genome constants each ear needs before it can hear a single frame.
# Checked in __init__ so a missing one is a named refusal at birth, never an
# AttributeError from inside pool() halfway through a beat. "onset" is the
# scar: ONSET_MS and ONSET_START_FRAC were deleted when the ear was frozen and
# exist in no revision of genome.py, so the shipped onset ear is unbuildable —
# proof/ear_frozen_audit.py reconstructs them on purpose, flags them as a
# reconstruction, and only then may build it.
_REPR_NEEDS = {
    "cochlea":  ("EAR_SLICES", "EAR_SPEECH_FRAC"),
    "bands":    (),
    "cepstrum": ("N_CEPSTRA",),
    "onset":    ("N_CEPSTRA", "ONSET_MS", "ONSET_START_FRAC"),
}


class Ears:
    def __init__(self, exam=False, n_bands=None, pooling=None, crown_path=None,
                 repr_=None):
        crown = load_crown(crown_path)
        self.repr = str(repr_ or crown.get("repr") or genome.EAR_REPR)
        # Door 1 — THE ORGANISM. Whatever the genome or a crown names must be
        # an ear the frozen anatomy allows. An explicit repr_ is door 2: the
        # examiner deliberately rebuilding a historical ear to compare against.
        # The test is `not repr_`, not `repr_ is None`, so it matches the `or`
        # chain above exactly — a falsy repr_ ("" ) resolves from the crown and
        # must therefore be judged as a crown, or it would slip past door 1.
        if not repr_ and self.repr not in genome.EAR_REPRS:
            raise ValueError(
                f"crowned ear repr {self.repr!r} is not the frozen anatomy "
                f"({'/'.join(genome.EAR_REPRS)}) — FROZEN ANATOMY, genome.py, "
                f"Iddo 2026-08-21. Fix state/crown.json or genome.EAR_REPR. "
                f"Only the examiner may build another ear, and only by "
                f"passing repr_= on purpose.")
        if self.repr not in _REPR_NEEDS:
            raise ValueError(
                f"unknown ear repr {self.repr!r} — this body knows only "
                f"{'/'.join(sorted(_REPR_NEEDS))}")
        missing = [c for c in _REPR_NEEDS[self.repr] if not hasattr(genome, c)]
        if missing:
            raise ValueError(
                f"the {self.repr!r} ear needs genome."
                f"{', genome.'.join(missing)}, which do not exist. That ear "
                f"was deleted with the freeze and cannot hear; supply the "
                f"constants explicitly (as proof/ear_frozen_audit.py does, "
                f"flagged as a reconstruction) or use {genome.EAR_REPR!r}.")
        self.exam = bool(exam)
        self.n_bands = int(n_bands or crown.get("n_bands") or genome.N_BANDS)
        self.pooling = str(pooling or crown.get("pooling") or genome.POOLING)
        # The percept's width. "bands" keeps the band profile; "cepstrum" and
        # "onset" return N_CEPSTRA-1 coefficients (c0 dropped). Everything that
        # sizes a brain must ask the EAR for its dim, never assume n_bands.
        if self.repr == "cochlea":
            self.dim = genome.EAR_SLICES * self.n_bands
        elif self.repr in ("cepstrum", "onset"):
            self.dim = min(genome.N_CEPSTRA, self.n_bands) - 1
        else:
            self.dim = self.n_bands
        self.frame = round(genome.SAMPLE_RATE * genome.FRAME_MS / 1000)   # 400
        self.hop = round(genome.SAMPLE_RATE * genome.HOP_MS / 1000)       # 160
        self.window = np.hanning(self.frame).astype(np.float32)
        self.slices = _band_slices(self.n_bands)

    # ------------------------------------------------------------------ guard
    def _guard(self, path):
        if not self.exam and "heldout" in str(path).replace("\\", "/").lower():
            raise HeldoutGuard(
                f"LIFE may not eat the heldout (exam-only): {path}")

    # ----------------------------------------------------------------- frames
    def _frames_from_samples(self, samples):
        """The actual framing+spectrum math, on whatever samples it is given.

        Shared by frames(path) and utterance_from_samples() below — a wav on
        disk and a mouth's own waveform in memory hit the EXACT same code
        from this line on. No separate implementation anywhere.
        """
        samples = np.asarray(samples, dtype=np.float32)
        if len(samples) < self.frame:
            samples = np.pad(samples, (0, self.frame - len(samples)))
        count = 1 + (len(samples) - self.frame) // self.hop
        starts = self.hop * np.arange(count)
        x = samples[starts[:, None] + np.arange(self.frame)[None, :]] * self.window
        rms = np.sqrt(np.mean(x * x, axis=1) + genome.EAR_EPS)
        spectrum = np.abs(np.fft.rfft(x, genome.N_FFT, axis=1)) + genome.EAR_EPS
        spectrum = spectrum / spectrum.sum(axis=1, keepdims=True)   # level-free
        bands = np.stack([spectrum[:, a:b].sum(axis=1) for a, b in self.slices],
                         axis=1)
        return np.log(bands + genome.EAR_EPS), rms

    def frames(self, path):
        """(n_frames, n_bands) log-band features + (n_frames,) frame RMS.

        Kept as an accessor for future sequence work; the utterance vector
        below is v0's only consumer.
        """
        self._guard(path)
        samples = read_wav(path)
        return self._frames_from_samples(samples)

    # -------------------------------------------------------------- utterance
    def pool(self, feats, rms):
        """Pooling per genome/crown: loudest60 (proven), mean, loudest40.

        The frozen cochlea reads none of it — it returns before `kept` is ever
        used, because a cochlea has no pooling choice. The branch survives for
        the legacy ears the examiner rebuilds (proof/ear_frozen_audit.py).
        """
        if self.pooling == "mean":
            kept = feats
        else:
            frac = 0.40 if self.pooling == "loudest40" else genome.LOUD_FRACTION
            keep = max(1, int(round(frac * len(feats))))
            order = np.argsort(rms, kind="stable")[-keep:]
            kept = feats[np.sort(order)]
        if self.repr == "cochlea":
            # THE FROZEN EAR. Frequency x time, the way a cochlea delivers it.
            # Per-slice loudness is removed (a cochlea codes shape, and the
            # brain should not be able to cheat with volume); each slice is
            # L2'd so no slice can shout down the others.
            live = rms > (float(np.max(rms)) * genome.EAR_SPEECH_FRAC
                          if len(rms) else 0.0)
            idx = np.where(live)[0]
            if len(idx) < genome.EAR_SLICES:
                idx = np.arange(len(rms))
            seg = feats[idx[0]:idx[-1] + 1]
            M = np.stack([p.mean(axis=0)
                          for p in np.array_split(seg, genome.EAR_SLICES)])
            M = M - M.mean(axis=1, keepdims=True)
            n = np.linalg.norm(M, axis=1, keepdims=True)
            v = (M / np.where(n > 0, n, 1.0)).ravel()
            vn = np.linalg.norm(v)
            return v / vn if vn > 0 else v
        if self.repr == "onset":
            # A syllable's identity lives in its ATTACK. Pooling the loudest
            # frames keeps the vowel and throws the consonant away, so ba, ah
            # and aa all collapse onto their shared /a/ — which is exactly
            # where the organism got stuck on 2026-08-21. It measured 66.67%
            # on the 22-class heldout against 40.15% for loudest-60% pooling,
            # and then LOST to the frozen cochlea's 79.55%. Kept only so the
            # examiner can re-measure that comparison; __init__ refuses to
            # build it unless its deleted constants are supplied explicitly.
            v = feats[slice(*self.onset_window(rms))].mean(axis=0)
        else:
            v = kept.mean(axis=0)
        if self.repr in ("cepstrum", "onset"):
            v = _dct(v, genome.N_CEPSTRA)[1:]      # drop c0: the shared tilt
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def onset_window(self, rms):
        """(start, stop) frame indices: speech onset -> onset + ONSET_MS.

        genome.ONSET_MS / ONSET_START_FRAC no longer exist; __init__ refuses to
        build an onset ear without them, so reaching here means the caller
        supplied them on purpose."""
        peak = float(np.max(rms)) if len(rms) else 0.0
        loud = rms > peak * genome.ONSET_START_FRAC
        start = int(np.argmax(loud)) if bool(loud.any()) else 0
        span = max(2, int(round(genome.ONSET_MS / genome.HOP_MS)))
        return start, min(len(rms), start + span)

    def utterance(self, path):
        """One wav -> one L2-normalized vector. The whole v0 percept."""
        feats, rms = self.frames(path)
        return self.pool(feats, rms)

    def utterance_from_samples(self, samples):
        """Raw float samples -> one L2-normalized vector, with NO file ever
        touching disk. This is how the organism hears its OWN mouth during
        babbling — voice/babble.py's only way in. It shares _frames_from_samples
        and pool() with utterance(path) exactly, so a wav and the same
        samples handed straight from the mouth produce byte-identical
        percepts (proof/test_mouth.py checks this directly). Never guarded
        against 'heldout' — there is no path here, and the mouth's own
        output was never anyone's held-out recording."""
        feats, rms = self._frames_from_samples(samples)
        return self.pool(feats, rms)

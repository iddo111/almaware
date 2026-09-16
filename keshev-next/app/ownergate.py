import os
import sys
import argparse
import logging
import numpy as np

DEFAULT_THRESHOLD = 0.65

_logger = logging.getLogger(__name__)
_encoder = None

def _get_encoder():
    global _encoder
    if _encoder is None:
        from resemblyzer import VoiceEncoder
        _encoder = VoiceEncoder(device="cpu", verbose=False)
    return _encoder

class OwnerGate:
    def __init__(self, profile_path=None, threshold=None):
        self._usable = False
        try:
            if profile_path is not None:
                final_profile_path = profile_path
            elif os.environ.get("KESHEV_VOICEPRINT"):
                final_profile_path = os.environ["KESHEV_VOICEPRINT"]
            else:
                root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                live_profile = os.path.join(root_dir, "state", "voiceprint-live.npy")
                fallback_profile = r"D:\CLAUDE\voice-input\profiles\iddo1\voiceprint.npy"
                final_profile_path = live_profile if os.path.exists(live_profile) else fallback_profile

            self._voiceprint = np.load(final_profile_path).astype(np.float32)
            if self._voiceprint.shape != (256,):
                raise ValueError("Voiceprint shape mismatch")
            if not np.isclose(np.linalg.norm(self._voiceprint), 1.0):
                raise ValueError("Voiceprint not normalized")

            if threshold is not None:
                self._threshold = float(threshold)
            elif os.environ.get("KESHEV_GATE_THRESHOLD"):
                try:
                    self._threshold = float(os.environ["KESHEV_GATE_THRESHOLD"])
                except ValueError:
                    self._threshold = DEFAULT_THRESHOLD
            else:
                self._threshold = DEFAULT_THRESHOLD

            self._usable = True
        except Exception as e:
            print(f"WARNING: OwnerGate unusable: {e}", file=sys.stderr)

    def identify(self, pcm_bytes: bytes, sample_rate: int = 16000) -> tuple[bool, float]:
        if not self._usable:
            return (False, 0.0)
        if not pcm_bytes or len(pcm_bytes) % 2 != 0:
            return (False, 0.0)
        try:
            int16_array = np.frombuffer(pcm_bytes, dtype=np.int16)
            float_array = int16_array.astype(np.float32) / 32768.0

            from resemblyzer import preprocess_wav
            wav = preprocess_wav(float_array, source_sr=sample_rate)
            if wav is None or len(wav) < 16000 * 0.4:
                return (False, 0.0)

            emb = _get_encoder().embed_utterance(wav)
            score = float(np.dot(emb, self._voiceprint))
            return (score >= self._threshold, score)
        except Exception:
            return (False, 0.0)

    def is_owner(self, pcm_bytes: bytes, sample_rate: int = 16000) -> bool:
        return self.identify(pcm_bytes, sample_rate)[0]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if not args.selftest:
        print("Usage: python app/ownergate.py --selftest")
        sys.exit(0)

    try:
        os.environ.pop("KESHEV_VOICEPRINT", None)
        os.environ.pop("KESHEV_GATE_THRESHOLD", None)
        gate = OwnerGate()
        if not hasattr(gate, '_voiceprint') or gate._voiceprint.shape != (256,):
            print("OWNERGATE FAIL: voiceprint shape mismatch")
            sys.exit(1)
        if abs(gate._threshold - 0.65) > 1e-6:
            print("OWNERGATE FAIL: threshold mismatch")
            sys.exit(1)

        os.environ["KESHEV_GATE_THRESHOLD"] = "0.9"
        if abs(OwnerGate()._threshold - 0.9) > 1e-6:
            print("OWNERGATE FAIL: env threshold not applied")
            sys.exit(1)
        os.environ["KESHEV_GATE_THRESHOLD"] = "not-a-number"
        if abs(OwnerGate()._threshold - 0.65) > 1e-6:
            print("OWNERGATE FAIL: malformed env threshold not defaulted")
            sys.exit(1)
        os.environ.pop("KESHEV_GATE_THRESHOLD", None)

        os.environ["KESHEV_VOICEPRINT"] = r"D:\CLAUDE\voice-input\profiles\iddo1\voiceprint.npy"
        if OwnerGate()._voiceprint.shape != (256,):
            print("OWNERGATE FAIL: env profile not loaded")
            sys.exit(1)
        os.environ.pop("KESHEV_VOICEPRINT", None)

        silence = b"\x00" * (16000 * 2)
        if gate.is_owner(silence) is not False:
            print("OWNERGATE FAIL: silence not rejected")
            sys.exit(1)

        rng = np.random.default_rng(0)
        noise_int16 = (rng.uniform(-0.25, 0.25, 16000 * 2) * 32767).astype(np.int16)
        noise = noise_int16.tobytes()
        r = gate.identify(noise)
        if not isinstance(r[0], (bool, np.bool_)) or not isinstance(r[1], float):
            print("OWNERGATE FAIL: noise result type mismatch")
            sys.exit(1)
        print(f"noise score vs owner: {r[1]:.3f}")

        broken = OwnerGate(profile_path=r"Z:\no\such\file.npy")
        if broken.is_owner(silence) is not False:
            print("OWNERGATE FAIL: broken gate not rejecting")
            sys.exit(1)

        print("OWNERGATE OK")
        sys.exit(0)
    except Exception as e:
        print(f"OWNERGATE FAIL: {e}")
        sys.exit(1)

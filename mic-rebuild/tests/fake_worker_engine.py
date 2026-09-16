"""K9 fake local engine — loaded by keshev_worker via `--engine fake:tests.fake_worker_engine`.

Lets the worker subprocess be exercised for real (real pipes, real kill,
real generation-id law) without CUDA, without faster-whisper, and without
the 8GB shared GPU that the live crutch mic is holding (wave guardrail).

Behavior triggers are carried IN THE PCM PAYLOAD so the worker code needs
no test-only branches:

  * payload starting with b"HANG"  -> decode blocks forever (stuck-decode
    kill path, section 4.3: "a STUCK decode never drains — it is killed").
  * payload starting with b"BOOM"  -> decode raises RuntimeError.
  * anything else                  -> deterministic Hebrew reply.

`build()` is the factory contract keshev_worker expects from an engine
module: build(model_name) -> engine with .warm() and .decode().
"""
from __future__ import annotations

import time

VRAM_MB = 7  # what the fake reports as its resident footprint


class FakeEngine:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.warm_called = False

    def warm(self) -> dict:
        """Stands in for the REAL 1s zero-audio CUDA inference."""
        if self.model_name == "warmfail":
            raise RuntimeError("synthetic warm failure (scar-11 path)")
        self.warm_called = True
        return {"vram_mb": VRAM_MB, "warm_ms": 1}

    def decode(self, pcm: bytes, lang_hint: str) -> dict:
        if not self.warm_called:
            raise RuntimeError("decode before warm — READY law violated")
        if pcm.startswith(b"HANG"):
            time.sleep(3600)
        if pcm.startswith(b"BOOM"):
            raise RuntimeError("synthetic engine failure")
        return {
            "text": "שלום עולם",
            "lang": "he" if lang_hint in ("auto", "he") else lang_hint,
            "avg_logprob": -0.21,
            "no_speech_prob": 0.02,
        }


def build(model_name: str) -> FakeEngine:
    return FakeEngine(model_name)

#!/usr/bin/env python3
"""K9 fallback-model measurement harness (PHASE2-DESIGN.md section 7 + K9 row,
open question 4).

Decides the worker's warm-resident fallback model by NUMBERS, not vibes:

  cer   — Hebrew CER of each candidate vs the PRIMARY engine's transcript
          (iddo-lora-run2-ct2 on eran1, K2-verified) over real Café-Claude /
          voice_corpus clips. Runs CPU-int8 BY DESIGN OF THE MEASUREMENT:
          the PC GPU is 8GB SHARED and the live crutch mic holds ~2.6GB of
          it — loading the big candidate (ivrit turbo, ~1.6GB) for a mere
          benchmark risks the crutch (wave guardrail). CER is compute-type
          stable enough for a ranking; the CHOSEN model's real GPU footprint
          is measured separately below. This file is a MEASUREMENT TOOL:
          the product's worker (client/keshev_worker.py) has no CPU code
          path (scar 47) and never imports this.
  vram  — REAL GPU footprint + kill-release proof for the small ladder
          rungs: spawns the real keshev_worker (--engine ct2), reads the
          ready frame's vram_mb (nvidia-smi delta across load+warm, i.e.
          scar-11 dummy inference included), TerminateProcess's it, and
          asserts free VRAM returns (criterion 2, real model edition).
          Only run when free VRAM >= need + guardrail floor; the harness
          probes first and REFUSES (exit 3) rather than squeeze the crutch.

Reference transcripts: produced on eran1 by ~/keshev-spike/ref_k9.py
(iddo-lora-run2-ct2, cuda/int8_float16, the same decode guards). CER here
is therefore "divergence from the primary engine" — the fallback's actual
job — not absolute ground truth; recorded honestly in the report.

Usage (PC, the python that has faster-whisper — py313 today):
  python tools/measure_k9_model.py cer  --wavs <dir> --ref <ref_k9.json>
  python tools/measure_k9_model.py vram --wavs <dir> --models tiny,base,small
Reports land in state/reports/k9-model-*.json.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CANDIDATES = {
    "ivrit-turbo": "ivrit-ai/whisper-large-v3-turbo-ct2",
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
    "tiny": "Systran/faster-whisper-tiny",
}

GUARDRAIL_FLOOR_MB = 1500  # never take the last 1.5GB from the shared GPU

_STRIP = re.compile(r"[֑-ׇ‎‏‪-‮]")
_PUNCT = re.compile(r"[^\w\s֐-׿]", re.UNICODE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _STRIP.sub("", text)
    text = _PUNCT.sub(" ", text)
    return " ".join(text.lower().split())


def cer(ref: str, hyp: str) -> float:
    """Character error rate: levenshtein(ref, hyp) / len(ref)."""
    r, h = normalize(ref), normalize(hyp)
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i, rc in enumerate(r, 1):
        cur = [i]
        for j, hc in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / len(r)


def free_vram_mb() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10, check=True).stdout
    return int(out.strip().splitlines()[0])


def report_path(kind: str) -> Path:
    d = REPO / "state" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"k9-model-{kind}-{date.today().isoformat()}.json"


# ------------------------------------------------------------------ cer

def run_cer(wav_dir: Path, ref_file: Path, models: list[str],
            threads: int) -> dict:
    from faster_whisper import WhisperModel
    from common.decode_params import decode_kwargs

    refs = json.loads(ref_file.read_text(encoding="utf-8"))
    wavs = sorted(p for p in wav_dir.glob("*.wav") if p.name in refs)
    if not wavs:
        raise SystemExit(f"no wavs in {wav_dir} matching the reference set")
    out = {"kind": "cer", "n_clips": len(wavs), "reference":
           "iddo-lora-run2-ct2 @ eran1 (primary engine, K2-verified)",
           "compute": f"cpu/int8 threads={threads} (guardrail: GPU shared w/ live crutch)",
           "models": {}}
    for name in models:
        src = CANDIDATES[name]
        t0 = time.time()
        m = WhisperModel(src, device="cpu", compute_type="int8",
                         cpu_threads=threads)
        load_s = round(time.time() - t0, 1)
        per, times = [], []
        for w in wavs:
            t1 = time.time()
            segs, info = m.transcribe(str(w), language="he", **decode_kwargs())
            hyp = " ".join(s.text.strip() for s in segs).strip()
            times.append(round((time.time() - t1) * 1000))
            per.append({"wav": w.name, "cer": round(cer(refs[w.name], hyp), 4),
                        "hyp": hyp})
        cers = sorted(p["cer"] for p in per)
        out["models"][name] = {
            "hf": src, "load_s": load_s,
            "cer_mean": round(sum(cers) / len(cers), 4),
            "cer_median": round(cers[len(cers) // 2], 4),
            "cer_worst": round(cers[-1], 4),
            "cpu_decode_ms_p50": sorted(times)[len(times) // 2],
            "per_clip": per,
        }
        del m
        print(f"  {name}: CER mean={out['models'][name]['cer_mean']} "
              f"median={out['models'][name]['cer_median']} "
              f"worst={out['models'][name]['cer_worst']}", flush=True)
    return out


# ------------------------------------------------------------------ vram

def run_vram(wav_dir: Path, models: list[str]) -> dict:
    """Real worker spawn -> ready.vram_mb -> one real decode -> kill ->
    free-VRAM recovery assert. The criterion-2 datapoint with a REAL model."""
    from common.protocol import pack_frame, read_frame

    out = {"kind": "vram", "gpu": "RTX 3070 Ti 8GB shared",
           "guardrail_floor_mb": GUARDRAIL_FLOOR_MB, "models": {}}
    wav = sorted(wav_dir.glob("*.wav"))[0]
    import wave as wavmod
    with wavmod.open(str(wav)) as w:
        pcm = w.readframes(w.getnframes())

    for name in models:
        free0 = free_vram_mb()
        # Wave guardrail, literal: probe first; free < 1.5GB -> DEFERRED.
        # Plus a self-OOM sanity margin over the provisional need.
        from client.keshev_worker import VRAM_NEED_MB
        need = VRAM_NEED_MB.get(name, 1000)
        if free0 < GUARDRAIL_FLOOR_MB or free0 < need + 300:
            out["models"][name] = {"verdict": "DEFERRED",
                                   "free_mb_at_probe": free0,
                                   "reason": "guardrail: would squeeze the live crutch"}
            print(f"  {name}: DEFERRED (free={free0}MB)", flush=True)
            continue
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "client.keshev_worker",
             "--gen", "1", "--engine", "ct2", "--model", name],
            cwd=str(REPO), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        rec = {"free_mb_before": free0}
        try:
            t0 = time.time()
            ready = None
            while True:
                fr = read_frame(proc.stdout)
                if fr is None:
                    err = proc.stderr.read().decode("utf-8", "replace")[-400:]
                    rec.update(verdict="FAILED", err=err)
                    break
                header, _ = fr
                if header.get("event") == "ready":
                    ready = header
                    break
                if header.get("event") == "fatal":
                    rec.update(verdict="FAILED", err=header.get("err"))
                    break
            if ready:
                rec["ready_s"] = round(time.time() - t0, 1)
                rec["vram_mb_load_plus_warm"] = ready["vram_mb"]
                rec["warm_ms"] = ready["warm_ms"]
                free_loaded = free_vram_mb()
                rec["free_mb_loaded"] = free_loaded
                t1 = time.time()
                proc.stdin.write(pack_frame(
                    {"gen": 1, "cmd": "decode", "id": "k9vram-000001",
                     "engine": "local", "lang_hint": "he"}, pcm[:960_000]))
                proc.stdin.flush()
                reply, _ = read_frame(proc.stdout)
                rec["real_decode_ms"] = int((time.time() - t1) * 1000)
                rec["decode_ok"] = bool(reply.get("ok"))
                rec["hyp_len"] = len(reply.get("text") or "")
        finally:
            proc.kill()
            proc.wait(timeout=15)
        if "verdict" not in rec:
            # criterion-2: the kill must give the VRAM back
            deadline = time.time() + 10
            free_after = free_vram_mb()
            while free_after - rec["free_mb_loaded"] < max(1, rec["vram_mb_load_plus_warm"] // 2) \
                    and time.time() < deadline:
                time.sleep(0.5)
                free_after = free_vram_mb()
            rec["free_mb_after_kill"] = free_after
            rec["released_mb"] = free_after - rec["free_mb_loaded"]
            rec["verdict"] = ("VERIFIED" if rec["released_mb"] >=
                              max(1, rec["vram_mb_load_plus_warm"] // 2) else "BROKEN")
        out["models"][name] = rec
        print(f"  {name}: {rec.get('verdict')} "
              f"footprint={rec.get('vram_mb_load_plus_warm')}MB "
              f"released={rec.get('released_mb')}MB "
              f"decode={rec.get('real_decode_ms')}ms", flush=True)
        time.sleep(1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=["cer", "vram"])
    ap.add_argument("--wavs", type=Path, required=True)
    ap.add_argument("--ref", type=Path, help="reference JSON (cer mode)")
    ap.add_argument("--models", default=None,
                    help="comma list; default: all candidates (cer) / tiny,base,small (vram)")
    ap.add_argument("--threads", type=int, default=6,
                    help="cpu threads for cer mode (thermal cap in force)")
    args = ap.parse_args()

    if args.mode == "cer":
        if not args.ref:
            ap.error("--ref required for cer mode")
        models = (args.models.split(",") if args.models
                  else list(CANDIDATES))
        result = run_cer(args.wavs, args.ref, models, args.threads)
    else:
        models = (args.models.split(",") if args.models
                  else ["tiny", "base", "small"])
        free0 = free_vram_mb()
        if free0 < GUARDRAIL_FLOOR_MB:
            print(f"REFUSED: free VRAM {free0}MB < guardrail floor "
                  f"{GUARDRAIL_FLOOR_MB}MB — GPU load test DEFERRED")
            return 3
        result = run_vram(args.wavs, models)

    path = report_path(args.mode)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

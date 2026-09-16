# -*- coding: utf-8 -*-
"""
KESHEV-LORA / eval_gate.py  --  the go/no-go gate. "Helps and does not harm", measured.

WHAT IT DOES
------------
On the HELD-OUT eval split of Iddo's own voice (never trained on), it decodes every clip
with BOTH models and compares them under decode settings identical to the live server:

    baseline = ivrit-ai/whisper-large-v3-turbo-ct2         (what :8738 serves today)
    lora     = ivrit-ai + personal LoRA, merged & CT2-converted   (data/lora-ct2)

Metrics per model:  CER, WER, and correct-project-name count.

THE RULE IDDO SET
-----------------
    PASS  iff   LoRA CER < baseline CER   AND   LoRA project-names >= baseline project-names
    FAIL  otherwise.  A tie or a loss is a LOSS -- the LoRA is discarded and we say so.

This does NOT deploy anything. It produces the numbers. Deployment is Iddo's call.

WHERE IT RUNS
-------------
On a fleet box with faster-whisper + ctranslate2 (same stack as keshev-6). It loads two
CT2 model dirs and decodes locally, so the comparison is apples-to-apples with serving.
(An HTTP mode against live :8738 / :8737 is also provided for baseline spot-checks.)

    PYTHONIOENCODING=utf-8 python eval_gate.py \
        --data ./data \
        --baseline-ct2 /path/to/ivrit-ai-whisper-large-v3-turbo-ct2 \
        --lora-ct2 ./data/lora-ct2
"""
from __future__ import annotations
import argparse, json, os, re, sys

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from script_he import is_eval  # noqa: E402

# Decode params identical to keshev-6 server (keshev6_server.py decode()).
DECODE = dict(language="he", beam_size=5, temperature=[0.0, 0.2],
              condition_on_previous_text=False, compression_ratio_threshold=2.4,
              no_speech_threshold=0.6, without_timestamps=True, vad_filter=False)

# Names-only initial prompt (matches the keshev-6 "a word enters the prompt only if the
# model cannot already know it" rule). Applied equally to BOTH models, so it never favours
# one over the other; it only makes the comparison reflect real serving.
PROMPT_HE = ("ערן, עלמה, קשב, צלם, קו, וינסטון, מיקו, מקום, דרוויש, פסייטראנס, "
             "הולובריין, פדרציה, צ'ינצ'ילה, סונט, אופוס, הרמס, OpenClaw, DGX.")

# Project names to score, each with accepted spelling variants (all normalised).
PROJECT_NAMES = {
    "eran": ["ערן"],
    "alma": ["עלמה"],
    "keshev": ["קשב"],
    "tzelem": ["צלם"],
    "kav": ["קו"],
    "winston": ["וינסטון"],
    "miko": ["מיקו"],
    "darwish": ["דרוויש", "דרויש"],
    "psytrance": ["פסייטראנס", "פסיטראנס"],
    "holobrain": ["הולובריין", "הולו בריין"],
    "makom": ["מקום"],
    "federation": ["פדרציה"],
    "chinchilla": ["צ'ינצ'ילה", "צינצילה"],
    "sonnet": ["סונט", "sonnet"],
    "opus": ["אופוס", "opus"],
    "hermes": ["הרמס", "hermes"],
    "openclaw": ["openclaw", "אופנקלו"],
    "dgx": ["dgx", "די ג'י אקס"],
    "claude": ["קלוד", "claude"],
    "shamash": ["שמש"],
    "almido": ["אלמידו"],
    "quorum": ["קוורום"],
    "ramchat": ["רמצ'אט", "רמצאט"],
    "lora": ["לורה"],
}

_punct = re.compile(r"[^\w\s]", re.UNICODE)
_niqqud = re.compile(r"[֑-ׇ‎‏]")


def norm(s: str) -> str:
    s = _niqqud.sub("", s or "")
    s = _punct.sub(" ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def edit_distance(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref, hyp):
    r = norm(ref).replace(" ", "")
    return edit_distance(r, norm(hyp).replace(" ", "")) / max(1, len(r))


def wer(ref, hyp):
    r, h = norm(ref).split(), norm(hyp).split()
    return edit_distance(r, h) / max(1, len(r))


def names_in(text):
    """Multiset of project-name keys present in `text` (by any accepted variant)."""
    t = " " + norm(text) + " "
    found = []
    for key, variants in PROJECT_NAMES.items():
        for v in variants:
            nv = norm(v)
            if nv and (" " + nv + " ") in t:
                found.append(key)
                break
    return found


# ------------------------------------------------------------------ decoders
def load_ct2(model_dir):
    from faster_whisper import WhisperModel
    return WhisperModel(model_dir, device="cuda", compute_type="int8_float16")


def decode_ct2(model, wav, use_prompt):
    import soundfile as sf
    audio, sr = sf.read(wav, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    kw = dict(DECODE)
    if use_prompt:
        kw["initial_prompt"] = PROMPT_HE
    segs, _ = model.transcribe(audio, **kw)
    return " ".join(s.text.strip() for s in segs).strip()


def decode_http(url, wav):
    """Spot-check baseline against a live server (:8738 etc). Best-effort."""
    import urllib.request
    with open(wav, "rb") as f:
        data = f.read()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/octet-stream",
                                          "X-Lang-Hint": "he"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return (json.loads(r.read().decode("utf-8")) or {}).get("text", "").strip()


# ------------------------------------------------------------------ eval
def load_eval_rows(data_dir):
    man = os.path.join(data_dir, "manifest.jsonl")
    if not os.path.exists(man):
        sys.exit(f"[gate] no manifest at {man}. Record clips first (python record.py).")
    rows = []
    with open(man, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            pid = r.get("prompt_id", 0)
            if not is_eval({"id": pid, "block": r.get("block", "")}):
                continue
            wav = os.path.join(data_dir, "clips", os.path.basename(r["wav"]))
            if os.path.exists(wav) and (r.get("text") or "").strip():
                rows.append({"wav": wav, "text": r["text"].strip(), "block": r.get("block", "")})
    if not rows:
        sys.exit("[gate] eval split is empty -- no held-out clips recorded yet.")
    return rows


def score(rows, decode_fn, tag):
    tot_cer = tot_wer = 0.0
    name_ref = name_hit = 0
    n = 0
    for r in rows:
        hyp = decode_fn(r["wav"])
        tot_cer += cer(r["text"], hyp)
        tot_wer += wer(r["text"], hyp)
        ref_names = names_in(r["text"])
        hyp_names = names_in(hyp)
        name_ref += len(ref_names)
        # count each referenced name that also appears in the hypothesis
        hleft = list(hyp_names)
        for k in ref_names:
            if k in hleft:
                hleft.remove(k)
                name_hit += 1
        n += 1
    res = {"tag": tag, "n": n, "cer": tot_cer / n, "wer": tot_wer / n,
           "names_ref": name_ref, "names_hit": name_hit}
    print(f"[gate] {tag:16s} n={n} CER={res['cer']:.4f} WER={res['wer']:.4f} "
          f"names={name_hit}/{name_ref}", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--baseline-ct2", dest="baseline_ct2", default="",
                    help="path to the ivrit-ai baseline CT2 model dir")
    ap.add_argument("--lora-ct2", dest="lora_ct2", default=os.path.join(HERE, "data", "lora-ct2"))
    ap.add_argument("--baseline-url", dest="baseline_url", default="",
                    help="alt: score baseline via a live HTTP server instead of a CT2 dir")
    ap.add_argument("--no-prompt", action="store_true",
                    help="decode without the names prompt (measures the raw model delta)")
    ap.add_argument("--out", default=os.path.join(HERE, "data", "gate_result.json"))
    a = ap.parse_args()

    use_prompt = not a.no_prompt
    rows = load_eval_rows(a.data)
    print(f"[gate] held-out eval clips: {len(rows)}   prompt={'on' if use_prompt else 'off'}\n")

    # baseline
    if a.baseline_url:
        base = score(rows, lambda w: decode_http(a.baseline_url, w), "BASELINE(http)")
    else:
        if not a.baseline_ct2:
            sys.exit("[gate] need --baseline-ct2 <dir-or-hf-repo-id> (or --baseline-url). See README.")
        # accepts a local CT2 dir OR a HF repo id (e.g. ivrit-ai/whisper-large-v3-turbo-ct2)
        bm = load_ct2(a.baseline_ct2)
        base = score(rows, lambda w: decode_ct2(bm, w, use_prompt), "BASELINE")

    # lora
    if not os.path.isdir(a.lora_ct2):
        sys.exit(f"[gate] no LoRA CT2 model at {a.lora_ct2}. Run train_lora.py first.")
    lm = load_ct2(a.lora_ct2)
    lora = score(rows, lambda w: decode_ct2(lm, w, use_prompt), "LORA")

    # verdict
    cer_better = lora["cer"] < base["cer"]
    names_ok = lora["names_hit"] >= base["names_hit"]
    passed = bool(cer_better and names_ok)
    d_cer = base["cer"] - lora["cer"]

    print("\n" + "=" * 60)
    print(f"  CER:   baseline {base['cer']:.4f}  ->  lora {lora['cer']:.4f}   "
          f"({'-' if d_cer>=0 else '+'}{abs(d_cer)*100:.2f} pts CER, "
          f"{'better' if cer_better else 'NOT better'})")
    print(f"  names: baseline {base['names_hit']}/{base['names_ref']}  ->  "
          f"lora {lora['names_hit']}/{lora['names_ref']}   "
          f"({'ok' if names_ok else 'REGRESSED'})")
    print(f"  WER:   baseline {base['wer']:.4f}  ->  lora {lora['wer']:.4f}   (context only)")
    print("-" * 60)
    print(f"  VERDICT:  {'PASS -- LoRA helps. Iddo may deploy.' if passed else 'FAIL -- LoRA does not beat baseline. Discard it.'}")
    print("  Rule: deploy iff CER strictly lower AND project-names not fewer.")
    print("=" * 60)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"baseline": base, "lora": lora, "passed": passed,
                   "cer_better": cer_better, "names_ok": names_ok,
                   "prompt": use_prompt}, f, ensure_ascii=False, indent=2)
    print(f"[gate] wrote {a.out}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

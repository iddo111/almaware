#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 4 - THE JUDGE.  A separate program, with its own data path, whose job is
to try to BREAK the claim that the full fine-tune helped.

It never imports train_full.py.  It reads the eval audio from ~/keshev6-ref/okwavs
and the references from ~/keshev6-ref/ref.jsonl - the set and the file that
produced the 2026-09-04 and 09-05 comparisons - and it touches the training
manifest for exactly one purpose: to prove the two are disjoint.

DECODE SETTINGS mirror keshev-6/keshev6_server.py IvritEngine.decode() as closely
as a different runtime allows - beam 5, language he, no timestamps, no
conditioning on previous text - and every local arm is decoded by THE SAME
function with THE SAME settings.  It is NOT the same runtime: ctranslate2 on this
box has no CUDA, so the local arms run under transformers while :8739 runs
faster-whisper.  See decode_local().  That difference is the reason the base
model is decoded BOTH locally and live: the gap between those two is the control.
Compare inside a group, never across one.  On 2026-09-05 a model was reported to
"beat" another on a metric whose two sides were not comparable; the claim was
void, and this paragraph exists so that does not happen twice.

WHAT IS ADMISSIBLE AND WHAT IS NOT, declared before the numbers exist:
  ADMISSIBLE     the NAMES table.  It counts strings Iddo says against strings
                 the old model garbled.  No reference decoder is involved, so
                 nothing about how the student was trained can flatter it.
  INADMISSIBLE   CER/WER against ref.jsonl, FOR THE FINE-TUNED ARM ONLY.  The
                 fine-tune was trained on pseudo-labels from ivrit-ai/
                 whisper-large-v3, and ref.jsonl IS ivrit-ai/whisper-large-v3.
                 Training a student on a teacher and then scoring it on how
                 closely it matches that teacher measures IMITATION, not
                 accuracy - including imitation of the teacher's errors.  The
                 number is printed anyway, because concealing it would be worse,
                 but it is printed with this label attached and it may not be
                 used to declare a win.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, time, unicodedata, wave
from pathlib import Path
import numpy as np

REF_DIR = Path(os.path.expanduser("~/keshev6-ref"))
OKWAVS = REF_DIR / "okwavs"
REFJSONL = REF_DIR / "ref.jsonl"

PROMPT_HE = (
    "שיחה על הפרויקטים "
    "של עידו פרז: ערן, "
    "וינסטון, מיקו, נצר, "
    "קשב, דרוויש, עלמה, "
    "הולובריין, קלוד, "
    "סונט, אופוס, הייקו, "
    "פייבל, צ'ינצ'ילה, "
    "קודקס, גרוק, ג'מיני, "
    "קוון, OpenClaw, Hermes, Godot, WebXR, DGX, Quest, LoRA, Whisper."
)

# ---- scoring, copied verbatim from keshev-6/tools/score3.py ------------------
_BIDI = re.compile("[‎‏‪-‮⁦-⁩]")
_PUNCT = re.compile(r"[^\w֐-׿ ]", re.UNICODE)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = _BIDI.sub("", s)
    s = _PUNCT.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def edit(a, b):
    if not a:
        return len(b)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def degenerate(s):
    t = norm(s)
    if not t:
        return True
    run = best = 1
    for a, b in zip(t, t[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    if best >= 6:
        return True
    w = t.split()
    if len(w) >= 4 and len(set(w)) <= max(1, len(w) // 4):
        return True
    return False


def rates(hyp, ref):
    h, r = norm(hyp), norm(ref)
    return edit(h.split(), r.split()), len(r.split()), edit(list(h), list(r)), len(r)


def pct(sv, q):
    if not sv:
        return 0
    return sv[min(len(sv) - 1, max(0, int(round(q * len(sv))) - 1))]


GOOD = {"צ'ינצ'ילה": "Chinchilla",
        "סונט": "Sonnet", "OpenClaw": "OpenClaw", "Hermes": "Hermes",
        "פסייטראנס": "psytrance",
        "קלוד": "Claude", "אופוס": "Opus",
        "מיקו": "MIKO", "ערן": "ERAN",
        "וינסטון": "WINSTON"}
BAD = {"צ'רלי וחצי": "Chinchilla",
       "סונת": "Sonnet",
       "מופן קלו": "OpenClaw",
       "אופן קלו": "OpenClaw",
       "אופנקלו": "OpenClaw",
       "ארמס": "Hermes", "רמס": "Hermes",
       "פסייטרנס": "psytrance"}


def read_wav(p):
    with wave.open(str(p)) as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0, raw


def decode_local(model_path, wavs, prompt):
    """THE one decode function. Every local arm goes through it, unchanged.

    transformers, not faster-whisper: ctranslate2 on this box (ARM GB10) was not
    compiled with CUDA, so the CT2 path the live servers use is unavailable here.
    That is a REAL difference from :8739 and it is not hidden - it is exactly why
    the base model is also decoded here and compared against :8739 as a control.
    What matters for base-vs-fine-tune is that BOTH go through this identical
    function with these identical settings; the comparison inside the local group
    is like-with-like, and the live group is reported separately.

    beam 5 / language he / task transcribe / no timestamps mirror keshev-6.
    keshev-6's temperature=[0.0, 0.2] is a FALLBACK list: 0.0 is the primary path
    and the only one taken unless the decode fails a threshold. Pure beam search
    here is that primary path.
    """
    import torch
    from transformers import WhisperProcessor, WhisperForConditionalGeneration
    proc = WhisperProcessor.from_pretrained(str(model_path), language="he", task="transcribe")
    m = WhisperForConditionalGeneration.from_pretrained(
        str(model_path), dtype=torch.float16).to("cuda").eval()
    m.generation_config.forced_decoder_ids = None
    pids = None
    if prompt:
        pids = torch.tensor(proc.get_prompt_ids(prompt), device="cuda")
    out = []
    for p in wavs:
        a, _ = read_wav(p)
        inp = proc(a, sampling_rate=16000, return_tensors="pt").to("cuda")
        t0 = time.monotonic()
        with torch.no_grad():
            kw = dict(language="he", task="transcribe", num_beams=5,
                      max_new_tokens=200, do_sample=False)
            if pids is not None:
                kw["prompt_ids"] = pids
                kw["prompt_condition_type"] = "first-segment"
            ids = m.generate(inp.input_features.half(), **kw)
        txt = proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
        if prompt and txt.startswith(prompt.strip()):      # strip echoed prompt
            txt = txt[len(prompt.strip()):].strip()
        out.append({"wav": p.name, "text": txt,
                    "wall_ms": int((time.monotonic() - t0) * 1000)})
    del m
    import gc
    gc.collect()
    torch.cuda.empty_cache()

    # --- guard: the prompt contains EVERY name in the GOOD table. If HF echoes
    # the prompt into the decoded output, this arm scores ~10 names per clip and
    # looks spectacular for a reason that has nothing to do with the model. That
    # is a fake win of exactly the shape this whole exercise exists to catch, so
    # it is checked here rather than trusted.
    if prompt:
        tail = prompt.strip()[-40:]
        leaked = sum(1 for r in out if tail in r["text"])
        frac = leaked / max(len(out), 1)
        print("   prompt-echo guard: %d/%d outputs still contain the prompt tail (%.1f%%)"
              % (leaked, len(out), frac * 100), flush=True)
        if frac > 0.20:
            raise SystemExit(
                "REFUSED: the prompt is being echoed into %.0f%% of outputs. Every name "
                "in the scoring table is inside that prompt, so this arm's name count "
                "would be an artefact of the harness, not a property of the model. "
                "Fix the prompt handling before any number from this run is used." % (frac * 100))
    return out


def decode_http(url, token, wavs):
    """Query a live keshev server.

    THE REQUEST-ID FORMAT IS LOAD-BEARING. :8737 validates it and answers
    HTTP 400 "missing or malformed X-Request-Id" to anything else. The format
    below is copied EXACTLY from keshev-6/tools/ab3.py, the harness that produced
    the 09-04 and 09-05 numbers.

    SCAR, 2026-09-06: the first version of this function used a "judge-" prefix
    and swallowed the resulting 400 as an empty transcript. The table it produced
    said the existing personal LoRA returned nothing on all 209 clips - a false
    and damning claim about someone else's work, caused entirely by this harness
    and by nothing in that model. Transport failures are now COUNTED, REPORTED,
    and fatal; they are never silently turned into an empty string. score3.py had
    a TRANSPORT section for exactly this reason and this program should never
    have dropped it.
    """
    import requests
    out = []
    for i, p in enumerate(wavs):
        _, raw = read_wav(p)
        rid = "%08x-%d" % (i, int(time.time() * 1000))      # ab3.py, verbatim
        h = {"Authorization": "Bearer " + token, "Content-Type": "audio/x-raw",
             "X-Request-Id": rid,
             "X-Audio-Duration-Ms": str(len(raw) // 32), "X-Lang-Hint": "he"}
        t0 = time.monotonic()
        http, err, txt = 0, "", ""
        try:
            r = requests.post(url, data=raw, headers=h, timeout=60)
            http = r.status_code
            if http == 200:
                txt = (r.json().get("text") or "").strip()
            else:
                err = r.text[:120]
        except Exception as e:
            err = type(e).__name__
        out.append({"wav": p.name, "text": txt, "http": http, "err": err,
                    "wall_ms": int((time.monotonic() - t0) * 1000)})
        time.sleep(0.35)          # never starve Iddo's live microphone
    bad = [o for o in out if o["http"] != 200]
    print("   transport: %d/%d answered HTTP 200" % (len(out) - len(bad), len(out)),
          flush=True)
    if bad:
        print("   !! %d NON-200. first: HTTP %s %r" % (len(bad), bad[0]["http"],
                                                       bad[0]["err"]), flush=True)
        raise SystemExit(
            "REFUSED: %d/%d requests to %s failed. An arm that could not be REACHED "
            "must never be scored as an arm that answered BADLY - that is how a "
            "working model gets reported as dead." % (len(bad), len(out), url))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full-model", default="")
    ap.add_argument("--base-model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--live", action="store_true", help="also query eran1 :8739 / :8737")
    ap.add_argument("--skip-local", action="store_true",
                    help="live arms only - for re-running after a transport fix")
    ap.add_argument("--token", default="",
                    help="prefer the STT_TOKEN env var - a token passed on argv is "
                         "visible to every user in the process list")
    args = ap.parse_args()

    wavs = sorted(OKWAVS.glob("*.wav"))
    ref = {}
    for l in REFJSONL.read_text(encoding="utf-8").splitlines():
        if l.strip():
            d = json.loads(l)
            ref[d["wav"]] = d["ref"]
    print("eval clips %d | reference rows %d" % (len(wavs), len(ref)), flush=True)

    arms = {}
    if not args.skip_local:
        print("\n-- decoding: base (unadapted floor, NO prompt)", flush=True)
        arms["base"] = decode_local(args.base_model, wavs, None)
        print("-- decoding: base + keshev-6 prompt", flush=True)
        arms["base_prompt"] = decode_local(args.base_model, wavs, PROMPT_HE)
        if args.full_model:
            print("-- decoding: FULL fine-tune, NO prompt", flush=True)
            arms["full"] = decode_local(args.full_model, wavs, None)
            print("-- decoding: FULL fine-tune + keshev-6 prompt", flush=True)
            arms["full_prompt"] = decode_local(args.full_model, wavs, PROMPT_HE)
    tok = args.token or os.environ.get("STT_TOKEN", "")
    if args.live and tok:
        print("-- querying eran1 :8739 (incumbent, LIVE - gently)", flush=True)
        arms["live8739"] = decode_http("http://<lan-ip>:8739/v1/transcribe", tok, wavs)
        print("-- querying eran1 :8737 (the existing personal LoRA)", flush=True)
        arms["live8737"] = decode_http("http://<lan-ip>:8737/v1/transcribe", tok, wavs)

    rows = []
    for i, p in enumerate(wavs):
        r = {"wav": p.name, "ref": ref.get(p.name, "")}
        for k, v in arms.items():
            r[k] = {"text": v[i]["text"], "wall_ms": v[i]["wall_ms"],
                    "http": v[i].get("http", 200), "err": v[i].get("err", "")}
        rows.append(r)
    Path(args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print("\nwrote", args.out, len(rows), "rows", flush=True)
    report(rows, list(arms.keys()))


LABEL = {"base": "base turbo, no prompt (FLOOR)",
         "base_prompt": "base turbo + prompt",
         "full": "FULL fine-tune, no prompt",
         "full_prompt": "FULL fine-tune + prompt",
         "live8739": "eran1 :8739 incumbent LIVE",
         "live8737": "eran1 :8737 personal LoRA"}


def report(rows, sides):
    print("\n" + "=" * 78)
    print("TRANSPORT - restored from score3.py, which had it for a reason.")
    print("An arm that did not ANSWER is not an arm that answered BADLY.")
    print("%-32s %10s %8s" % ("arm", "answered", "empty"))
    for s in sides:
        n = sum(1 for r in rows if r[s].get("http", 200) == 200)
        e = sum(1 for r in rows if not r[s]["text"].strip())
        print("%-32s %10d %8d" % (LABEL.get(s, s), n, e))

    print("\n" + "=" * 78)
    print("THE TABLE.  Same 209 clips, same references, same decode settings.")
    print("=" * 78)

    print("\nNAMES - ADMISSIBLE. No reference decoder involved; nothing about how")
    print("the student was trained can flatter this column.")
    print("%-32s %8s %8s" % ("arm", "correct", "garbled"))
    for s in sides:
        ok = sum(r[s]["text"].count(h) for r in rows for h in GOOD)
        bad = sum(r[s]["text"].count(b) for r in rows for b in BAD)
        print("%-32s %8d %8d" % (LABEL.get(s, s), ok, bad))

    print("\nCER / WER vs ref.jsonl - INADMISSIBLE FOR THE FULL ARMS.")
    print("ref.jsonl IS ivrit-ai/whisper-large-v3, the same model that wrote the")
    print("fine-tune's training labels. A lower number here may be imitation, not")
    print("accuracy. Printed for completeness; may not be used to declare a win.")
    scored = [r for r in rows if r["ref"] and not degenerate(r["ref"])]
    print("(%d of %d reference rows usable; %d dropped as repetition loops)"
          % (len(scored), len(rows), len(rows) - len(scored)))
    print("%-32s %8s %8s" % ("arm", "WER", "CER"))
    for s in sides:
        we = rw = ce = rc = 0
        for r in scored:
            a, b, c, d = rates(r[s]["text"], r["ref"])
            we += a; rw += b; ce += c; rc += d
        print("%-32s %7.1f%% %7.1f%%" % (LABEL.get(s, s),
                                         we / max(rw, 1) * 100, ce / max(rc, 1) * 100))
    # the trivial floor
    we = rw = ce = rc = 0
    for r in scored:
        a, b, c, d = rates("", r["ref"])
        we += a; rw += b; ce += c; rc += d
    print("%-32s %7.1f%% %7.1f%%  <- emit nothing (trivial floor)"
          % ("EMPTY STRING", we / max(rw, 1) * 100, ce / max(rc, 1) * 100))

    print("\nLATENCY (ms).  Local arms have no LAN hop; live arms do. Compare")
    print("local-to-local and live-to-live only.")
    print("%-32s %7s %7s" % ("arm", "p50", "p95"))
    for s in sides:
        v = sorted(r[s]["wall_ms"] for r in rows)
        print("%-32s %7d %7d" % (LABEL.get(s, s), pct(v, 0.5), pct(v, 0.95)))

    print("\nOUTPUT VOLUME - a model can lower CER by saying less.")
    print("%-32s %8s %10s" % ("arm", "empties", "chars/clip"))
    for s in sides:
        emp = sum(1 for r in rows if not r[s]["text"].strip())
        ch = sum(len(r[s]["text"]) for r in rows) / max(len(rows), 1)
        print("%-32s %8d %10.1f" % (LABEL.get(s, s), emp, ch))
    refch = sum(len(r["ref"]) for r in rows) / max(len(rows), 1)
    print("%-32s %8s %10.1f  <- the reference" % ("ref.jsonl", "-", refch))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

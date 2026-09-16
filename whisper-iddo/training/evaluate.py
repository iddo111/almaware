"""Evaluation harness. Mirrors what production actually does at decode time.

The mic app (alma-mic/stt.py) does NOT hand Whisper a language. It runs
detect_language() first, whitelists the answer to {he, en}, then decodes with
that language forced. Measuring with the correct language handed in for free
would hide the single most important failure mode on this fleet -- ivrit-ai
flipping English audio into fluent invented Hebrew -- so this harness reproduces
the production path: predict the language token, whitelist it, then decode.

LID accuracy is reported alongside WER because it is the number that decides
whether a Hebrew-specialised checkpoint is usable for a speaker who is 53%
English.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import corpus_cer, corpus_wer, normalise, score_norm  # noqa: E402
import melgpu  # noqa: E402

_MEL = {}


def _mel_for(fe, dev):
    key = id(fe), str(dev)
    if key not in _MEL:
        _MEL[key] = melgpu.GpuMel(fe, dev)
    return _MEL[key]

ROOT = os.path.expanduser("~/whisper-iddo")


def load_set(name):
    rows = [json.loads(l) for l in
            open(os.path.join(ROOT, "evalsets", name + ".jsonl"), encoding="utf-8")]
    if name.startswith("fleurs"):
        blob = np.memmap(os.path.join(ROOT, "evalsets", name + ".bin"), dtype=np.int16, mode="r")
    else:
        blob = np.memmap(os.path.join(ROOT, "audio.bin"), dtype=np.int16, mode="r")
    return rows, blob


def get_audio(blob, r):
    s = r["off"] // 2
    return np.asarray(blob[s:s + r["n"]], dtype=np.float32) / 32768.0


@torch.no_grad()
def run(model, processor, rows, blob, batch=16, whitelist=("he", "en"), max_new=180,
        force_lang=None):
    """force_lang: None reproduces production (predict + whitelist). Setting it
    to 'he'/'en'/'ref' bypasses language ID -- used to separate 'the model cannot
    transcribe this language' from 'the model cannot RECOGNISE this language',
    which are different defects with different fixes."""
    tok = processor.tokenizer
    fe = processor.feature_extractor
    dev = next(model.parameters()).device
    dt = next(model.parameters()).dtype

    sot = tok.convert_tokens_to_ids("<|startoftranscript|>")
    wl_ids = {lg: tok.convert_tokens_to_ids(f"<|{lg}|>") for lg in whitelist}
    transcribe = tok.convert_tokens_to_ids("<|transcribe|>")
    nots = tok.convert_tokens_to_ids("<|notimestamps|>")
    eot = tok.convert_tokens_to_ids("<|endoftext|>")

    hyps, lids = [], []
    model.eval()
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        wav = torch.from_numpy(
            melgpu.pad_batch([get_audio(blob, r) for r in chunk])).to(dev)
        feats = _mel_for(fe, dev)(wav).to(dt)
        ac = torch.autocast("cuda", torch.bfloat16, enabled=(dt == torch.float32))
        ac.__enter__()
        enc = model.model.encoder(feats)

        # --- step 1: language ID, whitelisted to {he,en} exactly like production
        dec_in = torch.full((len(chunk), 1), sot, device=dev, dtype=torch.long)
        out = model(decoder_input_ids=dec_in, encoder_outputs=enc)
        lg = out.logits[:, -1, :]
        cand = torch.tensor([wl_ids[l] for l in whitelist], device=dev)
        pick = cand[lg[:, cand].argmax(-1)]
        lids += [tok.convert_ids_to_tokens(int(p)).strip("<|>") for p in pick]
        if force_lang is not None:
            forced = [(r["lang"] if r["lang"] in wl_ids else "he") if force_lang == "ref"
                      else force_lang for r in chunk]
            pick = torch.tensor([wl_ids[f] for f in forced], device=dev)

        # --- step 2: decode with that language forced
        prefix = torch.stack([
            torch.tensor([sot, int(p), transcribe, nots], device=dev) for p in pick])
        gen = model.generate(encoder_outputs=enc, decoder_input_ids=prefix,
                             max_new_tokens=max_new, do_sample=False, num_beams=1)
        for g in gen:
            hyps.append(normalise(tok.decode(g, skip_special_tokens=True)))
        ac.__exit__(None, None, None)
        del enc
    return hyps, lids


def score(rows, hyps, lids):
    refs = [r["text"] for r in rows]
    res = {
        "n": len(rows),
        "wer": corpus_wer(refs, hyps),
        "cer": corpus_cer(refs, hyps),
        "empty": sum(1 for h in hyps if not h.strip()) / max(1, len(hyps)),
    }
    # LID accuracy: 'mixed' counts as correct either way -- he+en in one
    # utterance has no single right answer in Whisper's label set.
    ok = tot = 0
    for r, l in zip(rows, lids):
        if r["lang"] == "mixed":
            continue
        tot += 1
        ok += (l == r["lang"])
    res["lid_acc"] = ok / tot if tot else float("nan")
    for lang in ("he", "en", "mixed"):
        idx = [i for i, r in enumerate(rows) if r["lang"] == lang]
        if idx:
            res[f"wer_{lang}"] = corpus_wer([refs[i] for i in idx], [hyps[i] for i in idx])
            res[f"cer_{lang}"] = corpus_cer([refs[i] for i in idx], [hyps[i] for i in idx])
    return res


def load_model(path, dtype=torch.bfloat16, device="cuda"):
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    model = WhisperForConditionalGeneration.from_pretrained(path, dtype=dtype).to(device)
    model.config.forced_decoder_ids = None
    if hasattr(model, "generation_config"):
        model.generation_config.forced_decoder_ids = None
    proc = WhisperProcessor.from_pretrained(path)
    return model, proc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--sets", default="iddo_tierA,iddo_fast,fleurs_he,fleurs_en")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--dump", default=None)
    ap.add_argument("--force-lang", default=None, choices=[None,"he","en","ref"])
    args = ap.parse_args()

    model, proc = load_model(args.model)
    tag = args.tag or os.path.basename(args.model.rstrip("/"))
    allres = {}
    for name in args.sets.split(","):
        rows, blob = load_set(name)
        t0 = time.time()
        hyps, lids = run(model, proc, rows, blob, batch=args.batch,
                         force_lang=args.force_lang)
        r = score(rows, hyps, lids)
        r["secs"] = round(time.time() - t0, 1)
        allres[name] = r
        print(f"[{tag}] {name:12s} WER {r['wer']*100:6.2f}  CER {r['cer']*100:6.2f}  "
              f"LID {r['lid_acc']*100:5.1f}  empty {r['empty']*100:4.1f}%  "
              f"he {r.get('wer_he', float('nan'))*100:6.2f}  "
              f"en {r.get('wer_en', float('nan'))*100:6.2f}  ({r['secs']}s)", flush=True)
        if args.dump:
            os.makedirs(args.dump, exist_ok=True)
            with open(os.path.join(args.dump, f"{tag}.{name}.jsonl"), "w", encoding="utf-8") as f:
                for rr, h, l in zip(rows, hyps, lids):
                    f.write(json.dumps({"ref": rr["text"], "hyp": h, "lang": rr["lang"],
                                        "lid": l, "dur": rr["dur"]}, ensure_ascii=False) + "\n")
    print(json.dumps({tag: allres}, ensure_ascii=False))


if __name__ == "__main__":
    main()

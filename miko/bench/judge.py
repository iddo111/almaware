# -*- coding: utf-8 -*-
"""Stage 2 of pairs.jsonl: a MODEL scores relevance 0-1. Not me. Not a human.

Judge   : Qwen/Qwen3-4B-Instruct-2507  (local weights, eran2, GB10, bf16)
Method  : one forward pass per pair. The assistant turn is opened and the logits of the
          FIRST token are restricted to the six digits "0".."5", softmaxed, and the
          EXPECTED VALUE is taken and divided by 5. That gives a continuous 0-1 score,
          is fully deterministic (no sampling), and needs no generation.
Prompts : two rubrics (see RUBRIC_A / RUBRIC_B below, verbatim). A is the label.
          B is run on a subsample only, to measure how stable the labels are.
"""
import argparse, json, math, os, sys, time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL = "Qwen/Qwen3-4B-Instruct-2507"

SYSTEM = ("You are a strict search-relevance judge. You rate how well a web page answers "
          "a specific question. You reply with a single digit and nothing else.")

RUBRIC_A = """QUESTION:
{q}

WEB PAGE (excerpt):
{p}

Rate how relevant this web page is for answering the QUESTION:
0 = completely unrelated topic
1 = same broad field, but does not address the question at all
2 = touches the question's topic, but gives no usable answer
3 = partially answers the question, or gives useful background
4 = answers the question well
5 = directly and fully answers the question with specifics

Reply with one digit only (0-5)."""

RUBRIC_B = """A user asked this question and a search engine returned the page below.

USER QUESTION: {q}

RETURNED PAGE:
{p}

If the user read this page, how much of their question would be answered?
0 = nothing, the page is about something else entirely
1 = almost nothing, only a shared field or a shared word
2 = a little context, but the question itself is not addressed
3 = some of it, or enough background to start
4 = most of it
5 = all of it, with concrete specifics

Reply with one digit only (0-5)."""

def build(tok, rubric, q, p):
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": rubric.format(q=q, p=p)}]
    return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", default="/home/eran2/miko-bench/data/candidates.jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rubric", default="A")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--bs", type=int, default=16)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.inp, encoding="utf-8")]
    if a.stride > 1:
        rows = rows[::a.stride]
    if a.limit:
        rows = rows[:a.limit]
    rubric = RUBRIC_A if a.rubric == "A" else RUBRIC_B
    print(f"{len(rows)} pairs, rubric {a.rubric}", flush=True)

    tok = AutoTokenizer.from_pretrained(MODEL, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="cuda")
    model.eval()

    digits = [tok.encode(str(d), add_special_tokens=False)[0] for d in range(6)]
    assert len(set(digits)) == 6, digits
    dvals = torch.arange(6, dtype=torch.float32)

    out = open(a.out, "w", encoding="utf-8")
    t0 = time.time()
    done = 0
    for s in range(0, len(rows), a.bs):
        chunk = rows[s:s + a.bs]
        texts = [build(tok, rubric, r["question"], r["page"]) for r in chunk]
        enc = tok(texts, return_tensors="pt", padding=True, truncation=True,
                  max_length=1024).to("cuda")
        with torch.no_grad():
            logits = model(**enc).logits[:, -1, :].float()
        sel = logits[:, digits]
        prob = torch.softmax(sel, dim=-1).cpu()
        ev = (prob * dvals).sum(-1)
        argm = prob.argmax(-1)
        for r, e, am, pr in zip(chunk, ev.tolist(), argm.tolist(), prob.tolist()):
            r = dict(r)
            r["score"] = round(e / 5.0, 6)
            r["score_argmax_digit"] = int(am)
            r["score_digit_probs"] = [round(x, 5) for x in pr]
            r["scoring_model"] = MODEL
            r["scoring_rubric"] = a.rubric
            r["scoring_method"] = "expected value of softmax over first-token digits 0-5, /5"
            r["scored_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
        done += len(chunk)
        if s % (a.bs * 20) == 0:
            el = time.time() - t0
            print(f"  {done}/{len(rows)}  {el:.0f}s  eta {el/max(done,1)*(len(rows)-done):.0f}s",
                  flush=True)
    out.close()
    print(f"done {done} in {time.time()-t0:.0f}s -> {a.out}")

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
r"""Round 2, CHANGE 1: build a question pool of FOUR FIGURES, from two sources.

Round 1 had 65 questions and the diagnosis was explicit: train MSE fell while val MAE
stayed flat, and the vanilla control fit train HARDER while generalising WORSE. That is
memorisation of 39 training questions, not a capacity ceiling. So: more questions.

  --mode corpus : BREADTH, for TRAINING. Sample real fineweb-edu pages and ask the
                  judge model what general question each page genuinely answers. The
                  question is grounded in real corpus content, so the corpus can answer
                  it; the question is written to be GENERAL, so other pages can too.
  --mode iddo   : TRUTH, for TESTING. Take the seeds harvested from Iddo's own written
                  material (harvest_iddo.py) and derive one English research question
                  from each. The SOURCES are his; the PHRASING is derived, because his
                  writing is half Hebrew and the corpus is English. Round 1's 65
                  questions were derived from the same files by hand.

Generator = the same model that judges, Qwen/Qwen3-4B-Instruct-2507, greedy.
"""
import argparse, gzip, json, os, random, re, sys, time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL = "Qwen/Qwen3-4B-Instruct-2507"
HOME = "/home/eran2/miko-bench"

SYS = ("You write short, general research questions for a web search benchmark. "
       "You reply with the question and nothing else.")

P_CORPUS = """Below is an excerpt from an educational web page.

PAGE:
{t}

Write ONE general research question that this page genuinely answers.

Rules:
- It must be a question a curious person would type into a search engine, about the
  SUBJECT ITSELF - not about this page.
- Never write "this page", "the article", "the text", "the author", "the passage".
- Do not name a specific person, company, product or date that only this page mentions.
- One sentence, 8 to 22 words, ending in a question mark.
- Start with How, What, Why, When, Where, Which, Does, Can, Are or Is.

Reply with the question only."""

P_IDDO = """Below is a note from an engineer's own research files. He works on speech and
hearing, neural networks on small machines, custom chips and neuromorphic hardware,
analog and physical computing substrates, solar and community energy, biofeedback and
the nervous system, cycles and statistics, and workshop fabrication.

HIS NOTE:
{t}

Write ONE general research question about the underlying SCIENCE OR ENGINEERING that
this note is concerned with - the kind of question he would need answered from the open
educational web.

Rules:
- Ask about the general principle, not about his project.
- Never name his projects, his machines, his files, or any person.
- The question must be answerable by ordinary English educational web pages.
- One sentence, 8 to 22 words, ending in a question mark.
- Start with How, What, Why, When, Where, Which, Does, Can, Are or Is.

Reply with the question only."""

STARTS = ("how", "what", "why", "when", "where", "which", "does", "do", "can",
          "are", "is", "could", "would", "will", "should", "who")
BANNED = re.compile(r"\b(this page|the page|the article|the text|the passage|the author|"
                    r"the excerpt|the document|the note|above|below|mentioned)\b", re.I)


def normalise(q):
    q = q.strip().strip('"').strip("'").strip()
    q = re.sub(r"^(question|q)\s*[:\-]\s*", "", q, flags=re.I)
    q = q.split("\n")[0].strip()
    if "?" in q:
        q = q[:q.index("?") + 1]
    else:
        q = q.rstrip(".!;: ") + "?"
    return re.sub(r"\s+", " ", q).strip()


def acceptable(q):
    if not (30 <= len(q) <= 175):
        return False
    if not q.endswith("?") or q.count("?") != 1:
        return False
    first = q.lower().split()[0].strip(",")
    if first not in STARTS:
        return False
    if BANNED.search(q):
        return False
    w = len(q.split())
    return 7 <= w <= 26


def key(q):
    """Dedup key: content words only, so two phrasings of one question collapse."""
    ws = [w for w in re.findall(r"[a-z]+", q.lower()) if len(w) > 3]
    return " ".join(sorted(set(ws)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["corpus", "iddo"], required=True)
    ap.add_argument("--n", type=int, default=1600)
    ap.add_argument("--bs", type=int, default=48)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20260905)
    a = ap.parse_args()

    if a.mode == "corpus":
        docs = []
        with gzip.open(HOME + "/data/corpus_full.jsonl.gz", "rt", encoding="utf-8") as f:
            for line in f:
                docs.append(json.loads(line))
        rng = random.Random(a.seed)
        idx = rng.sample(range(len(docs)), min(a.n, len(docs)))
        items = [{"seed_id": "corpus::%d" % i, "source": "corpus",
                  "doc_id": docs[i]["doc_id"], "url": docs[i]["url"],
                  "text": docs[i]["text"][:1400]} for i in idx]
        prompt = P_CORPUS
    else:
        items = [json.loads(l) for l in open(HOME + "/data/iddo_seeds.jsonl",
                                             encoding="utf-8")]
        random.Random(a.seed).shuffle(items)
        items = items[:a.n]
        prompt = P_IDDO

    print("%d seeds, mode=%s" % (len(items), a.mode), flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16,
                                                 device_map="cuda")
    model.eval()

    out, seen, dropped = [], set(), 0
    t0 = time.time()
    for s in range(0, len(items), a.bs):
        chunk = items[s:s + a.bs]
        texts = [tok.apply_chat_template(
            [{"role": "system", "content": SYS},
             {"role": "user", "content": prompt.format(t=it["text"])}],
            tokenize=False, add_generation_prompt=True) for it in chunk]
        enc = tok(texts, return_tensors="pt", padding=True, truncation=True,
                  max_length=1200).to("cuda")
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=48, do_sample=False,
                                 pad_token_id=tok.pad_token_id or tok.eos_token_id)
        new = gen[:, enc["input_ids"].shape[1]:]
        for it, g in zip(chunk, tok.batch_decode(new, skip_special_tokens=True)):
            q = normalise(g)
            if not acceptable(q):
                dropped += 1
                continue
            k = key(q)
            if k in seen:
                dropped += 1
                continue
            seen.add(k)
            out.append({"question": q, "origin": a.mode, "seed_id": it["seed_id"],
                        "seed_source": it.get("source"), "seed_title": it.get("title"),
                        "seed_doc_id": it.get("doc_id"), "seed_url": it.get("url")})
        done = s + len(chunk)
        if s % (a.bs * 5) == 0:
            el = time.time() - t0
            print("  %d/%d kept=%d dropped=%d %.0fs eta %.0fs"
                  % (done, len(items), len(out), dropped, el,
                     el / max(done, 1) * (len(items) - done)), flush=True)

    with open(a.out, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("\nkept %d unique questions, dropped %d (unusable or duplicate) in %.0fs -> %s"
          % (len(out), dropped, time.time() - t0, a.out))
    for r in out[:12]:
        print("   ", r["question"])


if __name__ == "__main__":
    main()

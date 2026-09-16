#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KESHEV 7 eval harness -- 100% our own code, python stdlib only.

Lives in ~/keshev7-eval. The rally cannot touch it: the runner refuses every
command or file that names this directory, the files are chmod a-w, the
reference transcripts sit in refs/ with mode 000, and the runner fingerprints
the whole directory (mode, size, mtime, ctime, sha256) after every command.

Contract under test (the product):
    python3 ~/keshev7/transcribe.py <wav>   ->  prints the text to stdout
run by the runner inside the same cgroup scope and guard as every rally
command, one clip at a time, with a per-clip timeout.

Metric: corpus-level CER and WER after Hebrew normalization (normalize()):
total edits / total reference characters (or words). A clip whose product
fails or times out counts as an EMPTY hypothesis -- skipping clips can never
help. Bar for DONE-ACCEPTED: CER <= 0.25 and at most 5% failed clips.
Baselines (empty output, most-frequent-word) are logged next to every score
so a cheating product is visible.

CLI (manual, safe - never runs rally code):
    python3 eval.py selfcheck
    python3 eval.py baselines --train TRAIN.jsonl --refs HELDOUT.jsonl
To run a real eval use the runner:  python3 ~/keshev7-kof/kof_headless.py eval-now
"""
import collections
import concurrent.futures
import json
import sys
import time
import unicodedata

FINALS = str.maketrans("ךםןףץ", "כמנפצ")
_DROP_CHARS = set("׳״'’‘`\"“”")
_SPACE_HEBREW_MARKS = (0x05BE, 0x05C0, 0x05C3)  # maqaf, paseq, sof pasuq
HYP_MAX_CHARS = 5000


def normalize(text):
    """Hebrew-aware normalization, our own rules:
    NFKC; drop niqqud + cantillation (U+0591-U+05C7) except maqaf/paseq/
    sof-pasuq which become a space; drop geresh, gershayim, apostrophes and
    quote marks; drop combining marks and format chars (bidi RLE/RLM);
    every other non-letter/non-digit becomes a space; lowercase Latin;
    Hebrew final letters -> regular forms; collapse whitespace."""
    t = unicodedata.normalize("NFKC", text or "")
    out = []
    for ch in t:
        o = ord(ch)
        if 0x0591 <= o <= 0x05C7:
            out.append(" " if o in _SPACE_HEBREW_MARKS else "")
            continue
        if ch in _DROP_CHARS:
            continue
        cat = unicodedata.category(ch)
        if cat[0] in "LN":
            out.append(ch)
        elif cat[0] == "M" or cat == "Cf":
            continue
        else:
            out.append(" ")
    s = "".join(out).lower().translate(FINALS)
    return " ".join(s.split())


def has_hebrew(text):
    return any("א" <= c <= "ת" for c in text or "")


def edit_distance(a, b):
    """Levenshtein distance over two sequences (chars or word lists)."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(pairs):
    """pairs = [(reference, hypothesis), ...] -> corpus-level metrics."""
    ce = cn = we = wn = he_e = he_n = n = 0
    for ref, hyp in pairs:
        r = normalize(ref)
        h = normalize(hyp)[:4 * len(r) + 200]
        e = edit_distance(r, h)
        ce += e
        cn += len(r)
        rw = r.split()
        we += edit_distance(rw, h.split())
        wn += len(rw)
        if has_hebrew(r):
            he_e += e
            he_n += len(r)
        n += 1
    return {"cer": round(ce / max(cn, 1), 4),
            "wer": round(we / max(wn, 1), 4),
            "cer_hebrew": round(he_e / he_n, 4) if he_n else None,
            "clips": n, "ref_chars": cn, "ref_words": wn}


def most_frequent_word(texts):
    c = collections.Counter(w for t in texts for w in normalize(t).split())
    return c.most_common(1)[0][0] if c else ""


def baselines(train_texts, ref_texts):
    mfw = most_frequent_word(train_texts)
    b_empty = score([(r, "") for r in ref_texts])
    b_mfw = score([(r, mfw) for r in ref_texts])
    b_mfw["word"] = mfw
    return {"empty": b_empty, "most_frequent_word": b_mfw}


def transcribe_all(clips, transcribe_fn, workers=3, clip_timeout_s=60,
                   max_s=2700, should_stop=None):
    """Call the product's contract on every clip.
    clips: [(clip_id, wav_abs_path)]
    transcribe_fn(wav_abs_path, timeout_s) -> (rc, stdout_text)
    Returns {clip_id: {"text", "ok", "rc", "secs"}}. A clip not reached
    before max_s (or a stop request) is recorded as failed."""
    t0 = time.time()
    hyps = {}

    def one(item):
        cid, wav = item
        if (time.time() - t0 > max_s) or (should_stop and should_stop()):
            return cid, {"text": "", "ok": False, "rc": -1, "secs": 0.0,
                         "note": "not reached (time cap or stop)"}
        s = time.time()
        try:
            rc, out = transcribe_fn(wav, clip_timeout_s)
        except Exception as e:  # the product must never crash the harness
            rc, out = 127, ""
            return cid, {"text": "", "ok": False, "rc": rc,
                         "secs": round(time.time() - s, 2),
                         "note": "harness error: %s" % str(e)[:200]}
        text = " ".join(l.strip() for l in (out or "").splitlines()
                        if l.strip())[:HYP_MAX_CHARS]
        return cid, {"text": text if rc == 0 else "", "ok": rc == 0,
                     "rc": rc, "secs": round(time.time() - s, 2)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        for cid, res in ex.map(one, clips):
            hyps[cid] = res
    return hyps


def finalize(hyps, refs, bar_cer=0.25, max_fail_frac=0.05, base=None,
             runtime_s=0.0, round_no=None, tampered=False):
    """refs: [{"id","text"}]. Missing / failed hypotheses count as empty."""
    pairs = []
    fails = 0
    for r in refs:
        h = hyps.get(r["id"])
        if not h or not h.get("ok"):
            fails += 1
            pairs.append((r["text"], ""))
        else:
            pairs.append((r["text"], h.get("text", "")))
    m = score(pairs)
    fail_frac = fails / max(len(refs), 1)
    accepted = (not tampered and len(refs) > 0 and m["cer"] <= bar_cer
                and fail_frac <= max_fail_frac)
    res = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "round": round_no,
           "cer": m["cer"], "wer": m["wer"], "cer_hebrew": m["cer_hebrew"],
           "clips": len(refs), "failures": fails,
           "fail_frac": round(fail_frac, 4), "runtime_s": round(runtime_s, 1),
           "bar_cer": bar_cer, "accepted": accepted, "tampered": tampered}
    if base:
        res["baseline_empty_cer"] = base.get("empty", {}).get("cer")
        res["baseline_mfw_cer"] = base.get("most_frequent_word", {}).get("cer")
        res["baseline_mfw_word"] = base.get("most_frequent_word", {}).get("word")
    return res


def _selfcheck():
    assert normalize("‫תּוֹדָה רַבָּה.") == "תודה רבה", normalize("‫תּוֹדָה רַבָּה.")
    assert normalize("שלום, עולם!") == "שלומ עולמ"
    assert normalize("צה\"ל ו-ת״א") == "צהל ו תא"
    assert normalize("I don't KNOW.") == "i dont know"
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("abc".split(), "abc".split()) == 0
    assert edit_distance("", "abc") == 3
    s = score([("שלום עולם", "שלום עולם")])
    assert s["cer"] == 0.0 and s["wer"] == 0.0, s
    s = score([("שלום", "")])
    assert s["cer"] == 1.0 and s["wer"] == 1.0, s
    b = baselines(["אני אני הולך"], ["אני כאן"])
    assert b["most_frequent_word"]["word"] == "אני", b
    assert b["empty"]["cer"] == 1.0, b
    print("EVAL-SELFCHECK-OK")


def main(argv):
    if not argv or argv[0] == "selfcheck":
        return _selfcheck()
    if argv[0] == "baselines":
        a = dict(zip(argv[1::2], argv[2::2]))
        train = [json.loads(l)["text"] for l in open(a["--train"], encoding="utf-8") if l.strip()]
        refs = [json.loads(l)["text"] for l in open(a["--refs"], encoding="utf-8") if l.strip()]
        print(json.dumps(baselines(train, refs), ensure_ascii=False, indent=1))
        return
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

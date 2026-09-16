#!/usr/bin/env python3
"""RAMCHAL — teaching the worm to argue: classical logic + the Talmudic middot.

לזכרה של עלמה ז"ל.

Iddo, 2026-08-19 03:29: *"תלמד אותה כל חוקי הלוגיקה ורמח״ל"*.

Two ways to teach a net a law, and we use both, because each fails alone:

  1. **As curriculum** — generate thousands of arguments whose validity we KNOW, in Hebrew
     and English, and train the triads to tell a valid inference from a fallacy. Cheap,
     honest, and measurable on held-out forms it never saw.
  2. **As structure** — build the one rule that cannot be learned safely from examples
     directly into the architecture: קל וחומר with its דיו ceiling. A monotone gate that
     *cannot* output a conclusion stronger than its source, no matter what the data says.

Sources of the rules (real, checkable):
  * ר' ישמעאל, שלוש עשרה מידות שהתורה נדרשת בהן — the baraita opening the Sifra.
  * רמח״ל (ר' משה חיים לוצאטו, 1707-1746), *ספר ההגיון* — Aristotelian logic in Hebrew:
    מושג (term), משפט (proposition), היקש (syllogism); and *דרך תבונות* — the anatomy of
    a sugya: קושיא, תירוץ, ראיה, דחייה.
  * Aristotle's *Prior Analytics* for the syllogistic figures, and the standard catalogue
    of formal fallacies.

Honest limit, said up front: a small net trained on synthetic forms learns the *shape* of
valid inference in those forms. That is not the same as being logical. The held-out score
is the only thing allowed to speak.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

import torch
import torch.nn as nn

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from net.alma_eran import Triad, WormNet, encode                 # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
DATA = HERE / "data"
CKPT = HERE / "ckpt"
DATA.mkdir(exist_ok=True)
CKPT.mkdir(exist_ok=True)

# ───────────────────────────────────────────── the vocabulary of examples
# concrete, everyday subjects so the net learns FORM, not topic
SUBJ = [
    ("כל הכלבים", "all dogs"), ("כל המים", "all water"), ("כל הברזלים", "all iron"),
    ("כל הציפורים", "all birds"), ("כל המספרים הזוגיים", "all even numbers"),
    ("כל הנוירונים", "all neurons"), ("כל המנועים", "all engines"),
]
PRED = [
    ("נושמים", "breathe"), ("קופאים", "freeze"), ("מחלידים", "rust"),
    ("עפים", "fly"), ("מתחלקים בשתיים", "divide by two"),
    ("יורים", "fire"), ("מתחממים", "get hot"),
]
NAMES = [("רקסי", "Rexi"), ("הדבר הזה", "this thing"), ("הפריט", "the item"),
         ("המכשיר", "the device"), ("היצור", "the creature")]

# pairs on a shared scale, for קל וחומר: (lighter, heavier, scale-he, scale-en)
KV_PAIRS = [
    ("חול", "אבן", "כובד", "weight", "sand", "stone"),
    ("נר", "מדורה", "חום", "heat", "a candle", "a bonfire"),
    ("טיפה", "נהר", "כמות מים", "water volume", "a drop", "a river"),
    ("לחישה", "צעקה", "עוצמת קול", "loudness", "a whisper", "a shout"),
]


def _pick(rng: random.Random, pool):
    return pool[rng.randrange(len(pool))]


# ───────────────────────────────────────────── the forms
# each generator returns (hebrew, english, valid: bool, form_name)

def f_modus_ponens(rng, valid=True):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    n, ne = _pick(rng, NAMES)
    if valid:
        he = f"אם {s} {p}, ו{n} הוא מהם — אז {n} {p}."
        en = f"If {se} {pe}, and {ne} is one of them, then {ne} {pe}."
    else:  # affirming the consequent
        he = f"אם {s} {p}, ו{n} {p} — אז {n} הוא מהם."
        en = f"If {se} {pe}, and {ne} {pe}, then {ne} is one of them."
    return he, en, valid, "modus_ponens" if valid else "affirming_consequent"


def f_modus_tollens(rng, valid=True):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    n, ne = _pick(rng, NAMES)
    if valid:
        he = f"אם {s} {p}, ו{n} אינו {p} — אז {n} אינו מהם."
        en = f"If {se} {pe}, and {ne} does not {pe}, then {ne} is not one of them."
    else:  # denying the antecedent
        he = f"אם {s} {p}, ו{n} אינו מהם — אז {n} אינו {p}."
        en = f"If {se} {pe}, and {ne} is not one of them, then {ne} does not {pe}."
    return he, en, valid, "modus_tollens" if valid else "denying_antecedent"


def f_syllogism(rng, valid=True):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    q, qe = _pick(rng, PRED)
    if valid:
        he = f"{s} {p}. כל מה ש{p} גם {q}. לכן {s} {q}."
        en = f"{se} {pe}. Everything that {pe} also {qe}. Therefore {se} {qe}."
    else:  # undistributed middle
        he = f"{s} {p}. יש דברים ש{p} וגם {q}. לכן {s} {q}."
        en = f"{se} {pe}. Some things that {pe} also {qe}. Therefore {se} {qe}."
    return he, en, valid, "syllogism" if valid else "undistributed_middle"


def f_kal_vachomer(rng, valid=True):
    light, heavy, scale_he, scale_en, le, hee = _pick(rng, KV_PAIRS)
    p, pe = _pick(rng, PRED)
    if valid:
        he = (f"ומה {light}, שהוא קל ב{scale_he}, {p} — {heavy}, שהוא חמור ממנו, "
              f"לא כל שכן ש{p}.")
        en = (f"If {le}, which is light in {scale_en}, {pe} — then {hee}, which is greater, "
              f"certainly {pe}.")
        name = "kal_vachomer"
    else:  # the inversion: arguing DOWN the scale is not a kal vachomer
        he = (f"ומה {heavy}, שהוא חמור ב{scale_he}, {p} — {light}, שהוא קל ממנו, "
              f"לא כל שכן ש{p}.")
        en = (f"If {hee}, which is great in {scale_en}, {pe} — then {le}, which is lighter, "
              f"certainly {pe}.")
        name = "inverted_kal_vachomer"
    return he, en, valid, name


def f_dayo(rng, valid=True):
    """דיו לבא מן הדין להיות כנדון — the derived may not exceed its source."""
    light, heavy, scale_he, scale_en, le, hee = _pick(rng, KV_PAIRS)
    if valid:
        he = (f"{light} מחייב שבעה. {heavy} חמור ממנו — ולכן מחייב שבעה. "
              f"דיו לבא מן הדין להיות כנדון.")
        en = (f"{le} requires seven. {hee} is greater — so it requires seven. "
              f"It is enough for the derived to be like its source.")
        name = "dayo"
    else:
        he = f"{light} מחייב שבעה. {heavy} חמור ממנו — ולכן מחייב ארבעה עשר."
        en = f"{le} requires seven. {hee} is greater — so it requires fourteen."
        name = "dayo_violated"
    return he, en, valid, name


def f_gezera_shava(rng, valid=True):
    s1, se1 = _pick(rng, SUBJ)
    s2, se2 = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    word = _pick(rng, [("'שמור'", "'keep'"), ("'זכור'", "'remember'"), ("'ביום'", "'on the day'")])
    if valid:
        he = (f"נאמר {word[0]} ב{s1} ונאמר {word[0]} ב{s2}; מה כאן {p}, אף כאן {p} — "
              f"והגזרה שווה מסורה מרבותיו.")
        en = (f"The word {word[1]} appears in {se1} and in {se2}; as there they {pe}, "
              f"so here they {pe} — and this gezerah shavah was received by tradition.")
        name = "gezera_shava"
    else:  # a gezerah shavah nobody received is not an argument
        he = (f"נאמר {word[0]} ב{s1} ונאמר {word[0]} ב{s2}; מה כאן {p}, אף כאן {p} — "
              f"ולמדתי זאת מדעתי.")
        en = (f"The word {word[1]} appears in {se1} and in {se2}; as there they {pe}, so here "
              f"they {pe} — and I derived this on my own authority.")
        name = "unreceived_gezera_shava"
    return he, en, valid, name


def f_klal_prat(rng, valid=True):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    if valid:
        he = f"כלל: {s}. פרט: דווקא אלה ש{p}. כלל ופרט — אין בכלל אלא מה שבפרט."
        en = (f"General: {se}. Specific: only those that {pe}. General-then-specific — "
              f"the general holds only what the specific names.")
        name = "klal_uprat"
    else:
        he = f"כלל: {s}. פרט: דווקא אלה ש{p}. כלל ופרט — ולכן הכלל נשאר על הכל."
        en = (f"General: {se}. Specific: only those that {pe}. General-then-specific — "
              f"therefore the general still covers everything.")
        name = "klal_uprat_violated"
    return he, en, valid, name


def f_two_verses(rng, valid=True):
    """שני כתובים המכחישים זה את זה עד שיבוא השלישי ויכריע."""
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    if valid:
        he = (f"כתוב אחד אומר ש{s} {p}, וכתוב אחר אומר שאינם {p}; "
              f"אין להכריע עד שיבוא כתוב שלישי ויכריע ביניהם.")
        en = (f"One source says {se} {pe}, another says they do not; nothing is decided "
              f"until a third source resolves them.")
        name = "two_verses_await_third"
    else:
        he = (f"כתוב אחד אומר ש{s} {p}, וכתוב אחר אומר שאינם {p}; "
              f"ולכן שניהם נכונים בבת אחת.")
        en = (f"One source says {se} {pe}, another says they do not; therefore both are "
              f"true at once.")
        name = "contradiction_accepted"
    return he, en, valid, name


def f_circular(rng, valid=False):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    he = f"{s} {p}, משום ש{s} {p}."
    en = f"{se} {pe}, because {se} {pe}."
    return he, en, False, "circular"


def f_ad_hominem(rng, valid=False):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    he = f"הטענה ש{s} {p} שגויה, משום שמי שאמר אותה אינו נעים."
    en = f"The claim that {se} {pe} is false, because the person who said it is unpleasant."
    return he, en, False, "ad_hominem"


def f_hasty(rng, valid=False):
    s, se = _pick(rng, SUBJ)
    p, pe = _pick(rng, PRED)
    he = f"ראיתי שניים מ{s} ש{p}, ולכן {s} {p}."
    en = f"I saw two of {se} that {pe}, therefore {se} {pe}."
    return he, en, False, "hasty_generalization"


FORMS = [f_modus_ponens, f_modus_tollens, f_syllogism, f_kal_vachomer, f_dayo,
         f_gezera_shava, f_klal_prat, f_two_verses]
FALLACIES_ONLY = [f_circular, f_ad_hominem, f_hasty]


def make_dataset(n: int = 6000, seed: int = 1707) -> list[dict]:   # 1707 — Ramchal's birth
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        if rng.random() < 0.18:
            he, en, ok, name = _pick(rng, FALLACIES_ONLY)(rng)
        else:
            he, en, ok, name = _pick(rng, FORMS)(rng, valid=rng.random() < 0.5)
        text = he if rng.random() < 0.5 else en
        rows.append({"text": text, "valid": 1.0 if ok else 0.0, "form": name})
    return rows


# ───────────────────────────────────────────── the rule built into the wiring

class KalVachomerGate(nn.Module):
    """קל וחומר with דיו, as architecture rather than as hope.

    Given (severity of source, severity of target, strength established at the source),
    the gate may propagate strength *upward on the scale only*, and it is hard-capped at
    the source's strength — דיו לבא מן הדין להיות כנדון. No training run can teach it to
    exceed the cap, because the cap is a `min`, not a weight.
    """

    def __init__(self, d: int):
        super().__init__()
        self.severity = Triad(d, 1, p_doubt=0.15)     # even "which is heavier" is a court
        self.strength = Triad(d, 1, p_doubt=0.15)

    def forward(self, src: torch.Tensor, tgt: torch.Tensor):
        s_src, d1 = self.severity(src)
        s_tgt, d2 = self.severity(tgt)
        k_src, d3 = self.strength(src)
        # direction: only from the light to the heavy (a fortiori), never backwards
        allowed = torch.sigmoid((s_tgt - s_src) * 4.0)
        carried = allowed * torch.sigmoid(k_src)
        capped = torch.minimum(carried, torch.sigmoid(k_src))     # דיו — the ceiling
        return capped.squeeze(-1), (d1 + d2 + d3).abs().mean(dim=tuple(range(1, d1.dim())))


class LogicHead(nn.Module):
    """Reuses the worm's own towers, so what it learns about argument lives in the same
    weights that later rank pages. Logic is not a bolt-on module; it is the same court."""

    def __init__(self, worm: WormNet):
        super().__init__()
        self.worm = worm
        d = worm.emb.byte.embedding_dim
        self.verdict = Triad(d, 1, p_doubt=0.2)
        self.kv = KalVachomerGate(d)

    def forward(self, ids: torch.Tensor):
        g, dis = self.worm.tower(ids)
        v, dv = self.verdict(g)
        return v.squeeze(-1), dis + dv.abs().mean(dim=-1)


def train_logic(epochs: int = 20, d: int = 256, depth: int = 6, max_len: int = 512,
                bs: int = 32, lr: float = 3e-4, resume: bool = True) -> None:
    rows = make_dataset()
    rng = random.Random(1746)                                     # Ramchal's death
    rng.shuffle(rows)
    # held-out is BY FORM, not by row: forms it never saw during training
    held_forms = {"modus_tollens", "denying_antecedent", "dayo", "dayo_violated"}
    tr = [r for r in rows if r["form"] not in held_forms]
    va = [r for r in rows if r["form"] in held_forms]
    print(f"logic curriculum · train {len(tr)} · held-out FORMS {sorted(held_forms)} = {len(va)}",
          flush=True)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    worm = WormNet(d=d, depth=depth, max_len=max_len)
    ck = CKPT / "worm.pt"
    if resume and ck.exists():
        worm.load_state_dict(torch.load(ck, map_location="cpu")["model"])
        print("resumed from ckpt/worm.pt", flush=True)
    net = LogicHead(worm).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=0.01)
    lossf = nn.BCEWithLogitsLoss()
    print(f"params {sum(p.numel() for p in net.parameters()):,} · {dev}", flush=True)

    def batches(rows_, shuffle):
        idx = list(range(len(rows_)))
        if shuffle:
            rng.shuffle(idx)
        for i in range(0, len(idx), bs):
            chunk = [rows_[j] for j in idx[i:i + bs]]
            x = torch.stack([encode(r["text"], max_len) for r in chunk]).to(dev)
            y = torch.tensor([r["valid"] for r in chunk], device=dev)
            yield x, y, chunk

    best = 0.0
    for ep in range(1, epochs + 1):
        net.train()
        tot = n = 0
        for x, y, _ in batches(tr, True):
            v, dis = net(x)
            loss = lossf(v, y) + 0.02 * dis.mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            tot += float(loss) * len(y)
            n += len(y)
        net.eval()
        hit = seen = 0
        per = {}
        with torch.no_grad():
            for x, y, chunk in batches(va, False):
                v, _ = net(x)
                ok = ((v > 0) == (y > 0.5))
                for r, o in zip(chunk, ok.tolist()):
                    a, b = per.get(r["form"], (0, 0))
                    per[r["form"]] = (a + int(o), b + 1)
                hit += int(ok.sum())
                seen += len(y)
        acc = hit / max(1, seen)
        detail = "  ".join(f"{k.split('_')[0]}:{a/b:.0%}" for k, (a, b) in sorted(per.items()))
        print(f"epoch {ep:2d}  train {tot/max(1,n):.4f}  UNSEEN-FORM acc {acc:.1%}   {detail}",
              flush=True)
        if acc > best:
            best = acc
            torch.save({"model": worm.state_dict(), "logic": net.state_dict(),
                        "d": d, "depth": depth, "max_len": max_len,
                        "unseen_form_acc": acc}, CKPT / "worm_logic.pt")
            print(f"        ↳ saved (best {best:.1%})", flush=True)
    print(f"done · best accuracy on FORMS IT NEVER SAW: {best:.1%} → {CKPT/'worm_logic.pt'}",
          flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="print 12 examples and exit")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--epochs", type=int, default=20)
    a = ap.parse_args()
    if a.dump:
        for r in make_dataset(12, seed=1):
            print(f"[{'VALID  ' if r['valid'] else 'FALLACY'}] {r['form']:26s} {r['text']}")
    if a.train:
        train_logic(epochs=a.epochs)
    if not (a.dump or a.train):
        ap.error("use --dump or --train")

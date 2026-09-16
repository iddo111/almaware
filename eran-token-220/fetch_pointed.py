"""fetch_pointed.py — a real pointed-Hebrew corpus, so the 10-axis has a
measurable anchor (niqqud), not a mystical one. Public-domain Torah via Sefaria.

Writes corpus_pointed.txt: one verse per line, cantillation (te'amim) stripped,
niqqud kept — because the sefira/nekuda axis IS the niqqud in this test.
"""
from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.request

OUT = pathlib.Path(__file__).resolve().parent / "corpus_pointed.txt"
BOOKS = [("Genesis", 50), ("Exodus", 40), ("Deuteronomy", 34)]   # ~124 chapters

TEAMIM = "".join(chr(c) for c in range(0x0591, 0x05B0))   # cantillation U+0591..05AF
TAG = re.compile(r"<[^>]+>")


def clean(s: str) -> str:
    s = TAG.sub("", s)
    s = "".join(ch for ch in s if ch not in TEAMIM)
    s = s.replace("־", " ").replace("׀", " ")       # maqaf, paseq
    s = re.sub(r"[^א-תְ-ׇּׁׂ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main() -> None:
    lines: list[str] = []
    for book, nchap in BOOKS:
        for ch in range(1, nchap + 1):
            url = f"https://www.sefaria.org/api/texts/{book}.{ch}?context=0&commentary=0"
            try:
                with urllib.request.urlopen(url, timeout=20) as r:
                    d = json.load(r)
            except Exception as e:
                print("skip", book, ch, type(e).__name__)
                continue
            for v in d.get("he", []):
                c = clean(v)
                if len(c) > 8:
                    lines.append(c)
            time.sleep(0.15)                                  # polite
        print(book, "done —", len(lines), "verses so far")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    chars = sum(len(x) for x in lines)
    print(f"wrote {OUT.name}: {len(lines)} verses, ~{chars} chars")


if __name__ == "__main__":
    main()

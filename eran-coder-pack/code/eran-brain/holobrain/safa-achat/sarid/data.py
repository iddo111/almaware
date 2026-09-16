"""Load the bundled Swadesh-style wordlist (TSV, UTF-8)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "swadesh.tsv"

LANG_NAMES = {
    "heb": "Hebrew",
    "arb": "Arabic",
    "arc": "Aramaic",
    "eng": "English",
    "deu": "German",
    "lat": "Latin",
}


@dataclass(frozen=True)
class Entry:
    concept: str
    lang: str
    family: str
    branch: str
    status: str  # living / dead / liturgical
    orthography: str
    ipa: str

    @property
    def lang_name(self) -> str:
        return LANG_NAMES.get(self.lang, self.lang)


def load_wordlist(path: Path | str = DATA_FILE) -> list[Entry]:
    entries: list[Entry] = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            entries.append(
                Entry(
                    concept=row["concept"].strip(),
                    lang=row["lang"].strip(),
                    family=row["family"].strip(),
                    branch=row["branch"].strip(),
                    status=row["status"].strip(),
                    orthography=row["orthography"].strip(),
                    ipa=row["ipa"].strip(),
                )
            )
    return entries


def by_concept(entries: list[Entry]) -> dict[str, list[Entry]]:
    out: dict[str, list[Entry]] = {}
    for e in entries:
        out.setdefault(e.concept, []).append(e)
    return out

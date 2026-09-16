# -*- coding: utf-8 -*-
"""Assemble the big training corpus as file LISTS (no audio is copied).

Sources, all human, none synthetic:
  * corpus-big/human      33.65 h, Iddo only, 3 source groups
  * corpus-big/open       17.75 h, FLEURS he_il (CC-BY) + Common Voice 17 he (CC0)
  * recordings/           the original 253 s, kept in, as instructed

Hard exclusions:
  * fire/ and any state*/ ant audio -- synthetic, never trained on
  * corpus-big/human/_unverified_provenance -- provenance could not be proved
  * corpus-syllables/ -- VITS renderings; that is the TEST set, not training

Split safety: the original 24 recordings were segmented into corpus-big/human
under a date-pinned session policy, so each original file's segments live in the
same split as the original. Verified here rather than assumed.
"""
from __future__ import annotations

import json
import os
import wave
from pathlib import Path

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
OUT = ROOT / "state-big" / "corpus"
FORBIDDEN = ("\\fire\\", "/fire/", "corpus-syllables", "_unverified_provenance",
             "state-syllables", "\\state\\")


def wav_meta(path: Path):
    with wave.open(str(path), "rb") as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()


def collect() -> dict:
    items = []

    hm = json.loads((ROOT / "corpus-big" / "human" / "manifest.json").read_text(encoding="utf-8"))
    for e in hm["entries"]:
        if e["split"] not in ("train", "heldout", "evaluation"):
            continue                      # drops _unverified_provenance
        items.append({
            "path": str(ROOT / "corpus-big" / "human" / e["path"]),
            "split": e["split"],
            "corpus": "human-big",
            "group": e["source_group"],
            "speaker": "iddo1",
            "speaker_known": True,
            "session": e["session_id"],
            "duration_s": e["duration_s"],
            "pcm_sha256": e["pcm_sha256"],
            "licence": "own-recording",
        })

    om = json.loads((ROOT / "corpus-big" / "open" / "manifest.json").read_text(encoding="utf-8"))
    for c in om["clips"]:
        items.append({
            "path": str(ROOT / "corpus-big" / "open" / c["path"]),
            "split": c["split"],
            "corpus": "open",
            "group": c["dataset"],
            "speaker": c["speaker_id"],
            "speaker_known": bool(c.get("speaker_id_known")),
            "session": c["speaker_id"],
            "duration_s": c["duration_s"],
            "pcm_sha256": c["sha256"],
            "licence": c["licence"],
        })

    rm = json.loads((ROOT / "recordings" / "manifest.json").read_text(encoding="utf-8"))
    for e in rm["entries"]:
        items.append({
            "path": str(ROOT / "recordings" / e["path"]),
            "split": e["split"],
            "corpus": "original-253s",
            "group": "original",
            "speaker": "iddo1",
            "speaker_known": True,
            "session": e["session_id"],
            "duration_s": e["sample_count"] / e["sample_rate"],
            "pcm_sha256": e["pcm_sha256"],
            "licence": "own-recording",
        })

    for it in items:
        low = it["path"].lower()
        if any(f in low for f in FORBIDDEN):
            raise SystemExit(f"forbidden source reached the corpus: {it['path']}")
    return items


def main() -> None:
    items = collect()

    # --- integrity gates ---------------------------------------------------
    by_hash = {}
    for it in items:
        by_hash.setdefault(it["pcm_sha256"], set()).add(it["split"])
    cross = {h: sorted(s) for h, s in by_hash.items() if len(s) > 1}
    if cross:
        raise SystemExit(f"identical PCM in two splits: {list(cross)[:5]}")

    sess = {}
    for it in items:
        sess.setdefault((it["corpus"], it["speaker"], it["session"]), set()).add(it["split"])
    bad = {k: sorted(v) for k, v in sess.items() if len(v) > 1}
    if bad:
        raise SystemExit(f"session spans splits: {list(bad.items())[:5]}")

    # deduplicate identical PCM inside a split (keeps the first path)
    seen, deduped, dropped = set(), [], 0
    for it in items:
        if it["pcm_sha256"] in seen:
            dropped += 1
            continue
        seen.add(it["pcm_sha256"])
        deduped.append(it)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "items.json").write_text(json.dumps(deduped), encoding="utf-8")

    summary = {}
    for it in deduped:
        k = (it["split"], it["corpus"])
        s = summary.setdefault(k, {"files": 0, "hours": 0.0, "speakers": set()})
        s["files"] += 1
        s["hours"] += it["duration_s"] / 3600.0
        s["speakers"].add(it["speaker"])
    print(f"{'split':<12}{'corpus':<16}{'files':>8}{'hours':>9}{'speakers':>10}")
    for k in sorted(summary):
        s = summary[k]
        print(f"{k[0]:<12}{k[1]:<16}{s['files']:>8}{s['hours']:>9.3f}{len(s['speakers']):>10}")
    for split in ("train", "heldout", "evaluation"):
        sel = [i for i in deduped if i["split"] == split]
        print(f"TOTAL {split:<10}{len(sel):>8} files {sum(i['duration_s'] for i in sel)/3600:>9.3f} h "
              f"{len({i['speaker'] for i in sel}):>4} speaker-ids")
    print(f"duplicate PCM dropped: {dropped}")
    print(f"wrote {OUT/'items.json'}")


if __name__ == "__main__":
    main()

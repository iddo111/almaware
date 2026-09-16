#!/usr/bin/env python3
"""Survey EVERY Darwish item reachable on YouTube. Metadata only - downloads nothing.

Iddo, 2026-08-14: "feed the Darwish model everything of Darwish from the whole
internet - that is the maximum we can - size the model to it."

The model size has to be set by a measured corpus, not a guess, so this counts
first. It also exists to size the damage from the old sweep's filter: the daily
downloader ran with `--match-filter "duration > 3600"`, which discards every
upload under an hour - single tracks, remixes, EPs, promo mixes, short club sets.
For a DJ that is most of the catalogue.

Dedupe is by video id, because the same set appears under many titles across
queries and channels, and counting it twice would inflate the corpus estimate
that the model size depends on.
"""
import json
import subprocess
import sys
from collections import OrderedDict

QUERIES = [
    # the five the old sweep used
    "darwish psytrance set", "darwish desert adventure", "dj darwish goa trance",
    "darwish live set trance", "darwish ozora",
    # everything it never asked for
    "darwish psytrance", "dj darwish", "darwish deep dave", "deep dave psytrance",
    "darwish remix psytrance", "darwish original mix psytrance",
    "darwish full album psytrance", "darwish ep psytrance",
    "darwish live psytrance israel", "darwish trance mix",
    "darwish psy trance track", "darwish festival set",
    "darwish stomping ground", "darwish purple valley", "darwish exposed album",
    "darwish pettra", "darwish rising dust", "darwish twina", "darwish azax",
    "darwish shpongle", "darwish unite", "darwish psy-fi", "darwish indigo festival",
    "darwish boom festival", "darwish doof", "darwish sunrise set",
]
PER_QUERY = int(sys.argv[1]) if len(sys.argv) > 1 else 60

# titles that are a DIFFERENT Darwish - the poet, the reciter, the singer.
REJECT = ("mahmoud", "poem", "poetry", "quran", "sayed", "nasheed", "محمود")


def probe(q):
    cmd = ["yt-dlp", f"ytsearch{PER_QUERY}:{q}", "--flat-playlist",
           "--print", "%(id)s\t%(duration)s\t%(title)s", "--no-warnings",
           "--ignore-errors"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                             encoding="utf-8", errors="replace")
        return [l for l in out.stdout.splitlines() if "\t" in l]
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT on {q!r}", file=sys.stderr)
        return []


items = OrderedDict()          # id -> (duration_s, title)
for i, q in enumerate(QUERIES, 1):
    rows = probe(q)
    new = 0
    for r in rows:
        parts = r.split("\t", 2)
        if len(parts) < 3:
            continue
        vid, dur, title = parts
        low = title.lower()
        if any(w in low for w in REJECT):
            continue
        if "darwish" not in low and "deep dave" not in low:
            continue                       # the impostor filter, kept
        try:
            d = int(float(dur))
        except (ValueError, TypeError):
            continue
        if d < 60:
            continue                       # shorts / clips, not music
        if vid not in items:
            items[vid] = (d, title)
            new += 1
    print(f"[{i:2d}/{len(QUERIES)}] {q:38s} +{new:3d} new   total {len(items)}",
          flush=True)

total_s = sum(d for d, _ in items.values())
longs = {k: v for k, v in items.items() if v[0] > 3600}
short = {k: v for k, v in items.items() if v[0] <= 3600}

print("\n" + "=" * 64)
print(f"UNIQUE ITEMS      {len(items)}")
print(f"TOTAL AUDIO       {total_s/3600:.1f} hours")
print(f"  > 1 hour        {len(longs):4d} items, {sum(d for d,_ in longs.values())/3600:6.1f} h"
      f"   <- all the old sweep kept")
print(f"  <= 1 hour       {len(short):4d} items, {sum(d for d,_ in short.values())/3600:6.1f} h"
      f"   <- all the old sweep THREW AWAY")
print("=" * 64)

json.dump({"queries": QUERIES, "per_query": PER_QUERY,
           "unique_items": len(items), "total_hours": round(total_s/3600, 2),
           "over_1h_items": len(longs),
           "over_1h_hours": round(sum(d for d, _ in longs.values())/3600, 2),
           "under_1h_items": len(short),
           "under_1h_hours": round(sum(d for d, _ in short.values())/3600, 2),
           "items": [{"id": k, "seconds": v[0], "title": v[1]}
                     for k, v in sorted(items.items(), key=lambda x: -x[1][0])]},
          open("catalog_survey.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("wrote catalog_survey.json")

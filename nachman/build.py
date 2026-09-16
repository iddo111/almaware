"""build.py -- נחמן / Nachman v0.1. Iddo Perez's AI, 2026-08-22. לזכרה של עלמה ז"ל.

Rabbi Nachman said the treasure (אוצר) in Likutei Moharan is not each Torah alone
but the CONNECTIONS -- within each Torah and between them. And Torah 1 itself
teaches that the intellect (שכל) enlivens every thing and CONNECTS it to its root.
So Nachman is built, from the first line, on the connection-graph -- the treasure
as data. Sefaria has already mapped these links; we traverse them.

v0.1: pull Torah 1 (אשרי תמימי דרך) in full -- its text and every connection it
carries (to Tanakh, Talmud, Chasidut, other Torahs) -- and lay the graph bare.
This proves the treasure is traversable. Scaling to the whole corpus is more of
the same loop.
"""
import json, time, urllib.request, urllib.parse, pathlib

API = "https://www.sefaria.org/api"
OUT = pathlib.Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)


def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def text_of(ref):
    """the Hebrew + English of a ref"""
    u = f"{API}/texts/{urllib.parse.quote(ref)}?context=0&commentary=0"
    try:
        d = get(u)
        he = d.get("he", "")
        en = d.get("text", "")
        if isinstance(he, list): he = " ".join(x for x in he if isinstance(x, str))
        if isinstance(en, list): en = " ".join(x for x in en if isinstance(x, str))
        return he, en
    except Exception:
        return "", ""


def links_of(ref):
    u = f"{API}/links/{urllib.parse.quote(ref.replace(' ', '_'))}?with_text=0"
    try:
        return get(u)
    except Exception:
        return []


# how many segments does Torah 1 have? probe the index structure
print("fetching Likutei Moharan structure ...", flush=True)
# Torah 1 segments are Likutei Moharan 1:1, 1:2, ...  probe until empty
torah = 1
segments = []
seg = 1
while seg <= 40:
    ref = f"Likutei Moharan {torah}:{seg}"
    he, en = text_of(ref)
    if not he and not en:
        break
    lk = links_of(f"Likutei Moharan.{torah}.{seg}")
    segments.append({"ref": ref, "seg": seg, "he": he, "en": en, "links": lk})
    print(f"  {ref}: {len(he)} he-chars, {len(lk)} connections", flush=True)
    seg += 1
    time.sleep(0.15)

# build the connection graph for Torah 1
graph = {"torah": 1, "title": "אשרי תמימי דרך", "segments": len(segments), "connections": []}
cats = {}
for s in segments:
    for l in s["links"]:
        c = l.get("category", "?")
        cats[c] = cats.get(c, 0) + 1
        graph["connections"].append({"from": s["ref"], "to": l.get("ref"),
                                     "category": c, "collection": l.get("collectiveTitle", {}).get("en", "")})

(OUT / "torah1.json").write_text(json.dumps({"segments": segments, "graph": graph}, ensure_ascii=False, indent=1), encoding="utf-8")

print("\n===== נחמן v0.1 — תורה א׳, האוצר בקשרים =====")
print(f"segments: {len(segments)}   total connections: {len(graph['connections'])}")
print("the treasure, by category:")
for c, n in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"   {n:4d}  {c}")
print(f"\nsaved -> {OUT/'torah1.json'}")
# show a few actual connections
print("\nsample connections from Torah 1 (each thing linked to its root):")
for con in graph["connections"][:12]:
    print(f"   {con['from']}  →  {con['to']}   [{con['category']}]")

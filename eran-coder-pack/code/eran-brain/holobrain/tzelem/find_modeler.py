"""FIND THE MODELER — our own search for the model that does 3D modelling.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-01 20:50: "תכנת חיפוש שלנו למצוא את המודל שעושה מודלינג - כמו NLP".

The Hub's own text search only matches repository NAMES, so asking it for
"3D mesh generation" returns hobby repos with two downloads and misses every
model that matters. This asks the API the question that actually sorts the field:

    give me every repo carrying the task tag, ordered by downloads

plus a second pass over the AUTOREGRESSIVE-MESH family by name — the lineage that
is literally NLP for geometry: tokenise a mesh, predict the next face the way a
language model predicts the next token (PolyGen -> MeshGPT -> MeshAnything ->
LLaMA-Mesh -> whatever 2026 calls it). That family is the real subject of the
question, and no task tag describes it.

stdlib only: urllib and json. No API key — these endpoints are public.
Every row printed carries its URL, because a result you cannot click is a result
you have to retype.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

API = "https://huggingface.co/api/models"
UA = {"User-Agent": "ALMAWARE-tzelem-find-modeler/1.0"}

TASKS = ["image-to-3d", "text-to-3d"]

# the lineage that models geometry the way an LM models language
AUTOREGRESSIVE = ["MeshGPT", "MeshAnything", "LLaMA-Mesh", "PolyGen", "MeshXL",
                  "MeshAnythingV2", "EdgeRunner", "BPT", "MeshCraft", "TreeMeshGPT"]

# the image-to-3d lineage, for comparison
RECON = ["TRELLIS", "Hunyuan3D", "TripoSR", "TripoSG", "InstantMesh", "SF3D",
         "CraftsMan", "Zero123", "Michelangelo", "Direct3D", "Step1X-3D",
         "PartCrafter", "Hi3DGen"]


def get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def by_task(task: str, limit: int = 40) -> list[dict]:
    q = urllib.parse.urlencode({"pipeline_tag": task, "sort": "downloads",
                                "direction": -1, "limit": limit,
                                "full": "true"})
    return get(f"{API}?{q}")


def by_name(name: str, limit: int = 8) -> list[dict]:
    q = urllib.parse.urlencode({"search": name, "sort": "downloads",
                                "direction": -1, "limit": limit})
    return get(f"{API}?{q}")


def row(m: dict) -> dict:
    return {"id": m.get("modelId") or m.get("id"),
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "task": m.get("pipeline_tag", ""),
            "licence": (m.get("cardData") or {}).get("license", "?"),
            "updated": (m.get("lastModified") or "")[:10],
            "url": "https://huggingface.co/" + (m.get("modelId") or m.get("id", ""))}


def show(title: str, rows: list[dict], n: int = 12) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)
    print("%-46s %10s %6s %-11s" % ("model", "downloads", "likes", "updated"))
    for r in rows[:n]:
        print("%-46s %10d %6d %-11s" % (r["id"][:46], r["downloads"], r["likes"],
                                        r["updated"]))
        print("    %s   licence=%s" % (r["url"], r["licence"]))


def main() -> int:
    out: dict[str, list[dict]] = {}

    for t in TASKS:
        try:
            rows = [row(m) for m in by_task(t)]
        except Exception as e:                                   # noqa: BLE001
            print(f"!! task {t} failed: {e}", file=sys.stderr)
            continue
        out[t] = rows
        show(f"TASK TAG: {t}   (ranked by real downloads)", rows)

    seen = set()
    fam: list[dict] = []
    for name in AUTOREGRESSIVE:
        try:
            hits = by_name(name)
        except Exception as e:                                   # noqa: BLE001
            print(f"!! name {name} failed: {e}", file=sys.stderr)
            continue
        for m in hits:
            r = row(m)
            if r["id"] not in seen:
                seen.add(r["id"])
                r["family_query"] = name
                fam.append(r)
    fam.sort(key=lambda r: -r["downloads"])
    out["autoregressive_mesh"] = fam
    show("THE NLP-SHAPED FAMILY — a mesh predicted token by token", fam, 14)

    seen.clear()
    rec: list[dict] = []
    for name in RECON:
        try:
            hits = by_name(name, limit=5)
        except Exception:                                        # noqa: BLE001
            continue
        for m in hits:
            r = row(m)
            if r["id"] not in seen:
                seen.add(r["id"])
                r["family_query"] = name
                rec.append(r)
    rec.sort(key=lambda r: -r["downloads"])
    out["image_to_3d_lineage"] = rec
    show("THE RECONSTRUCTION LINEAGE — a picture in, a shape out", rec, 14)

    with open("modeler-search.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("\nwrote modeler-search.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

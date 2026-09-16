# -*- coding: utf-8 -*-
"""The roaming world — an ant walks the streets, led by its own curiosity.

Chapter 2 of the cheider (Iddo, 2026-08-11). The ant has ONE eye (retina.py,
the same eye that reads the letter board) and walks a street-imagery graph.
Each step it looks at the neighbouring views, and moves toward what its own
representation finds most NOVEL: high quantisation error against its own
sight-codebook plus a low-visit-count bonus. No script, no labels, no goal —
count-based curiosity. Its visited-graph is journaled: the ant's own map.

Providers (pluggable via state/world/config.json — created on first run):
  offline    a local folder of street photos Iddo drops in
             (world-offline/). No network, no token. Tests the machinery.
  mapillary  Meta's free street-level imagery (CC BY-SA 4.0). Needs a token
             only Iddo can create (MLY|...). Sequence + radius neighbours.
  gsv        Google Street View Static API. Needs an API key with billing
             that only Iddo can create. A HARD MONTHLY CAP is enforced in
             code BEFORE any billable request: default 4500 = 90% of the
             ~5000 free-tier requests/month; the counter persists in
             state/world/gsv-usage.json and the walker refuses past it.
             (The GSV *website* is free for humans; scraping it violates
             Google's ToS, so only the official API is wired.)

Tokens/keys are read from the config file; this code never creates, stores,
or transmits credentials anywhere except the provider's own API.

    py -3.13 world_walker.py --steps 25 --provider offline
    py -3.13 world_walker.py --status
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

import retina
from acoustic_units import encode, write_json_atomic

ROOT = Path(__file__).resolve().parent
WDIR = ROOT / "state" / "world"
CONFIG = WDIR / "config.json"
JOURNAL = WDIR / "walk-journal.json"
GSV_USAGE = WDIR / "gsv-usage.json"
CACHE = ROOT / "world-cache"
OFFLINE_DIR = ROOT / "world-offline"

DEFAULT_CONFIG = {
    "provider": "offline",
    "mapillary_token": None,
    "gsv_api_key": None,
    "offline_dir": str(OFFLINE_DIR),
    "seed_lat": 32.0642,             # Rothschild Blvd, Tel Aviv
    "seed_lon": 34.7743,
    "bbox": [34.74, 32.03, 34.82, 32.12],   # Tel Aviv metro, lon/lat pairs
    "gsv_monthly_cap": 4500,
    "min_seconds_between_requests": 2.0,
    "epsilon": 0.1,
    "codebook_size": 64,
    "cache_max_gb": 2.0,
}


def load_config() -> dict:
    if CONFIG.exists():
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
        return cfg
    WDIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(CONFIG, DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def load_journal() -> dict:
    if JOURNAL.exists():
        return json.loads(JOURNAL.read_text(encoding="utf-8"))
    return {"note": "the ant's own map — every place it chose to look at",
            "steps": [], "visit_counts": {}}


# ------------------------------------------------------------- providers --

class OfflineProvider:
    """A folder of photos = a fully connected little town square."""

    name = "offline"

    def __init__(self, cfg: dict) -> None:
        self.folder = Path(cfg["offline_dir"])
        self.files = sorted(p for p in self.folder.glob("*")
                            if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        if not self.files:
            raise SystemExit(
                f"offline world is empty — drop street photos into "
                f"{self.folder} (png/jpg) and run again")
        self.rng = np.random.default_rng(1234)

    def start_node(self) -> str:
        return self.files[0].name

    def neighbours(self, node: str, limit: int = 8) -> list[dict]:
        others = [f for f in self.files if f.name != node]
        pick = self.rng.choice(len(others), min(limit, len(others)),
                               replace=False)
        return [{"id": others[i].name, "lat": None, "lon": None,
                 "local_path": str(others[i])} for i in pick]

    def fetch(self, cand: dict) -> Path:
        return Path(cand["local_path"])


class MapillaryProvider:
    """Meta's free street imagery. Sequence + radius-search neighbours."""

    name = "mapillary"
    API = "https://graph.mapillary.com"

    def __init__(self, cfg: dict) -> None:
        self.token = cfg.get("mapillary_token")
        if not self.token:
            raise SystemExit(
                "mapillary needs a token in state/world/config.json "
                "(\"mapillary_token\": \"MLY|...\") — only Iddo can create "
                "one at mapillary.com/dashboard/developers")
        self.cfg = cfg
        self._last = 0.0

    def _get(self, path: str, params: dict) -> dict:
        wait = self.cfg["min_seconds_between_requests"] - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        params = dict(params, access_token=self.token)
        url = f"{self.API}{path}?{urllib.parse.urlencode(params)}"
        self._last = time.time()
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read())

    def start_node(self) -> str:
        cfg = self.cfg
        d = 0.004
        bbox = f"{cfg['seed_lon']-d},{cfg['seed_lat']-d}," \
               f"{cfg['seed_lon']+d},{cfg['seed_lat']+d}"
        data = self._get("/images", {"fields": "id", "bbox": bbox, "limit": 1})
        if not data.get("data"):
            raise SystemExit("no mapillary imagery near the seed coordinate")
        return data["data"][0]["id"]

    def neighbours(self, node: str, limit: int = 12) -> list[dict]:
        meta = self._get(f"/{node}",
                         {"fields": "id,geometry,sequence,thumb_256_url"})
        lon, lat = meta["geometry"]["coordinates"]
        d = 0.0006                                      # ~60 m box
        out, seen = [], {node}
        data = self._get("/images", {
            "fields": "id,geometry,thumb_256_url",
            "bbox": f"{lon-d},{lat-d},{lon+d},{lat+d}", "limit": limit * 2})
        west, south, east, north = self.cfg["bbox"]
        for img in data.get("data", []):
            if img["id"] in seen:
                continue
            seen.add(img["id"])
            ilon, ilat = img["geometry"]["coordinates"]
            if not (west <= ilon <= east and south <= ilat <= north):
                continue
            out.append({"id": img["id"], "lat": ilat, "lon": ilon,
                        "url": img.get("thumb_256_url")})
            if len(out) >= limit:
                break
        return out

    def fetch(self, cand: dict) -> Path:
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f"mly_{cand['id']}.jpg"
        if path.exists():
            return path
        url = cand.get("url")
        if not url:
            meta = self._get(f"/{cand['id']}", {"fields": "thumb_256_url"})
            url = meta["thumb_256_url"]
        wait = self.cfg["min_seconds_between_requests"] - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        with urllib.request.urlopen(url, timeout=30) as resp:
            path.write_bytes(resp.read())
        return path


class GSVProvider:
    """Official Street View Static API with a hard free-tier cap.

    Every BILLABLE image request is counted in state/world/gsv-usage.json
    before it is made; at the cap the walker refuses and says so. Metadata
    requests (free per Google's documentation) locate panoramas.
    """

    name = "gsv"
    IMG = "https://maps.googleapis.com/maps/api/streetview"
    META = "https://maps.googleapis.com/maps/api/streetview/metadata"

    def __init__(self, cfg: dict) -> None:
        self.key = cfg.get("gsv_api_key")
        if not self.key:
            raise SystemExit(
                "gsv needs an API key in state/world/config.json "
                "(\"gsv_api_key\": \"AIza...\") — only Iddo can create one "
                "(Google Cloud console, billing enabled; the free tier is "
                "~5000 static requests/month)")
        self.cfg = cfg
        self._last = 0.0

    def _usage(self) -> dict:
        month = dt.date.today().strftime("%Y-%m")
        if GSV_USAGE.exists():
            u = json.loads(GSV_USAGE.read_text(encoding="utf-8"))
            if u.get("month") == month:
                return u
        return {"month": month, "billable_requests": 0}

    def _count_billable(self) -> None:
        u = self._usage()
        cap = int(self.cfg["gsv_monthly_cap"])
        if u["billable_requests"] >= cap:
            raise SystemExit(
                f"GSV hard cap reached: {u['billable_requests']}/{cap} "
                f"billable requests this month ({u['month']}). The walker "
                f"stops here rather than risk a charge. It resets next month.")
        u["billable_requests"] += 1
        write_json_atomic(GSV_USAGE, u)

    def _throttle(self) -> None:
        wait = self.cfg["min_seconds_between_requests"] - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def _meta(self, lat: float, lon: float) -> dict:
        self._throttle()
        url = f"{self.META}?{urllib.parse.urlencode({'location': f'{lat},{lon}', 'key': self.key, 'radius': 60})}"
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read())

    def start_node(self) -> str:
        m = self._meta(self.cfg["seed_lat"], self.cfg["seed_lon"])
        if m.get("status") != "OK":
            raise SystemExit(f"no GSV panorama near seed: {m.get('status')}")
        lat, lon = m["location"]["lat"], m["location"]["lng"]
        return f"{m['pano_id']}|{lat}|{lon}"

    def neighbours(self, node: str, limit: int = 8) -> list[dict]:
        _pano, lat, lon = node.split("|")
        lat, lon = float(lat), float(lon)
        west, south, east, north = self.cfg["bbox"]
        out, seen = [], {node.split("|")[0]}
        step = 0.00012                                   # ~13 m
        for k in range(8):
            ang = k * np.pi / 4
            nlat = lat + step * np.cos(ang)
            nlon = lon + step * np.sin(ang) / np.cos(np.radians(lat))
            if not (west <= nlon <= east and south <= nlat <= north):
                continue
            m = self._meta(nlat, nlon)                   # metadata = free
            if m.get("status") != "OK" or m["pano_id"] in seen:
                continue
            seen.add(m["pano_id"])
            plat, plon = m["location"]["lat"], m["location"]["lng"]
            out.append({"id": f"{m['pano_id']}|{plat}|{plon}",
                        "lat": plat, "lon": plon,
                        "pano_id": m["pano_id"], "heading": int(45 * k)})
            if len(out) >= limit:
                break
        return out

    def fetch(self, cand: dict) -> Path:
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f"gsv_{cand['pano_id']}_{cand.get('heading', 0)}.jpg"
        if path.exists():
            return path
        self._count_billable()                           # cap check FIRST
        self._throttle()
        params = {"pano": cand["pano_id"], "size": "256x256",
                  "heading": cand.get("heading", 0), "key": self.key}
        url = f"{self.IMG}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            path.write_bytes(resp.read())
        return path


PROVIDERS = {"offline": OfflineProvider, "mapillary": MapillaryProvider,
             "gsv": GSVProvider}


# ----------------------------------------------------------------- walker --

class Curiosity:
    """Novelty = quantisation error vs the ant's OWN sight-codebook,
    plus a low-visit-count bonus on the resulting sight-unit."""

    def __init__(self, k: int, seed: int = 7007) -> None:
        self.k = k
        self.rng = np.random.default_rng(seed)
        self.memory: list[np.ndarray] = []
        self.centers: np.ndarray | None = None
        self.scaler: np.ndarray | None = None
        self.visits = np.zeros(k)

    def _rebuild(self) -> None:
        x = np.stack(self.memory)
        self.scaler = np.maximum(x.astype(np.float64).std(axis=0), 1e-6
                                 ).astype(np.float32)
        pick = self.rng.choice(len(x), min(self.k, len(x)), replace=False)
        self.centers = (x[pick] / self.scaler).astype(np.float32)

    def novelty(self, g: np.ndarray) -> tuple[float, int]:
        if self.centers is None or len(self.centers) < 2:
            return 1.0, 0
        z = (g / self.scaler)[None, :]
        d = ((z - self.centers) ** 2).sum(axis=1)
        unit = int(d.argmin())
        bonus = 1.0 / np.sqrt(1.0 + self.visits[unit % self.k])
        return float(d.min()) + float(bonus), unit

    def absorb(self, g: np.ndarray, unit: int) -> None:
        self.memory.append(g.astype(np.float32))
        self.visits[unit % self.k] += 1
        if len(self.memory) in (8, 16, 32) or len(self.memory) % 64 == 0:
            self._rebuild()


def cache_size_gb() -> float:
    if not CACHE.exists():
        return 0.0
    return sum(p.stat().st_size for p in CACHE.rglob("*") if p.is_file()) / 1e9


def walk(steps: int, provider_name: str | None = None) -> dict:
    cfg = load_config()
    name = provider_name or cfg["provider"]
    provider = PROVIDERS[name](cfg)
    journal = load_journal()
    curiosity = Curiosity(int(cfg["codebook_size"]))
    rng = np.random.default_rng()

    node = (journal["steps"][-1]["node"] if journal["steps"]
            and journal["steps"][-1].get("provider") == name
            else provider.start_node())
    taken = 0
    for _ in range(steps):
        if cache_size_gb() > float(cfg["cache_max_gb"]):
            print(f"cache over {cfg['cache_max_gb']} GB — stopping politely")
            break
        cands = provider.neighbours(node)
        if not cands:
            print("dead end — no neighbours; stopping")
            break
        scored = []
        for c in cands:
            try:
                img = retina.load_image(provider.fetch(c))
            except SystemExit:
                raise
            except Exception as exc:
                print(f"  skip {c['id']}: {exc}")
                continue
            g = retina.glimpse(img)
            nov, unit = curiosity.novelty(g)
            scored.append((nov, c, g, unit))
        if not scored:
            break
        if rng.random() < float(cfg["epsilon"]):
            nov, chosen, g, unit = scored[int(rng.integers(len(scored)))]
        else:
            nov, chosen, g, unit = max(scored, key=lambda t: t[0])
        curiosity.absorb(g, unit)
        node = chosen["id"]
        key = str(node)
        journal["visit_counts"][key] = journal["visit_counts"].get(key, 0) + 1
        journal["steps"].append({
            "t": dt.datetime.now().isoformat(timespec="seconds"),
            "provider": name, "node": node,
            "lat": chosen.get("lat"), "lon": chosen.get("lon"),
            "novelty": round(nov, 4), "sight_unit": unit,
            "candidates": len(scored),
        })
        taken += 1
    write_json_atomic(JOURNAL, journal)
    result = {"provider": name, "steps_taken": taken,
              "total_steps_journaled": len(journal["steps"]),
              "distinct_places": len(journal["visit_counts"]),
              "cache_gb": round(cache_size_gb(), 3)}
    if name == "gsv":
        result["gsv_usage"] = GSVProvider(cfg)._usage()
    print(json.dumps(result, indent=1))
    return result


def status() -> None:
    cfg = load_config()
    journal = load_journal()
    print(json.dumps({
        "provider": cfg["provider"],
        "mapillary_token_present": bool(cfg.get("mapillary_token")),
        "gsv_key_present": bool(cfg.get("gsv_api_key")),
        "gsv_cap": cfg["gsv_monthly_cap"],
        "steps_journaled": len(journal["steps"]),
        "distinct_places": len(journal["visit_counts"]),
        "cache_gb": round(cache_size_gb(), 3),
        "offline_dir": cfg["offline_dir"],
    }, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default=None)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.status:
        status()
        return
    walk(args.steps, args.provider)


if __name__ == "__main__":
    main()

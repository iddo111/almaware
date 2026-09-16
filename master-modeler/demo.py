#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

ALMAWARE Master Modeler — demo.py (offline demo + self-test, v0.3)
=================================================================
Runs the whole control plane OFFLINE, against a MOCK registry/prober — no
network, no CLIs, no ssh, no model calls. Proves:

  1. routing.recommend encodes Iddo's rule (Fable=hard, cheap=bulk, DGX=training)
  2. health.check_endpoints works config-driven with an INJECTED mock prober
     (so reachability is faked; the real code path is exercised, offline)
  3. health.health(prober=...) produces a full snapshot offline
  4. registry model cards + a combined status assemble without touching anything

Exit code 0 = all assertions passed. Use as a smoke test in CI or by hand:

    python demo.py            # human-readable demo + PASS/FAIL
    python demo.py --json     # machine-readable result bundle
    python demo.py --quiet    # only the final PASS/FAIL line + exit code
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

import routing                                          # noqa: E402
import health                                           # noqa: E402


# --------------------------------------------------------------------------- #
# A MOCK registry + prober — fully offline. The prober returns a deterministic
# fake status per endpoint kind, so no CLI/HTTP/TCP is ever touched.
# --------------------------------------------------------------------------- #
MOCK_ENDPOINTS = [
    {"name": "claude-cli", "kind": "cloud-cli", "check": "cli",
     "command": ["claude", "--version"], "provider": "anthropic"},
    {"name": "grok-cli", "kind": "cloud-cli", "check": "cli",
     "command": ["grok", "--version"], "provider": "xai"},
    {"name": "gemini-cli", "kind": "cloud-cli", "check": "cli",
     "command": ["gemini", "--version"], "provider": "google"},
    {"name": "ollama-local", "kind": "local-http", "check": "http",
     "url": "http://localhost:11434/api/version", "provider": "ollama"},
    {"name": "eran-local", "kind": "local-http", "check": "http",
     "url": "http://localhost:7800/health", "provider": "eran"},
    {"name": "eran1-dgx", "kind": "dgx-trainer", "check": "tcp",
     "host": "<fabric-ip>", "port": 22, "provider": "eran"},
    {"name": "eran4-dgx", "kind": "dgx-trainer", "check": "tcp",
     "host": "<fabric-ip>", "port": 22, "provider": "eran"},
]

# Deterministic offline verdicts keyed by endpoint name — the "world" the demo
# pretends to see. eran4 is down (GPU-reset story); everything else reachable.
_MOCK_WORLD = {
    "claude-cli": {"status": "OK", "detail": "claude 1.2.3 (mock)"},
    "grok-cli": {"status": "OK", "detail": "grok 0.9 (mock)"},
    "gemini-cli": {"status": "OK", "detail": "gemini 0.4 (mock)"},
    "ollama-local": {"status": "OK", "detail": "http 200 (mock)"},
    "eran-local": {"status": "OK", "detail": "http 200 (mock)"},
    "eran1-dgx": {"status": "OK", "detail": "tcp reachable (mock)"},
    "eran4-dgx": {"status": "OFFLINE", "detail": "ConnectionRefused (mock)"},
}


def mock_prober(ep: dict) -> dict:
    """Fake, deterministic, side-effect-free reachability — the offline stand-in."""
    return dict(_MOCK_WORLD.get(ep.get("name"), {"status": "UNKNOWN"}))


# --------------------------------------------------------------------------- #
# Assertions
# --------------------------------------------------------------------------- #
def _check(cond: bool, label: str, results: list) -> None:
    results.append((bool(cond), label))


def run_demo() -> dict:
    results: list[tuple[bool, str]] = []

    # 1) Routing policy — Iddo's rule, exact.
    hard = routing.recommend("hard-design")
    _check(hard.worker == "fable", "hard-design -> fable (Iddo's rule)", results)

    bulk = routing.recommend("cheap-bulk")
    _check(bulk.kind == "local-http" and "haiku" in (bulk.fallback + [bulk.worker])
           or bulk.worker in ("ollama-local", "gemma2:2b"),
           "cheap-bulk -> cheap local/Haiku worker", results)

    train = routing.recommend("training")
    _check(train.kind == "dgx-trainer" and train.fleet_task is None,
           "training -> DGX fleet, and NOT auto-launched (fleet_task=None)", results)

    # free-text keyword resolution still lands on the right policy
    ft = routing.recommend("please do a cheap bulk summarization job")
    _check(ft.tag == "cheap-bulk", "free-text 'cheap bulk' -> cheap-bulk tag", results)

    ft2 = routing.recommend("train the next Eran on the cluster")
    _check(ft2.tag == "training", "free-text 'train ... cluster' -> training", results)

    # unknown -> safe cheap default, never a silent wrong pick
    unk = routing.recommend("zzz-unknown-tag")
    _check(unk.tag == "default", "unknown tag -> safe cheap default", results)

    # 2) Config-driven endpoints via INJECTED mock prober (fully offline)
    eps = health.check_endpoints(endpoints=MOCK_ENDPOINTS, prober=mock_prober)
    by_name = {e["name"]: e for e in eps}
    _check(len(eps) == len(MOCK_ENDPOINTS), "all mock endpoints probed", results)
    _check(by_name["claude-cli"]["status"] == "OK", "claude-cli OK (mock)", results)
    _check(by_name["eran4-dgx"]["status"] == "OFFLINE",
           "eran4-dgx OFFLINE reported honestly (mock)", results)
    _check(all(e.get("kind") for e in eps),
           "every endpoint keeps its kind (cloud-cli/local-http/dgx-trainer)",
           results)

    # 3) Full health snapshot, offline, prober injected — must never raise
    snap = health.health(prober=mock_prober)
    _check(isinstance(snap, dict) and snap.get("read_only") is True,
           "health() snapshot is read_only and offline-safe", results)
    _check(isinstance(snap.get("endpoints"), list),
           "snapshot carries the config-driven endpoints block", results)

    # 4) registry model cards + combined status assemble without side effects
    reg_ok = True
    cards = []
    try:
        import registry
        cards = registry.registry()
        reg_ok = len(cards) > 0
    except Exception:
        reg_ok = False
    _check(reg_ok, "registry model cards assemble (>=1 card)", results)

    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    return {
        "_header": 'לזכרה של עלמה ז"ל',
        "offline": True,
        "passed": passed,
        "total": total,
        "all_passed": passed == total,
        "checks": [{"ok": ok, "label": lbl} for ok, lbl in results],
        "sample": {
            "hard_design": hard.to_dict(),
            "cheap_bulk": bulk.to_dict(),
            "training": train.to_dict(),
            "endpoints": eps,
            "model_cards": len(cards),
        },
    }


def render(bundle: dict) -> str:
    lines = ['לזכרה של עלמה ז"ל — Master Modeler · OFFLINE demo + self-test\n']
    lines.append("Routing policy (Iddo's rule):")
    for tag in ("hard-design", "cheap-bulk", "training"):
        r = bundle["sample"][tag.replace("-", "_")]
        lines.append(f"  {tag:<13}-> {r['worker']:<14}({r['kind']})  "
                     f"fallback: {', '.join(r['fallback']) or '—'}")
    lines.append("\nEndpoints (MOCK prober — fully offline, no network/CLI):")
    for e in bundle["sample"]["endpoints"]:
        lines.append(f"  {e['name']:<13}{e['kind']:<12}{e['status']:<8}"
                     f"{e.get('detail', '')}")
    lines.append(f"\nModel cards assembled: {bundle['sample']['model_cards']}")
    lines.append("\nChecks:")
    for c in bundle["checks"]:
        lines.append(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['label']}")
    verdict = "PASS" if bundle["all_passed"] else "FAIL"
    lines.append(f"\n{verdict}: {bundle['passed']}/{bundle['total']} checks "
                 "(offline, read-only, nothing launched or touched)")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    bundle = run_demo()
    if "--json" in argv:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    elif "--quiet" in argv:
        print("PASS" if bundle["all_passed"] else "FAIL",
              f"{bundle['passed']}/{bundle['total']}")
    else:
        print(render(bundle))
    return 0 if bundle["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

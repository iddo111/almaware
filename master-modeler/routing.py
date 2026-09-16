#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

ALMAWARE Master Modeler — routing.py (v0.3)
===========================================
A small, PURE routing helper: given a task TAG (e.g. "hard-design",
"cheap-bulk", "training"), recommend which model/worker to use — encoding
Iddo's standing rule:

  * hard design / deep reasoning  -> Fable   (top Anthropic model)
  * cheap bulk / high-volume      -> cheap models (Ollama local, then Haiku)
  * training                      -> the DGX fleet (eran1..eran4), NOT the PC
  * Hebrew / creative / ALMAWARE  -> Eran (our own), fallback sonnet

This module is stdlib-only and side-effect-free: it RECOMMENDS, it never calls
a model, never launches a job, never touches training. It is the policy layer;
the fleet router (fleet/router.py) owns the actual inference call, and the
trainer-orchestrator owns actual training. See SPEC.md §3 (route) / §5.

Usage:
    python routing.py hard-design
    python routing.py "make me a cheap bulk summary"   # matches by keyword
    python routing.py --list                            # all known tags
    python routing.py --json training
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict, field
from typing import Optional

# Windows consoles default to cp1252; ALMAWARE speaks Hebrew. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


# --------------------------------------------------------------------------- #
# The policy table — Iddo's rule, encoded once. Each tag maps to a primary
# worker + an honest fallback chain + WHY. `worker` is a name from the endpoint
# registry / fleet_config where possible, so a recommendation is actionable.
# --------------------------------------------------------------------------- #
@dataclass
class Recommendation:
    tag: str                          # the canonical tag matched
    worker: str                       # primary recommended worker
    kind: str                         # cloud-cli | local-http | dgx-trainer | ours
    fallback: list[str] = field(default_factory=list)
    reason: str = ""
    fleet_task: Optional[str] = None  # hint for fleet/router.py --task, if inference

    def to_dict(self) -> dict:
        return asdict(self)


# canonical tag -> policy. Order matters only for --list readability.
POLICY: dict[str, Recommendation] = {
    "hard-design": Recommendation(
        tag="hard-design", worker="fable", kind="cloud-cli",
        fallback=["sonnet", "grok"],
        reason="Hard architecture/design + deep reasoning -> Fable, Anthropic's "
               "strongest. Iddo's rule: Fable for the hard stuff.",
        fleet_task="reasoning"),
    "reasoning": Recommendation(
        tag="reasoning", worker="fable", kind="cloud-cli",
        fallback=["sonnet", "grok"],
        reason="Deep reasoning -> Fable; sonnet/grok as capable fallbacks.",
        fleet_task="reasoning"),
    "code": Recommendation(
        tag="code", worker="sonnet", kind="cloud-cli",
        fallback=["fable", "gemini-pro"],
        reason="Code generation -> sonnet (strong, cheaper than Fable); escalate "
               "to Fable for the hardest designs.",
        fleet_task="code"),
    "cheap-bulk": Recommendation(
        tag="cheap-bulk", worker="ollama-local", kind="local-http",
        fallback=["gemma2:2b", "haiku", "gemini-flash"],
        reason="High-volume / cheap bulk -> local Ollama first (free), then "
               "Haiku (cheapest cloud). Iddo's rule: cheap models for bulk.",
        fleet_task="high_volume"),
    "bulk": Recommendation(
        tag="bulk", worker="ollama-local", kind="local-http",
        fallback=["gemma2:2b", "haiku"],
        reason="Bulk work -> cheapest capable worker (local Ollama, then Haiku).",
        fleet_task="batch"),
    "fast": Recommendation(
        tag="fast", worker="ollama-local", kind="local-http",
        fallback=["gemma2:2b", "gemini-flash", "haiku"],
        reason="Fast/simple replies -> local small model, cloud-cheap fallback.",
        fleet_task="fast"),
    "training": Recommendation(
        tag="training", worker="dgx-fleet", kind="dgx-trainer",
        fallback=["eran1-dgx", "eran2-dgx", "eran3-dgx", "eran4-dgx"],
        reason="Model TRAINING -> the DGX Spark fleet (eran1..eran4), never the "
               "PC (it overheats; Eran's run is sacred). Iddo's rule: DGX for "
               "training. Master Modeler only RECOMMENDS — it never launches a "
               "training job (gated, owner-confirmed).",
        fleet_task=None),
    "hebrew": Recommendation(
        tag="hebrew", worker="eran-local", kind="ours",
        fallback=["eran-dgx4", "sonnet"],
        reason="Hebrew/ALMAWARE work -> Eran (our own), fallback sonnet. "
               "Ours-first per the Purity Law.",
        fleet_task="hebrew"),
    "creative": Recommendation(
        tag="creative", worker="eran-local", kind="ours",
        fallback=["eran-dgx4", "sonnet"],
        reason="Creative/ALMAWARE -> Eran first, sonnet fallback.",
        fleet_task="creative"),
    "web": Recommendation(
        tag="web", worker="grok-web", kind="cloud-cli",
        fallback=["gemini-pro"],
        reason="Real-time web / news -> Grok with live search.",
        fleet_task="web_search"),
}

# keyword -> canonical tag, so free-text ("do a cheap bulk job") still routes.
# First matching keyword wins; scanned in this order.
_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("train", "training"),
    ("dgx", "training"),
    ("hard", "hard-design"),
    ("design", "hard-design"),
    ("architect", "hard-design"),
    ("reason", "reasoning"),
    ("cheap", "cheap-bulk"),
    ("bulk", "cheap-bulk"),
    ("high-volume", "cheap-bulk"),
    ("high volume", "cheap-bulk"),
    ("batch", "bulk"),
    ("code", "code"),
    ("hebrew", "hebrew"),
    ("עברית", "hebrew"),
    ("creativ", "creative"),
    ("web", "web"),
    ("news", "web"),
    ("fast", "fast"),
    ("quick", "fast"),
    ("simple", "fast"),
)

# Aliases so common synonyms hit a canonical tag directly.
_ALIASES = {
    "hard": "hard-design",
    "design": "hard-design",
    "cheap": "cheap-bulk",
    "high-volume": "cheap-bulk",
    "train": "training",
    "dgx": "training",
}


def recommend(task: str) -> Recommendation:
    """Recommend a worker for a task tag OR free-text. Never calls a model.

    Resolution order: exact canonical tag -> alias -> keyword scan -> default.
    Always returns a Recommendation (falls back to a safe cheap default).
    """
    if not task or not task.strip():
        base = POLICY["fast"]
        return Recommendation(**{**base.to_dict(), "tag": "default",
                                 "reason": "empty task -> safe cheap default. "
                                           + base.reason})
    key = task.strip().lower()

    if key in POLICY:
        return POLICY[key]
    if key in _ALIASES:
        return POLICY[_ALIASES[key]]

    for needle, tag in _KEYWORDS:
        if needle in key:
            rec = POLICY[tag]
            if needle != tag and needle not in tag:
                # note that we matched by keyword, not exact tag
                return Recommendation(**{**rec.to_dict(),
                                         "reason": f"(matched keyword '{needle}') "
                                                   + rec.reason})
            return rec

    # Unknown -> honest safe default (cheap), not a silent wrong pick.
    base = POLICY["cheap-bulk"]
    return Recommendation(**{**base.to_dict(), "tag": "default",
                             "reason": f"unknown task '{task}' -> safe cheap "
                                       "default. " + base.reason})


def all_tags() -> list[str]:
    return list(POLICY.keys())


def render(rec: Recommendation) -> str:
    lines = [
        'לזכרה של עלמה ז"ל — Master Modeler · route recommendation',
        "",
        f"  task      : {rec.tag}",
        f"  -> worker : {rec.worker}  ({rec.kind})",
        f"  fallback  : {', '.join(rec.fallback) or '(none)'}",
        f"  why       : {rec.reason}",
    ]
    if rec.fleet_task:
        lines.append(f"  run it    : python master_modeler.py route "
                     f"--task {rec.fleet_task} \"<prompt>\"")
    else:
        lines.append("  run it    : (training is gated — recommend only, "
                     "never auto-launched)")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]

    if "--list" in argv or not argv:
        recs = {t: recommend(t).to_dict() for t in all_tags()}
        if as_json:
            print(json.dumps(recs, ensure_ascii=False, indent=2))
        else:
            print('לזכרה של עלמה ז"ל — Master Modeler · routing policy (tags)\n')
            for t in all_tags():
                r = POLICY[t]
                print(f"  {t:<13}-> {r.worker:<14}({r.kind})  "
                      f"fallback: {', '.join(r.fallback) or '—'}")
        return 0

    task = " ".join(argv)
    rec = recommend(task)
    print(json.dumps(rec.to_dict(), ensure_ascii=False, indent=2)
          if as_json else render(rec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

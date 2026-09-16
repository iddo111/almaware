#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

ALMAWARE Master Modeler — registry.py (v0.2: model cards)
=========================================================
THE one honest roster: a model card for EVERY model in the ALMAWARE frame —
★ours, external helpers, and products — with status gathered from the REAL
dirs/configs at call time, never from wishful memory.

Honesty rules (feedback_grounded_not_theatrical + feedback_clean_experiments):
  - planned is reported as planned, blocked as blocked, prototype as prototype;
  - a checkpoint on disk is checked, not assumed;
  - vanilla-control results are reported even when OUR arm loses;
  - remote state we cannot verify from this machine is marked "unknown (remote)".

HARD SAFETY (encoded, not just documented — see SAFETY below):
  This module OBSERVES and reports only. It must NEVER kill/start processes,
  and NEVER touch Eran's training (D:\\CLAUDE\\eran-live) or the mic. Any future
  control action must pass through an explicit, owner-confirmed gate.

Design: stdlib only, read-only, REUSES master_modeler.py paths/helpers and
fleet/fleet_config.json + fleet/eran_live_status.json (zero duplication).
See SPEC.md §5.4 (model cards).

Usage:
    python registry.py                 # text roster (all model cards)
    python registry.py --json          # same as JSON
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Reuse master_modeler's single-sources-of-truth (same dir; zero duplication).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from master_modeler import (                                    # noqa: E402
    ROOT, FLEET_CONFIG, ERAN_STATUS, _read_json, _file_age_seconds,
    _load_config, _is_ours,
)

# Windows consoles default to cp1252; ALMAWARE speaks Hebrew. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

# --------------------------------------------------------------------------- #
# HARD SAFETY — machine-readable rule, importable by any future control code.
# --------------------------------------------------------------------------- #
SAFETY = {
    "observe_only": True,                    # this module NEVER starts/kills
    "control_requires_explicit_gate": True,  # any action = owner-confirmed
    "never_touch": [                         # sacred — hands off, always
        str(ROOT / "eran-live"),             # Eran's live training
        "mic",                               # ALMA-MIC / audio capture
    ],
}


def assert_read_only(action: str) -> None:
    """Guard for any future control path: refuse by construction."""
    raise PermissionError(
        f"registry.py is OBSERVE-ONLY; refusing action {action!r}. "
        f"Control actions need an explicit gated command (SAFETY={SAFETY})")


# --------------------------------------------------------------------------- #
# Innovation vocabulary (feedback_all_models_innovations) — fixed spellings so
# coverage can be computed; a card lists only what is actually BAKED IN.
# --------------------------------------------------------------------------- #
INNOVATIONS = (
    "Beit-Din",                 # every-neuron-a-judge / 3-judge quorum
    "GIST score==weight",       # gist score used directly as the weight
    "multi-weight",             # several weights per connection
    "multi-reference-frames",   # parallel frames + voting
    "Or-Chozer-backprop",       # returning-light learning rule
    "neuromodulation",          # oxytocin+ (not dopamine-only) learning
)

# Model project dirs (the REAL state lives here — we inspect, not assume).
ERAN_LIVE = ROOT / "eran-live"
ALMA_OZEN = ROOT / "alma-ozen"
COFFEE = ALMA_OZEN / "coffee"
BRAIN_SIM = ROOT / "alma-brain-sim"
PONG_ALMA = ROOT / "pong-alma"
PROTONEURON = ROOT / "protoneuron"
PERETS = ROOT / "perets"


# --------------------------------------------------------------------------- #
# ModelCard
# --------------------------------------------------------------------------- #
@dataclass
class ModelCard:
    name: str
    kind: str                    # "ours" | "external" | "product"
    location: str                # dir / host / endpoint
    status: str                  # training|idle|planned|blocked|prototype|working|unknown (remote)
    purity: str                  # 100% ours / external / base-external+our-layers
    innovations: list[str] = field(default_factory=list)   # subset of INNOVATIONS
    eval_status: str = "none"
    vanilla_control: str = "none"
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Probe helpers — small, filesystem/env only (read-only by construction).
# --------------------------------------------------------------------------- #
def _age_h(path: Path) -> Optional[float]:
    age = _file_age_seconds(path)
    return None if age is None else age / 3600.0


def _count(dirp: Path, pattern: str = "*") -> int:
    try:
        return sum(1 for p in dirp.glob(pattern) if p.is_file())
    except OSError:
        return 0


def _log_tail(path: Path) -> str:
    """Last non-empty line of a log (honest verbatim evidence)."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            if line.strip():
                return line.strip()
    except OSError:
        pass
    return ""


def _has_env(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


# --------------------------------------------------------------------------- #
# Per-model probes — each returns one honest card from REAL on-disk state.
# --------------------------------------------------------------------------- #
def _card_eran_live() -> ModelCard:
    ckpt = ERAN_LIVE / "checkpoints" / "latest.pt"
    hb = _read_json(ERAN_STATUS)                    # heartbeat eran-live writes
    hb_age = _age_h(ERAN_STATUS)
    if hb and hb_age is not None and hb_age < 0.25:         # <15 min = live
        status = "training"
        beat = (f"LIVE step {hb.get('step', '?'):,} loss {hb.get('loss', '?')} "
                f"on {hb.get('device', '?')}")
    elif hb:
        status = "idle"
        beat = (f"last heartbeat {hb_age:.1f}h ago — step {hb.get('step', 0):,}, "
                f"loss {hb.get('loss', '?')} (training paused, not lost)")
    else:
        status = "idle"
        beat = "no heartbeat file — trainer not seen from this machine"
    return ModelCard(
        name="eran-v1 (live)", kind="ours", location=str(ERAN_LIVE),
        status=status,
        purity="100% ours — from-scratch byte-LM, code + weights",
        innovations=[],          # honest: v1 is a PLAIN transformer prototype
        eval_status="loss-only (train loss/EMA); no held-out eval yet",
        vanilla_control="none — v1 IS the baseline the innovations must beat",
        notes=(f"checkpoint {'present' if ckpt.exists() else 'MISSING'}; {beat}. "
               "PROTOTYPE: 4-layer, voice-only corpus; innovations live in "
               "siblings (coffee/pong/DGX-GIST), not yet merged here. "
               "Serving: fleet keys eran-local :7800 / eran-dgx4 :7801. SACRED "
               "— never auto-touched (SAFETY.never_touch)."))


def _card_eran_dgx_gist() -> ModelCard:
    return ModelCard(
        name="eran-gist (DGX)", kind="ours", location="eran2 (DGX Spark)",
        status="unknown (remote)",
        purity="100% ours — GIST arm of Eran",
        innovations=["GIST score==weight"],
        eval_status="not verifiable from this machine",
        vanilla_control="intended vs plain eran-v1; result not verified here",
        notes=("Lives on eran2; this registry is read-only + local-filesystem "
               "only, so remote state is honestly UNKNOWN until the roadmap "
               "`health` command pings it (SPEC §5.1)."))


def _card_alma_ozen() -> ModelCard:
    best = ALMA_OZEN / "ckpt" / "best.pt"
    int8 = ALMA_OZEN / "models" / "ozen_int8.pt"
    gold_n = _count(ALMA_OZEN / "gold" / "wav", "*.wav")
    return ModelCard(
        name="alma-ozen (ASR)", kind="ours", location=str(ALMA_OZEN),
        status="prototype",
        purity="100% ours — from-scratch Hebrew char-CTC, ZERO Whisper",
        innovations=[],          # honest: plain CTC; innovations trial = coffee/
        eval_status=("smoke-tested end-to-end (selftest_e2e.py); no real-speech "
                     f"WER yet — gold set has {gold_n} clip(s)"),
        vanilla_control="none on main model (the coffee/ sub-experiment has one)",
        notes=(f"ckpt {'trained (best.pt)' if best.exists() else 'MISSING'}; "
               f"int8 export {'present' if int8.exists() else 'absent'} "
               "(feedback_smart_compression). BLOCKED-on-data: needs gold "
               f"recordings via record_gui.py ({gold_n} recorded so far)."))


def _card_ozen_coffee() -> ModelCard:
    ours_pt = COFFEE / "models" / "coffee_ours.pt"
    van_pt = COFFEE / "models" / "coffee_vanilla.pt"
    kafe_n = _count(COFFEE / "data" / "kafe")
    other_n = _count(COFFEE / "data" / "other")
    ours_tail = _log_tail(COFFEE / "logs" / "coffee_ours.log")
    van_tail = _log_tail(COFFEE / "logs" / "coffee_vanilla.log")

    def _gold_verdict(tail: str) -> str:
        if "FALSE ALARM" in tail:
            return "FALSE-ALARM on gold clip"
        if "OK" in tail:
            return "passed gold clip"
        return "no gold-clip verdict logged"

    trained = ours_pt.exists() and van_pt.exists()
    return ModelCard(
        name="alma-ozen/coffee", kind="ours", location=str(COFFEE),
        status="prototype" if trained else "planned",
        purity="100% ours — both arms (ours + control) our code",
        innovations=["Beit-Din", "GIST score==weight"],
        eval_status=(
            (f"clean A/B ran — ours: {_gold_verdict(ours_tail)}; "
             f"vanilla: {_gold_verdict(van_tail)}. HONEST: reported even "
             "where the control wins (feedback_clean_experiments)")
            if trained else "not run yet"),
        vanilla_control=(
            f"YES — param-matched model_vanilla.py, "
            f"{'trained (coffee_vanilla.pt)' if van_pt.exists() else 'untrained'}"),
        notes=(f"keyword-spotter ('קפה') A/B: Beit-Din+GIST arm vs vanilla. "
               f"Real recordings: kafe={kafe_n}, other={other_n} — "
               f"{'AWAITING recordings (record_coffee.py); current run used bootstrap data only' if kafe_n == 0 else 'has real data'}."))


def _card_brain_sim() -> ModelCard:
    core = [BRAIN_SIM / f for f in
            ("hhcore.py", "synapses.py", "plasticity.py", "neuromod.py",
             "network.py")]
    built = all(p.exists() for p in core)
    return ModelCard(
        name="alma-brain-sim", kind="ours", location=str(BRAIN_SIM),
        status="prototype" if built else "planned",
        purity="100% ours — biophysical simulator (HH + STDP), from scratch",
        innovations=["neuromodulation"],
        eval_status=("validate_core.py present"
                     if (BRAIN_SIM / "validate_core.py").exists()
                     else "no validation script"),
        vanilla_control="n/a — simulator, not a trained model",
        notes=("Hodgkin-Huxley core + synapses/STDP/neuromodulators + network "
               "demos. A research substrate for Eran's rich-neuron ideas, "
               "not a serving model."))


def _card_pong_alma() -> ModelCard:
    players = {p: (PONG_ALMA / f"player_{p}.py").exists()
               for p in ("beitdin", "gist", "multiweight")}
    have = [p for p, ok in players.items() if ok]
    return ModelCard(
        name="pong-alma players", kind="ours", location=str(PONG_ALMA),
        status="prototype" if have else "planned",
        purity="100% ours — eran-neuron primitive players",
        innovations=["Beit-Din", "GIST score==weight", "multi-weight"],
        eval_status=("arena.py head-to-head harness present"
                     if (PONG_ALMA / "arena.py").exists()
                     else "no arena harness"),
        vanilla_control=("arena compares the three innovation arms against "
                         "each other; no plain-NN control arm yet"),
        notes=f"players on disk: {', '.join(have) or 'none'}. Testbed, not product.")


def _card_protoneuron() -> ModelCard:
    sim = PROTONEURON / "sim_protoneuron.py"
    return ModelCard(
        name="protoneuron", kind="ours", location=str(PROTONEURON),
        status="prototype" if sim.exists() else "planned",
        purity="100% ours — hardware-neuron simulator",
        innovations=[],
        eval_status="sim only; no hardware measurement yet",
        vanilla_control="n/a — hardware sim",
        notes="Sim + BUILD.md/CIRCUIT.md toward the physical neuron cell "
              "(memristor/neuromorphic track). Paper-and-sim stage.")


def _card_perets() -> ModelCard:
    py_n = sum(1 for _ in PERETS.rglob("*.py")) if PERETS.exists() else 0
    md_n = sum(1 for _ in PERETS.rglob("*.md")) if PERETS.exists() else 0
    return ModelCard(
        name="Perets", kind="product", location=str(PERETS),
        status="planned" if py_n == 0 else "prototype",
        purity="base EXTERNAL (Qwen3.6-35B-A3B) + our tri-brain layers on top",
        innovations=["multi-reference-frames"],   # designed-in, not yet built
        eval_status="design docs only (GROUNDING_DATA_EVAL.md); nothing run",
        vanilla_control="planned in design; none exists",
        notes=(f"PLANNED, honestly: {md_n} planning docs, {py_n} code files. "
               "Tri-brain + multi-frame voting design; DGX deployment runbook "
               "written, not executed."))


def _cards_fleet_externals(cfg: dict) -> list[ModelCard]:
    """External helpers straight from fleet_config.json (single source of truth).
    Ours entries (eran-local/eran-dgx4) are skipped — the eran-v1 card covers
    them — so nothing is listed twice."""
    cards: list[ModelCard] = []
    for key, spec in cfg.get("models", {}).items():
        if _is_ours(key, spec):
            continue
        provider = spec.get("provider", "?")
        secret = spec.get("secret")
        status, why = "idle", ""
        if provider == "gemini":
            status, why = "blocked", "no GEMINI_API_KEY"
        elif provider == "xai":
            status, why = "blocked", "xAI team has no credits"
        elif secret and not _has_env(secret):
            status, why = "blocked", f"{secret} not set in this environment"
        loc = spec.get("endpoint_default") or f"{provider} API"
        cards.append(ModelCard(
            name=key, kind="external", location=loc, status=status,
            purity=f"external ({provider})", innovations=[],
            eval_status="n/a — external helper",
            vanilla_control="n/a",
            notes=(f"{'BLOCKED: ' + why + '. ' if why else ''}"
                   f"best_for: {', '.join(spec.get('best_for', []))}. "
                   "Fallback helper per Purity Law — APPS not models; "
                   "not pinged (roadmap `health`).")))
    return cards


def _cards_fleet_remote() -> list[ModelCard]:
    """Remote fleet members not in fleet_config.json — declared honestly as
    not-verifiable-from-here rather than invented."""
    return [
        ModelCard(
            name="fleet-claude-agents", kind="external",
            location="eran2 / eran3 / eran4 (DGX)",
            status="working",
            purity="external (Anthropic Claude Opus, subscription)",
            innovations=[], eval_status="n/a — agent workforce, not a model we train",
            vanilla_control="n/a",
            notes="Claude Code agents on the DGX fleet — WORKING via "
                  "subscription (no API key burn). Liveness not re-verified "
                  "by this local probe."),
        ModelCard(
            name="grok-1 rpc-server", kind="external",
            location="eran2 / eran3",
            status="unknown (remote)",
            purity="external (xAI open-weights Grok-1)",
            innovations=[], eval_status="n/a",
            vanilla_control="n/a",
            notes="Open-weights Grok-1 rpc-server deployed on eran2/3; state "
                  "not verifiable from this machine (roadmap `health`)."),
    ]


# --------------------------------------------------------------------------- #
# registry — the whole honest roster, gathered fresh on every call
# --------------------------------------------------------------------------- #
def registry() -> list[ModelCard]:
    cfg = _load_config() if FLEET_CONFIG.exists() else {"models": {}}
    cards = [
        # ★ours — flagship first
        _card_eran_live(),
        _card_eran_dgx_gist(),
        _card_alma_ozen(),
        _card_ozen_coffee(),
        _card_brain_sim(),
        _card_pong_alma(),
        _card_protoneuron(),
        # product
        _card_perets(),
        # external / fleet
        *_cards_fleet_remote(),
        *_cards_fleet_externals(cfg),
    ]
    return cards


def innovation_coverage(cards: list[ModelCard]) -> dict[str, list[str]]:
    """Which models bake in each innovation — empty list = not yet real anywhere."""
    return {innov: [c.name for c in cards if innov in c.innovations]
            for innov in INNOVATIONS}


# --------------------------------------------------------------------------- #
# render_roster / roster_json
# --------------------------------------------------------------------------- #
_KIND_MARK = {"ours": "★ours", "product": "prod.", "external": "ext."}


def roster_json(cards: Optional[list[ModelCard]] = None) -> str:
    cards = cards if cards is not None else registry()
    return json.dumps({
        "_header": 'לזכרה של עלמה ז"ל',
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "safety": SAFETY,
        "innovation_coverage": innovation_coverage(cards),
        "cards": [c.to_dict() for c in cards],
    }, ensure_ascii=False, indent=2)


def render_roster(cards: Optional[list[ModelCard]] = None) -> str:
    cards = cards if cards is not None else registry()
    out = ['לזכרה של עלמה ז"ל — ALMAWARE Master Modeler · model cards\n']
    out.append(f"{'MODEL':<22}{'KIND':<7}{'STATUS':<18}{'INNOVATIONS':<42}EVAL / CONTROL")
    out.append("-" * 110)
    for c in cards:
        innov = ", ".join(c.innovations) or "—"
        has_ctrl = c.vanilla_control.upper().startswith("YES")
        ctrl = " · ctrl:yes" if has_ctrl else ""
        out.append(f"{c.name:<22}{_KIND_MARK.get(c.kind, c.kind):<7}"
                   f"{c.status:<18}{innov:<41} {c.eval_status[:40]}{ctrl}")
        out.append(f"{'':<22}@ {c.location}")
        out.append(f"{'':<22}purity: {c.purity}")
        if not c.vanilla_control.startswith(("none", "n/a")):
            out.append(f"{'':<22}control: {c.vanilla_control}")
        out.append(f"{'':<22}{c.notes}")
        out.append("")
    ours = sum(1 for c in cards if c.kind == "ours")
    prod = sum(1 for c in cards if c.kind == "product")
    ext = len(cards) - ours - prod
    out.append(f"{len(cards)} cards · {ours} ★ours · {prod} product · {ext} external")
    cov = innovation_coverage(cards)
    baked = [f"{k} -> {', '.join(v)}" for k, v in cov.items() if v]
    unbaked = [k for k, v in cov.items() if not v]
    out.append("innovations baked in: " + ("; ".join(baked) or "none"))
    if unbaked:
        out.append("not yet real in ANY model (honest): " + ", ".join(unbaked))
    out.append("safety: OBSERVE-ONLY registry — never touches eran-live or the mic")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    as_json = "--json" in (argv if argv is not None else sys.argv[1:])
    cards = registry()
    print(roster_json(cards) if as_json else render_roster(cards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

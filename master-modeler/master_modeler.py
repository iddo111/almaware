#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

ALMAWARE Master Modeler — v0.2
==============================
One control plane over EVERY ALMAWARE model. It does NOT route or train itself;
it REUSES the tools that already do that (fleet/router.py, registry.py,
health.py) and gives a single honest answer to "what is the state of all our
models, and where should this job go?":

  - model cards (all models, ours vs external)  <- registry.py
  - live health (dashboards / reach / heartbeat) <- health.py
  - inference roster + routing                   <- fleet/router.py + fleet_config.json
  - training heartbeat                           <- fleet/eran_live_status.json

Design: stdlib only (like router.py), READ-ONLY by construction, reuse not
duplicate. See SPEC.md.

HARD SAFETY: this whole tool OBSERVES and routes only. It NEVER kills or starts
Eran's training or the mic. The `control` verb is a GATED STUB — it prints only
what it WOULD do and refuses to act (see registry.assert_read_only / SAFETY).

Usage:
    python master_modeler.py roster                 # every model card, ours flagged
    python master_modeler.py status                 # roster + LIVE health (honest)
    python master_modeler.py status --json           # for project_eran_dashboard
    python master_modeler.py eval                    # per-model vanilla-control view
    python master_modeler.py route --task hebrew "תרגם: hello"   # delegate to router
    python master_modeler.py route --dry-run "what's the news?"  # show pick, no call
    python master_modeler.py control stop eran       # GATED STUB — prints, never acts
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------- #
# Locations — single sources of truth that already exist. We READ these.
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent          # D:\CLAUDE
HERE = Path(__file__).resolve().parent                 # D:\CLAUDE\master-modeler
FLEET_DIR = ROOT / "fleet"
ROUTER_PY = FLEET_DIR / "router.py"
FLEET_CONFIG = FLEET_DIR / "fleet_config.json"
ERAN_STATUS = FLEET_DIR / "eran_live_status.json"
ORCH_LOG = ROOT / "trainer-orchestrator" / "orchestrator.log"

# Models that are 100% OURS (the others are external helpers / fallbacks).
OURS_PROVIDERS = {"eran"}                               # provider tag in config
OURS_KEYS = {"eran-local", "eran-dgx4", "alma"}         # by-name, for clarity

# Windows consoles default to cp1252; ALMAWARE speaks Hebrew. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")          # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


# --------------------------------------------------------------------------- #
# Reuse the existing fleet router instead of reimplementing routing.
# --------------------------------------------------------------------------- #
def _load_router():
    """Import fleet/router.py as a module by path (it's not on sys.path)."""
    if not ROUTER_PY.exists():
        raise RuntimeError(f"fleet router not found at {ROUTER_PY}")
    spec = importlib.util.spec_from_file_location("alma_fleet_router", ROUTER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                        # type: ignore[union-attr]
    return mod


def _load_config() -> dict:
    with open(FLEET_CONFIG, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _is_ours(key: str, spec: dict) -> bool:
    return key in OURS_KEYS or spec.get("provider") in OURS_PROVIDERS


# --------------------------------------------------------------------------- #
# Sibling modules (v0.2) — registry.py (model cards) + health.py (live pings).
# Imported lazily/defensively so a missing sibling degrades honestly instead of
# crashing the whole tool.
# --------------------------------------------------------------------------- #
def _load_registry():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import registry                                     # noqa: WPS433 (local import)
    return registry


def _load_health():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import health                                       # noqa: WPS433 (local import)
    return health


def _load_routing():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import routing                                      # noqa: WPS433 (local import)
    return routing


# --------------------------------------------------------------------------- #
# small readers (kept here so registry.py can reuse them — zero duplication)
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _file_age_seconds(path: Path) -> Optional[float]:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# roster — delegate to registry.py (all model cards, ours flagged)
# --------------------------------------------------------------------------- #
def cmd_roster(as_json: bool) -> int:
    reg = _load_registry()
    cards = reg.registry()
    print(reg.roster_json(cards) if as_json else reg.render_roster(cards))
    return 0


# --------------------------------------------------------------------------- #
# status — roster (registry) + LIVE health (health.py), honest by construction
# --------------------------------------------------------------------------- #
def build_status() -> dict:
    """One combined, HONEST snapshot: model cards + live health + training.
    Every piece degrades to a clearly-labelled UNKNOWN rather than lying."""
    reg = _load_registry()
    cards = reg.registry()

    # Live health (dashboards / reach / heartbeat / mic). Never raises.
    try:
        live = _load_health().health()
    except Exception as exc:                            # health must never sink status
        live = {"status": "UNKNOWN", "error": type(exc).__name__}

    ours = [c.name for c in cards if c.kind == "ours"]
    product = [c.name for c in cards if c.kind == "product"]
    external = [c.name for c in cards if c.kind == "external"]

    return {
        "_header": 'לזכרה של עלמה ז"ל',
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "read_only": True,
        "safety": reg.SAFETY,
        "models": {
            "total": len(cards),
            "ours": ours,
            "product": product,
            "external": external,
            "cards": [c.to_dict() for c in cards],
        },
        "innovation_coverage": reg.innovation_coverage(cards),
        "health": live,
    }


def cmd_status(as_json: bool) -> int:
    st = build_status()
    if as_json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0

    m = st["models"]
    print('לזכרה של עלמה ז"ל — ALMAWARE Master Modeler · status  '
          f'{st["generated"]}\n')
    print("MODELS")
    print(f"  total      {m['total']} "
          f"({len(m['ours'])} ours, {len(m['product'])} product, "
          f"{len(m['external'])} external)")
    print(f"  ours       {', '.join(m['ours']) or '(none)'}")
    print(f"  product    {', '.join(m['product']) or '(none)'}")

    # Per-card one-liner so `status` shows the honest state of EACH model.
    print("\nMODEL STATE (honest)")
    for c in m["cards"]:
        ctrl = " ·ctrl" if str(c.get("vanilla_control", "")).upper().startswith("YES") else ""
        print(f"  {c['name']:<22}{c['status']:<18}{c['purity'][:38]}{ctrl}")

    # LIVE health block (from health.py) — this is what makes status LIVE not declared.
    print("\nLIVE HEALTH (read-only)")
    h = st["health"]
    try:
        print(_load_health().render_health(h))
    except Exception:
        # Fall back to a terse honest summary if the renderer is unavailable.
        tr = (h.get("training") or {}) if isinstance(h, dict) else {}
        hb = (tr.get("eran_live_status") or {})
        print(f"  training heartbeat: {hb.get('status', 'UNKNOWN')} "
              f"(age {hb.get('age_h', '?')}h)")
        print(f"  mic: {(h.get('mic') or {}).get('status', 'UNKNOWN')}")
    return 0


# --------------------------------------------------------------------------- #
# eval — per-model vanilla-control comparison (clean-experiments view)
# Shows, for EVERY model, whether a param-matched control exists and what the
# honest A/B verdict was — reported even where OUR arm loses.
# --------------------------------------------------------------------------- #
def build_eval() -> dict:
    reg = _load_registry()
    cards = reg.registry()
    rows = []
    for c in cards:
        vc = str(c.vanilla_control or "")
        has_control = vc.upper().startswith("YES")
        rows.append({
            "model": c.name,
            "kind": c.kind,
            "has_vanilla_control": has_control,
            "eval_status": c.eval_status,
            "vanilla_control": c.vanilla_control,
        })
    return {
        "_header": 'לזכרה של עלמה ז"ל',
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "clean_experiments_note": (
            "param-matched control, report truth even if our model loses "
            "(feedback_clean_experiments)"),
        "with_control": [r for r in rows if r["has_vanilla_control"]],
        "without_control": [r for r in rows if not r["has_vanilla_control"]],
        "rows": rows,
    }


def cmd_eval(as_json: bool) -> int:
    ev = build_eval()
    if as_json:
        print(json.dumps(ev, ensure_ascii=False, indent=2))
        return 0
    print('לזכרה של עלמה ז"ל — ALMAWARE Master Modeler · eval (vanilla-control)\n')
    print(ev["clean_experiments_note"])
    with_ctrl = ev["with_control"]
    print(f"\nMODELS WITH A PARAM-MATCHED CONTROL ({len(with_ctrl)})")
    if not with_ctrl:
        print("  (none yet)")
    for r in with_ctrl:
        print(f"  {r['model']}")
        print(f"      control : {r['vanilla_control']}")
        print(f"      eval    : {r['eval_status']}")
    without = ev["without_control"]
    print(f"\nMODELS WITHOUT A CONTROL YET ({len(without)}) — honest:")
    for r in without:
        # keep it terse; note WHY (n/a for external/sim, or simply not built)
        why = r["vanilla_control"] if r["vanilla_control"] not in ("", "none") else "none"
        print(f"  {r['model']:<22}{r['eval_status'][:44]:<45}({why})")
    return 0


# --------------------------------------------------------------------------- #
# route-plan — RECOMMEND a worker for a task tag (routing.py). Pure policy:
# it never calls a model or launches a job. Encodes Iddo's rule (Fable for hard,
# cheap for bulk, DGX for training). Use `route` to actually run inference.
# --------------------------------------------------------------------------- #
def cmd_route_plan(task: str, as_json: bool, list_all: bool) -> int:
    routing = _load_routing()
    if list_all or not task:
        if as_json:
            print(json.dumps({t: routing.recommend(t).to_dict()
                              for t in routing.all_tags()},
                             ensure_ascii=False, indent=2))
        else:
            print('לזכרה של עלמה ז"ל — Master Modeler · routing policy (tags)\n')
            for t in routing.all_tags():
                r = routing.POLICY[t]
                print(f"  {t:<13}-> {r.worker:<14}({r.kind})  "
                      f"fallback: {', '.join(r.fallback) or '—'}")
        return 0
    rec = routing.recommend(task)
    print(json.dumps(rec.to_dict(), ensure_ascii=False, indent=2)
          if as_json else routing.render(rec))
    return 0


# --------------------------------------------------------------------------- #
# route — delegate to the existing fleet router (reuse, don't reimplement)
# --------------------------------------------------------------------------- #
def cmd_route(prompt: str, task: Optional[str], auto: bool,
              dry_run: bool, as_json: bool) -> int:
    router = _load_router()
    chosen_task = None if auto else task
    res = router.route(prompt, task=chosen_task, dry_run=dry_run)
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        tag = (f"[master-modeler -> {res['model']} · {res['provider']} · "
               f"{'free' if res['free'] else 'paid'}"
               f"{' · dry-run' if dry_run else ''}]")
        print(tag, file=sys.stderr)
        print(res.get("output", res.get("error", "")))
    return 0 if "error" not in res else 1


# --------------------------------------------------------------------------- #
# control — GATED STUB. This tool is READ-ONLY. `control` NEVER acts; it only
# prints what it WOULD do and then refuses via registry.assert_read_only.
# Kept here so callers get a clear, honest "not wired, by design" answer instead
# of a missing command — the real lifecycle path is a later, owner-gated step.
# --------------------------------------------------------------------------- #
def cmd_control(verb: str, target: str, as_json: bool) -> int:
    reg = _load_registry()
    would = (f"control {verb} {target}".strip())
    # NEVER touch these — sacred (SAFETY.never_touch): Eran's training + the mic.
    sacred = any(s.lower() in target.lower()
                 for s in ("eran", "mic", "alma") if s)
    plan = {
        "_header": 'לזכרה של עלמה ז"ל',
        "requested": would,
        "would_do": (f"[STUB] would {verb!r} target {target!r} via the "
                     "trainer-orchestrator (NOT executed)"),
        "executed": False,
        "read_only": True,
        "refused_because": ("Master Modeler v0.2 is OBSERVE-ONLY; lifecycle "
                            "control is a later owner-gated step (SPEC §5.2)."),
        "sacred_target": sacred,
        "safety": reg.SAFETY,
    }
    if sacred:
        plan["would_do"] = (f"[STUB] REFUSED even to plan: {target!r} is SACRED "
                            "(SAFETY.never_touch) — Eran's training / the mic are "
                            "never auto-touched.")

    if as_json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        print('לזכרה של עלמה ז"ל — Master Modeler · control (GATED STUB)\n')
        print(f"  requested : {plan['requested']}")
        print(f"  would do  : {plan['would_do']}")
        print(f"  executed  : NO (read-only by construction)")
        print(f"  why       : {plan['refused_because']}")
        if sacred:
            print("  NOTE      : target is SACRED — hands off, always.")

    # Prove read-only by construction: the guard REFUSES any real action.
    try:
        reg.assert_read_only(would)
    except PermissionError as exc:
        print(f"\n[safety guard] {exc}", file=sys.stderr)
    # A gated stub that only prints is a success (exit 0); it did exactly what
    # it promised — nothing — and said so.
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def cmd_brain(args, as_json: bool) -> int:
    """THE WELDER'S OWN SECOND BRAIN — level 3 of the three Iddo named on 2026-09-05.

    Levels 1 and 2 are a brain per project and a brain per model. This is the
    third: the thing that CONNECTS models remembers what it learned about
    connecting them -- which route was tried, which teacher had nothing to teach,
    which pairing failed and why. Without it, every routing lesson has to be
    re-learned by the next session reading logs.

    A pure delegation to D:\\CLAUDE\\alma-second-brain-system (store.py + bridge.py),
    exactly as `route` delegates to fleet/router.py and `teach` to teachability.py.
    Scope is fixed to "welder": this verb cannot write into a project or a model
    brain, so the welder can never speak in another brain's name.
    """
    brain_dir = os.environ.get("ALMA_BRAIN_DIR", str(ROOT / "alma-second-brain-system"))
    if not os.path.isdir(brain_dir):
        print("second brain not installed at %s" % brain_dir, file=sys.stderr)
        return 1
    sys.path.insert(0, brain_dir)
    import bridge as B
    import store as S

    if args.action == "read":
        rows = S.read("welder", args.id, query=args.query, n=args.n)
        if as_json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        else:
            for e in rows:
                print("%s  %-8s %s" % (e["ts"][:16], e["kind"], B.digest(e)))
        return 0
    if not args.source:
        print("write: --source is mandatory (provenance)", file=sys.stderr)
        return 2
    res = B.write_and_publish("welder", args.id, args.author, args.kind, args.text,
                              refs=args.ref, outcome=args.outcome,
                              provenance={"source": args.source, "via": "master_modeler"})
    print(json.dumps(res if as_json else
                     {"seq": res["entry"]["seq"], "sha": res["entry"]["sha"],
                      "council": res["ramchat"]["published"]}, ensure_ascii=False, indent=1))
    return 0


def cmd_teach(args, as_json: bool) -> int:
    """MODEH — the corpus-teachability organ.

    The rest of this control plane answers 'which model is best for this job'.
    This verb answers the half that was missing and that cost ERAN a month:
    'does this teacher have anything to teach at all?' It is a pure delegation
    to teachability.py, which owns the measurement, exactly as `route`
    delegates to fleet/router.py. Read-only, like everything else here.
    """
    sys.path.insert(0, str(HERE))
    import teachability as T

    T._below_normal()
    reg = T.load_registry(args.scratch)
    ear = T.Ear()
    if args.units:
        if len(args.corpus) != 1:
            print("teach --units needs exactly one corpus id", file=sys.stderr)
            return 2
        spec = next((c for c in reg["corpora"] if c["id"] == args.corpus[0]), None)
        if spec is None:
            print(f"unknown corpus id: {args.corpus[0]}", file=sys.stderr)
            return 2
        v = T.judge(spec, reg, ear, verbose=False)
        if as_json:
            print(json.dumps(v["per_unit"], ensure_ascii=False, indent=2))
        else:
            print(f"{'unit':<8}{'clips':>6}{'cosine':>9}{'n_eff':>8}{'twins':>8}")
            for u in sorted(v["per_unit"], key=lambda x: -x["k"]):
                print(f"{u['unit']:<8}{u['k']:>6}{str(u['within_cosine']):>9}"
                      f"{u['n_eff']:>8}{u['twin_frac']:>8}")
        return 0

    ids = args.corpus or [c["id"] for c in reg["corpora"]]
    out = []
    for cid in ids:
        spec = next((c for c in reg["corpora"] if c["id"] == cid), None)
        if spec is None:
            print(f"unknown corpus id: {cid}", file=sys.stderr)
            continue
        v = T.judge(spec, reg, ear, verbose=False)
        out.append(v)
        if not as_json:
            T.print_report(v)
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    # --json is accepted BOTH before and after the subcommand (a shared parent
    # parser) so `status --json` works for project_eran_dashboard, exactly as
    # the docstring/README promise.
    jsonp = argparse.ArgumentParser(add_help=False)
    jsonp.add_argument("--json", action="store_true", help="emit JSON")

    ap = argparse.ArgumentParser(
        parents=[jsonp],
        description="ALMAWARE Master Modeler — one control plane over every model")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("roster", parents=[jsonp],
                   help="every model card, ours flagged (registry.py)")
    sub.add_parser("status", parents=[jsonp],
                   help="roster + LIVE health snapshot (honest)")
    sub.add_parser("eval", parents=[jsonp],
                   help="per-model vanilla-control comparison view")

    rp = sub.add_parser("route-plan", parents=[jsonp],
                        help="RECOMMEND a worker for a task tag (Fable/cheap/DGX); "
                             "never calls a model")
    rp.add_argument("task", nargs="?", help="task tag or free text "
                    "(hard-design | cheap-bulk | training | ...)")
    rp.add_argument("--list", action="store_true", dest="list_all",
                    help="list every known tag and its recommended worker")

    pr = sub.add_parser("route", parents=[jsonp],
                        help="delegate a task to the fleet router")
    pr.add_argument("prompt", nargs="?", help="prompt (or pipe via stdin)")
    pr.add_argument("--task", help="explicit task type (see fleet_config.json)")
    pr.add_argument("--auto", action="store_true", help="auto-classify the task")
    pr.add_argument("--dry-run", action="store_true",
                    help="show the pick, don't call the model")

    pc = sub.add_parser(
        "control", parents=[jsonp],
        help="GATED STUB — prints what it WOULD do; never acts (read-only)")
    pc.add_argument("verb", help="e.g. start / stop / restart (NOT executed)")
    pc.add_argument("target", help="model/target name (NOT executed)")

    pt = sub.add_parser(
        "teach", parents=[jsonp],
        help="MODEH — judge a CORPUS: is there anything here to learn? "
             "(delegates to teachability.py, read-only)")
    pt.add_argument("corpus", nargs="*",
                    help="corpus ids from corpora.json (default: all)")
    pt.add_argument("--units", action="store_true",
                    help="per-unit table for ONE corpus instead of a verdict")
    pt.add_argument("--scratch", default="",
                    help="path substituted for @SCRATCH@ in corpora.json")

    pb = sub.add_parser(
        "brain", parents=[jsonp],
        help="THE WELDER'S SECOND BRAIN (level 3) — what this control plane has "
             "learned about connecting models. Append-only; provenance mandatory.")
    pb.add_argument("action", choices=["read", "write"])
    pb.add_argument("text", nargs="?", default="", help="the lesson (write only)")
    pb.add_argument("--id", default="master", help="which welder brain (default: master)")
    pb.add_argument("--kind", default="learned",
                    choices=["tried", "worked", "failed", "decided", "learned"])
    pb.add_argument("--author", default="master-modeler")
    pb.add_argument("--source", default="", help="PROVENANCE — required to write")
    pb.add_argument("--ref", action="append", default=[])
    pb.add_argument("--outcome", default="")
    pb.add_argument("--query", default="")
    pb.add_argument("-n", type=int, default=20)

    args = ap.parse_args(argv)

    # --json may be given before OR after the subcommand. argparse's subparser
    # default (False) can clobber the parent's True when it's given first, so
    # honour it from either position.
    raw_argv = argv if argv is not None else sys.argv[1:]
    as_json = bool(getattr(args, "json", False)) or ("--json" in raw_argv)

    if args.cmd == "roster":
        return cmd_roster(as_json)
    if args.cmd == "status":
        return cmd_status(as_json)
    if args.cmd == "eval":
        return cmd_eval(as_json)
    if args.cmd == "route-plan":
        return cmd_route_plan(args.task, as_json, args.list_all)
    if args.cmd == "control":
        return cmd_control(args.verb, args.target, as_json)
    if args.cmd == "brain":
        return cmd_brain(args, as_json)
    if args.cmd == "teach":
        return cmd_teach(args, as_json)

    # route
    prompt = args.prompt
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        ap.error("route: no prompt given (pass as arg or pipe via stdin)")
    return cmd_route(prompt, args.task, args.auto, args.dry_run, as_json)


if __name__ == "__main__":
    raise SystemExit(main())

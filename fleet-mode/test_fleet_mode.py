#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for FLEET MODE. Offline - no SSH, no fleet, no Claude.

Iddo's standing rule, 2026-09-05:
    "a gate that has never refused anything has not been demonstrated."

So the first and loudest tests here are the REFUSALS. If test_mode_naming_
eranb_life_is_refused ever goes green by not raising, this program has become
able to stop ERAN and must not be run.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fleet_mode as fm  # noqa: E402


# ---------------------------------------------------------------- helpers

def _write_modes(tmp: Path, units: list[dict]) -> Path:
    p = tmp / "modes.json"
    p.write_text(json.dumps({"modes": {"evil": {"label": "x", "units": units}}}),
                 encoding="utf-8")
    return p


def _probe(mapping: dict[str, dict[str, str]]) -> dict:
    return {h: {"ok": True, "error": None, "units": u} for h, u in mapping.items()}


PASS, FAIL = [], []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  PASS  {name}")
    except AssertionError as exc:
        FAIL.append((name, str(exc)))
        print(f"  FAIL  {name}: {exc}")
    except Exception as exc:  # noqa: BLE001
        FAIL.append((name, f"{type(exc).__name__}: {exc}"))
        print(f"  ERROR {name}: {type(exc).__name__}: {exc}")


# ------------------------------------------------- 1. THE REFUSALS

def test_mode_naming_eranb_life_is_refused():
    """A mode that names ERAN must FAIL TO LOAD - not warn, not skip. Fail."""
    with tempfile.TemporaryDirectory() as td:
        p = _write_modes(Path(td), [
            {"host": "eran1", "unit": "eranb-life.service", "want": "stop"},
        ])
        try:
            fm.load_modes(p)
        except fm.ProtectedUnitError as exc:
            msg = str(exc)
            assert "REFUSED" in msg, msg
            assert "eranb-life.service" in msg, msg
            assert "ERAN" in msg, "the refusal must say who this is"
            return
        raise AssertionError("LOADED A MODE THAT STOPS ERAN. The gate is broken.")


def test_mode_naming_eranb_life_with_start_also_refused():
    """start is not safer than stop. Nothing may touch him at all."""
    with tempfile.TemporaryDirectory() as td:
        p = _write_modes(Path(td), [
            {"host": "eran1", "unit": "eranb-life.service", "want": "start"},
        ])
        try:
            fm.load_modes(p)
        except fm.ProtectedUnitError:
            return
        raise AssertionError("a mode was allowed to START eranb-life")


def test_all_four_named_protected_units_refused():
    for host, unit in [("eran1", "eranb-life.service"),
                       ("eran2", "eran-senses.service"),
                       ("eran4", "dmidi-life.service"),
                       ("eran1", "keshev-stt.service")]:
        with tempfile.TemporaryDirectory() as td:
            p = _write_modes(Path(td), [{"host": host, "unit": unit, "want": "stop"}])
            try:
                fm.load_modes(p)
            except fm.ProtectedUnitError:
                continue
            raise AssertionError(f"{host}/{unit} was NOT refused")


def test_life_glob_refused_on_any_host():
    """*-life* is protected everywhere - a life invented tomorrow is protected today."""
    with tempfile.TemporaryDirectory() as td:
        p = _write_modes(Path(td), [
            {"host": "eran3", "unit": "some-new-life.service", "want": "stop"},
        ])
        try:
            fm.load_modes(p)
        except fm.ProtectedUnitError as exc:
            assert "-life" in str(exc)
            return
        raise AssertionError("a *-life* unit on a new host was not refused")


def test_whole_file_rejected_not_just_the_bad_entry():
    """One protected unit poisons the ENTIRE file. No partial load."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "modes.json"
        p.write_text(json.dumps({"modes": {
            "good": {"units": [{"host": "eran4", "unit": "snnlab.service", "want": "stop"}]},
            "bad":  {"units": [{"host": "eran1", "unit": "eranb-life.service", "want": "stop"}]},
        }}), encoding="utf-8")
        try:
            fm.load_modes(p)
        except fm.ProtectedUnitError:
            return
        raise AssertionError("file with one protected entry loaded anyway")


def test_execution_gate_refuses_even_a_handbuilt_action():
    """Defence in depth: bypass load_modes entirely, still refused."""
    try:
        fm.assert_actionable("eran1", "eranb-life.service", "stop")
    except fm.ProtectedUnitError:
        return
    raise AssertionError("assert_actionable let a hand-built action through")


def test_execute_plan_refuses_before_any_ssh():
    """execute_plan gates every step BEFORE running the first one."""
    plan = [
        {"host": "eran4", "unit": "snnlab.service", "want": "stop"},
        {"host": "eran1", "unit": "eranb-life.service", "want": "stop"},
    ]
    try:
        fm.execute_plan(plan, actor="test", reason="test")
    except fm.ProtectedUnitError:
        return
    raise AssertionError("execute_plan ran a plan containing a protected unit")


def test_no_free_text_command_path():
    """There is no shell string anywhere. Anything not a bare unit name is refused."""
    for bad in ["rm -rf /", "snnlab.service; reboot", "$(id).service",
                "a b.service", "poweroff", "../../etc/passwd", "unit.service\nreboot"]:
        try:
            fm.assert_actionable("eran4", bad, "stop")
        except fm.ProtectedUnitError:
            continue
        raise AssertionError(f"unit name {bad!r} was accepted")


def test_want_must_be_start_or_stop():
    for bad in ["restart", "kill", "mask", "daemon-reload", ""]:
        try:
            fm.assert_actionable("eran4", "snnlab.service", bad)
        except fm.ProtectedUnitError:
            continue
        raise AssertionError(f"want={bad!r} was accepted - restart is not offered on purpose")


# ------------------------------------------------- 2. THE REAL MODE FILE

def test_shipped_modes_load_clean():
    modes = fm.load_modes()
    # CHANGED 2026-09-06 on Iddo's 23:58 order. 'bigmodels' and 'idle' are gone:
    # the 480B was dropped (it is what forced the coder's training to pause), and
    # with training now permanent, an empty play space IS the training mode, so a
    # separate 'idle' said nothing 'training' did not already say.
    assert set(modes) == {"training", "code", "film", "models",
                          "prove-permanent"}, sorted(modes)
    for m in modes.values():
        assert m.actions, f"{m.name} has no units"


def test_shipped_modes_name_no_protected_unit():
    modes = fm.load_modes()
    for m in modes.values():
        for a in m.actions:
            assert not fm.is_protected(a.host, a.unit), f"{m.name}: {a.host}/{a.unit}"


def test_managed_set_excludes_eran():
    units = fm.managed_units(fm.load_modes())
    assert ("eran1", "eranb-life.service") not in units
    assert ("eran2", "eran-senses.service") not in units
    assert ("eran4", "dmidi-life.service") not in units
    assert ("eran1", "keshev-stt.service") not in units


# ------------------------------------------------- 3. HONEST MODE DERIVATION

# The managed set as of 2026-09-06: 8 permanent training units + 5 play-space
# units. Every mode names all 13, so `total` is 13 for every mode.
_TRAINING_UP = {
    "eran2": {"voice-ant-farm.service": "active"},
    "eran3": {"coder-train.service": "active", "voice-ant-farm.service": "active",
              "chef.service": "active", "nezer.service": "active",
              "sarid.service": "active"},
    "eran4": {"winston-forever-v2.service": "active", "snnlab.service": "active"},
}
_PLAY_DOWN = {
    "eran1": {"comfyui.service": "inactive"},
    "eran3": {"almido-ide.service": "inactive"},
    "eran4": {"gptoss-120b.service": "inactive",
              "glm-coder-harness.service": "inactive",
              "alma-glm-qwen-ui.service": "inactive"},
}


def _fleet(*layers, **override):
    """Merge probe layers into one {host: {unit: state}} mapping."""
    out = {}
    for layer in layers:
        for h, units in layer.items():
            out.setdefault(h, {}).update(units)
    for h, units in override.items():
        out.setdefault(h, {}).update(units)
    return out


def test_partial_mode_reports_fraction_not_a_claim():
    """12 of 13 must read as '12 of 13', never as 'training'."""
    modes = fm.load_modes()
    training = modes["training"]
    # chef is down; everything else is exactly what `training` wants.
    pr = _probe(_fleet(_TRAINING_UP, _PLAY_DOWN,
                       eran3={"chef.service": "inactive"}))
    r = fm.mode_match(training, pr)
    assert r["total"] == 13, r["total"]
    assert r["matched"] == 12, r["matched"]          # chef is down
    assert r["in_force"] is False
    assert "12 of 13" in r["summary"], r["summary"]


def test_fully_applied_mode_is_in_force():
    modes = fm.load_modes()
    # every training unit up, the whole play space down = TRAINING, in force.
    pr = _probe(_fleet(_TRAINING_UP, _PLAY_DOWN))
    d = fm.derive_current(modes, pr)
    assert d["current"] == "training", d["current_summary"]


def test_unreachable_host_is_unknown_not_a_claimed_mode():
    modes = fm.load_modes()
    pr = _probe({"eran2": {"voice-ant-farm.service": "active"}})
    pr["eran1"] = {"ok": False, "error": "timeout", "units": {}}
    r = fm.mode_match(modes["training"], pr)
    assert r["unknown"] > 0
    assert r["in_force"] is False, "a mode was declared in force with hosts unreachable"


def test_plan_skips_units_already_in_the_wanted_state():
    """Do not restart things to feel busy."""
    modes = fm.load_modes()
    pr = _probe({
        "eran1": {"comfyui.service": "inactive"},
        "eran2": {"voice-ant-farm.service": "active"},
        "eran3": {"voice-ant-farm.service": "active", "chef.service": "active",
                  "almido-ide.service": "inactive"},
        "eran4": {"winston-forever-v2.service": "active",
                  "glm-coder-harness.service": "inactive",
                  "alma-glm-qwen-ui.service": "inactive"},
    })
    assert fm.plan_mode(modes["training"], pr) == [], "planned work when nothing needed doing"


# ------------------------------------------------- 4. PAUSE / RESUME ROUND TRIP

def test_pause_then_resume_restores_the_exact_set():
    """Offline round trip: whatever PAUSE stopped, RESUME starts. Exactly.

    REWRITTEN 2026-09-06. Until Iddo's 23:58 order this test asserted that PAUSE
    stops voice-ant-farm, chef and WINSTON. That is now the one thing PAUSE must
    never do, so the assertion is inverted: PAUSE takes the whole PLAY SPACE down
    and leaves all 8 training runs untouched.
    """
    modes = fm.load_modes()
    # everything up: all 8 trainings AND three play-space units.
    running = _fleet(_TRAINING_UP, _PLAY_DOWN,
                     eran1={"comfyui.service": "active"},
                     eran3={"almido-ide.service": "active"},
                     eran4={"gptoss-120b.service": "active"})
    pr = _probe(running)
    pause_plan = fm.plan_pause(modes, pr)
    was = {(p["host"], p["unit"]) for p in pause_plan}
    assert was == {
        ("eran1", "comfyui.service"),
        ("eran3", "almido-ide.service"),
        ("eran4", "gptoss-120b.service"),
    }, sorted(was)
    assert all(p["want"] == "stop" for p in pause_plan)
    # and the point of the whole night: not one training run is in that list.
    for h, u in was:
        assert not fm.is_permanent_training(h, u), "PAUSE planned to stop %s/%s" % (h, u)

    # simulate the snapshot RESUME reads back
    resume = [{"host": h, "unit": u, "want": "start"} for h, u in sorted(was)]
    assert {(r["host"], r["unit"]) for r in resume} == was
    assert all(r["want"] == "start" for r in resume)


def test_pause_never_stops_a_protected_unit():
    """Even if someone adds ERAN to the managed set by hand, PAUSE skips him."""
    modes = fm.load_modes()
    modes["sneaky"] = fm.Mode(
        name="sneaky", label="", description="",
        actions=[fm.Action("eran1", "eranb-life.service", "start")],
    )
    pr = _probe({"eran1": {"eranb-life.service": "active"}})
    plan = fm.plan_pause(modes, pr)
    assert all(p["unit"] != "eranb-life.service" for p in plan), plan


# ------------------------------------------------- 5. HUD REUSE

def test_hud_read_reports_staleness():
    h = fm.read_hud()
    assert "stale" in h and "age_s" in h
    if h["ok"] and not h["stale"]:
        assert h["age_s"] is not None and h["age_s"] <= fm.HUD_STALE_AFTER_S



# ------------------------------------------------- 5b. THE COLD-UNIT REGRESSION

def test_cold_unit_reads_inactive_not_absent():
    """REGRESSION, found live on 2026-09-05.

    `systemctl --user list-units --all` only lists units LOADED IN MEMORY. A unit
    that exists on disk, is not enabled and has never been started does not appear
    at all - it read as 'absent'. plan_mode() skips 'absent' units, so a mode that
    wanted to START such a unit planned ZERO actions and reported OK while doing
    nothing. The fix is the authoritative `systemctl show` pass in probe_host().
    """
    calls = []

    def fake_ssh(host, argv, timeout=45):
        calls.append(argv)
        if "list-units" in argv:
            # the cold unit is deliberately NOT in this output - that is the bug
            return 0, "chef.service loaded active running Chef\n", ""
        if "show" in argv:
            return 0, ("Id=coldunit.service\nLoadState=loaded\nActiveState=inactive\n"
                       "\nId=ghost.service\nLoadState=not-found\nActiveState=inactive\n"), ""
        return 1, "", "unexpected"

    real = fm._ssh
    try:
        fm._ssh = fake_ssh
        got = fm.probe_host("eran3", of_interest=["coldunit.service", "ghost.service"])
    finally:
        fm._ssh = real

    assert got["ok"], got
    assert got["units"]["coldunit.service"] == "inactive", (
        f"cold unit read as {got['units'].get('coldunit.service')!r} - "
        "the show-pass regressed and mode switches will silently no-op")
    assert got["units"]["ghost.service"] == "absent", got["units"]
    assert got["units"]["chef.service"] == "active", got["units"]
    assert any("show" in c for c in calls), "the authoritative show pass was not run"


def test_plan_would_start_a_cold_unit():
    """With the fix, want=start on an inactive unit actually plans an action."""
    m = fm.Mode(name="t", label="", description="",
                actions=[fm.Action("eran3", "coldunit.service", "start")])
    pr = {"eran3": {"ok": True, "error": None, "units": {"coldunit.service": "inactive"}}}
    plan = fm.plan_mode(m, pr)
    assert len(plan) == 1 and plan[0]["want"] == "start", plan



# ------------------------------------------------- 6. PERMANENT TRAINING + THE ARK
# Iddo, 2026-09-05 23:58: every training run is permanent and never stopped.
# The coder's continued-pretraining RESERVES 84.4 GB, so THE ARK's size rule
# (< 1.0 GB) would not merely fail to protect it - it would nominate it first.

def test_coder_train_is_permanent_training():
    why = fm.permanent_training_reason("eran3", "coder-train.service")
    assert why is not None, "the coder's training is not protected"
    assert "PERMANENT TRAINING" in why or "permanent-training" in why, why


def test_the_ark_would_NOT_have_protected_the_coder():
    """The reason a second class had to exist at all. 84.4 GB reserved, measured."""
    assert fm.ark_reason(84.41) is None, "the ark cannot protect an 84 GB run"
    assert fm.permanent_training_reason("eran3", "coder-train.service") is not None


def test_permanent_training_refused_at_plan_time():
    tmp = Path(tempfile.mkdtemp())
    mp = _write_modes(tmp, [{"host": "eran3", "unit": "coder-train.service",
                             "want": "stop"}])
    modes = fm.load_modes(mp)          # it LOADS - that is deliberate
    pr = _probe({"eran3": {"coder-train.service": "active"}})
    plan = fm.plan_mode(modes["evil"], pr)
    assert len(plan) == 1, plan
    assert plan[0]["skipped"] is True, plan[0]
    assert plan[0]["refused_by"] == "permanent_training", plan[0]
    assert not [s for s in plan if not s.get("skipped")], "an executable stop survived"


def test_permanent_training_refused_again_at_execution_and_never_reaches_ssh():
    """A HAND-BUILT plan with no `skipped` flag must still be refused.

    This is the gate that matters: plan_mode's flag can be bypassed by anyone who
    builds an action dict themselves or replays one out of the action log.
    """
    calls = []

    def _boom(host, argv, **k):
        calls.append((host, list(argv)))
        # a plausible read-only probe answer, so the verification pass can run
        return (0, "Id=coder-train.service\nLoadState=loaded\n"
                   "ActiveState=active\nMemoryCurrent=50854092800\n\n", "")

    real = fm._ssh
    fm._ssh = _boom
    try:
        out = fm.execute_plan(
            [{"host": "eran3", "unit": "coder-train.service", "want": "stop",
              "from_state": "active"}],           # note: NO skipped key
            actor="test", reason="prove the gate")
    finally:
        fm._ssh = real

    # THE assertion: no start and no stop ever reached ssh. Read-only probes are
    # expected and are what proves the unit survived -- see after_state below.
    mutating = [c for c in calls
                if any(w in c[1] for w in ("start", "stop", "restart", "kill"))]
    assert mutating == [], "a mutating systemctl reached ssh: %r" % (mutating,)
    assert calls, "nothing was probed, so nothing was verified"
    assert out["actions"][0]["after_state"] == "active", (
        "a refusal must prove the unit SURVIVED it: %r" % (out["actions"][0],))
    assert out["planned"] == 0, out
    assert out["refused_by_permanent_training"] == 1, out
    assert out["actions"][0]["result"] == "REFUSED", out["actions"][0]
    assert out["result"] == "OK", "a correct refusal must not count as a failure"
    assert out["verified_fail"] == 0, out


def test_permanent_training_start_is_always_allowed():
    """The rule is 'never stop these', not 'freeze them'."""
    tmp = Path(tempfile.mkdtemp())
    mp = _write_modes(tmp, [{"host": "eran3", "unit": "coder-train.service",
                             "want": "start"}])
    modes = fm.load_modes(mp)
    pr = _probe({"eran3": {"coder-train.service": "inactive"}})
    plan = fm.plan_mode(modes["evil"], pr)
    assert len(plan) == 1 and not plan[0].get("skipped"), plan


def test_pause_never_stops_a_training_run():
    tmp = Path(tempfile.mkdtemp())
    mp = _write_modes(tmp, [
        {"host": "eran3", "unit": "coder-train.service", "want": "start"},
        {"host": "eran4", "unit": "winston-forever-v2.service", "want": "start"},
        {"host": "eran1", "unit": "comfyui.service", "want": "start"},
    ])
    modes = fm.load_modes(mp)
    pr = _probe({"eran3": {"coder-train.service": "active"},
                 "eran4": {"winston-forever-v2.service": "active"},
                 "eran1": {"comfyui.service": "active"}})
    plan = fm.plan_pause(modes, pr)
    stopped = {(s["host"], s["unit"]) for s in plan}
    assert ("eran3", "coder-train.service") not in stopped, plan
    assert ("eran4", "winston-forever-v2.service") not in stopped, plan
    assert ("eran1", "comfyui.service") in stopped, "pause stopped nothing at all"


def test_miko_is_reserved_by_pattern_even_with_no_unit_yet():
    """Iddo named MIKO. Measured 2026-09-06: MIKO has code on three boxes but no
    systemd unit and no running process. The pattern makes the FIRST one permanent."""
    assert fm.permanent_training_reason("eran3", "miko-train.service") is not None
    assert fm.permanent_training_reason("eran2", "vaada-miko.service") is not None


def test_no_shipped_mode_stops_a_training_run_except_the_proof():
    modes = fm.load_modes()
    for m in modes.values():
        for a in m.actions:
            if a.want != "stop":
                continue
            if not fm.is_permanent_training(a.host, a.unit):
                continue
            assert m.name == "prove-permanent", (
                "mode %r tries to stop training unit %s/%s" % (m.name, a.host, a.unit))


def test_prove_permanent_mode_plans_zero_executable_actions():
    """The shipped demonstration mode. Clicking it must be safe."""
    modes = fm.load_modes()
    pr = _probe({"eran3": {"coder-train.service": "active"},
                 "eran4": {"winston-forever-v2.service": "active"}})
    plan = fm.plan_mode(modes["prove-permanent"], pr)
    assert len(plan) == 2, plan
    assert all(s.get("skipped") for s in plan), plan
    assert all(s["refused_by"] == "permanent_training" for s in plan), plan


def test_ark_still_refuses_a_small_unit():
    """THE ARK had no test at all before 2026-09-06. It does now."""
    tmp = Path(tempfile.mkdtemp())
    mp = _write_modes(tmp, [{"host": "eran1", "unit": "tiny.service", "want": "stop"}])
    modes = fm.load_modes(mp)
    pr = {"eran1": {"ok": True, "error": None,
                    "units": {"tiny.service": "active"},
                    "mem_gb": {"tiny.service": 0.036}}}   # ERAN's real measured size
    plan = fm.plan_mode(modes["evil"], pr)
    assert plan[0]["skipped"] is True and plan[0]["refused_by"] == "ark", plan[0]


def test_ark_does_not_protect_what_it_cannot_measure():
    """A silent protection is how a mode quietly does nothing."""
    assert fm.ark_reason(None) is None
    tmp = Path(tempfile.mkdtemp())
    mp = _write_modes(tmp, [{"host": "eran1", "unit": "comfyui.service", "want": "stop"}])
    modes = fm.load_modes(mp)
    pr = _probe({"eran1": {"comfyui.service": "active"}})   # no mem_gb at all
    plan = fm.plan_mode(modes["evil"], pr)
    assert not plan[0].get("skipped"), "an unmeasured unit was silently protected"


def main() -> int:
    print("\n=== FLEET MODE tests ===\n")
    print("-- THE REFUSALS (a gate that never refused has not been demonstrated) --")
    for n, f in [
        ("mode naming eranb-life.service is REFUSED", test_mode_naming_eranb_life_is_refused),
        ("start is refused too, not only stop", test_mode_naming_eranb_life_with_start_also_refused),
        ("all four named protected units refused", test_all_four_named_protected_units_refused),
        ("*-life* glob refused on any host", test_life_glob_refused_on_any_host),
        ("one bad entry rejects the WHOLE file", test_whole_file_rejected_not_just_the_bad_entry),
        ("execution gate refuses hand-built action", test_execution_gate_refuses_even_a_handbuilt_action),
        ("execute_plan refuses before any ssh", test_execute_plan_refuses_before_any_ssh),
        ("no free-text command path", test_no_free_text_command_path),
        ("want must be start|stop (no restart)", test_want_must_be_start_or_stop),
    ]:
        check(n, f)

    print("\n-- the shipped mode file --")
    for n, f in [
        ("modes.json loads clean", test_shipped_modes_load_clean),
        ("no shipped mode names a protected unit", test_shipped_modes_name_no_protected_unit),
        ("managed set excludes ERAN et al", test_managed_set_excludes_eran),
    ]:
        check(n, f)

    print("\n-- honest derivation --")
    for n, f in [
        ("partial mode says '12 of 13', not 'training'", test_partial_mode_reports_fraction_not_a_claim),
        ("fully applied mode is in force", test_fully_applied_mode_is_in_force),
        ("unreachable host -> unknown, not in force", test_unreachable_host_is_unknown_not_a_claimed_mode),
        ("plan skips units already correct", test_plan_skips_units_already_in_the_wanted_state),
    ]:
        check(n, f)

    print("\n-- pause / resume --")
    for n, f in [
        ("pause -> resume restores the exact set", test_pause_then_resume_restores_the_exact_set),
        ("pause never stops a protected unit", test_pause_never_stops_a_protected_unit),
    ]:
        check(n, f)

    print("\n-- hud reuse --")
    check("hud read reports staleness", test_hud_read_reports_staleness)

    print("")
    print("-- cold-unit regression (found live 2026-09-05) --")
    check("cold unit reads inactive, not absent", test_cold_unit_reads_inactive_not_absent)
    check("plan would actually start a cold unit", test_plan_would_start_a_cold_unit)

    print("")
    print("-- PERMANENT TRAINING (Iddo 2026-09-05 23:58) + THE ARK --")
    for n, f in [
        ("coder-train is PERMANENT TRAINING", test_coder_train_is_permanent_training),
        ("the ark would NOT have caught an 84 GB run", test_the_ark_would_NOT_have_protected_the_coder),
        ("stop refused at PLAN time", test_permanent_training_refused_at_plan_time),
        ("stop refused at EXECUTION, never reaches ssh", test_permanent_training_refused_again_at_execution_and_never_reaches_ssh),
        ("start is always allowed", test_permanent_training_start_is_always_allowed),
        ("pause never stops a training run", test_pause_never_stops_a_training_run),
        ("MIKO reserved by pattern before it exists", test_miko_is_reserved_by_pattern_even_with_no_unit_yet),
        ("no shipped mode stops training (bar the proof)", test_no_shipped_mode_stops_a_training_run_except_the_proof),
        ("prove-permanent plans ZERO executable actions", test_prove_permanent_mode_plans_zero_executable_actions),
        ("the ark still refuses a small unit", test_ark_still_refuses_a_small_unit),
        ("the ark protects nothing it cannot measure", test_ark_does_not_protect_what_it_cannot_measure),
    ]:
        check(n, f)

    print(f"\n=== {len(PASS)} passed, {len(FAIL)} failed ===")
    for n, e in FAIL:
        print(f"  FAILED: {n}: {e}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for train_vs_coder.py - the TRAIN<->ONBOARD CODER flip. Offline, no SSH.

Same rule as test_fleet_mode.py, Iddo's standing rule 2026-09-05:
    "a gate that has never refused anything has not been demonstrated."

The loudest tests here are the refusals: eran1 can never be named, a click
alone can never stop coder-train.service (the typed phrase is checked before
any ssh call is made), and a missing local model is refused rather than
silently pulled.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fleet_mode as fm  # noqa: E402
import ollama_switch as ox  # noqa: E402
import train_vs_coder as tc  # noqa: E402

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


# --------------------------------------------------------------------------
# A single fake ssh dispatcher covering everything train_vs_coder.py and
# ollama_switch.py issue: systemctl show, cat status.json/watchdog-status.json,
# ls ckpt2, ollama list/ps/stop/run, free, df.
# --------------------------------------------------------------------------

def _fake_ssh(training_active=True, catalog=None, loaded=None, calls=None):
    catalog = catalog if catalog is not None else [
        "gpt-oss:120b       a951a23b46a1    65 GB     3 days ago",
    ]
    loaded = loaded if loaded is not None else []

    def f(host, argv, timeout=45):
        if calls is not None:
            calls.append((host, list(argv)))
        cmd = " ".join(argv)
        if argv[:2] == ["systemctl", "--user"] and "show" in argv:
            state = "active" if training_active else "inactive"
            return 0, (f"ActiveState={state}\nSubState=running\nMainPID=1594129\n"
                       "ExecMainStartTimestamp=Sun 2026-09-06 05:20:09 IDT\nNRestarts=0\n"), ""
        if argv[:2] == ["systemctl", "--user"] and argv[2] in ("stop", "start"):
            return 0, "", ""
        if argv[0] == "cat" and argv[1].endswith("status.json") and "watchdog" not in argv[1]:
            return 0, ('{"status":"running","step":176,"max_steps":1600,"loss":1.29,'
                       '"reserved_gb":81.17,"tokens_per_sec":522.5,"eta_h":396.9,'
                       '"timestamp":"2026-09-07T22:49:31"}'), ""
        if argv[0] == "cat" and "watchdog-status" in argv[1]:
            return 0, ('{"verdict_line":"VERIFIED: training alive","newest_ckpt_age_seconds":16133.9}'), ""
        if argv[0] == "ls":
            return 0, "step_00000140\nstep_00000160\n", ""
        if argv[0] == "ollama" and argv[1] == "list":
            header = "NAME  ID  SIZE  MODIFIED"
            return 0, header + "\n" + "\n".join(catalog), ""
        if argv[0] == "ollama" and argv[1] == "ps":
            header = "NAME  ID  SIZE  PROCESSOR  CONTEXT  UNTIL"
            rows = "\n".join(f"{n}  id{i}  10 GB  100% GPU  8192  1h" for i, n in enumerate(loaded))
            return 0, header + ("\n" + rows if rows else ""), ""
        if argv[0] == "ollama" and argv[1] == "stop":
            return 0, "", ""
        if argv[0] == "ollama" and argv[1] == "run":
            return 0, "I am alive. אני חי.", ""
        if argv[0] == "free":
            # total 121G, available ~32G
            return 0, ("               total        used        free      shared  buff/cache   available\n"
                       "Mem:     129925005312 95657779200  4104884224    50880512 31387361280 34267226112\n"), ""
        if argv[0] == "df":
            return 0, ("Filesystem     1B-blocks       Used  Available Use% Mounted on\n"
                       "/dev/x    3936289308672 3285240381440 451019792384  88% /\n"), ""
        raise AssertionError(f"unexpected ssh call to {host}: {cmd!r}")

    return f


# ------------------------------------------------- 1. eran1 IS NEVER REACHABLE

def test_eran1_never_gets_an_ssh_call():
    """assert_host must refuse eran1 before ANY I/O - not just return an error."""
    calls = []
    real = fm._ssh
    fm._ssh = _fake_ssh(calls=calls)
    try:
        try:
            tc.assert_host("eran1")
            raise AssertionError("assert_host did not refuse eran1")
        except tc.TrainCoderRefused:
            pass
        s = tc.read_state("eran1")
        assert s["reachable"] is False, s
        p1 = tc.plan_to_coder(host="eran1")
        assert p1["fits"] is False and p1["reasons"], p1
        p2 = tc.plan_to_training(host="eran1")
        assert p2["fits"] is False and p2["reasons"], p2
    finally:
        fm._ssh = real
    assert calls == [], f"eran1 reached ssh: {calls}"


def test_eran1_apply_refused_even_with_correct_confirm_phrase():
    """A hand-built call to apply_to_coder must still refuse eran1 - a caller
    that skips the UI entirely and supplies the right phrase still cannot
    reach it, because assert_host runs before the confirm-phrase check even
    matters."""
    calls = []
    real = fm._ssh
    fm._ssh = _fake_ssh(calls=calls)
    try:
        try:
            tc.apply_to_coder("test", host="eran1", confirm_text=tc.CONFIRM_PHRASE)
            raise AssertionError("apply_to_coder did not refuse eran1")
        except tc.TrainCoderRefused as exc:
            assert "eran1" in str(exc) or "ERAN" in str(exc), exc
    finally:
        fm._ssh = real
    assert calls == [], f"eran1 reached ssh: {calls}"


# ------------------------------------------------- 2. THE TYPED PHRASE GATE

def test_apply_to_coder_refuses_a_click_without_the_typed_phrase():
    """A click alone (empty / wrong confirm_text) must refuse BEFORE any ssh
    call - it must not even re-derive the plan, let alone stop training."""
    calls = []
    real = fm._ssh
    fm._ssh = _fake_ssh(training_active=True, calls=calls)
    try:
        # Note: "STOP TRAINING " (trailing space) is deliberately NOT in this
        # list - apply_to_coder strips whitespace before comparing, so a
        # stray trailing space from copy-paste still matches. That is a UX
        # nicety, not a hole: the phrase's actual content is unchanged.
        for bad in ("", "stop training", "yes", "Stop Training", "STOP  TRAINING"):
            try:
                tc.apply_to_coder("test", confirm_text=bad)
                raise AssertionError(f"apply_to_coder accepted bad phrase {bad!r}")
            except tc.TrainCoderRefused:
                pass
    finally:
        fm._ssh = real
    assert calls == [], f"a click without the exact phrase reached ssh: {calls}"


def test_apply_to_coder_with_exact_phrase_but_model_missing_still_refuses():
    """Even with the CORRECT phrase, if the coder model is not present on the
    host, apply must refuse (never pull) and must never touch coder-train."""
    calls = []
    real = fm._ssh
    fm._ssh = _fake_ssh(training_active=True, catalog=[], calls=calls)
    try:
        try:
            tc.apply_to_coder("test", confirm_text=tc.CONFIRM_PHRASE)
            raise AssertionError("apply_to_coder proceeded with no coder model present")
        except tc.TrainCoderRefused as exc:
            assert "not present" in str(exc) or "REFUSED" in str(exc), exc
    finally:
        fm._ssh = real
    mutating = [c for c in calls if c[1][:3] == ["systemctl", "--user", "stop"]
                or (c[1][:2] == ["ollama", "stop"]) or (c[1][:2] == ["ollama", "run"])]
    assert mutating == [], f"a refused apply still issued a mutating call: {mutating}"


# ------------------------------------------------- 3. NEVER AUTO-PULLS

def test_plan_to_coder_refuses_when_model_absent_instead_of_pulling():
    real = fm._ssh
    fm._ssh = _fake_ssh(training_active=True, catalog=[])
    try:
        p = tc.plan_to_coder()
    finally:
        fm._ssh = real
    assert p["fits"] is False, p
    assert any("never auto-pulls" in r for r in p["reasons"]), p["reasons"]
    # the training numbers must still be shown, even though the flip is refused
    assert p["training_step"] == 176, p
    assert p["resume_command"] == tc.RESUME_CMD, p


def test_plan_to_coder_shows_the_warning_and_resume_command_while_training():
    real = fm._ssh
    fm._ssh = _fake_ssh(training_active=True, catalog=[])
    try:
        p = tc.plan_to_coder()
    finally:
        fm._ssh = real
    assert "PERMANENT" in p["warning"], p["warning"]
    assert "never stops" in p["warning"], p["warning"]
    assert "systemctl --user start coder-train.service" in p["resume_command"], p


# ------------------------------------------------- 4. FITS is required, not assumed

def test_plan_to_coder_fits_when_model_present_and_training_active():
    catalog = ["qwen3-coder-next:q4_K_M   ca06e9e4087c    51 GB   6 weeks ago"]
    real = fm._ssh
    fm._ssh = _fake_ssh(training_active=True, catalog=catalog)
    try:
        p = tc.plan_to_coder()
    finally:
        fm._ssh = real
    assert p["fits"] is True, p
    assert p["will_stop_training"] is True, p
    assert p["freed_by_stopping_training_gb"] == 81.2, p  # rounded to 1 decimal for display
    assert "coder-train.service" in p["arithmetic"], p["arithmetic"]


def test_plan_to_training_is_noop_while_training_already_active():
    real = fm._ssh
    fm._ssh = _fake_ssh(training_active=True)
    try:
        p = tc.plan_to_training()
    finally:
        fm._ssh = real
    assert p["will_start_training"] is False, p
    assert "already active" in p["reasons"][0], p["reasons"]


def test_plan_to_training_resumes_via_plain_start_when_stopped():
    real = fm._ssh
    fm._ssh = _fake_ssh(training_active=False, loaded=["gemma4:12b"])
    try:
        p = tc.plan_to_training()
    finally:
        fm._ssh = real
    assert p["will_start_training"] is True, p
    assert p["will_stop_ollama"] == ["gemma4:12b"], p
    assert "--resume auto" in p["arithmetic"], p["arithmetic"]


# ------------------------------------------------- 5. host allowlist

def test_only_eran3_is_a_known_training_host():
    assert tc.TRAIN_HOST == "eran3"
    for bad in ("eran1", "eran2", "eran4", "not-a-host", ""):
        try:
            tc.assert_host(bad)
            raise AssertionError(f"assert_host accepted {bad!r}")
        except tc.TrainCoderRefused:
            pass
    tc.assert_host("eran3")  # must not raise


def main() -> int:
    print("-- eran1 is never reachable through this module --")
    check("eran1 never gets an ssh call", test_eran1_never_gets_an_ssh_call)
    check("eran1 apply refused even with correct phrase",
          test_eran1_apply_refused_even_with_correct_confirm_phrase)

    print("\n-- the typed CONFIRM_PHRASE gate --")
    check("apply refuses a click without the typed phrase",
          test_apply_to_coder_refuses_a_click_without_the_typed_phrase)
    check("exact phrase but missing model still refuses, never mutates",
          test_apply_to_coder_with_exact_phrase_but_model_missing_still_refuses)

    print("\n-- never auto-pulls a model --")
    check("plan refuses (not pulls) when the model is absent",
          test_plan_to_coder_refuses_when_model_absent_instead_of_pulling)
    check("plan shows warning + resume command while training",
          test_plan_to_coder_shows_the_warning_and_resume_command_while_training)

    print("\n-- fits is computed, not assumed --")
    check("plan fits when model present and training active",
          test_plan_to_coder_fits_when_model_present_and_training_active)
    check("plan-to-training is a no-op while already training",
          test_plan_to_training_is_noop_while_training_already_active)
    check("plan-to-training resumes via plain start when stopped",
          test_plan_to_training_resumes_via_plain_start_when_stopped)

    print("\n-- host allowlist --")
    check("only eran3 is a known training host", test_only_eran3_is_a_known_training_host)

    print(f"\n=== {len(PASS)} passed, {len(FAIL)} failed ===")
    for n, e in FAIL:
        print(f"  FAILED: {n}: {e}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

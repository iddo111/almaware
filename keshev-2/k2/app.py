"""KESHEV 2 assembly — honest shadow-mode entry point (night 1).

WHAT THIS IS TONIGHT, stated plainly: KESHEV A is king of the microphone
and holds the BRIO. K2 has NO capture module — deliberately; building one
beside a live mic is the double-mic scar. This entry point assembles every
real module (mutex, config, journal, interlock, device law, gates,
typer+Win32, STT client), reports its honest state, and exits. It is the
production import root the wiring-discipline test checks against — the
modules run HERE, not only under tests.

States it can truthfully announce:
  HALT_CONFIG        config missing/corrupt/invalid (scar 40 — loud, no
                     defaults, exit 2)
  IDLE_RIVAL_ALIVE   KESHEV A is alive (interlock D-002) — capture would
                     be refused; shadow mode only
  IDLE_NO_CAPTURE    A is gone and the ticket was granted — and K2 still
                     cannot capture, because the capture module is not
                     built. The ticket proves the interlock, not the mic.
  SHADOW_READY       assembly complete: gates live, typer live, STT
                     client constructed (add --probe for a real server
                     round-trip).

Run:  python -m k2.app [--probe]
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from k2 import configstore, devicelaw, hotkeys, interlock, journal, \
    presence, sttclient
from k2.typer import Typer
from k2.win32type import Win32OsLayer

REPO = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO / "config" / "k2.json"
STATE_DIR = REPO / "state"

EXIT_OK = 0
EXIT_CONFIG_HALT = 2


def build(cfg, jr: journal.Journal, idle_api=None, hotkey_factory=None):
    """Assemble the real pipeline pieces from a loaded config. Returns
    (gates_decide, typer, stt) — the seams the future router will hold.

    `idle_api` is a test seam ONLY: production callers pass nothing and
    get the real Win32 clock. It exists because seam tests that read the
    REAL idle clock flip when Iddo walks away — the first suite run of
    this repo failed at 22:20 for exactly that reason (the gate FIRED on
    the real machine mid-test-run; scar: environmental test honesty)."""
    emit = journal.emitter(jr)

    gate = presence.PresenceGate(
        api=idle_api,
        emit=emit,
        enter_idle_limit_s=cfg["enter_idle_limit_s"],
        type_idle_limit_s=cfg["type_idle_limit_s"])
    arm = presence.ArmSwitch(
        enabled=cfg["armed_mode"],
        timeout_s=cfg["arm_timeout_s"],
        emit=emit)

    # D-008: an enabled arm layer MUST have a real key behind it. If the
    # bind fails, the layer is disabled LOUDLY — an enabled-but-unarmable
    # switch is a mic that can never type, with no path out (deafness
    # fails open; the presence gate still guards).
    # The factory contract carries the journal emit: any factory (real or
    # test) receives it, so a bind failure is journalled by construction —
    # not only when the default factory remembered to pass it.
    if arm.enabled:
        hk = (hotkey_factory or (lambda cb, em: hotkeys.ArmHotkey(
            presence.ARM_HOTKEY, cb, emit=em)))(arm.toggle, emit)
        if not hk.start():
            arm.enabled = False
            emit("STATE", state="ARM_LAYER_DISABLED",
                 reason="hotkey_bind_fail", spec=presence.ARM_HOTKEY)

    def decide() -> presence.Decision:
        return presence.combined_decision(gate, arm)

    typer = Typer(
        os_layer=Win32OsLayer(),
        decide=decide,
        emit=emit,
        parked_path=STATE_DIR / "parked.txt")

    token = sttclient.load_token(cfg["server_token_path"])
    stt = sttclient.SttClient(
        cfg["server_url"], token,
        default_hint=cfg["lang_hint_default"],
        emit=emit)
    return decide, typer, stt


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # 1. one instance (scar 1) — before anything heavy
    interlock.acquire_own_mutex_or_exit()

    # 2. config — HALT loud on anything wrong (scar 40)
    store = configstore.ConfigStore(CONFIG_PATH)
    try:
        cfg = store.load()
    except configstore.ConfigHaltError as exc:
        print(f"KESHEV2 HALT_CONFIG: {exc}", file=sys.stderr, flush=True)
        return EXIT_CONFIG_HALT

    # 3. journal
    sid = uuid.uuid4().hex[:8]
    jr = journal.Journal(STATE_DIR, sid)
    emit = journal.emitter(jr)
    jr.session_begin(mode="shadow", config_revision=cfg["revision"])

    try:
        # 4. rival interlock (D-002) — the verdict IS the door
        verdict = interlock.check(emit=emit)
        if verdict.rival_alive:
            state = interlock.IDLE_RIVAL_ALIVE
        else:
            try:
                verdict.grant()          # proves the ticket law end-to-end
                state = "IDLE_NO_CAPTURE"
            except interlock.RivalUnprovableError:
                state = interlock.IDLE_RIVAL_ALIVE   # fail closed

        # 5. device law dry statement — no enumeration tonight (no audio
        # lib in this build, lint G2); the law itself is live and testable.
        extra = cfg["never_use_devices_extra"]
        sel = devicelaw.select([], extra=extra)
        emit("STATE", state=state, device_state=sel.state,
             never_mic_markers=len(devicelaw.never_mic_markers()))

        # 6. full assembly — gates, typer, STT client
        decide, typer, stt = build(cfg, jr)
        d = decide()
        emit("STATE", state="SHADOW_READY", may_type=d.may_type,
             may_enter=d.may_enter, armed_mode=bool(cfg["armed_mode"]))

        line = (f"KESHEV2 shadow: state={state} device={sel.state} "
                f"gates(type={d.may_type},enter={d.may_enter}) "
                f"typer=live stt=constructed")
        print(line, flush=True)

        # 7. optional real server round-trip
        if "--probe" in argv:
            p = stt.probe()
            emit("STATE", state="PROBE",
                 healthy=p.healthy, reason=p.reason,
                 server_state=p.state, p50=p.decode_p50_ms,
                 canary_age_s=p.canary_age_s)
            print(f"KESHEV2 probe: healthy={p.healthy} reason={p.reason} "
                  f"state={p.state} p50={p.decode_p50_ms}ms "
                  f"canary_age={p.canary_age_s:.0f}s", flush=True)

        return EXIT_OK
    finally:
        jr.session_end()
        jr.close()


if __name__ == "__main__":
    sys.exit(main())

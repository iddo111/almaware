#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA-EMDR — buzzers_ble.py
==========================

לקוח הבאזרים של ALMA-EMDR — צד המחשב.
The PC-side buzzer client for ALMA-EMDR.

מימוש מלא של ``PROTOCOL-buzzers-20260901.md`` v1.0 — מסגרת בינארית אחת בת 9 בתים,
זהה על USB, על BLE ועל השידור. שלושה מובילים: סימולטור (ללא חומרה), חוט (USB CDC),
ואלחוט (BLE). לעולם לא חוסם את חוט ה-UI. כלל האיש-המת ממומש בשלוש שכבות בצד הלקוח.

Full implementation of ``PROTOCOL-buzzers-20260901.md`` v1.0 — one 9-byte binary frame,
byte-identical on USB, BLE and ESP-NOW broadcast. Three transports: simulator (no
hardware), wire (USB CDC), radio (BLE). Never blocks the UI thread. The dead-man rule
is implemented in three client-side layers on top of the five firmware layers.

STATUS / מצב
------------
⚠️  **NO HARDWARE EXISTS YET.**  Nothing in this file has been tested against a real
    buzzer, a real ESP32-C3, or a real BLE peripheral. What *is* proven, by running
    ``python buzzers_ble.py vectors`` and ``python buzzers_ble.py sweep``:

      * the 8 wire test vectors of PROTOCOL §C.7 encode and decode byte-exact;
      * a full 90 s sweep drives the simulated balls with the measured timing shown
        by the ``sweep`` command, including the pending-tap, hysteresis, duplicate-
        suppression, duty-limiter and dead-man rules of §C.3 and §D.5.

    ``SerialTransport`` is written against pyserial 3.5 (installed) but has never
    opened a real port here.  ``BleTransport`` is written against bleak (NOT
    installed on this machine) and has never seen a peripheral.  Both are marked
    UNTESTED in ``Transport.tested_against_hardware``.

WHY THIS FILE DOES NOT USE THE ORB'S PIXEL POSITION
---------------------------------------------------
PROTOCOL §D.4 is binding: clients MUST derive taps from **phase crossing**, never from
a pixel threshold.  ``emdr_widget.py``'s existing 6-pixel edge band is combined with a
±2 % random amplitude jitter, and when the jitter is negative the orb never reaches the
band — the edge event never fires, silently, for the whole session (32.8 % of seeds at
1920 px, 41.6 % at 3840 px).  A buzzer hung off that test would never buzz for a third
of users.  ``BuzzerClient.on_phase()`` therefore takes the raw monotonic phase and does
exact crossing arithmetic, which is immune to amplitude jitter and cannot be skipped by
a dropped frame.  Run ``python buzzers_ble.py sweep --seed 1`` to see it fire on a seed
where the widget's own beep is silent.

USAGE (see INTEGRATION-pc-buzzers.md for the widget patch)
----------------------------------------------------------
    import buzzers_ble

    bz = buzzers_ble.BuzzerClient.from_settings(settings)   # returns None if disabled
    bz.start()                       # non-blocking; opens the transport on a worker
    ...
    bz.on_phase(phase, hz)           # 60 Hz from the UI thread — pure arithmetic
    ...
    bz.stop()                        # non-blocking; STOP x5 then idle

CLI
---
    python buzzers_ble.py vectors            # verify PROTOCOL §C.7 test vectors
    python buzzers_ble.py sweep              # full sweep through the simulator
    python buzzers_ble.py sweep --seed 1 --secs 6 --hz 1.0
    python buzzers_ble.py deadman            # prove the dead-man rule
    python buzzers_ble.py ports              # list serial ports (read-only)
    python buzzers_ble.py scan               # BLE scan (needs bleak; read-only)

Author: claude-cli-BUZZPC, 2026-09-01.  Nothing here opens an audio device.
"""

from __future__ import annotations

import atexit
import collections
import math
import struct
import sys
import threading
import time
from typing import Callable, Iterable, Optional, Sequence

__version__ = "1.0.0"
PROTOCOL_VERSION = 1

# =============================================================================
# PROTOCOL CONSTANTS — PROTOCOL-buzzers-20260901.md §C.1, §C.2, §D.5
# These are the contract. Do not "tidy" them.
# =============================================================================

MAGIC = 0xE1                    # protocol id + version 1

OP_TAP = 0x01
OP_STOP = 0x02
OP_KEEP = 0x03
OP_SET = 0x04
OP_HELLO = 0x05
OP_STATUS = 0x06

OP_NAMES = {
    OP_TAP: "TAP", OP_STOP: "STOP", OP_KEEP: "KEEP",
    OP_SET: "SET", OP_HELLO: "HELLO", OP_STATUS: "STATUS",
}

SIDE_NONE = 0x00
SIDE_BOTH = 0x42        # 'B'
SIDE_L = 0x4C           # 'L'
SIDE_R = 0x52           # 'R'

SIDE_NAMES = {SIDE_NONE: "-", SIDE_BOTH: "B", SIDE_L: "L", SIDE_R: "R"}

ROOM_ALL = 0x00

# Firmware constants (§D.5). The client mirrors the clamps so that what we send is
# already what the ball will do — a command the firmware would clamp is a lie in a log.
DEADMAN_MS = 1500
HYSTERESIS_MS = 30
DUR_MIN_MS = 40
DUR_MAX_MS = 600
DELAY_MAX_MS = 8000
INTENSITY_FLOOR = 40
DUTY_MAX_PCT = 60
DUTY_WINDOW_MS = 2000
WDT_MS = 2000
ERM_LEAD_MS = 30
OVERDRIVE_MS = 20

# STATUS flag bits (§C.2)
FLAG_MOTOR_ACTIVE = 1 << 0
FLAG_DEADMAN_TRIPPED = 1 << 1
FLAG_CHARGING = 1 << 2
FLAG_BATTERY_LOW = 1 << 3
FLAG_LINK_BLE = 1 << 4
FLAG_LINK_ESPNOW = 1 << 5
FLAG_LINK_USB = 1 << 6
FLAG_DUTY_LIMITED = 1 << 7

# BLE GATT (§C.4)
BLE_SERVICE_UUID = "d5ffea00-0555-4abc-b5f0-734ccd124d13"
BLE_RX_UUID = "d5ffea01-0555-4abc-b5f0-734ccd124d13"   # write-without-response, client->ball
BLE_TX_UUID = "d5ffea02-0555-4abc-b5f0-734ccd124d13"   # notify, ball->client
BLE_NAME_PREFIX = "EMDR-"

# Legacy ASCII, USB only (§C.6). Kept so today's ALMA-EMDR.html works unchanged.
LEGACY_BAUD = 115200

FRAME_LEN = 9

TWO_PI = 2.0 * math.pi
HALF_PI = 0.5 * math.pi


# =============================================================================
# §C.1 — the frame codec
# =============================================================================

class ProtocolError(ValueError):
    """A frame that does not conform to PROTOCOL §C.1."""


def encode(op: int, seq: int, room: int = 1, side: int = SIDE_NONE,
           intensity: int = 0, dur_ms: int = 0, delay_ms: int = 0) -> bytes:
    """Build one 9-byte frame.

    ``dur_ms`` is quantised DOWN to the protocol's 4 ms grid (``dur4 = dur_ms // 4``);
    ``delay_ms`` is a little-endian uint16 of milliseconds. Out-of-range values raise
    rather than silently wrap — a wrapped duration is a motor stuck on someone's hand.
    """
    if not (0 <= op <= 255):
        raise ProtocolError(f"op out of range: {op}")
    if not (0 <= room <= 255):
        raise ProtocolError(f"room out of range: {room}")
    if side not in SIDE_NAMES:
        raise ProtocolError(f"side must be one of L/R/B/none, got {side!r}")
    if not (0 <= intensity <= 255):
        raise ProtocolError(f"intensity out of range: {intensity}")
    if not (0 <= dur_ms <= 1020):
        raise ProtocolError(f"dur_ms out of range 0..1020: {dur_ms}")
    if not (0 <= delay_ms <= 65535):
        raise ProtocolError(f"delay_ms out of range 0..65535: {delay_ms}")
    return (bytes([MAGIC, op, seq & 0xFF, room, side, intensity, dur_ms // 4])
            + struct.pack("<H", delay_ms))


def decode(buf: bytes) -> dict:
    """Parse one 9-byte frame back into fields. Raises ProtocolError on anything else."""
    if len(buf) != FRAME_LEN:
        raise ProtocolError(f"frame must be {FRAME_LEN} bytes, got {len(buf)}")
    if buf[0] != MAGIC:
        raise ProtocolError(f"bad magic 0x{buf[0]:02X}, expected 0x{MAGIC:02X}")
    return {
        "op": buf[1],
        "seq": buf[2],
        "room": buf[3],
        "side": buf[4],
        "intensity": buf[5],
        "dur_ms": buf[6] * 4,
        "delay_ms": struct.unpack("<H", buf[7:9])[0],
    }


def frame_hex(buf: bytes) -> str:
    return " ".join(f"{b:02X}" for b in buf)


def frame_repr(buf: bytes) -> str:
    """One-line human reading of a frame, for logs."""
    try:
        f = decode(buf)
    except ProtocolError as exc:
        return f"<malformed: {exc}>"
    op = OP_NAMES.get(f["op"], f"op{f['op']:02X}")
    room = "ALL" if f["room"] == ROOM_ALL else str(f["room"])
    if f["op"] == OP_TAP:
        return (f"{op:<6} room={room} seq={f['seq']:<3} side={SIDE_NAMES[f['side']]} "
                f"int={f['intensity']:<3} dur={f['dur_ms']:<3}ms in={f['delay_ms']}ms")
    if f["op"] == OP_STATUS:
        return (f"{op:<6} room={room} seq={f['seq']:<3} side={SIDE_NAMES[f['side']]} "
                f"batt={f['intensity']}% fw={f['dur_ms'] // 4} flags=0x{f['delay_ms']:04X}")
    return f"{op:<6} room={room} seq={f['seq']:<3}"


# §C.7 — the eight test vectors, verbatim. A conformant implementation reproduces these.
TEST_VECTORS: Sequence[tuple] = (
    ("TAP left,  room 1, seq 7,  int 200, 160 ms, now",
     dict(op=OP_TAP, seq=7, room=1, side=SIDE_L, intensity=200, dur_ms=160, delay_ms=0),
     "E1 01 07 01 4C C8 28 00 00"),
    ("TAP right, room 1, seq 8,  int 200, 160 ms, in 120 ms",
     dict(op=OP_TAP, seq=8, room=1, side=SIDE_R, intensity=200, dur_ms=160, delay_ms=120),
     "E1 01 08 01 52 C8 28 78 00"),
    ("TAP left,  ALL rooms, seq 9, int 255, 200 ms, in 250 ms",
     dict(op=OP_TAP, seq=9, room=ROOM_ALL, side=SIDE_L, intensity=255, dur_ms=200, delay_ms=250),
     "E1 01 09 00 4C FF 32 FA 00"),
    ("KEEP room 1, seq 10",
     dict(op=OP_KEEP, seq=10, room=1),
     "E1 03 0A 01 00 00 00 00 00"),
    ("STOP room 1, seq 11",
     dict(op=OP_STOP, seq=11, room=1),
     "E1 02 0B 01 00 00 00 00 00"),
    ("STOP ALL rooms, seq 12",
     dict(op=OP_STOP, seq=12, room=ROOM_ALL),
     "E1 02 0C 00 00 00 00 00 00"),
    ("HELLO room 1, seq 13",
     dict(op=OP_HELLO, seq=13, room=1),
     "E1 05 0D 01 00 00 00 00 00"),
    ("STATUS room 1, L, 91% batt, fw 1, link=BLE",
     dict(op=OP_STATUS, seq=13, room=1, side=SIDE_L, intensity=91, dur_ms=4, delay_ms=0x0010),
     "E1 06 0D 01 4C 5B 01 10 00"),
)


def verify_test_vectors(out=None) -> bool:
    """Encode + round-trip all §C.7 vectors. Returns True only if every one is exact."""
    out = out or sys.stdout
    ok = True
    for i, (name, kwargs, expect) in enumerate(TEST_VECTORS, 1):
        got = encode(**kwargs)
        got_hex = frame_hex(got)
        good = (got_hex == expect)
        # round-trip: every field we put in must come back out
        rt = decode(got)
        for k, v in kwargs.items():
            if k == "seq":
                continue
            if rt.get(k, v) != v and k in rt:
                good = False
        ok = ok and good
        out.write(f"  [{'OK ' if good else 'FAIL'}] {i}. {name}\n")
        out.write(f"        expect  {expect}\n")
        out.write(f"        got     {got_hex}\n")
        if not good:
            out.write(f"        decoded {rt}\n")
    # Range checks the protocol calls out explicitly
    checks = [
        ("dur4 reaches 1020 ms", encode(OP_TAP, 0, 1, SIDE_L, 200, 1020, 0)[6] == 255),
        ("delay u16 reaches 65535 ms", decode(encode(OP_TAP, 0, 1, SIDE_L, 200, 0, 65535))["delay_ms"] == 65535),
        ("delay covers browser 0.15 Hz half-cycle (3333 ms)",
         decode(encode(OP_TAP, 0, 1, SIDE_L, 200, 0, 3333))["delay_ms"] == 3333),
        ("0xE1 is not ASCII (legacy parser can never confuse the two)", MAGIC > 0x7F),
    ]
    for name, good in checks:
        ok = ok and good
        out.write(f"  [{'OK ' if good else 'FAIL'}] {name}\n")
    return ok


# =============================================================================
# Packet log — every frame, with a timestamp. §"testable with zero hardware".
# =============================================================================

class PacketLog:
    """Ring buffer of timestamped protocol events. Thread-safe, bounded, never raises."""

    def __init__(self, capacity: int = 4000, echo: Optional[Callable[[str], None]] = None):
        self._events = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._t0 = time.perf_counter()
        self.echo = echo

    def reset_clock(self) -> None:
        self._t0 = time.perf_counter()

    @property
    def t0(self) -> float:
        return self._t0

    def add(self, kind: str, text: str, t: Optional[float] = None, **extra) -> None:
        t = time.perf_counter() if t is None else t
        rel_ms = (t - self._t0) * 1000.0
        rec = {"t": t, "rel_ms": rel_ms, "kind": kind, "text": text}
        rec.update(extra)
        with self._lock:
            self._events.append(rec)
        if self.echo is not None:
            try:
                self.echo(f"{rel_ms:9.1f} ms  {kind:<10} {text}")
            except Exception:
                pass

    def events(self, kind: Optional[str] = None) -> list:
        with self._lock:
            evs = list(self._events)
        if kind is None:
            return evs
        return [e for e in evs if e["kind"] == kind]

    def render(self, limit: Optional[int] = None) -> str:
        evs = self.events()
        if limit is not None:
            evs = evs[:limit]
        lines = [f"{e['rel_ms']:9.1f} ms  {e['kind']:<10} {e['text']}" for e in evs]
        return "\n".join(lines)


# =============================================================================
# Transports
# =============================================================================

class Transport:
    """A way of getting 9 bytes to a ball. Opened, written and closed by the worker
    thread only — never by the UI thread."""

    name = "base"
    default_repeat = 3          # §C.1 triple-send
    link_latency_ms = 0.0       # subtracted from `delay` so the ball fires on target
    tested_against_hardware = False

    def open(self) -> bool:
        raise NotImplementedError

    def send(self, frame: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def describe(self) -> str:
        return self.name


class NullTransport(Transport):
    """Buzzers disabled. Accepts and discards. Exists so callers never branch on None."""

    name = "off"
    default_repeat = 1
    tested_against_hardware = True   # doing nothing is testable and it does nothing

    def open(self) -> bool:
        return True

    def send(self, frame: bytes) -> None:
        pass


# ---------------------------------------------------------------- simulated ball

class SimBall:
    """A software model of one buzzer ball, implementing PROTOCOL §C.3 and §D.5.

    This is the thing under test. It is deliberately written the way the firmware will
    be written — pending tap, hysteresis, dead-man, duty limiter, ERM lead, hard clamps —
    so that the packet log below is the REAL output of the protocol, not a proxy for it.

    ⚠️ It is a model. It cannot prove anything about a real ERM motor, a real radio, or
    a real MCU. It proves the protocol and the client are self-consistent.
    """

    def __init__(self, side: int, room: int = 1, label: Optional[str] = None,
                 log: Optional[PacketLog] = None):
        self.side = side
        self.room = room
        self.label = label or f"ball-{SIDE_NAMES.get(side, '?')}"
        self.log = log
        # §C.3 pending tap
        self._pending_target: Optional[float] = None
        self._pending_fire_at: Optional[float] = None
        self._pending_dur_ms = 0
        self._pending_int = 0
        # motor
        self._motor_off_at: Optional[float] = None
        self.motor_on = False
        # §C.1 idempotence: last 8 (op, seq) for 2000 ms
        self._recent: collections.deque = collections.deque(maxlen=8)
        # §D.5 dead-man
        self._deadman_deadline: Optional[float] = None
        self.deadman_tripped = False
        self._last_fired_target: Optional[float] = None
        # §D.5 duty limiter
        self._duty: collections.deque = collections.deque()   # (t_on, ms)
        self.duty_limited = False
        # bookkeeping for the proof
        self.fires: list = []          # dicts: fire_at, felt_at, off_at, dur, intensity
        self.counters = collections.Counter()

    # -- helpers ------------------------------------------------------------
    def _emit(self, kind: str, text: str, t: float) -> None:
        self.counters[kind] += 1
        if self.log is not None:
            self.log.add(kind, f"[{self.label}] {text}", t=t)

    def _duty_ms_in_window(self, now: float) -> float:
        cutoff = now - DUTY_WINDOW_MS / 1000.0
        while self._duty and self._duty[0][0] < cutoff:
            self._duty.popleft()
        return sum(ms for _, ms in self._duty)

    # -- the wire -----------------------------------------------------------
    def on_frame(self, buf: bytes, now: float) -> None:
        try:
            f = decode(buf)
        except ProtocolError as exc:
            self._emit("BAD_FRAME", str(exc), now)
            return

        if f["room"] != ROOM_ALL and f["room"] != self.room:
            self.counters["other_room"] += 1
            return

        # Any well-formed frame for our room is proof the link is alive, so the
        # dead-man is reset BEFORE duplicate suppression, not after. (Harmless today
        # because the 3 copies are 8 ms apart, but a firmware that reset the dead-man
        # only on non-duplicates would be one dropped original away from a false trip.)
        self._deadman_deadline = now + DEADMAN_MS / 1000.0

        # §C.1 idempotence: silently ignore a repeat of (op, seq) seen in the last 2 s
        key = (f["op"], f["seq"])
        self._recent = collections.deque(
            [(k, t) for (k, t) in self._recent if now - t < 2.0], maxlen=8)
        if any(k == key for k, _ in self._recent):
            self._emit("DUP_DROP", f"{OP_NAMES.get(f['op'], f['op'])} seq={f['seq']} ignored", now)
            return
        self._recent.append((key, now))

        op = f["op"]
        if op == OP_KEEP:
            self._deadman_deadline = now + DEADMAN_MS / 1000.0
            self.deadman_tripped = False
            return

        if op == OP_STOP:
            self._pending_target = None
            self._pending_fire_at = None
            if self.motor_on:
                self._motor_off(now, reason="STOP")
            self._deadman_deadline = now + DEADMAN_MS / 1000.0
            self._emit("STOP_RX", "pending cancelled, motor off", now)
            return

        if op == OP_HELLO:
            self._emit("HELLO_RX", "would answer STATUS", now)
            self._deadman_deadline = now + DEADMAN_MS / 1000.0
            return

        if op == OP_SET:
            self.room = f["room"] if f["room"] != ROOM_ALL else self.room
            self._emit("SET_RX", f"room={self.room}", now)
            return

        if op != OP_TAP:
            self._emit("UNKNOWN_OP", f"op=0x{op:02X}", now)
            return

        # ---- TAP -----------------------------------------------------------
        # A TAP always arms the dead-man, even if it is not for our side.
        self._deadman_deadline = now + DEADMAN_MS / 1000.0
        self.deadman_tripped = False

        if f["side"] not in (self.side, SIDE_BOTH):
            return

        # §D.5 hard clamps, applied exactly as the firmware will apply them
        dur = f["dur_ms"]
        if dur > DUR_MAX_MS:
            self._emit("CLAMP", f"dur {dur} -> {DUR_MAX_MS} ms", now)
            dur = DUR_MAX_MS
        if 0 < dur < DUR_MIN_MS:
            dur = DUR_MIN_MS
        delay = f["delay_ms"]
        if delay > DELAY_MAX_MS:
            self._emit("CLAMP", f"delay {delay} -> {DELAY_MAX_MS} ms", now)
            delay = DELAY_MAX_MS
        inten = f["intensity"]
        if 0 < inten < INTENSITY_FLOOR:
            inten = INTENSITY_FLOOR
        if inten == 0 or dur == 0:
            return

        target = now + delay / 1000.0

        # A restatement that arrives AFTER the beat already played must not replay it.
        # (Found by simulation 2026-09-01: without this, the last whisper of a beat can
        # land after MOTOR_ON, re-arm with delay 0 and buzz the hand twice. This rule
        # belongs in the firmware too - see INTEGRATION-pc-buzzers.md, protocol note.)
        if (self._last_fired_target is not None
                and abs(target - self._last_fired_target) * 1000.0 < HYSTERESIS_MS):
            self._emit("ALREADY_PLAYED", "restatement of a beat already played - dropped", now)
            return

        # §C.3 hysteresis: a whisper that agrees with the pending beat to within
        # HYSTERESIS_MS is the SAME beat restated by a jittery link, not a new beat.
        if (self._pending_target is not None
                and abs(target - self._pending_target) * 1000.0 < HYSTERESIS_MS):
            self._emit("RESTATE",
                       f"target moved {abs(target - self._pending_target) * 1000.0:5.1f} ms "
                       f"(< {HYSTERESIS_MS} ms) - keeping pending beat", now)
            return

        self._pending_target = target
        self._pending_fire_at = target - ERM_LEAD_MS / 1000.0
        self._pending_dur_ms = dur
        self._pending_int = inten
        self._emit("ARM", f"pending tap in {delay} ms  dur={dur} int={inten}", now)

    # -- the MCU loop --------------------------------------------------------
    def pump(self, now: float) -> None:
        # motor off timer (armed in the same step that starts the PWM — §D.5)
        if self.motor_on and self._motor_off_at is not None and now >= self._motor_off_at:
            self._motor_off(now, reason="one-shot")

        # dead-man: no frame for DEADMAN_MS -> cancel and stay stopped
        if (self._deadman_deadline is not None and now >= self._deadman_deadline
                and not self.deadman_tripped):
            self.deadman_tripped = True
            self._pending_target = None
            self._pending_fire_at = None
            if self.motor_on:
                self._motor_off(now, reason="DEAD-MAN")
            self._emit("DEADMAN", f"no frame for {DEADMAN_MS} ms - stopped, LED amber", now)

        if self.deadman_tripped:
            return

        # scheduled fire
        if self._pending_fire_at is not None and now >= self._pending_fire_at:
            dur = self._pending_dur_ms
            # One motor, one pulse. Without this, a pulse starting while the motor is
            # still running merges with it into a single continuous buzz LONGER than
            # DUR_MAX - defeating the one-shot clamp that D.5 relies on. The hand is
            # already buzzing; a second beat on top of it is not felt as a beat anyway.
            if self.motor_on:
                self._emit("MOTOR_BUSY", "motor still running - tap refused "
                                         "(would merge past DUR_MAX)", now)
                self._last_fired_target = self._pending_target
                self._pending_target = None
                self._pending_fire_at = None
                return
            used = self._duty_ms_in_window(now)
            budget = DUTY_WINDOW_MS * DUTY_MAX_PCT / 100.0
            if used + dur > budget:
                # §D.5: excess taps are REFUSED, not truncated.
                self.duty_limited = True
                self._emit("REFUSE_DUTY",
                           f"{used:.0f}+{dur} ms > {budget:.0f} ms in {DUTY_WINDOW_MS} ms "
                           f"- tap refused, STATUS bit 7", now)
                self._pending_target = None
                self._pending_fire_at = None
                return
            self._motor_on(now, dur, self._pending_int, self._pending_target)
            self._last_fired_target = self._pending_target
            self._pending_target = None
            self._pending_fire_at = None

    def _motor_on(self, now: float, dur_ms: int, intensity: int, target: float) -> None:
        self.motor_on = True
        self._motor_off_at = now + dur_ms / 1000.0
        self._duty.append((now, dur_ms))
        overdrive = min(OVERDRIVE_MS, dur_ms // 3)
        # felt_at is the REAL perceived onset: the instant the pump actually started
        # the PWM, plus the ERM's own rise time. It is NOT the scheduled target -
        # reporting the schedule would be measuring a proxy for the thing under test.
        rec = {"fire_at": now, "felt_at": now + ERM_LEAD_MS / 1000.0,
               "scheduled_felt_at": target, "off_at": self._motor_off_at,
               "dur_ms": dur_ms, "intensity": intensity, "side": self.side}
        self.fires.append(rec)
        self._emit("MOTOR_ON",
                   f"PWM {intensity} for {dur_ms} ms (kick {overdrive} ms @255); "
                   f"felt at +{ERM_LEAD_MS} ms", now)

    def _motor_off(self, now: float, reason: str) -> None:
        self.motor_on = False
        self._motor_off_at = None
        self._emit("MOTOR_OFF", f"({reason})", now)


class LoopbackTransport(Transport):
    """Simulator transport: logs every packet with a timestamp and feeds it to SimBalls.

    This is the zero-hardware test rig. The 1 kHz pump thread stands in for the MCU's
    main loop; its resolution is reported by ``pump_resolution_ms`` after a run so the
    log's timings can be read honestly.
    """

    name = "sim"
    default_repeat = 3
    link_latency_ms = 0.0
    tested_against_hardware = True   # the simulator IS the thing being tested

    def __init__(self, log: Optional[PacketLog] = None, room: int = 1,
                 balls: Optional[Iterable[SimBall]] = None, pump_hz: float = 1000.0,
                 air_latency_ms: float = 0.0, air_jitter_ms: float = 0.0,
                 loss_pct: float = 0.0, rng_seed: int = 0):
        self.log = log or PacketLog()
        self.room = room
        if balls is None:
            balls = [SimBall(SIDE_L, room=room, label="ball-L", log=self.log),
                     SimBall(SIDE_R, room=room, label="ball-R", log=self.log)]
        self.balls = list(balls)
        self._pump_hz = pump_hz
        self._air_latency = air_latency_ms / 1000.0
        # A BLE central sends on the next connection event, so real latency is
        # base + uniform(0, connection_interval). Loss models an unacknowledged
        # broadcast (ESP-NOW), which is why §C.1 triple-sends.
        self._air_jitter = air_jitter_ms / 1000.0
        self._loss = max(0.0, min(1.0, loss_pct / 100.0))
        import random as _r
        self._rng = _r.Random(rng_seed)
        self.frames_lost = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._inflight: collections.deque = collections.deque()   # (arrive_at, frame)
        self._inflight_lock = threading.Lock()
        self.frames_seen = 0
        self._pump_gaps: list = []

    def open(self) -> bool:
        self._stop.clear()
        self._thread = threading.Thread(target=self._pump_loop, name="emdr-simball",
                                        daemon=True)
        self._thread.start()
        self.log.add("TRANSPORT", f"simulator open, {len(self.balls)} balls, room {self.room}")
        return True

    def send(self, frame: bytes) -> None:
        self.frames_seen += 1
        now = time.perf_counter()
        self.log.add("TX", f"{frame_hex(frame)}   {frame_repr(frame)}", t=now)
        if self._loss > 0.0 and self._rng.random() < self._loss:
            self.frames_lost += 1
            self.log.add("LOST", f"{frame_hex(frame)}   (simulated link loss)", t=now)
            return
        extra = self._rng.uniform(0.0, self._air_jitter) if self._air_jitter > 0 else 0.0
        arrive = now + self._air_latency + extra
        if arrive <= now:
            self._deliver(frame, now)
        else:
            with self._inflight_lock:
                self._inflight.append((arrive, frame))

    def _deliver(self, frame: bytes, t: float) -> None:
        for b in self.balls:
            b.on_frame(frame, t)

    def _pump_loop(self) -> None:
        period = 1.0 / self._pump_hz
        last = time.perf_counter()
        while not self._stop.is_set():
            now = time.perf_counter()
            self._pump_gaps.append((now - last) * 1000.0)
            last = now
            if self._air_latency > 0 or self._air_jitter > 0:
                due = []
                with self._inflight_lock:
                    self._inflight = collections.deque(sorted(self._inflight,
                                                              key=lambda x: x[0]))
                    while self._inflight and self._inflight[0][0] <= now:
                        due.append(self._inflight.popleft()[1])
                for fr in due:
                    self._deliver(fr, now)
            for b in self.balls:
                b.pump(now)
            # NOT Event.wait(): on Windows it quantises to the ~15.6 ms scheduler tick,
            # which silently turned this "1 kHz" MCU model into a 64 Hz one. time.sleep()
            # uses a high-resolution waitable timer on Python 3.11+ (measured below).
            time.sleep(period)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.log.add("TRANSPORT", "simulator closed")

    @property
    def pump_resolution_ms(self) -> dict:
        g = sorted(self._pump_gaps[2:]) or [0.0]
        return {"n": len(g), "p50": g[len(g) // 2], "p99": g[int(len(g) * 0.99)], "max": g[-1]}

    def describe(self) -> str:
        return f"sim({len(self.balls)} balls, room {self.room})"


# ---------------------------------------------------------------- wired USB box

class SerialTransport(Transport):
    """Phase 1 — the wired USB box (PROTOCOL §C.6, Part E Phase 1).

    ⚠️ UNTESTED AGAINST REAL HARDWARE. No box exists. Written against pyserial 3.5,
    which IS installed here, so this needs no new dependency — that is the whole point
    of building the wire first, as Iddo asked.

    Sends the same 9-byte binary frames. ``legacy_*`` helpers speak the old ASCII line
    protocol that ``ALMA-EMDR.html`` already uses, for bring-up only.
    """

    name = "serial"
    default_repeat = 1          # USB CDC is a reliable stream; triple-send is for radio
    link_latency_ms = 2.0       # design target, §D.2 — remeasure when the box exists
    tested_against_hardware = False

    def __init__(self, port: Optional[str] = None, baud: int = LEGACY_BAUD,
                 log: Optional[PacketLog] = None, write_timeout: float = 0.25):
        self.port = port
        self.baud = baud
        self.log = log or PacketLog()
        self.write_timeout = write_timeout
        self._ser = None
        self.last_error: Optional[str] = None

    @staticmethod
    def list_ports() -> list:
        try:
            from serial.tools import list_ports  # type: ignore
        except Exception as exc:                  # pragma: no cover
            return [("<pyserial unavailable>", str(exc))]
        return [(p.device, f"{p.description} [{p.hwid}]") for p in list_ports.comports()]

    @staticmethod
    def autodetect() -> Optional[str]:
        """Best-effort guess at the buzzer box. Never opens anything."""
        try:
            from serial.tools import list_ports  # type: ignore
        except Exception:
            return None
        wanted = ("esp32", "cp210", "ch340", "ch910", "usb serial", "usb-serial", "wch")
        for p in list_ports.comports():
            blob = f"{p.description} {p.manufacturer} {p.hwid}".lower()
            if any(w in blob for w in wanted):
                return p.device
        return None

    def open(self) -> bool:
        try:
            import serial  # type: ignore
        except Exception as exc:
            self.last_error = f"pyserial not available: {exc}"
            self.log.add("TRANSPORT", f"serial open FAILED - {self.last_error}")
            return False
        port = self.port or self.autodetect()
        if not port:
            self.last_error = "no serial port given and autodetect found nothing"
            self.log.add("TRANSPORT", f"serial open FAILED - {self.last_error}")
            return False
        try:
            self._ser = serial.Serial(port, self.baud, timeout=0.1,
                                      write_timeout=self.write_timeout)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.log.add("TRANSPORT", f"serial open FAILED on {port} - {self.last_error}")
            return False
        self.port = port
        self.log.add("TRANSPORT", f"serial open {port} @{self.baud} (UNTESTED vs hardware)")
        return True

    def send(self, frame: bytes) -> None:
        if self._ser is None:
            raise IOError("serial port not open")
        self.log.add("TX", f"{frame_hex(frame)}   {frame_repr(frame)}")
        self._ser.write(frame)

    # -- legacy ASCII, USB only (§C.6) --------------------------------------
    def legacy_send(self, line: str) -> None:
        """Send an old-protocol line ('?', 'I200', 'P160', 'L', 'R', 'X')."""
        if self._ser is None:
            raise IOError("serial port not open")
        self._ser.write((line + "\n").encode("ascii"))
        self.log.add("TX-ASCII", repr(line))

    def legacy_identify(self, timeout: float = 0.5) -> Optional[str]:
        """Bring-up helper: '?' and read one line back."""
        if self._ser is None:
            return None
        try:
            self.legacy_send("?")
            self._ser.timeout = timeout
            return self._ser.readline().decode("ascii", "replace").strip() or None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
            self.log.add("TRANSPORT", "serial closed")

    def describe(self) -> str:
        return f"serial({self.port or 'auto'} @{self.baud})"


# ---------------------------------------------------------------- BLE

class BleTransport(Transport):
    """Phase 2 — BLE, one pair of balls (PROTOCOL §C.4, Part E Phase 2).

    ⚠️ UNTESTED AGAINST REAL HARDWARE, and ``bleak`` is NOT installed on this machine
    (verified 2026-09-01: ``ModuleNotFoundError: No module named 'bleak'``).
    ``pip install bleak`` is required before this transport can do anything.

    Design constraints taken straight from bleak's own documentation and issues:

      * asyncio-only API, and **"Bleak will hang forever if the current thread is not
        MTA"** on Windows. This class therefore owns a dedicated thread with its own
        event loop and is never called from the Qt/UI thread. PyQt initialises COM as
        STA on the main thread, which is exactly the trap.
      * **Connect using the BLEDevice object from a scan, never an address string** —
        bleak documents that address-based connects break with multiple devices, and
        two balls is precisely that case.
      * **Write Without Response.** 9 bytes fits the default 23-byte ATT MTU, so no MTU
        negotiation is ever needed (§C.4).
      * **No pairing, no bonding, no encryption** (§C.6 decision 6) — Windows 11 pairing
        prompts break connects (bleak #1880, 0x800704C7), and there is no PHI on this
        link. The accepted residual risk is stated in the protocol, not hidden here.
    """

    name = "ble"
    default_repeat = 3
    link_latency_ms = 30.0      # design target: OS connection interval, §C.4/§D.2
    tested_against_hardware = False

    def __init__(self, room: int = 1, log: Optional[PacketLog] = None,
                 scan_timeout: float = 8.0, name_prefix: str = BLE_NAME_PREFIX,
                 max_devices: int = 2):
        self.room = room
        self.log = log or PacketLog()
        self.scan_timeout = scan_timeout
        self.name_prefix = name_prefix
        self.max_devices = max_devices
        self.last_error: Optional[str] = None
        self._loop = None
        self._thread: Optional[threading.Thread] = None
        self._clients: list = []
        self._ready = threading.Event()
        self._opened = False

    # -- loop plumbing ------------------------------------------------------
    def _run_loop(self) -> None:
        import asyncio
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    def _call(self, coro, timeout: float):
        import asyncio
        if self._loop is None:
            raise IOError("BLE loop not running")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    # -- Transport ----------------------------------------------------------
    def open(self) -> bool:
        try:
            import bleak  # noqa: F401  # type: ignore
        except Exception as exc:
            self.last_error = (f"bleak not installed ({exc}). "
                               f"Phase 2 needs: pip install bleak")
            self.log.add("TRANSPORT", f"BLE open FAILED - {self.last_error}")
            return False

        self._ready.clear()
        self._thread = threading.Thread(target=self._run_loop, name="emdr-ble", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5.0):
            self.last_error = "BLE event loop did not start"
            return False
        try:
            n = self._call(self._connect_all(), timeout=self.scan_timeout + 20.0)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.log.add("TRANSPORT", f"BLE open FAILED - {self.last_error}")
            return False
        self._opened = n > 0
        if not self._opened:
            self.last_error = f"no {self.name_prefix}* peripherals found in {self.scan_timeout}s"
            self.log.add("TRANSPORT", f"BLE open FAILED - {self.last_error}")
        return self._opened

    async def _connect_all(self) -> int:
        from bleak import BleakScanner, BleakClient  # type: ignore
        # Scan by service UUID first; fall back to the name prefix.
        devices = await BleakScanner.discover(timeout=self.scan_timeout,
                                              service_uuids=[BLE_SERVICE_UUID])
        if not devices:
            devices = [d for d in await BleakScanner.discover(timeout=self.scan_timeout)
                       if (d.name or "").startswith(self.name_prefix)]
        devices = devices[: self.max_devices]
        self.log.add("TRANSPORT", f"BLE scan found {len(devices)} device(s)")
        for d in devices:
            # NOTE: `d` is a BLEDevice object, deliberately not d.address (bleak docs).
            client = BleakClient(d, disconnected_callback=self._on_disconnect)
            try:
                await client.connect()
            except Exception as exc:
                self.log.add("TRANSPORT", f"BLE connect FAILED {d}: {exc}")
                continue
            try:
                await client.start_notify(BLE_TX_UUID, self._on_notify)
            except Exception:
                pass    # TX notify is optional; a ball that cannot talk back still buzzes
            self._clients.append(client)
            self.log.add("TRANSPORT", f"BLE connected {d.name or d.address}")
        return len(self._clients)

    def _on_disconnect(self, client) -> None:
        # §D.5: BLE onDisconnect -> immediate all-off is a FIRMWARE duty. On the client
        # side all we can do is notice and stop pretending we still have a link.
        self.log.add("TRANSPORT", "BLE disconnected - ball will dead-man within "
                                  f"{DEADMAN_MS} ms")
        try:
            self._clients.remove(client)
        except ValueError:
            pass

    def _on_notify(self, _char, data: bytearray) -> None:
        try:
            self.log.add("RX", f"{frame_hex(bytes(data))}   {frame_repr(bytes(data))}")
        except Exception:
            pass

    def send(self, frame: bytes) -> None:
        if not self._clients:
            raise IOError("no BLE ball connected")
        self.log.add("TX", f"{frame_hex(frame)}   {frame_repr(frame)}")
        self._call(self._write_all(frame), timeout=2.0)

    async def _write_all(self, frame: bytes) -> None:
        for c in list(self._clients):
            try:
                # response=False -> Write Without Response (§C.4). Never a round trip.
                await c.write_gatt_char(BLE_RX_UUID, frame, response=False)
            except Exception as exc:
                self.log.add("TRANSPORT", f"BLE write failed: {exc}")

    def close(self) -> None:
        try:
            if self._loop is not None and self._clients:
                self._call(self._disconnect_all(), timeout=5.0)
        except Exception:
            pass
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._loop = None
        self._opened = False
        self.log.add("TRANSPORT", "BLE closed")

    async def _disconnect_all(self) -> None:
        for c in list(self._clients):
            try:
                await c.disconnect()
            except Exception:
                pass
        self._clients.clear()

    def describe(self) -> str:
        return f"ble({len(self._clients)} connected, room {self.room})"


def make_transport(spec: str, room: int = 1, log: Optional[PacketLog] = None) -> Transport:
    """Build a transport from a settings string.

        "off"            -> NullTransport
        "sim"            -> LoopbackTransport (2 simulated balls)
        "serial"         -> SerialTransport, autodetected port
        "serial:COM5"    -> SerialTransport on COM5
        "ble"            -> BleTransport
    """
    spec = (spec or "off").strip().lower()
    if spec in ("", "off", "none", "disabled"):
        return NullTransport()
    if spec in ("sim", "simulator", "loopback", "test"):
        return LoopbackTransport(log=log, room=room)
    if spec.startswith("serial") or spec.startswith("usb") or spec.startswith("com"):
        port = None
        if ":" in spec:
            port = spec.split(":", 1)[1].strip().upper() or None
        elif spec.startswith("com"):
            port = spec.upper()
        return SerialTransport(port=port, log=log)
    if spec.startswith("ble") or spec.startswith("bt") or spec.startswith("bluetooth"):
        return BleTransport(room=room, log=log)
    raise ValueError(f"unknown buzzer transport {spec!r}")


# =============================================================================
# §D.5 — the UI rule that follows from the motor, not from software
# =============================================================================

def recommended_pulse_ms(hz: float) -> int:
    """Pulse length must satisfy 150 <= dur <= min(400, 250/hz) ms."""
    hi = min(400.0, 250.0 / max(hz, 0.01))
    return int(max(DUR_MIN_MS, min(400.0, max(150.0, hi))))


def haptics_distinct(hz: float) -> bool:
    """False above ~1.6 Hz: the ceiling drops below the 150 ms ERM floor and the taps
    stop feeling like separate beats. Visual and audio remain fine — only haptics
    degrade. Say so plainly rather than delivering mush (§D.5)."""
    return (250.0 / max(hz, 0.01)) >= 150.0


# =============================================================================
# BuzzerClient — the public API
# =============================================================================

_LIVE_CLIENTS: "list[BuzzerClient]" = []
_LIVE_LOCK = threading.Lock()


def _shutdown_all() -> None:
    with _LIVE_LOCK:
        clients = list(_LIVE_CLIENTS)
    for c in clients:
        try:
            c.close(wait_ms=400)
        except Exception:
            pass


atexit.register(_shutdown_all)


class BuzzerClient:
    """One conductor for one room of balls.

    THREADING CONTRACT — this is the part that must not be broken:

      * ``on_phase()``, ``tap_now()``, ``stop()`` and ``start()`` are called from the
        UI (Qt) thread. They do **no I/O, no blocking waits and no locking that a slow
        transport could hold.** ``on_phase()`` is pure float arithmetic plus a
        ``deque.append`` and an ``Event.set()`` — both atomic under the GIL.
      * Every byte that reaches a transport is written by ``_worker``, a daemon thread.
        A serial port that stalls, or a BLE stack that hangs, delays the worker and
        nothing else. The orb keeps sweeping.
      * ``close(wait_ms=...)`` is the only call that may wait, and only on shutdown.

    DEAD-MAN, CLIENT SIDE (three layers on top of the firmware's five, §D.5):

      1. The worker whispers TAP/KEEP at ``whisper_hz``. Stop whispering for
         ``DEADMAN_MS`` and every ball stops itself. This is the layer that survives
         the whole application dying.
      2. If ``on_phase()`` stops arriving while armed (the sweep hung, the UI thread
         wedged), the worker notices after ``stale_ms`` and sends STOP x5 — faster than
         waiting for the firmware dead-man.
      3. ``atexit`` closes every live client with a final STOP x5.
    """

    def __init__(self,
                 transport: Optional[Transport] = None,
                 room: int = 1,
                 intensity: int = 200,
                 pulse_ms: int = 160,
                 lookahead_ms: int = 250,
                 whisper_hz: float = 3.0,
                 repeat: Optional[int] = None,
                 link_latency_ms: Optional[float] = None,
                 stale_ms: int = 1200,
                 log: Optional[PacketLog] = None,
                 logger: Optional[Callable[[str], None]] = None,
                 both_hands: bool = False):
        self.transport = transport if transport is not None else NullTransport()
        self.log = log if log is not None else getattr(self.transport, "log", None) or PacketLog()
        self.logger = logger
        self.room = int(room)
        self.intensity = max(0, min(255, int(intensity)))
        if 0 < self.intensity < INTENSITY_FLOOR:
            self.intensity = INTENSITY_FLOOR
        self.pulse_ms = max(DUR_MIN_MS, min(DUR_MAX_MS, int(pulse_ms)))
        self.lookahead_ms = max(0, min(DELAY_MAX_MS, int(lookahead_ms)))
        self.whisper_hz = max(0.5, float(whisper_hz))
        self.repeat = int(repeat) if repeat is not None else self.transport.default_repeat
        self.link_latency_ms = (float(link_latency_ms) if link_latency_ms is not None
                                else float(self.transport.link_latency_ms))
        self.stale_ms = int(stale_ms)
        self.both_hands = bool(both_hands)

        # --- state written by the UI thread, read by the worker -------------
        self._taps: collections.deque = collections.deque(maxlen=8)   # atomic append
        self._wake = threading.Event()
        self._armed = False              # sweep running -> derive taps
        self._last_phase_t = 0.0         # perf_counter of the last on_phase()
        self._k_fired: Optional[int] = None

        # --- worker state ---------------------------------------------------
        self._thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._stop_request = threading.Event()
        self._seq = 0
        self._open_ok = False
        self._fail_streak = 0
        self._stats = collections.Counter()
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------ ctor
    @classmethod
    def from_settings(cls, settings: dict, log: Optional[PacketLog] = None,
                      logger: Optional[Callable[[str], None]] = None
                      ) -> "Optional[BuzzerClient]":
        """Build from the widget's settings dict. Returns None when buzzers are off,
        and None (not an exception) if the transport cannot even be constructed —
        buzzers must never be able to stop a therapy session from starting."""
        spec = str(settings.get("buzzer_transport", "off") or "off")
        if spec.strip().lower() in ("", "off", "none", "disabled"):
            return None
        pl = log or PacketLog()
        try:
            tr = make_transport(spec, room=int(settings.get("buzzer_room", 1)), log=pl)
        except Exception as exc:
            if logger:
                logger(f"buzzers: bad transport {spec!r} ({exc}) - buzzers disabled")
            return None
        hz = float(settings.get("sweep_hz", 1.0))
        pulse = int(settings.get("buzzer_pulse_ms", 0)) or recommended_pulse_ms(hz)
        return cls(
            transport=tr,
            room=int(settings.get("buzzer_room", 1)),
            intensity=int(settings.get("buzzer_intensity", 200)),
            pulse_ms=pulse,
            lookahead_ms=int(settings.get("buzzer_lookahead_ms", 250)),
            link_latency_ms=settings.get("buzzer_link_latency_ms"),
            both_hands=bool(settings.get("buzzer_both_hands", False)),
            log=pl, logger=logger,
        )

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Start the worker. Non-blocking: the transport is opened ON the worker,
        so a slow BLE scan or a missing COM port never stalls the UI."""
        if self._thread is not None:
            return
        self._shutdown.clear()
        self._stop_request.clear()
        self._k_fired = None
        self._last_phase_t = time.perf_counter()
        self._armed = True
        self._thread = threading.Thread(target=self._worker, name="emdr-buzzers",
                                        daemon=True)
        self._thread.start()
        with _LIVE_LOCK:
            if self not in _LIVE_CLIENTS:
                _LIVE_CLIENTS.append(self)
        self._say(f"buzzers: starting on {self.transport.describe()} "
                  f"(room {self.room}, {self.intensity}/{self.pulse_ms}ms, "
                  f"lookahead {self.lookahead_ms}ms, link lead {self.link_latency_ms:.0f}ms)")

    def stop(self) -> None:
        """End of a set. Non-blocking. The worker sends STOP x5 and then idles."""
        self._armed = False
        self._stop_request.set()
        self._wake.set()

    def close(self, wait_ms: int = 800) -> None:
        """Shut down for good: STOP x5, close the transport, join the worker."""
        self._armed = False
        self._stop_request.set()
        self._shutdown.set()
        self._wake.set()
        t = self._thread
        if t is not None and wait_ms > 0:
            t.join(timeout=wait_ms / 1000.0)
        self._thread = None
        with _LIVE_LOCK:
            if self in _LIVE_CLIENTS:
                _LIVE_CLIENTS.remove(self)

    # ------------------------------------------------- UI-thread entry points
    def on_phase(self, phase: float, hz: float) -> None:
        """Called from the UI thread every frame with the sweep's monotonic phase
        (radians) and rate (Hz). PROTOCOL §D.4: this is a phase crossing, never a
        pixel threshold — the widget's ±2% amplitude jitter silences the pixel test
        for a third of seeds.

        The orb is at ``mid + amp*sin(phase)``, so the edges are exactly at
        ``phase = pi/2 + k*pi``. We look ``lookahead_ms`` ahead, and put the EXACT
        remaining time into the frame's ``delay`` field, so the tap lands on the edge
        instead of on the next 16 ms frame boundary. Sub-frame accurate by construction.

        Cost: ~15 float ops, one deque append, one Event.set(). No I/O, no lock.
        """
        if not self._armed:
            return
        now = time.perf_counter()
        self._last_phase_t = now
        if hz <= 0.0 or not math.isfinite(phase):
            return

        lead_rad = TWO_PI * hz * (self.lookahead_ms / 1000.0)
        # index of the last edge at or before (phase + lead); edges are pi/2 + k*pi
        k_now = int(math.floor((phase + lead_rad - HALF_PI) / math.pi)) + 1

        if self._k_fired is None:
            # Count only edges strictly BEHIND us. Using k_now here would mark every
            # edge already inside the look-ahead horizon as fired, which silently
            # swallowed the first buzz of every set. (Found by simulation 2026-09-01.)
            self._k_fired = int(math.floor((phase - HALF_PI) / math.pi)) + 1
            if k_now <= self._k_fired:
                return
        if k_now <= self._k_fired:
            return

        # A long stall must not fire a burst of stale taps into someone's hand.
        if k_now - self._k_fired > 2:
            self._k_fired = k_now - 1
            self._stats["backlog_dropped"] += 1

        for k in range(self._k_fired + 1, k_now + 1):
            phi = HALF_PI + (k - 1) * math.pi
            delay_s = (phi - phase) / (TWO_PI * hz)
            if delay_s < 0.0:
                delay_s = 0.0
            # k odd -> sin(phi) = +1 -> right edge; k even -> left edge
            side = SIDE_BOTH if self.both_hands else (SIDE_R if (k % 2) else SIDE_L)
            self._taps.append((side, now + delay_s, k))
        self._k_fired = k_now
        self._wake.set()

    # Alias so the object can also sit in the widget's existing pan-consumer list.
    set_phase = on_phase

    def set_pan(self, pan: float) -> None:
        """Deliberate no-op. Accepts the pan-consumer interface so this object can be
        dropped into ``EmdrSequence._pan_consumers`` without a special case, but pan is
        a POSITION and §D.4 forbids deriving taps from position. Use ``on_phase``."""
        return

    def tap_now(self, side: str = "L", delay_ms: int = 0) -> None:
        """Manual single buzz — for the Settings 'test buzzers' button. Non-blocking."""
        s = {"L": SIDE_L, "R": SIDE_R, "B": SIDE_BOTH}.get(str(side).upper()[:1], SIDE_L)
        self._taps.append((s, time.perf_counter() + delay_ms / 1000.0, None))
        self._wake.set()

    def reset_phase(self) -> None:
        """Call at the start of each set so the first edge is not mistaken for a jump."""
        self._k_fired = None

    # ----------------------------------------------------------------- worker
    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def _emit(self, frame: bytes, repeat: Optional[int] = None) -> bool:
        """Send one logical frame ``repeat`` times, ~8 ms apart (§C.1). All copies carry
        the SAME seq — that is what makes the ball's (op, seq) dedup work."""
        n = self.repeat if repeat is None else repeat
        ok = False
        for i in range(max(1, n)):
            try:
                self.transport.send(frame)
                ok = True
                self._stats["frames_sent"] += 1
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._stats["send_errors"] += 1
            if i + 1 < n:
                if self._shutdown.wait(0.008):
                    break
        if ok:
            self._fail_streak = 0
        else:
            self._fail_streak += 1
            if self._fail_streak in (1, 10, 100):
                self._say(f"buzzers: transport error ({self._last_error}) "
                          f"x{self._fail_streak} - session continues without haptics")
        return ok

    def _send_stop(self) -> None:
        # §D.5: STOP is repeated 5x because a lost STOP is a motor left running.
        self._emit(encode(OP_STOP, self._next_seq(), self.room), repeat=5)

    def _worker(self) -> None:
        try:
            self._open_ok = bool(self.transport.open())
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._open_ok = False
        if not self._open_ok:
            err = getattr(self.transport, "last_error", None) or self._last_error or "unknown"
            self._say(f"buzzers: transport {self.transport.name} did not open ({err}). "
                      f"Sweep continues WITHOUT haptics.")
            self._armed = False
            return

        whisper_period = 1.0 / self.whisper_hz
        # While a beat is pending we restate it faster than the idle KEEP rate, so
        # the ball's hysteresis (§C.3) has repeated statements to reject jitter
        # between. One whisper per beat would make that mechanism dead code.
        pending_period = max(0.060, min(whisper_period, self.lookahead_ms / 3000.0))
        # Last useful whisper: it must arrive comfortably before the ball's fire_at
        # (= target - ERM_LEAD_MS), or it re-arms a beat that already played.
        whisper_floor_ms = self.link_latency_ms + ERM_LEAD_MS + HYSTERESIS_MS
        next_whisper = time.perf_counter()
        pending: Optional[tuple] = None      # (side, target_perf)
        stopped = True

        while not self._shutdown.is_set():
            now = time.perf_counter()

            # ---- explicit stop request (end of set, or close) --------------
            if self._stop_request.is_set():
                self._stop_request.clear()
                pending = None
                self._send_stop()
                stopped = True
                self._say("buzzers: STOP x5 sent")
                if self._shutdown.is_set():
                    break

            # ---- layer 2 dead-man: on_phase() stopped arriving --------------
            if self._armed and (now - self._last_phase_t) * 1000.0 > self.stale_ms:
                self._armed = False
                pending = None
                self._send_stop()
                stopped = True
                self._say(f"buzzers: no phase update for {self.stale_ms} ms - "
                          f"STOP x5 (client dead-man)")

            # ---- new taps from the UI thread --------------------------------
            got_new = False
            while True:
                try:
                    side, target, _k = self._taps.popleft()
                except IndexError:
                    break
                pending = (side, target)
                got_new = True
            if got_new and pending is not None:
                self._whisper(pending, now)
                stopped = False
                next_whisper = now + pending_period

            # ---- periodic whisper: restate the pending tap, or KEEP ---------
            if now >= next_whisper:
                if (pending is not None
                        and (pending[1] - now) * 1000.0 > whisper_floor_ms):
                    self._whisper(pending, now)
                    stopped = False
                    next_whisper = now + pending_period
                    self._wake.wait(max(0.002, next_whisper - time.perf_counter()))
                    self._wake.clear()
                    continue
                elif self._armed:
                    if pending is not None and (pending[1] - now) * 1000.0 <= whisper_floor_ms:
                        pending = None
                    self._emit(encode(OP_KEEP, self._next_seq(), self.room))
                    stopped = False
                elif not stopped:
                    # Not armed and nothing pending: let the balls dead-man on their own.
                    stopped = True
                next_whisper = now + whisper_period

            timeout = max(0.002, min(next_whisper - time.perf_counter(), whisper_period))
            self._wake.wait(timeout)
            self._wake.clear()

        # ---- shutdown ------------------------------------------------------
        try:
            self._send_stop()
        except Exception:
            pass
        try:
            self.transport.close()
        except Exception:
            pass
        self._say("buzzers: closed")

    def _whisper(self, pending: tuple, now: float) -> None:
        """One TAP frame stating when the person should FEEL the buzz.

        ``delay`` is recomputed at send time and the link's own latency is subtracted,
        because the ball computes ``target = now_at_receipt + delay`` (§C.3). Repeated
        whispers of the same beat land inside HYSTERESIS_MS and are treated by the ball
        as the same beat restated — that is what turns link jitter into an even rhythm.
        """
        side, target = pending
        delay_ms = int(round((target - now) * 1000.0 - self.link_latency_ms))
        if delay_ms < 0:
            delay_ms = 0
        if delay_ms > DELAY_MAX_MS:
            delay_ms = DELAY_MAX_MS
        frame = encode(OP_TAP, self._next_seq(), self.room, side,
                       self.intensity, self.pulse_ms, delay_ms)
        if self._emit(frame):
            self._stats["taps"] += 1

    # ------------------------------------------------------------------ misc
    def _say(self, msg: str) -> None:
        self.log.add("CLIENT", msg)
        if self.logger is not None:
            try:
                self.logger(msg)
            except Exception:
                pass

    def stats(self) -> dict:
        d = dict(self._stats)
        d.update({
            "transport": self.transport.describe(),
            "open": self._open_ok,
            "armed": self._armed,
            "last_error": self._last_error,
            "tested_against_hardware": self.transport.tested_against_hardware,
        })
        return d

    def __repr__(self) -> str:
        return (f"<BuzzerClient {self.transport.describe()} room={self.room} "
                f"armed={self._armed} sent={self._stats['frames_sent']}>")


# =============================================================================
# CLI — the proof
# =============================================================================

def _drive_sweep(client: "BuzzerClient", secs: float, hz: float, seed: int,
                 fps: int = 60, screen_w: int = 1920, amplitude_pct: int = 95):
    """Drive the client exactly the way emdr_widget.EmdrSequence._tick does.

    Reproduces the widget's virtual clock (``_elapsed_ms += int(1000/FPS)`` = 16 ms,
    NOT 16.667) and its ``_amp_jitter = rng.uniform(-0.02, 0.02)``, so the log shows
    what would really happen in the widget. Returns (true_edges, jitter, widget_beeps).

    ``true_edges`` are wall-clock instants, interpolated between the two frames that
    straddle each phase crossing — i.e. the moment the ORB was actually at the edge.
    That is the ground truth the buzz is measured against.
    """
    import random as _random
    rng = _random.Random(seed)
    jitter = rng.uniform(-0.02, 0.02)

    frame_ms = int(1000 / fps)
    period_ms = int(1000 / hz)

    edge_margin = 80
    used = int((screen_w - 2 * edge_margin) * amplitude_pct / 100.0)
    center = screen_w // 2
    x_min = center - used // 2
    x_max = center + used // 2
    mid = (x_min + x_max) / 2.0
    base_amp = (x_max - x_min) / 2.0
    amp = base_amp * (1.0 + jitter)

    true_edges = []          # (k, wall_time, side)
    widget_beeps = []        # what the widget's own 6-px edge test would do
    last_side = None

    elapsed_ms = 0
    prev_phase = 0.0
    prev_wall = time.perf_counter()
    t_start = prev_wall
    n_ticks = int(secs * fps)

    for i in range(n_ticks):
        # sleep to the next frame boundary, like a 60 Hz QTimer
        target_wall = t_start + (i + 1) * (frame_ms / 1000.0)
        dt = target_wall - time.perf_counter()
        if dt > 0:
            time.sleep(dt)
        wall = time.perf_counter()

        elapsed_ms += frame_ms
        t = elapsed_ms / 1000.0
        phase = TWO_PI * t * 1000.0 / period_ms
        orb_x = mid + amp * math.sin(phase)

        # ground truth: interpolate the wall instant of every pi/2+k*pi crossing
        k_prev = int(math.floor((prev_phase - HALF_PI) / math.pi)) + 1
        k_now = int(math.floor((phase - HALF_PI) / math.pi)) + 1
        for k in range(k_prev + 1, k_now + 1):
            phi = HALF_PI + (k - 1) * math.pi
            frac = (phi - prev_phase) / (phase - prev_phase) if phase > prev_phase else 0.0
            true_edges.append((k, prev_wall + frac * (wall - prev_wall),
                               "R" if (k % 2) else "L"))

        # what the widget's own pixel-band edge test does with this seed
        if orb_x <= x_min + 6.0:
            if last_side != "L":
                last_side = "L"
                widget_beeps.append((wall, "L"))
        elif orb_x >= x_max - 6.0:
            if last_side != "R":
                last_side = "R"
                widget_beeps.append((wall, "R"))
        elif abs(orb_x - mid) < base_amp * 0.3:
            last_side = None

        # THE HOOK — one call, exactly what the integration patch adds
        client.on_phase(phase, hz)

        prev_phase = phase
        prev_wall = wall

    return true_edges, jitter, widget_beeps


def cmd_sweep(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="buzzers_ble.py sweep")
    ap.add_argument("--secs", type=float, default=8.0)
    ap.add_argument("--hz", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--lookahead", type=int, default=250)
    ap.add_argument("--link-latency", type=float, default=0.0)
    ap.add_argument("--air-latency", type=float, default=0.0,
                    help="simulated one-way link latency in ms (BLE ~15 base)")
    ap.add_argument("--air-jitter", type=float, default=0.0,
                    help="simulated link jitter in ms (BLE connection interval ~30-50)")
    ap.add_argument("--loss", type=float, default=0.0,
                    help="simulated packet loss %% (unacknowledged broadcast)")
    ap.add_argument("--quiet", action="store_true", help="do not echo packets live")
    args = ap.parse_args(argv)

    log = PacketLog(capacity=20000)
    tr = LoopbackTransport(log=log, room=1, air_latency_ms=args.air_latency,
                           air_jitter_ms=args.air_jitter, loss_pct=args.loss)
    pulse = recommended_pulse_ms(args.hz)
    client = BuzzerClient(transport=tr, room=1, intensity=200, pulse_ms=pulse,
                          lookahead_ms=args.lookahead,
                          link_latency_ms=args.link_latency, log=log)

    print("=" * 78)
    print("ALMA-EMDR buzzer client - FULL SWEEP THROUGH THE SIMULATOR")
    print("=" * 78)
    print(f"  sweep      {args.hz} Hz, {args.secs} s, seed {args.seed}, "
          f"screen {args.width}px, 60 Hz virtual clock (16 ms/tick, as the widget)")
    print(f"  pulse      {pulse} ms  (rule 150 <= dur <= min(400, 250/hz); "
          f"haptics distinct at this rate: {haptics_distinct(args.hz)})")
    print(f"  lookahead  {args.lookahead} ms   link lead assumed {args.link_latency} ms   "
          f"simulated air {args.air_latency}+U(0,{args.air_jitter}) ms   loss {args.loss}%")
    print(f"  transport  {tr.describe()}   triple-send={client.repeat}  "
          f"whisper={client.whisper_hz} Hz")
    print()

    log.reset_clock()
    client.start()
    time.sleep(0.05)
    true_edges, jitter, widget_beeps = _drive_sweep(
        client, args.secs, args.hz, args.seed, screen_w=args.width)
    client.stop()
    time.sleep(0.35)          # let STOP x5 and the last MOTOR_OFF land
    client.close(wait_ms=1500)
    time.sleep(0.05)

    print("-" * 78)
    print("PACKET LOG  (t = ms since the client started; every frame, every ball event)")
    print("-" * 78)
    if not args.quiet:
        print(log.render())
    print()

    # ---- the measurement -------------------------------------------------
    print("-" * 78)
    print("SYNCHRONISATION - simulated felt-onset vs the true orb-at-edge instant")
    print("-" * 78)
    ball_by_side = {SIDE_NAMES[b.side]: b for b in tr.balls}
    rows = []
    for k, t_edge, side in true_edges:
        b = ball_by_side.get(side)
        if b is None:
            continue
        best = None
        for f in b.fires:
            d = (f["felt_at"] - t_edge) * 1000.0
            if best is None or abs(d) < abs(best[0]):
                best = (d, f)
        if best is not None and abs(best[0]) < 400.0:
            rows.append((k, side, (t_edge - log.t0) * 1000.0, best[0], best[1]))
        else:
            rows.append((k, side, (t_edge - log.t0) * 1000.0, None, None))

    print(f"  {'edge':>4}  {'side':>4}  {'orb at edge':>12}  {'felt onset err':>15}  motor")
    for k, side, t_rel, err, f in rows:
        if err is None:
            print(f"  {k:>4}  {side:>4}  {t_rel:>10.1f} ms  {'MISSED':>15}")
        else:
            print(f"  {k:>4}  {side:>4}  {t_rel:>10.1f} ms  {err:>+12.1f} ms   "
                  f"PWM {f['intensity']} for {f['dur_ms']} ms")

    errs = [abs(r[3]) for r in rows if r[3] is not None]
    missed = sum(1 for r in rows if r[3] is None)
    print()
    if errs:
        errs_sorted = sorted(errs)
        print(f"  edges: {len(rows)}   fired: {len(errs)}   missed: {missed}")
        print(f"  |error|  mean {sum(errs) / len(errs):.1f} ms   "
              f"p50 {errs_sorted[len(errs_sorted) // 2]:.1f} ms   "
              f"max {errs_sorted[-1]:.1f} ms")
        hard = 80.0     # hand<->eye hard limit, PROTOCOL D.1
        target = 50.0
        print(f"  PROTOCOL D.1 hand<->eye: target +/-{target:.0f} ms, hard +/-{hard:.0f} ms "
              f"-> {'PASS' if max(errs) <= hard else 'FAIL'} "
              f"({sum(1 for e in errs if e <= target)}/{len(errs)} within target)")
    else:
        print("  NO TAPS FIRED - this is a failure.")

    # ---- the §D.4 point --------------------------------------------------
    print()
    print("-" * 78)
    print("PROTOCOL D.4 - why this does not use the orb's pixel position")
    print("-" * 78)
    print(f"  seed {args.seed} -> _amp_jitter = {jitter:+.5f}")
    print(f"  the widget's own 6-px edge test fired {len(widget_beeps)} time(s) "
          f"in this sweep")
    print(f"  this phase-crossing client fired  {len(errs)} time(s)")
    if len(widget_beeps) == 0 and errs:
        print("  ==> the widget's beep is SILENT for this seed; the buzzers still work.")
        print("      That is the whole reason for the phase-crossing rule.")

    # ---- protocol machinery actually exercised ---------------------------
    print()
    print("-" * 78)
    print("PROTOCOL MACHINERY EXERCISED (counted in the simulated balls)")
    print("-" * 78)
    for b in tr.balls:
        c = b.counters
        print(f"  {b.label:<8} ARM {c['ARM']:<4} MOTOR_ON {c['MOTOR_ON']:<4} "
              f"MOTOR_OFF {c['MOTOR_OFF']:<4} DUP_DROP {c['DUP_DROP']:<4} "
              f"RESTATE {c['RESTATE']:<4} REFUSE_DUTY {c['REFUSE_DUTY']:<3} "
              f"DEADMAN {c['DEADMAN']:<3} STOP_RX {c['STOP_RX']}")
    print(f"  client stats: {client.stats()}")
    print(f"  simulated link: {tr.frames_lost} frame(s) lost of {tr.frames_seen} sent")
    res = tr.pump_resolution_ms
    print(f"  simulated-MCU pump loop: n={res['n']} p50={res['p50']:.2f} ms "
          f"p99={res['p99']:.2f} ms max={res['max']:.2f} ms "
          f"(this is the log's timing floor)")
    print()
    print("  ALL TIMINGS ABOVE ARE SIMULATOR TIMINGS. NO HARDWARE EXISTS.")
    print("  UNTESTED AGAINST REAL HARDWARE: SerialTransport, BleTransport, "
          "any real ERM motor.")
    return 0 if (errs and missed == 0 and max(errs) <= 80.0) else 1


def cmd_deadman(argv: list) -> int:
    """Prove the dead-man rule: stop whispering, the ball stops itself."""
    print("=" * 78)
    print("DEAD-MAN PROOF - PROTOCOL D.5 layer 1")
    print("=" * 78)
    log = PacketLog(capacity=4000)
    tr = LoopbackTransport(log=log, room=1)
    client = BuzzerClient(transport=tr, room=1, intensity=200, pulse_ms=160, log=log)
    log.reset_clock()
    client.start()
    time.sleep(0.05)

    print("  1. arm a tap 200 ms out, then simulate the UI thread dying "
          "(stop calling on_phase, never call stop())")
    client.tap_now("L", delay_ms=200)
    time.sleep(0.6)
    print(f"     ball-L motor fired: {tr.balls[0].counters['MOTOR_ON']} time(s)")

    print(f"  2. the client's own layer-2 dead-man should fire after "
          f"{client.stale_ms} ms of no on_phase()...")
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 3.2:
        time.sleep(0.05)

    stops = tr.balls[0].counters["STOP_RX"]
    dm = tr.balls[0].counters["DEADMAN"] + tr.balls[1].counters["DEADMAN"]
    print()
    print(log.render())
    print()
    print(f"  STOP received by ball-L: {stops}   firmware DEADMAN trips: {dm}")
    ok = stops >= 1
    print(f"  RESULT: {'PASS' if ok else 'FAIL'} - the ball is stopped without the app "
          f"asking it to be.")
    client.close(wait_ms=1000)
    return 0 if ok else 1


def cmd_ports(argv: list) -> int:
    print("Serial ports visible to pyserial (read-only, nothing was opened):")
    for dev, desc in SerialTransport.list_ports():
        print(f"  {dev:<10} {desc}")
    guess = SerialTransport.autodetect()
    print(f"\n  autodetect guess: {guess or '(none)'}")
    print("  NOTE: no buzzer box exists yet. SerialTransport is UNTESTED against hardware.")
    return 0


def cmd_scan(argv: list) -> int:
    try:
        import bleak  # noqa: F401  # type: ignore
    except Exception as exc:
        print(f"bleak is NOT installed on this machine ({exc}).")
        print("Phase 2 needs:  pip install bleak")
        print("BleTransport is written but has never run. UNTESTED AGAINST HARDWARE.")
        return 2
    import asyncio
    from bleak import BleakScanner  # type: ignore

    async def _scan():
        print(f"Scanning 8 s for service {BLE_SERVICE_UUID} ...")
        devs = await BleakScanner.discover(timeout=8.0)
        for d in devs:
            mark = "  <== EMDR" if (d.name or "").startswith(BLE_NAME_PREFIX) else ""
            print(f"  {d.address}  {d.name or '(no name)'}{mark}")
    asyncio.run(_scan())
    return 0


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "vectors"
    rest = argv[1:]
    if cmd in ("vectors", "verify"):
        print("PROTOCOL-buzzers-20260901.md  §C.7 test vectors")
        ok = verify_test_vectors()
        print(f"\n  {'ALL VECTORS PASS' if ok else 'FAILURES PRESENT'}")
        return 0 if ok else 1
    if cmd == "sweep":
        return cmd_sweep(rest)
    if cmd == "deadman":
        return cmd_deadman(rest)
    if cmd == "ports":
        return cmd_ports(rest)
    if cmd == "scan":
        return cmd_scan(rest)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())

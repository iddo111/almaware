# ALMA Optical Perceptron Mark-II Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A 4-input+bias perceptron whose weights live in photochromic film, trained by dosed 405 nm light, per the approved spec `docs/specs/2026-08-08-alma-optical-perceptron-design.md`.

**Architecture:** Pure-logic modules (`perceptron.py`, `calibration.py`) run identically under desktop pytest and MicroPython on the ESP32; a thin `hal.py` owns pins; `main.py` is a serial-driven state machine; `bench/bench.py` on the PC drives the T1–T7 protocols and logs `session.jsonl`. Housing is parametric OpenSCAD printed on the K2 Plus.

**Tech Stack:** MicroPython 1.22+ (ESP32), Python 3.12 + pytest on PC, OpenSCAD, `mpremote` for deploy.

## Global Constraints

- All firmware modules MUST run unmodified under both CPython 3.12 and MicroPython (stdlib subset only: no typing at runtime beyond comments, no dataclasses, no f-string `=`).
- Spec §3 electrical resolution (BOM addendum, approved by this plan): LDR readout via **1× CD74HC4067** 16-ch analog mux into one ADC1 pin; violet LED drive via **2× 74HC595** shift registers into **2× ULN2803**. Green LEDs on direct GPIO.
- Patch/channel indexing everywhere: synapses `0..4` (4 = bias), patch id = `synapse*2 + polarity` where polarity `0=E`, `1=I` → patches `0..9`.
- Chopped read (spec §3.4): every read = LED-on sample minus LED-off sample.
- Exposure dosing (spec §3.3): time-based, `quanta × Q_MS` milliseconds full-on; `Q_MS` from calibration.
- Lid interlock (spec §6): violet fire refuses when lid switch open.
- Every commit in repo `D:\CLAUDE\alma-optical-perceptron`, message prefix `feat:`/`test:`/`cad:`/`bench:`.
- Physical tasks (8–13) are checklists with measured pass criteria from spec §5; do not mark complete without the measurement.

## File Structure

```
firmware/config.py        pin map + constants (single source of truth)
firmware/perceptron.py    pure: weights from transmissions, activation, train step → dose plan
firmware/calibration.py   pure: dose-response tables, quanta planning, ≥5-level check
firmware/hal.py           device-only: mux ADC, shift-register violet, chopped read, interlock
firmware/main.py          state machine over serial JSON-lines (mockable HAL injected)
tests/test_perceptron.py  host pytest
tests/test_calibration.py host pytest
tests/test_main_sm.py     host pytest with FakeHal
bench/bench.py            PC serial runner for T1–T7 → session.jsonl
bench/analysis.py         pure: σ, crosstalk %, decay fit
bench/test_analysis.py    host pytest
hardware/housing.scad     5×2 light-tight cell array, slots, pockets
hardware/wiring.md        exact pin↔part table (generated from config.py values)
```

---

### Task 1: Repo scaffolding + config

**Files:**
- Create: `firmware/config.py`, `pytest.ini`
- Test: (none — configuration only, folded into Task 2's cycle)

**Interfaces:**
- Produces: `config.PINS` dict, `config.N_SYN = 5`, `config.N_PATCH = 10`, `config.Q_MS_DEFAULT = 40`, `config.ADC_SETTLE_MS = 5`, patch-id convention constants `POL_E = 0`, `POL_I = 1`.

- [ ] **Step 1: Write config.py**

```python
# firmware/config.py — single source of truth for wiring + constants.
N_SYN = 5           # 4 inputs + bias (synapse 4)
N_PATCH = 10        # patch id = syn*2 + pol ; pol 0=E, 1=I
POL_E = 0
POL_I = 1
Q_MS_DEFAULT = 40   # default exposure quantum, ms (T1 recalibrates)
ADC_SETTLE_MS = 5   # mux settle before sample
READ_AVG = 8        # samples averaged per chopped half-read

PINS = {
    "green": [25, 26, 27, 14, 12],      # synapse 0..4 input LEDs
    "mux_sel": [4, 16, 17, 5],          # HC4067 S0..S3
    "mux_adc": 34,                      # ADC1 input-only pin
    "sr_data": 23, "sr_clock": 18, "sr_latch": 19,  # 74HC595 chain -> ULN2803
    "lid": 32,                          # lid switch, closed = LOW
}
# HC4067 channel wired per patch id 0..9 (channels 10-15 unused, grounded)
MUX_CH_FOR_PATCH = list(range(N_PATCH))
# 74HC595 output bit per patch id 0..9 (bits 10-15 unused)
SR_BIT_FOR_PATCH = list(range(N_PATCH))
```

- [ ] **Step 2: Write pytest.ini**

```ini
[pytest]
testpaths = tests bench
pythonpath = firmware bench
```

- [ ] **Step 3: Commit**

```bash
git add firmware/config.py pytest.ini
git commit -m "feat: config pin map and constants"
```

### Task 2: Pure perceptron core

**Files:**
- Create: `firmware/perceptron.py`
- Test: `tests/test_perceptron.py`

**Interfaces:**
- Consumes: `config.N_SYN`, `POL_E/POL_I`.
- Produces:
  - `weights_from_transmissions(trans) -> list[float]` — `trans` is list of 10 floats 0..1; returns 5 weights `T(E)-T(I)`.
  - `activation(weights, x) -> float` — x is list of 5 ints 0/1 (x[4] must be 1 = bias).
  - `predict(weights, x) -> int` — step at 0.
  - `train_step(weights, x, y) -> list[tuple[int, int]]` — returns dose plan `[(patch_id, quanta)]`; empty when correct. Rule per spec §3.6: err<0 → dose E-patch of each active input; err>0 → dose I-patch. quanta=1 each.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_perceptron.py
from perceptron import weights_from_transmissions, activation, predict, train_step

def T(e_i_pairs):  # helper: [(Te,Ti)x5] -> flat 10-list
    out = []
    for e, i in e_i_pairs:
        out += [e, i]
    return out

def test_weights_are_transmission_differences():
    trans = T([(0.9, 0.1), (0.5, 0.5), (0.2, 0.8), (1.0, 0.0), (0.6, 0.4)])
    w = weights_from_transmissions(trans)
    assert w == [0.8, 0.0, -0.6, 1.0, 0.2] or all(abs(a-b) < 1e-9 for a, b in zip(w, [0.8, 0.0, -0.6, 1.0, 0.2]))

def test_predict_fires_on_positive_sum():
    w = [0.5, 0.5, 0.0, 0.0, -0.4]      # bias weight negative
    assert predict(w, [1, 1, 0, 0, 1]) == 1
    assert predict(w, [1, 0, 0, 0, 1]) == 1
    assert predict(w, [0, 0, 0, 0, 1]) == 0

def test_train_step_correct_prediction_no_doses():
    w = [1.0, 0.0, 0.0, 0.0, -0.5]
    assert train_step(w, [1, 0, 0, 0, 1], 1) == []

def test_train_step_false_fire_doses_E_of_active_inputs():
    w = [1.0, 1.0, 0.0, 0.0, 0.0]
    plan = train_step(w, [1, 1, 0, 0, 1], 0)   # fires, should not
    assert plan == [(0, 1), (2, 1), (8, 1)]     # E patches of syn 0,1,4

def test_train_step_missed_fire_doses_I_of_active_inputs():
    w = [-1.0, 0.0, 0.0, 0.0, -1.0]
    plan = train_step(w, [1, 0, 0, 0, 1], 1)   # silent, should fire
    assert plan == [(1, 1), (9, 1)]             # I patches of syn 0,4
```

- [ ] **Step 2: Run tests, verify all fail** — `pytest tests/test_perceptron.py -v` → ImportError.

- [ ] **Step 3: Implement**

```python
# firmware/perceptron.py — pure logic, CPython + MicroPython compatible.
import config

def weights_from_transmissions(trans):
    return [trans[s * 2] - trans[s * 2 + 1] for s in range(config.N_SYN)]

def activation(weights, x):
    total = 0.0
    for i in range(config.N_SYN):
        total += weights[i] * x[i]
    return total

def predict(weights, x):
    return 1 if activation(weights, x) > 0 else 0

def train_step(weights, x, y):
    err = y - predict(weights, x)
    if err == 0:
        return []
    pol = config.POL_E if err < 0 else config.POL_I
    return [(i * 2 + pol, 1) for i in range(config.N_SYN) if x[i]]
```

- [ ] **Step 4: Run tests, verify pass** — `pytest tests/test_perceptron.py -v`.

- [ ] **Step 5: Commit** — `git add firmware/perceptron.py tests/test_perceptron.py && git commit -m "feat: pure perceptron core with dose-plan training"`

### Task 3: Calibration module

**Files:**
- Create: `firmware/calibration.py`
- Test: `tests/test_calibration.py`

**Interfaces:**
- Produces:
  - `DoseTable(points)` — `points` = list of `(cumulative_quanta, transmission)` tuples, monotonically decreasing transmission.
  - `.levels(n=5, floor=0.15) -> list[float]` — n target transmissions evenly spaced between max and `floor`; raises `ValueError` if table span can't produce n distinguishable levels (min gap 0.03).
  - `.quanta_to(target, current) -> int` — additional quanta to move from `current` transmission down to `target` (linear interpolation on the table; 0 if target ≥ current).
  - `check_five_levels(points) -> bool` — spec S1 gate.

- [ ] **Step 1: Failing tests**

```python
# tests/test_calibration.py
import pytest
from calibration import DoseTable, check_five_levels

POINTS = [(0, 1.00), (5, 0.85), (10, 0.68), (20, 0.45), (40, 0.22)]

def test_levels_spread_between_max_and_floor():
    t = DoseTable(POINTS)
    lv = t.levels(5, floor=0.20)
    assert len(lv) == 5 and abs(lv[0] - 1.00) < 1e-9 and abs(lv[-1] - 0.20) < 1e-9
    gaps = [lv[i] - lv[i+1] for i in range(4)]
    assert all(g >= 0.03 for g in gaps)

def test_quanta_to_interpolates():
    t = DoseTable(POINTS)
    assert t.quanta_to(0.85, 1.00) == 5
    assert t.quanta_to(0.565, 0.85) == 10   # halfway 0.68->0.45 => 15 total, minus 5 spent
    assert t.quanta_to(0.9, 0.5) == 0        # can't brighten

def test_five_levels_gate_rejects_flat_film():
    assert check_five_levels(POINTS) is True
    assert check_five_levels([(0, 1.0), (40, 0.95)]) is False
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_calibration.py -v`.

- [ ] **Step 3: Implement**

```python
# firmware/calibration.py — dose-response tables. Pure; MicroPython-safe.
class DoseTable:
    def __init__(self, points):
        self.points = sorted(points)          # (quanta, transmission), trans decreasing

    def _trans_to_quanta(self, trans):
        pts = self.points
        if trans >= pts[0][1]:
            return pts[0][0]
        for i in range(1, len(pts)):
            q0, t0 = pts[i - 1]
            q1, t1 = pts[i]
            if trans >= t1:
                return q0 + (t0 - trans) * (q1 - q0) / (t0 - t1)
        return pts[-1][0]

    def levels(self, n=5, floor=0.15):
        top = self.points[0][1]
        bottom = max(floor, self.points[-1][1])
        step = (top - bottom) / (n - 1)
        if step < 0.03:
            raise ValueError("film span too small for %d levels" % n)
        return [top - step * i for i in range(n)]

    def quanta_to(self, target, current):
        if target >= current:
            return 0
        extra = self._trans_to_quanta(target) - self._trans_to_quanta(current)
        return int(round(extra)) if extra > 0 else 0

def check_five_levels(points):
    try:
        DoseTable(points).levels(5, floor=points[-1][1])
        return True
    except ValueError:
        return False
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat: calibration dose tables and S1 gate"`

### Task 4: Bench analysis functions

**Files:**
- Create: `bench/analysis.py`
- Test: `bench/test_analysis.py`

**Interfaces:**
- Produces: `repeatability_sigma(reads) -> float` (σ as fraction of mean); `crosstalk_pct(lit, others_delta) -> float` (max |other delta| / lit signal × 100); `decay_tau_minutes(samples) -> float` — samples `[(minutes, weight_span)]`, log-linear least-squares fit of `span = A·exp(-t/τ)`.

- [ ] **Step 1: Failing tests**

```python
# bench/test_analysis.py
import math
from analysis import repeatability_sigma, crosstalk_pct, decay_tau_minutes

def test_sigma_fraction_of_mean():
    assert abs(repeatability_sigma([10.0, 10.0, 10.0]) - 0.0) < 1e-9
    s = repeatability_sigma([9.0, 10.0, 11.0])
    assert 0.08 < s < 0.09

def test_crosstalk_is_worst_case_percentage():
    assert crosstalk_pct(1000.0, [5.0, -12.0, 3.0]) == 1.2

def test_decay_tau_recovers_synthetic_exponential():
    tau = 42.0
    samples = [(t, 0.8 * math.exp(-t / tau)) for t in (0, 10, 20, 40, 60)]
    assert abs(decay_tau_minutes(samples) - tau) < 1.0
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement**

```python
# bench/analysis.py
import math

def repeatability_sigma(reads):
    n = len(reads)
    mean = sum(reads) / n
    var = sum((r - mean) ** 2 for r in reads) / n
    return math.sqrt(var) / mean if mean else 0.0

def crosstalk_pct(lit, others_delta):
    return max(abs(d) for d in others_delta) / lit * 100.0

def decay_tau_minutes(samples):
    pts = [(t, math.log(s)) for t, s in samples if s > 0]
    n = len(pts)
    sx = sum(t for t, _ in pts); sy = sum(y for _, y in pts)
    sxx = sum(t * t for t, _ in pts); sxy = sum(t * y for t, y in pts)
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return -1.0 / slope
```

- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** — `git commit -am "bench: analysis functions for T1/T2/T3/T6"`

### Task 5: Main state machine with injectable HAL

**Files:**
- Create: `firmware/main.py`
- Test: `tests/test_main_sm.py`

**Interfaces:**
- Consumes: `perceptron.*`, `calibration.DoseTable`, a `hal` object with: `read_patch_chopped(syn) -> (e_raw, i_raw)` for its synapse's two patches normalized 0..1, `read_all() -> list[10 floats]`, `fire(patch_id, quanta) -> bool` (False = interlock refused), `lid_closed() -> bool`.
- Produces: `Machine(hal)` with `.handle(cmd: dict) -> dict` — serial JSON-lines commands:
  - `{"op":"read"}` → `{"ok":1,"trans":[10 floats],"weights":[5]}`
  - `{"op":"predict","x":[...4 ints]}` → `{"ok":1,"y":0|1,"act":float}` (bias appended internally)
  - `{"op":"train","x":[...4],"y":0|1}` → `{"ok":1,"err":int,"doses":[[patch,quanta]...],"fired":int}`
  - `{"op":"dose","patch":int,"quanta":int}` → `{"ok":1}` or `{"ok":0,"why":"lid"}`
  - Unknown op → `{"ok":0,"why":"badop"}`

- [ ] **Step 1: Failing tests**

```python
# tests/test_main_sm.py
from main import Machine

class FakeHal:
    def __init__(self, trans):
        self.trans = trans[:]      # 10 floats
        self.fired = []
        self.lid = True
    def read_all(self):
        return self.trans[:]
    def fire(self, patch, quanta):
        if not self.lid:
            return False
        self.fired.append((patch, quanta))
        self.trans[patch] = max(0.0, self.trans[patch] - 0.05 * quanta)
        return True
    def lid_closed(self):
        return self.lid

def flat(e, i):
    return [e, i] * 5

def test_read_reports_weights():
    m = Machine(FakeHal(flat(0.9, 0.1)))
    r = m.handle({"op": "read"})
    assert r["ok"] == 1 and len(r["trans"]) == 10
    assert all(abs(w - 0.8) < 1e-9 for w in r["weights"])

def test_train_applies_doses_to_hal():
    hal = FakeHal(flat(0.9, 0.1))          # all weights strongly positive -> always fires
    m = Machine(hal)
    r = m.handle({"op": "train", "x": [1, 0, 0, 0], "y": 0})
    assert r["ok"] == 1 and r["err"] == -1
    assert hal.fired == [(0, 1), (8, 1)]    # E of syn0 + E of bias
    assert r["fired"] == 2

def test_lid_open_refuses_dose():
    hal = FakeHal(flat(0.5, 0.5)); hal.lid = False
    m = Machine(hal)
    r = m.handle({"op": "dose", "patch": 3, "quanta": 2})
    assert r == {"ok": 0, "why": "lid"}
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement**

```python
# firmware/main.py — serial JSON-lines state machine. Runs on device via run();
# Machine class is host-testable with any HAL object.
import sys, json
import config, perceptron

class Machine:
    def __init__(self, hal):
        self.hal = hal

    def handle(self, cmd):
        op = cmd.get("op")
        if op == "read":
            trans = self.hal.read_all()
            return {"ok": 1, "trans": trans,
                    "weights": perceptron.weights_from_transmissions(trans)}
        if op == "predict":
            x = list(cmd["x"]) + [1]
            w = perceptron.weights_from_transmissions(self.hal.read_all())
            return {"ok": 1, "y": perceptron.predict(w, x),
                    "act": perceptron.activation(w, x)}
        if op == "train":
            x = list(cmd["x"]) + [1]
            w = perceptron.weights_from_transmissions(self.hal.read_all())
            err = cmd["y"] - perceptron.predict(w, x)
            plan = perceptron.train_step(w, x, cmd["y"])
            fired = 0
            for patch, quanta in plan:
                if self.hal.fire(patch, quanta):
                    fired += 1
                else:
                    return {"ok": 0, "why": "lid"}
            return {"ok": 1, "err": err,
                    "doses": [list(p) for p in plan], "fired": fired}
        if op == "dose":
            if self.hal.fire(cmd["patch"], cmd["quanta"]):
                return {"ok": 1}
            return {"ok": 0, "why": "lid"}
        return {"ok": 0, "why": "badop"}

def run():                                   # device entry point
    import hal as real_hal
    m = Machine(real_hal.Hal())
    while True:
        line = sys.stdin.readline()
        if not line:
            continue
        try:
            out = m.handle(json.loads(line))
        except (ValueError, KeyError):
            out = {"ok": 0, "why": "badjson"}
        print(json.dumps(out))

if __name__ == "__main__" and sys.platform not in ("win32", "linux", "darwin"):
    run()
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/test_main_sm.py -v`.
- [ ] **Step 5: Commit** — `git commit -am "feat: serial state machine with injectable HAL"`

### Task 6: Device HAL

**Files:**
- Create: `firmware/hal.py`

**Interfaces:**
- Consumes: `config.PINS`, `MUX_CH_FOR_PATCH`, `SR_BIT_FOR_PATCH`, `Q_MS_DEFAULT`, `READ_AVG`, `ADC_SETTLE_MS`.
- Produces: `Hal` class implementing exactly the FakeHal surface from Task 5: `read_all()`, `fire(patch, quanta)`, `lid_closed()`. Chopped read per Global Constraints. Normalization: raw ADC with green ON minus OFF, divided by per-patch `open_max` stored in `caldata.json` on device flash (fallback 4095).

- [ ] **Step 1: Implement (no host test possible — device review checklist replaces it)**

```python
# firmware/hal.py — ESP32 only. All pin knowledge lives here + config.
import time, json
from machine import Pin, ADC
import config

class Hal:
    def __init__(self):
        p = config.PINS
        self.green = [Pin(n, Pin.OUT, value=0) for n in p["green"]]
        self.sel = [Pin(n, Pin.OUT, value=0) for n in p["mux_sel"]]
        self.adc = ADC(Pin(p["mux_adc"]))
        self.adc.atten(ADC.ATTN_11DB)
        self.sr_d = Pin(p["sr_data"], Pin.OUT, 0)
        self.sr_c = Pin(p["sr_clock"], Pin.OUT, 0)
        self.sr_l = Pin(p["sr_latch"], Pin.OUT, 0)
        self.lid = Pin(p["lid"], Pin.IN, Pin.PULL_UP)
        try:
            self.open_max = json.load(open("caldata.json"))["open_max"]
        except (OSError, ValueError, KeyError):
            self.open_max = [4095.0] * config.N_PATCH
        self._sr_write(0)

    def lid_closed(self):
        return self.lid.value() == 0

    def _sr_write(self, bits):
        self.sr_l.value(0)
        for i in range(15, -1, -1):
            self.sr_c.value(0)
            self.sr_d.value((bits >> i) & 1)
            self.sr_c.value(1)
        self.sr_c.value(0)
        self.sr_l.value(1)
        self.sr_l.value(0)

    def _mux(self, ch):
        for b, pin in enumerate(self.sel):
            pin.value((ch >> b) & 1)
        time.sleep_ms(config.ADC_SETTLE_MS)

    def _sample(self):
        return sum(self.adc.read() for _ in range(config.READ_AVG)) / config.READ_AVG

    def _read_patch_raw(self, patch):
        syn = patch // 2
        self._mux(config.MUX_CH_FOR_PATCH[patch])
        self.green[syn].value(1)
        time.sleep_ms(config.ADC_SETTLE_MS)
        on = self._sample()
        self.green[syn].value(0)
        time.sleep_ms(config.ADC_SETTLE_MS)
        off = self._sample()
        return max(0.0, on - off)

    def read_all(self):
        return [min(1.0, self._read_patch_raw(p) / self.open_max[p])
                for p in range(config.N_PATCH)]

    def fire(self, patch, quanta):
        if not self.lid_closed():
            return False
        self._sr_write(1 << config.SR_BIT_FOR_PATCH[patch])
        time.sleep_ms(config.Q_MS_DEFAULT * quanta)
        self._sr_write(0)
        return True
```

- [ ] **Step 2: Static check both interpreters** — `python -c "import ast; ast.parse(open('firmware/hal.py').read())"` and `mpremote run firmware/hal.py` expecting only ImportError-free load on device (bench Task 8 exercises it live).
- [ ] **Step 3: Commit** — `git commit -am "feat: ESP32 HAL - mux reads, shift-register violet, interlock"`

### Task 7: Bench runner

**Files:**
- Create: `bench/bench.py`
- Test: extend `bench/test_analysis.py` (protocol framing tests with a fake serial)

**Interfaces:**
- Consumes: Machine protocol ops from Task 5; `analysis.*`.
- Produces: CLI `python bench/bench.py --port COMx t1|t2|t3|t4|t5|t6` running the spec §5 protocols; every exchange appended to `bench/session.jsonl` as `{"ts","sent","got"}`. `send(ser, obj) -> dict` is the framing function under test.

- [ ] **Step 1: Failing test for framing**

```python
# append to bench/test_analysis.py
from bench import send

class FakeSer:
    def __init__(self, reply):
        self.reply = reply; self.wrote = b""
    def write(self, b):
        self.wrote += b
    def readline(self):
        return self.reply

def test_send_writes_jsonl_and_parses_reply():
    fs = FakeSer(b'{"ok": 1, "y": 1}\n')
    out = send(fs, {"op": "predict", "x": [1, 0, 0, 0]})
    assert fs.wrote.endswith(b"\n") and out == {"ok": 1, "y": 1}
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement bench.py**

```python
# bench/bench.py — PC-side protocol runner for T1-T7. Requires pyserial.
import sys, json, time, itertools
from analysis import repeatability_sigma, crosstalk_pct, decay_tau_minutes

LOG = __file__.replace("bench.py", "session.jsonl")

def send(ser, obj):
    ser.write((json.dumps(obj) + "\n").encode())
    got = json.loads(ser.readline().decode())
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "sent": obj, "got": got}) + "\n")
    return got

def patterns4():
    return [list(p) for p in itertools.product([0, 1], repeat=4)]

def t1(ser, patch):                       # dose-response for one patch
    points = []
    total = 0
    for step in [0, 5, 5, 10, 20]:
        if step:
            send(ser, {"op": "dose", "patch": patch, "quanta": step})
            total += step
        tr = send(ser, {"op": "read"})["trans"][patch]
        points.append((total, tr))
        print("dose", total, "->", round(tr, 3))
    print("T1 points:", points)

def t2(ser, patch):
    reads = [send(ser, {"op": "read"})["trans"][patch] for _ in range(100)]
    print("T2 sigma:", repeatability_sigma(reads), "(pass < 0.015)")

def t4(ser, truth):                       # truth: dict pattern-tuple -> y
    for epoch in range(50):
        wrong = 0
        for x in patterns4():
            r = send(ser, {"op": "train", "x": x, "y": truth[tuple(x)]})
            wrong += 1 if r["err"] else 0
        print("epoch", epoch, "wrong:", wrong)
        if wrong == 0:
            print("LEARNED in", epoch + 1, "epochs"); return
    print("FAILED to converge in 50 epochs")

AND = {p: int(all(p)) for p in itertools.product([0, 1], repeat=4)}
OR = {p: int(any(p)) for p in itertools.product([0, 1], repeat=4)}

def main():
    import serial
    port = sys.argv[sys.argv.index("--port") + 1]
    proto = sys.argv[-1]
    ser = serial.Serial(port, 115200, timeout=30)
    if proto == "t1": t1(ser, int(input("patch id: ")))
    elif proto == "t2": t2(ser, int(input("patch id: ")))
    elif proto == "t4": t4(ser, AND)
    elif proto == "t5": t4(ser, OR)
    else: print("t3/t6 are manual protocols - see docs/specs §5")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests, verify pass** — `pytest bench -v`.
- [ ] **Step 5: Commit** — `git commit -am "bench: serial protocol runner for T1-T5"`

### Task 8: Housing CAD + print

**Files:**
- Create: `hardware/housing.scad`, `hardware/wiring.md`

**Interfaces:**
- Consumes: physical dimensions — patch slot 10×10×1.2 mm; GL5528 body Ø5.1 mm; 5 mm LED Ø5.1 mm.
- Produces: STL of a 5×2 cell block, cell pitch 16 mm, wall 2.4 mm, slot from top, LED pocket one end, LDR pocket other end, lid with switch boss.

- [ ] **Step 1: Write housing.scad**

```openscad
// hardware/housing.scad — ALMA Optical Perceptron Mark-II cell block
cellW=12; cellL=30; cellH=12; wall=2.4; pitch=16; rows=2; cols=5;
module cell(){
  difference(){
    cube([cellL+2*wall, cellW+2*wall, cellH+wall]);
    translate([wall,wall,wall]) cube([cellL,cellW,cellH+1]);          // cavity
    translate([wall+cellL/2-0.75, -1, wall]) cube([1.5, cellW+2*wall+2, cellH+1]); // film slot
    translate([-1, wall+cellW/2, wall+cellH/2]) rotate([0,90,0]) cylinder(d=5.3,h=wall+2,$fn=32);   // LED pocket
    translate([cellL+wall-1, wall+cellW/2, wall+cellH/2]) rotate([0,90,0]) cylinder(d=5.3,h=wall+2,$fn=32); // LDR pocket
    translate([wall+cellL*0.25, wall+cellW/2, cellH+wall-1]) cylinder(d=5.3,h=wall+2,$fn=32); // violet top port
  }
}
for(r=[0:rows-1]) for(c=[0:cols-1])
  translate([0, 0, 0]) translate([c*pitch*2.2, r*pitch, 0]) cell();
```

- [ ] **Step 2: Render STL** — `openscad -o hardware/housing.stl hardware/housing.scad`; open in CrealityPrint, verify 10 cells, slots visible.
- [ ] **Step 3: Print on K2 Plus** — matte black PLA, 0.2 mm, AFTER the hydro-planter job completes. Verify: film patch slides in slot, LED and LDR press-fit.
- [ ] **Step 4: Write wiring.md** — table mapping every part to pins, copied from `config.PINS` values, plus the HC4067/74HC595/ULN2803 wiring columns.
- [ ] **Step 5: Commit** — `git commit -am "cad: 5x2 cell housing + wiring table"`

### Task 9: Deploy + smoke test on ESP32 (physical)

- [ ] Flash MicroPython 1.22+, `mpremote fs cp firmware/*.py :` then `mpremote exec "import main; main.run()"` via `mpremote repl`.
- [ ] From PC: `python -c` one-liner sends `{"op":"read"}` over serial → expect 10 floats.
- [ ] Lid open → `{"op":"dose","patch":0,"quanta":1}` → `{"ok":0,"why":"lid"}`.
- [ ] Commit any pin fixes: `git commit -am "feat: bring-up pin corrections"`.

### Task 10: T1 dose–response (physical, spec S1)

- [ ] Insert fresh patch in cell 0-E; `python bench/bench.py --port COMx t1`.
- [ ] Record the 5-point curve; run `check_five_levels(points)` → must be True (S1 pass gate).
- [ ] Repeat for all 10 patches; store per-patch `open_max` + tables into device `caldata.json`.
- [ ] Log curves into `docs/results/t1-<date>.md`; commit.

### Task 11: T2 repeatability + T3 crosstalk (physical)

- [ ] `bench.py t2` per patch: σ < 1.5% of span, else fix light-tightness and repeat.
- [ ] T3: light channel 0 only, read all others; `crosstalk_pct` < 2%, else add foam baffles.
- [ ] Record in `docs/results/`; commit.

### Task 12: T4/T5/T6 learning runs (physical, spec S2/S3)

- [ ] `bench.py t4` (AND): converge ≤50 epochs. Film it (S5).
- [ ] `bench.py t5` (OR) from the AND state: converge ≤50 epochs.
- [ ] T6: wait 30 min, replay all 16 patterns with `{"op":"predict"}`: ≥14/16 (S3); fit `decay_tau_minutes` from interleaved reads.
- [ ] Results tables to `docs/results/`; commit.

### Task 13: T7 digipot control + publish (spec S4)

- [ ] Run identical AND/OR protocol on the digipot Mark-I rig (existing DIGIPOT-Neuron-VERIFIED build).
- [ ] Side-by-side table: epochs, retention, σ, drama. → `docs/results/mark1-vs-mark2.md`.
- [ ] Post summary + paths to RAMCHAT; hand footage to the perceptron-movie project.

## Self-Review (performed at write time)

- **Spec coverage:** S1→T10, S2→T12, S3→T12, S4→T13, S5→T12; §3.1-3.6 → Tasks 1/2/5/6; §5 T1-T7 → Tasks 10-13; §6 interlock → Tasks 5/6/9. v1.1 analog rails (spec §3.2) intentionally deferred past M2 — not in this plan; next plan after M2 results.
- **Placeholders:** none — every code step is complete and runnable.
- **Type consistency:** `fire(patch, quanta) -> bool` and `read_all() -> list[10]` identical across FakeHal (T5), Hal (T6), and bench protocol (T7). Patch-id convention defined once in Global Constraints and used in tests (`(0,1),(2,1),(8,1)` = syn*2+pol).

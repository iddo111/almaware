> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# PC THERMAL — benchmark + baseline (IDDO1, i7-7700K)

Repeatable CPU benchmark with live thermal logging, used to prove whether a
hardware change helped or hurt. **Re-run the scripts unchanged** so numbers compare.

## The story so far (2026-08-15)

| when | state |
|---|---|
| ~09:42 | **100 °C at 24 W** — at TjMax under near-idle load. Repaste had NOT fixed it. |
| ~10:50 | Iddo did a **clr-RTC (CMOS clear)** — battery out ~10 s — **and pulled an RTX 3070 Ti** |
| 10:55 | **73 °C at 24 W.** −27 °C at the same wattage. |
| 11:00 | Two 180 s soaks: **max 86 °C, zero throttling, abort never fired.** |

**Two variables moved at once, so neither is proven.** That is exactly what the
next run is for.

## Hardware facts (confirmed, do not re-litigate)

- The cooler is an **AIO (liquid)**, not an air tower. Hoses checked 11:02: both
  **lukewarm with flow felt** = a healthy loop.
- **There is no pump RPM reading, and that is not a fault.** Many AIOs power the
  pump straight from the PSU with no tach wire. Do not hunt for it.
- LHM **Fan #1 = 0 RPM is an empty header**, not a dead fan. Stop chasing it.
- Fan #2 (~1900→2100, +11 % swing) and Fan #3 (~1250→1810, +40 % swing) are the
  channels that actually move. Which is which is **not** established.

## Baseline — 2026-08-15 11:00, 80 % cap ON, **GPU OUT**

`baseline-20260815-gpu-out/`

| run | single | all-core | max °C | max W | clock |
|---|---|---|---|---|---|
| `cpu_bench.py` (mixed int/float) | 618,358 ops/s | 1,949,591 ops/s | 82 | 31.3 | 3400 MHz, no throttle |
| `cpu_bench_avx.py` (OpenBLAS DGEMM) | **34.5 GFLOPS** | **73.5 GFLOPS** | **86** | **38.8** | 3400 MHz, no throttle |

⚠️ **Both runs were measured on a busy machine** — Creality Print, Edge webviews and
four Claude sessions were already drawing 58-65 % CPU. The scores are understated.
Keep that identical-ish, or note it, when comparing.

## How to re-run (after the GPU goes back in)

**1. LibreHardwareMonitor must be running ELEVATED** — it does not autostart, and
without it the scripts have no sensors:

```bash
powershell -Command "Start-Process 'C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\LibreHardwareMonitor.LibreHardwareMonitor_Microsoft.Winget.Source_8wekyb3d8bbwe\LibreHardwareMonitor.exe' -Verb RunAs"
```

Iddo has to accept the UAC prompt. Then sensors live at http://localhost:8085/data.json

**2. Run both benchmarks** (~4 min each, into a new dated folder):

```bash
cd /d/CLAUDE/pc-thermal && mkdir -p run-gpu-in && python cpu_bench.py run-gpu-in/bench.csv && python cpu_bench_avx.py run-gpu-in/bench_avx.csv 180
```

**3. Read the verdict.**

| result | means |
|---|---|
| back near **100 °C** | the **RTX 3070 Ti** was the cause |
| stays near **86 °C** | the **CMOS clear** was the cause — card is innocent |

## Safety built in

Both scripts poll :8085 every 2 s and **hard-kill the workers at 95 °C**. Neither
baseline run triggered it. Do not raise `ABORT_C`.

## Still open

- **The 80 % cap stays.** `PROCTHROTTLEMAX = 0x50` on AC+DC, Balanced scheme.
  86 °C at only 38.8 W is not headroom — uncapped, the chip clocks to 4.2 GHz and
  roughly doubles its wattage, which lands past 95 °C. Do not lift it without a
  clean measured run proving otherwise.
- Worth a look in BIOS next time he is in there: whatever header the pump sits on,
  set it to **Full Speed**. That is where the remaining degrees are.

Memory: `project_pc_thermal_failure`.

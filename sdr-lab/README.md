# SDR Lab — first-signals kit

Everything to pick up radio signals with the RTL-SDR. Tools reused from the
2026-05 archive (nothing downloaded). Runs on the PC, no internet needed.

## One-time hardware setup (5 min)

1. Plug the RTL-SDR dongle into a USB port (a USB2 port is fine, and often quieter).
2. Screw on the antenna. For a first test the little telescopic whip is enough —
   stand it vertical, ~half-extended for FM.
3. Install the WinUSB driver so the rtl_ tools can grab the dongle:
   - run `bin\zadig-2.9.exe`
   - Options -> "List All Devices"
   - pick **"Bulk-In, Interface (0)"** (it may show as RTL2832U / RTL2838)
   - target driver **WinUSB** -> click **Replace Driver**
   - (this steals it from the Windows TV-tuner driver — that's correct)
4. Verify: `bin\rtl_test.exe` should now print the tuner type (e.g. R820T) and
   "Found 1 device(s)". If it still says "No supported devices", re-do zadig.

## Find signals (the fun part)

**Wide sweep — see the whole band as a picture:**
```
pwsh -File scan.ps1 88 108 25k        # FM broadcast — guaranteed strong signals, best first test
python plot_sweep.py captures\<the-csv-it-made>
```
The PNG shows every station as a spike, peaks labelled in MHz.

**Listen live:**
```
pwsh -File listen_fm.ps1 100.5              # tune an FM station through the speakers
pwsh -File listen_fm.ps1 100.5 wfm -Wav     # ...and record it to captures\
```

## What to point it at (Israel, worth trying in order)

| Band | Freq | What you'll hear/see | Mode |
|---|---|---|---|
| **FM radio** | 88–108 MHz | Local stations — the "hello world" of SDR | wfm |
| **Our 433 modules** | 433.05–434.79 MHz | Press the 433 remote — watch the spike jump | sweep, 5k bin |
| **Heltec LoRa** | 433 MHz band | LoRa chirps (visible as sweeps in a waterfall) | sweep |
| **PMR/walkie** | 446.0–446.2 MHz | Voice radios nearby | nfm |
| **Aircraft (AM)** | 118–137 MHz | Pilots + towers — always active near airports | am (rtl_fm -M am) |
| **ADS-B planes** | 1090 MHz | Live aircraft positions | `bin\rtl_adsb.exe` |
| **NOAA weather sats** | 137 MHz | Satellite image tones (needs a better antenna) | wfm/APT |
| **Time signal / ISM** | 40–watch | Doorbells, sensors, car fobs | sweep |

## First session plan

1. FM sweep (`scan.ps1 88 108 25k`) + plot — confirms the whole chain works and
   you SEE signals. This is the win to get first.
2. Tune the strongest FM peak with `listen_fm.ps1` — hear it.
3. The real experiment: sweep **433** (`scan.ps1 433 435 5k`), then press our 433
   remote / power the Heltec — watch our OWN signal appear on the plot.

## Honest limits

- RTL-SDR is **receive only** — it listens, never transmits. Safe, legal, passive.
- Coverage ~24 MHz–1.7 GHz. No HF (shortwave) without an upconverter.
- The stock whip antenna is poor above ~500 MHz and for satellites. FM/433/air
  will work; ADS-B and NOAA want a proper antenna (note for later).
- Receiving is legal in Israel; **decoding/acting on private comms is not** —
  we stick to broadcast, our own devices, and open beacons (ADS-B, weather).

## Files
- `bin/` — rtl_test, rtl_sdr, rtl_fm, rtl_power, rtl_tcp, rtl_adsb, zadig, DLLs
- `scan.ps1` — wideband power sweep -> CSV
- `plot_sweep.py` — CSV -> labelled spectrum PNG
- `listen_fm.ps1` — live audio / record
- `captures/` — output lands here

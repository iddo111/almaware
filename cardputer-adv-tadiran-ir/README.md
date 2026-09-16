> BROKEN WINDOWS LAW: if it is not working, fix it immediately and verify the real output.

# Cardputer ADV Tadiran IR Remote

A build-only, unflashed Cardputer ADV application for testing a Tadiran air
conditioner with the built-in IR LED on GPIO 44.

## Important

Tadiran is not a protocol name in IRremoteESP8266. Different Tadiran remote
models may use different OEM protocols. This project exposes three candidates:
GREE, MIDEA, and ELECTRA_AC. The exact remote model number or a captured signal
is required before treating any candidate as confirmed.

This project does not preserve the factory firmware if uploaded. Back up the
full 8 MB flash before any upload, or keep this as source/build output only.

## Controls

- `P`: power state
- `+` / `-`: temperature
- `M`: operating mode
- `F`: fan speed
- `S`: vertical swing
- `R`: candidate protocol
- `Enter`: transmit the complete A/C state

Point the top IR emitter at the indoor A/C unit when sending.

## Build

```powershell
pio run
```

Do not run `pio run -t upload` until the original firmware has been backed up
and the user has explicitly approved flashing.

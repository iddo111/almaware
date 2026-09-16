# Build results — 2026-07-21

- Target: `arduino:avr:uno`
- Arduino compile: PASS
- Program storage: `13,768 bytes (42%)`
- Global SRAM: `559 bytes (27%)`
- Python GUI syntax/import compile: PASS on Python 3.13 with tkinter + pyserial
- Physical Arduino identification: NOT VERIFIED; available COM ports were not identified as Uno
- Physical 12V lamp test: NOT RUN
- Measured hysteresis loop: NOT YET MEASURED

## No-INA219 shunt edition

- Sketch: `arduino/ALMAWARE_LAMP_SHUNT/ALMAWARE_LAMP_SHUNT.ino`
- Arduino compile: PASS
- Program storage: `11,562 bytes (35%)`
- Global SRAM: `356 bytes (17%)`
- Default measurement shunt: `1.000 ohm`, power rating must be at least `1 W`
- `ALMAWARE-LAMP-SHUNT-UNO.hex`
  `248F158128FA0C7D452BA34BFA573722196F0F7DDE7BF40CF3430FF16315D916`
- `ALMAWARE-LAMP-SHUNT-UNO-with-bootloader.hex`
  `4EDD2676D2C7E0F2F2E5707129FD518682A7007E3E795FD9D5F172D1B940F887`

## Firmware hashes

- `ALMAWARE-LAMP-LAB-UNO.hex`
  `78C03C7811FA89C36C76F156657B10C5E686D4B23EAA81545B80C155B93EE48D`
- `ALMAWARE-LAMP-LAB-UNO-with-bootloader.hex`
  `C5B4CB5D534D066740867F9A5DC0B8415679A48A73CB4FB06F4644DA25906B77`

Compilation verifies software compatibility and memory use. It does not verify MOSFET pinout,
physical wiring, fuse operation, supply current limiting, sensor calibration, or lamp temperature.

#!/usr/bin/env python3
# build_flash.py - assemble a 16MB ESP32-S3 flash image from the PlatformIO build
# outputs, so QEMU can boot exactly what would be flashed to the T-Deck.
# לזכרה של עלמה ז"ל - ALMAWARE
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, ".pio", "build", "tdeck")
FW = os.environ.get("ALMA_FW_DIR", BUILD)
BOOT_APP0 = os.path.expanduser(
    r"~\.platformio\packages\framework-arduinoespressif32\tools\partitions\boot_app0.bin")

FLASH_SIZE = 16 * 1024 * 1024
PARTS = [
    (0x00000, os.path.join(FW, "bootloader.bin")),
    (0x08000, os.path.join(FW, "partitions.bin")),
    (0x0e000, BOOT_APP0),
    (0x10000, os.path.join(FW, "firmware.bin")),
]

def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flash.bin")
    img = bytearray(b"\xff" * FLASH_SIZE)
    for off, path in PARTS:
        if not os.path.exists(path):
            print("MISSING:", path); sys.exit(1)
        with open(path, "rb") as f:
            data = f.read()
        img[off:off + len(data)] = data
        print(f"  0x{off:06x}  {len(data):>8,} B  {os.path.basename(path)}")
    with open(out, "wb") as f:
        f.write(img)
    print(f"\nwrote {out}  ({FLASH_SIZE:,} B)")

if __name__ == "__main__":
    main()

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src" / "main.cpp").read_text(encoding="utf-8")
CONFIG = (ROOT / "platformio.ini").read_text(encoding="utf-8")

FORBIDDEN_SOURCE_PATTERNS = {
    "Wi-Fi include": r"#include\s*[<\"]WiFi",
    "Wi-Fi API": r"\bWiFi\s*[.:]",
    "HTTP client": r"\bHTTPClient\b",
    "Bluetooth API": r"\bBluetoothSerial\b|\bBLEDevice\b",
    "camera driver": r"\besp_camera\b|\binitBgCamerImage\b",
    "camera capture": r"\bphotoSaveToTFCard\b|\bcamera_fb_get\b",
    "storage initialization": r"\binitSDFile\b|\bSD\.begin\b",
    "audio recording": r"\brecordSaveToTFCard\b",
    "game loop marker": r"\bscore\b|\blevelUp\b|\bgameOver\b",
}

REQUIRED_SOURCE_PATTERNS = {
    "K10 board initialization": r"\bk10\.begin\s*\(",
    "ambient light": r"\bk10\.readALS\s*\(",
    "accelerometer": r"\bk10\.getAccelerometerX\s*\(",
    "AHT20": r"\bDFRobot_AHT20\b",
    "button A": r"\bk10\.buttonA\b",
    "button B": r"\bk10\.buttonB\b",
    "bitmap Hebrew": r"drawHebrewBitmap",
}

failures: list[str] = []
for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
    if re.search(pattern, SOURCE, flags=re.IGNORECASE):
        failures.append(f"forbidden capability found: {label}")

for label, pattern in REQUIRED_SOURCE_PATTERNS.items():
    if not re.search(pattern, SOURCE):
        failures.append(f"required capability missing: {label}")

if "upload_port = COMPILE_ONLY_DO_NOT_UPLOAD" not in CONFIG:
    failures.append("compile-only upload guard is missing")

if re.search(r"COM\s*18", SOURCE + CONFIG, flags=re.IGNORECASE):
    failures.append("protected serial port appears in build inputs")

if failures:
    print("FAIL: offline/non-game policy")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)

print("PASS: offline, no-camera, no-storage, non-game source policy")


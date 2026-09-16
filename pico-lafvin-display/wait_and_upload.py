import subprocess
import sys
import time

from serial.tools import list_ports


TARGET_SERIAL = "E66480454F6E7E39"
FIRMWARE = r"D:\CLAUDE\pico-lafvin-display\main.py"
TIMEOUT_SECONDS = 240


def find_target_port():
    for port in list_ports.comports():
        if (port.serial_number or "").upper() == TARGET_SERIAL:
            return port.device
    return None


deadline = time.monotonic() + TIMEOUT_SECONDS
print("WAITING_FOR_LAFVIN_PICO", TARGET_SERIAL, flush=True)

while time.monotonic() < deadline:
    device = find_target_port()
    if device:
        print("FOUND", device, flush=True)
        upload = subprocess.run(
            [
                sys.executable,
                "-m",
                "mpremote",
                "connect",
                device,
                "fs",
                "cp",
                FIRMWARE,
                ":main.py",
            ],
            check=False,
        )
        if upload.returncode != 0:
            raise SystemExit(upload.returncode)

        reset = subprocess.run(
            [sys.executable, "-m", "mpremote", "connect", device, "reset"],
            check=False,
        )
        if reset.returncode != 0:
            raise SystemExit(reset.returncode)

        print("UPLOAD_AND_RESET_OK", device, flush=True)
        raise SystemExit(0)

    time.sleep(1)

print("TIMEOUT_TARGET_NOT_CONNECTED", flush=True)
raise SystemExit(2)

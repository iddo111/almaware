"""Raw-write the ALMA Pi image (xz) to a physical drive. Windows, admin required.

Usage: python raw-flash.py <disk_number> [volume_letter]
Streams lzma decompression straight to \\.\PhysicalDriveN in 4 MiB chunks with
progress lines. If a volume letter is given, that volume is locked and
dismounted first (required for removable media) and held for the duration.
"""
import ctypes
import lzma
import sys
import time

IMAGE = r"D:\CLAUDE\alma-pi\images\2026-06-18-raspios-trixie-arm64.img.xz"
CHUNK = 4 * 1024 * 1024

GENERIC_RW = 0xC0000000
SHARE_RW = 0x00000003
OPEN_EXISTING = 3
FSCTL_LOCK_VOLUME = 0x00090018
FSCTL_DISMOUNT_VOLUME = 0x00090020


def lock_and_dismount(letter):
    k32 = ctypes.windll.kernel32
    handle = k32.CreateFileW(r"\\.\%s:" % letter, GENERIC_RW, SHARE_RW,
                             None, OPEN_EXISTING, 0, None)
    if handle == -1:
        raise OSError("cannot open volume %s:" % letter)
    ret = ctypes.c_ulong(0)
    for code, name in ((FSCTL_LOCK_VOLUME, "lock"), (FSCTL_DISMOUNT_VOLUME, "dismount")):
        if not k32.DeviceIoControl(handle, code, None, 0, None, 0,
                                   ctypes.byref(ret), None):
            raise OSError("%s of %s: failed (err %d)" % (name, letter, k32.GetLastError()))
    print("volume %s: locked+dismounted" % letter, flush=True)
    return handle  # keep open for the duration


def main() -> int:
    disk = int(sys.argv[1])
    if len(sys.argv) > 2:
        lock_and_dismount(sys.argv[2])
    target = r"\\.\PhysicalDrive%d" % disk
    written = 0
    start = time.time()
    with lzma.open(IMAGE, "rb") as src, open(target, "r+b", buffering=0) as dst:
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            if len(chunk) % 512:  # physical drives need sector-aligned writes
                chunk = chunk + b"\x00" * (512 - len(chunk) % 512)
            dst.write(chunk)
            written += len(chunk)
            if written % (256 * 1024 * 1024) < CHUNK:
                mb = written / (1024 * 1024)
                rate = mb / max(1e-9, time.time() - start)
                print("progress %.0f MiB  %.1f MB/s" % (mb, rate), flush=True)
        dst.flush()
    print("DONE wrote %.2f GiB in %.0f s" % (written / 2**30, time.time() - start), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

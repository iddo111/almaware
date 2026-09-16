#!/usr/bin/env python3
"""ZENER NEURON logger (2026-09-10). The maths lives HERE so nothing is hidden on the ESP32.

usage:  python logger.py COM5 [--cond A|B|C|test] [--seconds N]
        python logger.py --fake --seconds 3        (no hardware: tests this script only)

Reads one integer per line (raw 12-bit ADC sample) and keeps EVERYTHING:
  logs/raw-<stamp>-<cond>.txt   one ADC value per line  (never hashed, never whitened)
  logs/bits-<stamp>-<cond>.bin  von Neumann bits packed 8 per byte (01->0, 10->1, 00/11 dropped)
Prints once a second: samples/s, mean, std, LSB ones-fraction, vN bits/s, total bits.

Conditions for phase 2:  A = Iddo asking   B = Iddo present, silent   C = empty room   test = bench work
"""
import os, sys, time, random, argparse, statistics


def open_source(port, fake):
    if fake:
        def gen():
            while True:
                time.sleep(0.0001)
                yield int(2000 + random.gauss(0, 40))      # a pretend amp: ~40 LSB of hiss
        return gen()
    try:
        import serial                                       # pip install pyserial
    except ImportError:
        sys.exit("pip install pyserial   (or run with --fake to test the script)")
    ser = serial.Serial(port, 921600, timeout=1)
    def gen():
        while True:
            line = ser.readline()
            if not line:
                continue
            try:
                yield int(line.strip())
            except ValueError:
                continue
    return gen()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", default="COM5")
    ap.add_argument("--cond", default="test", help="A=asking  B=present-silent  C=empty  test=bench")
    ap.add_argument("--fake", action="store_true", help="no hardware: gaussian stand-in to test this script")
    ap.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = forever)")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    logdir = os.path.join(here, "logs")
    os.makedirs(logdir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    raw_path = os.path.join(logdir, f"raw-{stamp}-{a.cond}.txt")
    bit_path = os.path.join(logdir, f"bits-{stamp}-{a.cond}.bin")
    raw_f = open(raw_path, "w")
    bit_f = open(bit_path, "wb")
    print(f"source={'FAKE' if a.fake else a.port}  cond={a.cond}\n  raw  -> {raw_path}\n  bits -> {bit_path}", flush=True)

    src = open_source(a.port, a.fake)
    t0 = last = time.time()
    win = []; ones = 0; lsb_n = 0
    prev = None; byte = 0; nb = 0; vn_total = 0; vn_sec = 0
    for v in src:
        raw_f.write(f"{v}\n")
        win.append(v)
        b = v & 1
        ones += b; lsb_n += 1
        if prev is None:
            prev = b
        else:
            if prev != b:                      # von Neumann: 01 -> 0, 10 -> 1, equal pairs dropped
                byte = (byte << 1) | prev
                nb += 1; vn_total += 1; vn_sec += 1
                if nb == 8:
                    bit_f.write(bytes([byte])); byte = 0; nb = 0
            prev = None
        now = time.time()
        if now - last >= 1.0:
            mean = statistics.fmean(win); sd = statistics.pstdev(win)
            print(f"{now - t0:6.0f}s  {len(win):6d} samp/s  mean {mean:7.1f}  std {sd:6.1f} LSB  "
                  f"LSB ones {ones / max(lsb_n, 1):.4f}  vN {vn_sec:5d} bit/s  total {vn_total}", flush=True)
            win.clear(); vn_sec = 0; last = now
            raw_f.flush(); bit_f.flush()
        if a.seconds and now - t0 >= a.seconds:
            break
    raw_f.close(); bit_f.close()
    print(f"done. {vn_total} von Neumann bits kept.")


if __name__ == "__main__":
    main()

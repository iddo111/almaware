"""
loop.py — the experiment: display a pattern, capture it back, transform it,
repeat. This file is LOOP MECHANICS ONLY (timing, sources, geometry). The
transform itself — "the optics" — lives entirely in optics.py and is called
from here as a single function, so the physical upgrade path (delete the
digital transform, let a real lens+mask+OASLM do it between two physical
planes) only ever touches one call site.

Two sources, selected with --source:

  virtual   No camera, no screen window, no hardware touched at all. The
            "capture" step reads back the exact buffer that was about to be
            displayed. This is a pure software test of the iterated map
            x_{t+1} = f(x_t). Safe to run any time, unattended.

  camera    The real thing: a cv2 window is put on a chosen monitor, a real
            webcam captures it, real photons cross real air. This is the
            only mode that actually tests the physical question. It is
            gated (see SAFETY CHECKS below) because the only camera on this
            machine is the Logitech BRIO, which is KESHEV's mic capture
            device, and because this machine has a single monitor — a
            fullscreen window here takes over the only screen there is.

See SIMULATE.md for exactly which parts of each mode are physically real.
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import deque
from pathlib import Path

import numpy as np
import cv2

from optics import OpticsConfig, apply_optics, make_fixed_mask
import calibration as calib

BASE_RES = 64  # the loop's internal state resolution (H=W=BASE_RES)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

class VirtualSource:
    """No hardware. capture() returns exactly what show() was given, plus
    an OPTIONAL synthetic camera-noise model that must be explicitly
    requested with --sim-noise / --sim-jitter. Default is the identity
    (idealized, noiseless) channel."""

    name = "virtual"

    def __init__(self, sim_noise: float = 0.0, sim_jitter: float = 0.0, seed: int = 0):
        self.sim_noise = sim_noise
        self.sim_jitter = sim_jitter
        self.rng = np.random.default_rng(seed)
        self._last = None

    def show(self, frame01: np.ndarray) -> None:
        self._last = frame01

    def capture(self) -> np.ndarray:
        out = self._last.copy()
        if self.sim_jitter > 0:
            h, w = out.shape[:2]
            dx, dy = self.rng.uniform(-self.sim_jitter, self.sim_jitter, size=2)
            M = cv2.getRotationMatrix2D((w / 2, h / 2), 0.0, 1.0)
            M[0, 2] += dx
            M[1, 2] += dy
            out = cv2.warpAffine(out, M, (w, h), borderMode=cv2.BORDER_REPLICATE)
        if self.sim_noise > 0:
            out = out + self.rng.normal(0, self.sim_noise, size=out.shape).astype(np.float32)
        return np.clip(out, 0.0, 1.0).astype(np.float32)

    def close(self) -> None:
        pass


class CameraSource:
    """The real thing. Opens a monitor window and a webcam. Gated: see
    check_camera_safety() in main(), called before this is ever constructed.
    """

    name = "camera"

    def __init__(self, camera_index: int, monitor_index: int, out_size: int = 512):
        try:
            import screeninfo
        except ImportError:
            print("ERROR: screeninfo not installed. pip install screeninfo (see requirements.txt)")
            raise
        monitors = screeninfo.get_monitors()
        if monitor_index >= len(monitors):
            raise SystemExit(f"monitor index {monitor_index} out of range (found {len(monitors)})")
        self.mon = monitors[monitor_index]
        self.out_size = out_size
        self.win = "optic-loop"
        cv2.namedWindow(self.win, cv2.WINDOW_NORMAL)
        cv2.moveWindow(self.win, self.mon.x, self.mon.y)
        cv2.setWindowProperty(self.win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise SystemExit(
                f"could not open camera {camera_index}. If this is the BRIO and KESHEV's "
                f"mic is running, this WILL fail or fight the mic for the device — see README."
            )
        # discard first few frames (exposure/AWB settling)
        for _ in range(5):
            self.cap.read()

        self.M = None
        self.calib_path = calib.calibration_path(camera_index, monitor_index)

    def calibrate(self) -> None:
        cached = calib.load_calibration(self.calib_path)
        if cached is not None:
            self.M, self.out_size = cached
            print(f"[calibration] loaded cached matrix from {self.calib_path}")
            return
        print("[calibration] displaying calibration border, capturing...")
        border = np.zeros((self.out_size, self.out_size), dtype=np.uint8)
        margin = self.out_size // 8
        border[margin:-margin, margin:-margin] = 255
        cv2.imshow(self.win, border)
        cv2.waitKey(500)
        for _ in range(5):
            ok, frame = self.cap.read()
        if not ok:
            raise SystemExit("camera read failed during calibration")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        quad = calib.find_display_quad(gray)
        if quad is None:
            raise SystemExit(
                "calibration FAILED: no bright rectangle found in the camera view. "
                "Point the camera at the monitor, reduce room light, and try again."
            )
        self.M = calib.compute_rectify_matrix(quad, self.out_size)
        calib.save_calibration(self.calib_path, self.M, self.out_size, quad)
        print(f"[calibration] saved to {self.calib_path}")

    def show(self, frame01: np.ndarray) -> None:
        big = cv2.resize(frame01, (self.out_size, self.out_size), interpolation=cv2.INTER_NEAREST)
        cv2.imshow(self.win, (big * 255).astype(np.uint8))
        cv2.waitKey(1)

    def capture(self) -> np.ndarray:
        ok, frame = self.cap.read()
        if not ok:
            raise SystemExit("camera read failed mid-loop")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.M is not None:
            gray = calib.rectify(gray, self.M, self.out_size)
        small = cv2.resize(gray, (BASE_RES, BASE_RES), interpolation=cv2.INTER_AREA)
        return (small.astype(np.float32) / 255.0)

    def close(self) -> None:
        self.cap.release()
        cv2.destroyWindow(self.win)


# ---------------------------------------------------------------------------
# Loop mechanics (source-agnostic)
# ---------------------------------------------------------------------------

def init_pattern(seed: int, res: int = BASE_RES) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random((res, res), dtype=np.float64).astype(np.float32)


def run_loop(source, cfg: OpticsConfig, iters: int, init_state: np.ndarray, mask=None,
             frame_history: int | None = None) -> dict:
    """The loop mechanics. Same shape whether `source` is virtual or camera:
    show -> capture -> apply_optics -> repeat. `apply_optics` (optics.py) is
    the ONLY thing that changes the signal; everything else here is just
    timing and bookkeeping.

    `frame_history`: None keeps every frame (fine for a single interactive
    run). measure.py runs hundreds of trials, so it passes a small integer
    to keep only the last N+1 frames (enough for periodicity detection),
    bounding memory instead of holding iters x hundreds of full frame
    histories at once.
    """
    state = init_state.astype(np.float32).copy()
    diffs = []
    frames = deque([state.copy()], maxlen=(frame_history + 1) if frame_history else None)
    for _t in range(iters):
        source.show(state)
        captured = source.capture()
        new_state = apply_optics(captured, cfg, mask)
        diff = float(np.mean(np.abs(new_state - state)))
        diffs.append(diff)
        state = new_state
        frames.append(state.copy())
    return {"diffs": diffs, "frames": list(frames), "final": state}


# ---------------------------------------------------------------------------
# Safety gate for the camera source
# ---------------------------------------------------------------------------

def check_camera_safety(args) -> None:
    if args.source != "camera":
        return
    if not args.yes_i_paused_the_mic:
        print(
            "REFUSING to open a camera.\n"
            "This machine's only camera is the Logitech BRIO, which is KESHEV's mic\n"
            "capture device (Sacred Audio Law: never seize it while the mic is running).\n"
            "This machine also has a single monitor, so a fullscreen window here takes\n"
            "over the only screen you have.\n\n"
            "Before running with --source camera:\n"
            "  1. Pause/stop the KESHEV mic (or use a second camera and pass --camera N\n"
            "     for that device's index).\n"
            "  2. Be at the keyboard and ready to lose the screen for the run's duration.\n"
            "  3. Re-run with --yes-i-paused-the-mic to confirm both of the above.\n"
        )
        raise SystemExit(2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_cfg(args) -> OpticsConfig:
    return OpticsConfig(
        blur_ksize=args.blur_ksize,
        blur_sigma=args.blur_sigma,
        weight_mode=args.weight_mode,
        malus_theta_deg=args.malus_theta_deg,
        threshold_mode=args.threshold_mode,
        threshold_k=args.threshold_k,
        threshold_bias=args.threshold_bias,
        gain=args.gain,
        decay=args.decay,
        shift_dx=args.shift_dx,
        shift_dy=args.shift_dy,
        rotate_deg=args.rotate_deg,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", choices=["virtual", "camera"], default="virtual")
    p.add_argument("--camera", type=int, default=0, help="camera index (camera source only)")
    p.add_argument("--monitor", type=int, default=0, help="monitor index (camera source only)")
    p.add_argument("--yes-i-paused-the-mic", action="store_true",
                   help="required to run --source camera; confirms KESHEV mic is paused "
                        "or a second camera is in use, and that you're at the screen")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--iters", type=int, default=100)
    p.add_argument("--sim-noise", type=float, default=0.0, help="virtual source only")
    p.add_argument("--sim-jitter", type=float, default=0.0, help="virtual source only")
    p.add_argument("--no-calibrate", action="store_true")
    p.add_argument("--out", type=str, default=None, help="save final frame PNG here")

    # optics parameters
    p.add_argument("--blur-ksize", type=int, default=5)
    p.add_argument("--blur-sigma", type=float, default=1.2)
    p.add_argument("--weight-mode", choices=["none", "fixed", "malus"], default="fixed")
    p.add_argument("--malus-theta-deg", type=float, default=20.0)
    p.add_argument("--threshold-mode", choices=["sigmoid", "hard", "off"], default="sigmoid")
    p.add_argument("--threshold-k", type=float, default=12.0)
    p.add_argument("--threshold-bias", type=float, default=0.5)
    p.add_argument("--gain", type=float, default=1.15)
    p.add_argument("--decay", type=float, default=0.08)
    p.add_argument("--shift-dx", type=float, default=0.0)
    p.add_argument("--shift-dy", type=float, default=0.0)
    p.add_argument("--rotate-deg", type=float, default=0.0)

    args = p.parse_args()
    check_camera_safety(args)

    cfg = build_cfg(args)
    mask = make_fixed_mask((BASE_RES, BASE_RES), seed=args.seed) if cfg.weight_mode == "fixed" else None
    init_state = init_pattern(args.seed)

    if args.source == "virtual":
        source = VirtualSource(sim_noise=args.sim_noise, sim_jitter=args.sim_jitter, seed=args.seed)
    else:
        source = CameraSource(args.camera, args.monitor)
        if not args.no_calibrate:
            source.calibrate()

    print(f"[loop] source={args.source} seed={args.seed} iters={args.iters} cfg={cfg}")
    t0 = time.time()
    result = run_loop(source, cfg, args.iters, init_state, mask=mask)
    dt = time.time() - t0
    source.close()

    diffs = result["diffs"]
    print(f"[loop] done in {dt:.2f}s. final frame-diff={diffs[-1]:.6f}, "
          f"min={min(diffs):.6f}, max={max(diffs):.6f}")

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_path), (result["final"] * 255).astype(np.uint8))
        print(f"[loop] saved final frame to {out_path}")


if __name__ == "__main__":
    main()

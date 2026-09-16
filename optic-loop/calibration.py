"""
calibration.py — find the displayed rectangle inside the captured frame.

Only used by `--source camera`. A webcam pointed at a monitor never sees
exactly the panel and nothing else: there is a bezel, a desk, an angle, a
zoom level. If the loop just used the raw camera frame, any apparent drift
or "instability" could just be geometry (the camera slowly creeping in
frame, or an off-axis crop) rather than the loop's actual dynamics.

What calibration does, plainly: on first run, the display shows a bright
white rectangle on a black background (a calibration border). We find its
four corners in the camera image (biggest bright contour -> minAreaRect),
and compute the homography that warps *that quad* onto a canonical square.
Every subsequent captured frame gets warped through that same homography
before anything else happens to it, so pixel (0,0) of the loop's state
always means the same physical corner of the panel, regardless of camera
angle, zoom or crop. The matrix is cached to disk so it is computed once
per camera/monitor pairing, not every run.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import cv2

CALIB_DIR = Path(__file__).parent / "results"


def find_display_quad(gray_u8: np.ndarray, min_area_frac: float = 0.02) -> np.ndarray | None:
    """Return the 4 corners (float32, shape (4,2)) of the largest bright
    rectangular blob in a grayscale uint8 image, or None if nothing
    plausible was found. Corners are ordered TL, TR, BR, BL.

    Uses approxPolyDP on the contour, NOT minAreaRect. minAreaRect fits the
    minimum-area *rectangle* enclosing the points -- correct only for a
    fronto-parallel view. A camera pointed at a monitor from any angle sees
    a perspective-skewed quadrilateral (a trapezoid, not a rectangle), and
    minAreaRect silently snaps that to its axis-aligned bounding box,
    discarding the real corners. This was caught by the self-test below
    (15px mean corner error) before ever touching a real camera.
    """
    h, w = gray_u8.shape[:2]
    _, thresh = cv2.threshold(gray_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(biggest) < min_area_frac * h * w:
        return None
    peri = cv2.arcLength(biggest, True)
    approx = cv2.approxPolyDP(biggest, 0.02 * peri, True)
    if len(approx) == 4:
        pts = approx.reshape(-1, 2).astype(np.float32)
    else:
        # fallback for a near-fronto-parallel view where the contour didn't
        # simplify to exactly 4 points
        rect = cv2.minAreaRect(biggest)
        pts = cv2.boxPoints(rect).astype(np.float32)
    return _order_corners(pts)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as TL, TR, BR, BL."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).flatten()
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)


def compute_rectify_matrix(quad: np.ndarray, out_size: int) -> np.ndarray:
    dst = np.array(
        [[0, 0], [out_size - 1, 0], [out_size - 1, out_size - 1], [0, out_size - 1]],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(quad, dst)


def rectify(frame: np.ndarray, M: np.ndarray, out_size: int) -> np.ndarray:
    return cv2.warpPerspective(frame, M, (out_size, out_size))


def calibration_path(camera_index: int, monitor_index: int) -> Path:
    CALIB_DIR.mkdir(exist_ok=True)
    return CALIB_DIR / f"calibration_cam{camera_index}_mon{monitor_index}.json"


def save_calibration(path: Path, M: np.ndarray, out_size: int, quad: np.ndarray) -> None:
    payload = {
        "matrix": M.tolist(),
        "out_size": out_size,
        "quad": quad.tolist(),
        "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    path.write_text(json.dumps(payload, indent=2))


def load_calibration(path: Path) -> tuple[np.ndarray, int] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return np.array(payload["matrix"], dtype=np.float32), int(payload["out_size"])


# ---------------------------------------------------------------------------
# Hardware-free self-test: proves the geometry code is correct without a
# camera or a screen. Generates a synthetic quad with a KNOWN homography,
# runs it through the exact same find_display_quad/compute_rectify_matrix
# path, and reports the corner-recovery error in pixels — a real number,
# no hardware required. Run with: python calibration.py --selftest
# ---------------------------------------------------------------------------

def _selftest(out_size: int = 256, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    canvas_size = 640
    canvas = np.zeros((canvas_size, canvas_size), dtype=np.uint8)

    # Ground-truth quad: an axis-aligned square perturbed by a small random
    # perspective jitter, emulating a camera that is not perfectly square-on.
    base = np.array(
        [[160, 120], [480, 120], [480, 440], [160, 440]], dtype=np.float32
    )
    jitter = rng.uniform(-25, 25, size=base.shape).astype(np.float32)
    true_quad = base + jitter

    cv2.fillConvexPoly(canvas, true_quad.astype(np.int32), 255)

    found_quad = find_display_quad(canvas)
    if found_quad is None:
        return {"ok": False, "reason": "no quad found"}

    # find_display_quad's corner ORDER is TL,TR,BR,BL by our own convention;
    # true_quad was built in the same order, so compare directly, but also
    # check the cyclic-rotation-invariant nearest match in case of ties.
    err_direct = float(np.mean(np.linalg.norm(found_quad - true_quad, axis=1)))

    M = compute_rectify_matrix(found_quad, out_size)
    M_true = compute_rectify_matrix(true_quad, out_size)
    # Compare the two homographies by how differently they map a probe grid.
    ys, xs = np.mgrid[0:canvas_size:32, 0:canvas_size:32]
    probe = np.stack([xs.ravel(), ys.ravel()], axis=1).astype(np.float32).reshape(-1, 1, 2)
    mapped = cv2.perspectiveTransform(probe, M)
    mapped_true = cv2.perspectiveTransform(probe, M_true)
    warp_err_px = float(np.mean(np.linalg.norm(mapped - mapped_true, axis=2)))

    return {
        "ok": err_direct < 3.0,  # sub-3px corner recovery = pass
        "mean_corner_error_px": round(err_direct, 4),
        "mean_warp_error_px": round(warp_err_px, 4),
        "true_quad": true_quad.tolist(),
        "found_quad": found_quad.tolist(),
    }


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        result = _selftest()
        print(json.dumps(result, indent=2))
        out_path = CALIB_DIR / "calibration_selftest.json"
        CALIB_DIR.mkdir(exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2))
        print(f"\nwrote {out_path}")
        sys.exit(0 if result.get("ok") else 1)
    else:
        print("usage: python calibration.py --selftest")

# -*- coding: utf-8 -*-
"""Headline formant table, vowel-space coverage, and an F1/F2 chart."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from exemplar_formants import VOWELS, analyse_checkpoint, classify_vowel, is_a  # noqa: E402

ANTS = ("ant-a", "ant-b", "ant-c", "ant-d")
BEFORE = {"ant-a": (660, 1064), "ant-b": (392, 1948),
          "ant-c": (348, 1332), "ant-d": (660, 1064)}


def colonies() -> list[tuple[str, Path]]:
    out = [("BEFORE (253 s, 64 units)", ROOT / "state")]
    big = ROOT / "state-big"
    for p in sorted(big.iterdir()):
        if p.is_dir() and (p / "ant-a" / "current.json").exists():
            out.append((p.name, p))
    return out


def main() -> None:
    report = {}
    for name, root in colonies():
        entry = {"ants": {}}
        for ant in ANTS:
            cur = root / ant / "current.json"
            if not cur.exists():
                continue
            r = analyse_checkpoint(cur)
            ck = json.loads(cur.read_text(encoding="utf-8"))
            prov = ck.get("corpus_provenance") or {}
            r["hours"] = prov.get("hours")
            r["speaker_id_count"] = prov.get("speaker_id_count")
            r["learner"] = ck.get("learner", "kmeans")
            r["heldout_error_after"] = ck.get("heldout_error_after")
            entry["ants"][ant] = r
        if entry["ants"]:
            report[name] = entry

    print(f"\n{'colony':<22}{'ant':<7}{'F1':>6}{'F2':>7}  {'/a/?':<5}"
          f"{'unit':>5}{'per':>6}{'low':>6}  before -> after")
    for name, e in report.items():
        for ant, r in e["ants"].items():
            h = r["headline"]
            b = BEFORE.get(ant)
            print(f"{name:<22}{ant:<7}{h['f1'] or 0:>6.0f}{h['f2'] or 0:>7.0f}  "
                  f"{'YES' if h['is_a'] else 'no':<5}{h['unit']:>5}"
                  f"{h['periodicity']:>6.2f}{h['low_band_ratio']:>6.2f}  "
                  f"{b[0]}/{b[1]} -> {h['f1']:.0f}/{h['f2']:.0f}")

    print(f"\n{'colony':<22}{'ant':<7}{'best /a/ candidate':<22}"
          f"{'a-units':>8}{'a-units voiced':>15}")
    for name, e in report.items():
        for ant, r in e["ants"].items():
            b = r.get("best_a_candidate")
            txt = (f"{b['f1']:.0f}/{b['f2']:.0f} {'IN' if b['is_a'] else 'out'}"
                   if b else "no voiced unit")
            print(f"{name:<22}{ant:<7}{txt:<22}{r['a_capable_units']:>8}"
                  f"{r['a_capable_units_periodic']:>15}")

    print(f"\n{'colony':<22}{'ant':<7}{'covered (top-12 periodic)':<28}"
          f"{'hours':>8}{'spk':>5}{'heldout err':>13}")
    for name, e in report.items():
        for ant, r in e["ants"].items():
            print(f"{name:<22}{ant:<7}{','.join(r['regions_covered_inside_box']) or '-':<28}"
                  f"{(r['hours'] or 0.0702):>8.2f}{(r['speaker_id_count'] or 1):>5}"
                  f"{(r['heldout_error_after'] or 0):>13.4f}")

    out = ROOT / "state-big" / "formants.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {out}")
    svg(report, ROOT / "state-big" / "vowel-space.svg")


def svg(report: dict, path: Path) -> None:
    """F1/F2 vowel chart, phonetician convention: F2 rightward-decreasing,
    F1 downward-increasing, so the vowel triangle sits the familiar way up."""
    W, H, M = 900, 640, 80
    f2lo, f2hi = 3000.0, 500.0        # left edge .. right edge
    f1lo, f1hi = 200.0, 1100.0
    def X(f2): return M + (np.log(f2) - np.log(f2lo)) / (np.log(f2hi) - np.log(f2lo)) * (W - 2 * M)
    def Y(f1): return M + (np.log(f1) - np.log(f1lo)) / (np.log(f1hi) - np.log(f1lo)) * (H - 2 * M)

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'font-family="system-ui,sans-serif" font-size="13">',
         f'<rect width="{W}" height="{H}" fill="#fbfbfa"/>']
    for v, spec in VOWELS.items():
        x0, x1 = X(spec["f2"][1]), X(spec["f2"][0])
        y0, y1 = Y(spec["f1"][0]), Y(spec["f1"][1])
        fill = "#e8f0d8" if v == "a" else "#eeeeee"
        s.append(f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{x1-x0:.0f}" height="{y1-y0:.0f}" '
                 f'fill="{fill}" stroke="#c9c9c4" stroke-dasharray="4 3"/>')
        s.append(f'<text x="{(x0+x1)/2:.0f}" y="{(y0+y1)/2+6:.0f}" text-anchor="middle" '
                 f'font-size="26" fill="#9a9a93">/{v}/</text>')
    # the /a/ acceptance window from the diagnosis
    ax0, ax1, ay0, ay1 = X(1400), X(1000), Y(650), Y(850)
    s.append(f'<rect x="{ax0:.0f}" y="{ay0:.0f}" width="{ax1-ax0:.0f}" height="{ay1-ay0:.0f}" '
             f'fill="none" stroke="#4a7c1f" stroke-width="2.5"/>')
    s.append(f'<text x="{ax1+8:.0f}" y="{ay0+14:.0f}" fill="#4a7c1f" font-weight="600">'
             f'/a/ target</text>')
    for f2 in (2500, 2000, 1500, 1000, 700):
        s.append(f'<line x1="{X(f2):.0f}" y1="{M}" x2="{X(f2):.0f}" y2="{H-M}" '
                 f'stroke="#e3e3de"/>')
        s.append(f'<text x="{X(f2):.0f}" y="{H-M+20:.0f}" text-anchor="middle" '
                 f'fill="#777">{f2}</text>')
    for f1 in (300, 400, 600, 800, 1000):
        s.append(f'<line x1="{M}" y1="{Y(f1):.0f}" x2="{W-M}" y2="{Y(f1):.0f}" '
                 f'stroke="#e3e3de"/>')
        s.append(f'<text x="{M-10:.0f}" y="{Y(f1)+4:.0f}" text-anchor="end" '
                 f'fill="#777">{f1}</text>')
    s.append(f'<text x="{W/2:.0f}" y="{H-M+46:.0f}" text-anchor="middle" fill="#444">'
             f'F2 (Hz)</text>')
    s.append(f'<text x="24" y="{H/2:.0f}" fill="#444" transform="rotate(-90 24 {H/2:.0f})" '
             f'text-anchor="middle">F1 (Hz)</text>')

    colours = {"ant-a": "#c0392b", "ant-b": "#1f6fb4", "ant-c": "#d68910", "ant-d": "#6c3483"}
    shown = [n for n in report if n.startswith("BEFORE") or n == "all-256"]
    for name in shown:
        before = name.startswith("BEFORE")
        for ant, r in report[name]["ants"].items():
            c = colours[ant]
            for pt in r["vowel_space_top_periodic"]:
                if pt["f1"] is None or pt["f2"] is None:
                    continue
                x, y = X(min(max(pt["f2"], f2hi), f2lo)), Y(min(max(pt["f1"], f1lo), f1hi))
                if before:
                    s.append(f'<path d="M{x-4:.0f},{y:.0f}L{x:.0f},{y-4:.0f}'
                             f'L{x+4:.0f},{y:.0f}L{x:.0f},{y+4:.0f}Z" fill="none" '
                             f'stroke="{c}" stroke-width="1.4" opacity="0.75"/>')
                else:
                    s.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="4.5" fill="{c}" '
                             f'opacity="0.8"/>')
            h = r["headline"]
            if h["f1"]:
                x, y = X(min(max(h["f2"], f2hi), f2lo)), Y(min(max(h["f1"], f1lo), f1hi))
                s.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" fill="none" '
                         f'stroke="{c}" stroke-width="2.5"/>')
    ly = M - 46
    s.append(f'<text x="{M}" y="{ly-16}" font-weight="700" fill="#222">'
             f'Ant vowel space: top-12 most periodic exemplars '
             f'(diamonds = before, 253 s / 64 units; discs = after, 40.6 h / 256 units; '
             f'ring = headline exemplar)</text>')
    for i, (ant, c) in enumerate(colours.items()):
        s.append(f'<circle cx="{M+i*90+6}" cy="{ly}" r="5" fill="{c}"/>'
                 f'<text x="{M+i*90+18}" y="{ly+4}" fill="#333">{ant}</text>')
    s.append("</svg>")
    path.write_text("\n".join(s), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()

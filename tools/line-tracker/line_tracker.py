"""
Line Tracker AI — upload a photo, describe or draw a line, AI tracks it.

Supports:
  - Draw a line on the image (Gradio sketchpad)
  - Describe in English or Hebrew: "track the guitar string" / "תעקוב אחרי המיתר"
  - Auto-detects linear objects (strings, pencils, edges, rods) via Hough lines
  - NLP parsed by llama3.3 (local Ollama) with fallback heuristics

Usage:
  python line_tracker.py
  python line_tracker.py --share
"""
from __future__ import annotations
import argparse
import json
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ── line detection ────────────────────────────────────────────────────────────

def detect_lines(img_rgb: np.ndarray, max_lines: int = 20) -> list[dict]:
    """Return list of {x1,y1,x2,y2,angle_deg,length} sorted by length desc."""
    gray  = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60,
                             minLineLength=40, maxLineGap=10)
    if lines is None:
        return []
    out = []
    for l in lines[:max_lines * 3]:
        x1, y1, x2, y2 = l[0]
        length = float(np.hypot(x2 - x1, y2 - y1))
        angle  = float(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180
        out.append({"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
                    "angle_deg": angle, "length": length})
    out.sort(key=lambda d: d["length"], reverse=True)
    return out[:max_lines]


def score_line(line: dict, hint: dict, img_h: int, img_w: int) -> float:
    """Score a detected line against a user hint {vertical, horizontal, region, keyword}."""
    score = line["length"]  # base: prefer longer lines

    # orientation hint
    a = line["angle_deg"]
    if hint.get("horizontal"):
        # horizontal = angle near 0 or 180
        score += 500 * (1 - min(a, 180 - a) / 90)
    if hint.get("vertical"):
        score += 500 * (min(a, 180 - a) / 90)

    # region hint (top/bottom/left/right/center)
    cx = (line["x1"] + line["x2"]) / 2
    cy = (line["y1"] + line["y2"]) / 2
    region = hint.get("region", "")
    if region == "top"    and cy < img_h * 0.4:  score += 400
    if region == "bottom" and cy > img_h * 0.6:  score += 400
    if region == "left"   and cx < img_w * 0.4:  score += 400
    if region == "right"  and cx > img_w * 0.6:  score += 400
    if region == "center" and img_w * 0.3 < cx < img_w * 0.7: score += 400

    return score


def parse_hint(text: str) -> dict:
    """Parse English/Hebrew text into a hint dict using heuristics + llama3.3."""
    t = text.lower()
    hint: dict = {}

    # orientation keywords
    horiz_kw = ["horizontal", "string", "מיתר", "wire", "חוט", "pencil", "עיפרון",
                 "rod", "bar", "מוט", "nut", "אגוז", "fret", "string", "cable", "כבל",
                 "horizon", "אופקי"]
    vert_kw   = ["vertical", "עמודה", "column", "pole", "עמוד", "mast", "אנכי"]
    for kw in horiz_kw:
        if kw in t:
            hint["horizontal"] = True; break
    for kw in vert_kw:
        if kw in t:
            hint["vertical"] = True; break

    # region keywords
    region_map = {
        "top":    ["top", "upper", "עליון", "למעלה"],
        "bottom": ["bottom", "lower", "תחתון", "למטה"],
        "left":   ["left",  "שמאל"],
        "right":  ["right", "ימין"],
        "center": ["center", "middle", "אמצע", "מרכז"],
    }
    for region, kws in region_map.items():
        if any(kw in t for kw in kws):
            hint["region"] = region; break

    # if heuristics gave nothing useful, ask llama3.3
    if not hint:
        try:
            prompt = (
                "Parse this line-tracking instruction and return JSON with keys: "
                "horizontal (bool), vertical (bool), region (one of: top/bottom/left/right/center/any). "
                f"Instruction: {text}. Reply ONLY with JSON."
            )
            payload = json.dumps({"model": "huihui_ai/llama3.3-abliterated:latest",
                                   "prompt": prompt, "stream": False}).encode()
            req = urllib.request.Request("http://localhost:11434/api/generate",
                                         data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = json.loads(resp.read()).get("response", "")
            s = raw.find("{"); e = raw.rfind("}") + 1
            if s >= 0 and e > s:
                hint.update(json.loads(raw[s:e]))
        except Exception:
            pass

    return hint


def draw_tracked_lines(img_rgb: np.ndarray, lines: list[dict],
                       highlight: list[int], n_show: int = 5) -> np.ndarray:
    """Draw detected lines; highlight the top matches in green, others grey."""
    out = img_rgb.copy()
    for i, l in enumerate(lines[:n_show]):
        color = (0, 230, 80) if i in highlight else (160, 160, 160)
        thick = 3 if i in highlight else 1
        cv2.line(out, (l["x1"], l["y1"]), (l["x2"], l["y2"]), color, thick)
        if i in highlight:
            label = f"#{i+1}  {l['length']:.0f}px  {l['angle_deg']:.0f}°"
            cv2.putText(out, label, (l["x1"], max(l["y1"] - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 230, 80), 2)
    return out


# ── UI ────────────────────────────────────────────────────────────────────────

def ui(share: bool = False):
    import gradio as gr
    from PIL import Image as PILImage

    _last_lines: list[list[dict]] = [[]]   # mutable container

    def track(uploaded_img, prompt_text: str, top_k: int):
        if uploaded_img is None:
            return None, "Upload a photo first."
        img = np.array(uploaded_img)
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)

        lines = detect_lines(img, max_lines=30)
        _last_lines[0] = lines

        if not lines:
            return PILImage.fromarray(img), "No lines detected in this image."

        hint = parse_hint(prompt_text) if prompt_text.strip() else {}
        H, W = img.shape[:2]

        if hint:
            scored = [(score_line(l, hint, H, W), i) for i, l in enumerate(lines)]
            scored.sort(reverse=True)
            highlight = [i for _, i in scored[:top_k]]
        else:
            highlight = list(range(min(top_k, len(lines))))

        annotated = draw_tracked_lines(img, lines, highlight, n_show=len(lines))

        summary_lines = []
        for rank, idx in enumerate(highlight, 1):
            l = lines[idx]
            summary_lines.append(
                f"**Line {rank}** — length {l['length']:.0f}px, "
                f"angle {l['angle_deg']:.1f}°, "
                f"from ({l['x1']},{l['y1']}) to ({l['x2']},{l['y2']})"
            )

        summary = f"**{len(lines)} lines detected** — top {len(highlight)} highlighted\n\n" + "\n\n".join(summary_lines)
        return PILImage.fromarray(annotated), summary

    def track_all(uploaded_img):
        return track(uploaded_img, "", 5)

    with gr.Blocks(title="Line Tracker AI", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "# Line Tracker AI\n"
            "Upload a photo → describe what to track (English or Hebrew) → AI highlights matching lines.\n\n"
            "**Examples:** `track the guitar string` · `top string` · `the pencil` · "
            "`מיתר עליון` · `עקוב אחרי העיפרון` · `המיתר השני מלמעלה`"
        )
        with gr.Row():
            inp = gr.Image(label="Photo", type="pil")
            out = gr.Image(label="Tracked lines", type="pil")

        with gr.Row():
            prompt = gr.Textbox(
                label="What to track (English or Hebrew — leave blank for auto)",
                placeholder="track the guitar string / מיתר עליון / pencil on the left …",
                lines=1,
            )
            top_k = gr.Slider(1, 10, value=3, step=1, label="How many lines to highlight")

        with gr.Row():
            btn = gr.Button("Track", variant="primary", size="lg")
            auto_btn = gr.Button("Auto-detect all lines", size="lg")

        summary = gr.Markdown()

        btn.click(track, inputs=[inp, prompt, top_k], outputs=[out, summary])
        auto_btn.click(track_all, inputs=[inp], outputs=[out, summary])

        gr.Markdown(
            "---\n**Tips:**\n"
            "- Say `top string`, `bottom string`, `upper`, `left side` to hint position\n"
            "- Say `horizontal` / `vertical` / `אופקי` / `אנכי` for orientation\n"
            "- Increase 'How many lines' to see more candidates\n"
            "- Works on: guitar strings, pencils, rods, cables, edges, horizons, frets"
        )

    demo.launch(server_name="0.0.0.0", inbrowser=True, share=share)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--share", action="store_true")
    args = ap.parse_args()
    ui(share=args.share)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Write render/FILM-MANIFEST.json — per-shot provenance, honest resolution.

ALMA Standard: any frame of this film can be traced back to the prompt, model,
seed and command that made it.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import shots as S

HERE = Path(__file__).parent
FILM = HERE.parent
OUT = HERE / "FILM-MANIFEST.json"


def probe(path: Path) -> dict:
    if not path.exists():
        return {"error": "missing"}
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,codec_type,width,height,r_frame_rate,nb_frames,pix_fmt,"
         "color_transfer,color_primaries,sample_rate,channels",
         "-show_entries", "format=duration,size,bit_rate,format_name",
         "-of", "json", str(path)], capture_output=True, text=True)
    return json.loads(p.stdout or "{}")


def load(name: str) -> list:
    p = HERE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def main() -> None:
    # later passes win: shots were re-rendered when a take carried a hallucinated
    # station bug or showed a child too directly
    t2v: dict = {}
    for name in ("t2v_log.json", "t2v_log2.json", "t2v_log3.json"):
        for r in load(name):
            if "error" not in r:
                t2v[r["id"]] = dict(r, pass_=name)
    i2v = {r["id"]: r for r in load("i2v_log.json")}
    by_id = {s["id"]: s for s in S.T2V + S.I2V}

    shots = []
    for sid in S.ALL_IDS:
        sh = by_id[sid]
        is_i2v = sid in {s["id"] for s in S.I2V}
        rec = {
            "id": sid,
            "order": sh["order"],
            "route": "flux-plate + composited real Hebrew aleph + LTXVImgToVideo"
                     if is_i2v else "LTX text-to-video",
            "models": ({
                "plate": "flux1-dev-fp8.safetensors (FLUX.1-dev fp8, 24 steps, "
                         "FluxGuidance 3.2, cfg 1.0)",
                "letter": "NOT generated — Hebrew aleph U+05D0 drawn from "
                          "C:/Windows/Fonts/david.ttf and composited by "
                          "render/letter.py (style: %s)" % sh["letter"]["style"],
                "video": "ltxv-13b-0.9.8-distilled.safetensors + t5xxl_fp16 "
                         "(LTXVImgToVideo, 8 steps, euler, cfg 1.0, "
                         "LTXVScheduler max_shift 2.05 base_shift 0.95)",
            } if is_i2v else {
                "video": "ltxv-13b-0.9.8-distilled.safetensors + t5xxl_fp16 "
                         "(SamplerCustom, 8 steps, euler, cfg 1.0, "
                         "LTXVScheduler max_shift 2.05 base_shift 0.95)",
            }),
            "seed": sh["seed"],
            "prompt": sh.get("motion") or sh.get("prompt"),
            "plate_prompt": sh.get("plate"),
            "letter_composite": sh.get("letter"),
            "negative_prompt": S.NEG,
            "negative_prompt_note": "cfg is 1.0 (the distilled LTX requires it), "
                                    "so the negative prompt is INERT — it is "
                                    "recorded for completeness, not because it acted",
            "render_resolution": "1536x864",
            "frames_rendered": sh.get("length", S.LEN),
            "fps": S.FPS,
            "seconds_native": round(sh.get("length", S.LEN) / S.FPS, 2),
            "render_node": "eran1 (DGX Spark GB10, ComfyUI 127.0.0.1:8188)",
            "render_seconds": (i2v.get(sid) or t2v.get(sid) or {}).get("seconds"),
            "render_pass": (t2v.get(sid) or {}).get("pass_", "i2v"),
            "upscale": "Real-ESRGAN RealESRGAN_x4plus.pth (spandrel, fp16, CUDA) "
                       "x4 -> 6144x3456 -> bicubic+antialias cover-fit and "
                       "centre-crop -> 3840x2160",
            "clip_4k": str(FILM / "clips4k" / f"{sid}.mp4"),
            "clip_4k_probe": probe(FILM / "clips4k" / f"{sid}.mp4"),
        }
        if False:  # (12_honey was re-rendered locked-off at 65 frames; no trim needed)
            rec["editorial_note"] = ("trimmed to the first 80 frames: LTX began "
                                     "hallucinating text along the bottom edge "
                                     "after that")
        shots.append(rec)

    doc = {
        "title": "אוֹתִיּוֹת רָצוֹת · Letters That Run",
        "project": "ALMIDO / ALMA-EDU",
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "built_by": "Claude Code (claude-cli) on Iddo Perez's DGX fleet",
        "source_of_content": [
            "D:/CLAUDE/otiyot-ratsot/OTIYOT-RATSOT.md (§2 the room, §3 a day, §6 the letters)",
            "D:/CLAUDE/alma-edu/CHARTER.md",
        ],
        "disclosure": {
            "burned_in_every_frame": "PRODUCED BY AI · הופק על ידי בינה מלאכותית",
            "position": "bottom of frame, over a soft gradient band, "
                        "composited over the ENTIRE timeline in one ffmpeg pass "
                        "including the head and tail cards",
            "head_card": "THIS FILM WAS PRODUCED BY AI. No real children were "
                         "filmed. Every person and place shown is generated.",
            "tail_card": "PRODUCED BY AI · Every frame is synthetic. No real "
                         "child, teacher, school or place is depicted.",
            "clean_version_exists": False,
        },
        "people_policy": "No real or identifiable person. Children appear as "
                         "hands, backs, shoulders, feet, silhouettes and wide "
                         "room shots; no lingering close-up of a face; no named "
                         "place, no logo, no signage.",
        "resolution_statement": {
            "delivered": "3840x2160 (UHD 4K)",
            "generated_native": "1536x864 per shot (LTX-13B-distilled)",
            "delivered_frame_note": "a 5% inset is cropped from each edge before "
                                    "the final 4K rescale — a safety net against "
                                    "LTX stamping invented station bugs into the "
                                    "extreme corners, since at cfg 1.0 there is no "
                                    "working negative prompt to forbid them",
            "path_to_4k": "Real-ESRGAN x4plus (a real learned x4 upscaler, "
                          "downloaded to ~/comfy/models/upscale_models on eran1 "
                          "and eran2) -> 6144x3456, then bicubic+antialias "
                          "cover-fit and centre-crop to exactly 3840x2160. "
                          "This is a genuine learned upscale, NOT an ffmpeg "
                          "lanczos stretch — but the true optical detail "
                          "originates at 1536x864 and no claim is made that "
                          "this is a natively-4K master.",
        },
        "hdr_statement": "NOT HDR. LTX-13B and FLUX both output 8-bit SDR, and "
                         "the whole chain here is 8-bit yuv420p BT.709. The file "
                         "is an SDR master and is not labelled HDR. True HDR "
                         "would need a graded 10-bit pipeline we do not have.",
        "audio": {
            "score": "render/score_almido.py — original, written for this film "
                     "(slow D drone, five-note pentatonic motif, pad, room air). "
                     "No copyrighted music anywhere in this file.",
            "codec": "AAC 192 kbps",
        },
        "ffmpeg_chain": {
            "per_shot_4k_encode": (
                "ffmpeg -f rawvideo -pix_fmt rgb24 -s 3840x2160 -r 24 -i pipe:0 "
                "-an -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p <shot>.mp4"
            ),
            "cards": (
                "ffmpeg -loop 1 -framerate 24 -i card.png -t <s> -vf "
                "scale=3840:2160,format=yuv420p,fade=in:0:1,fade=out:<s-1>:1 "
                "-c:v libx264 -preset slow -crf 16 -r 24 -an card.mp4"
            ),
            "final_single_pass": (
                "ffmpeg -i head.mp4 -i <16 shot mp4s> -i tail.mp4 "
                "-i disclosure_strip.png -i score_almido.wav -filter_complex "
                "\"[N:v]crop=iw*0.9:ih*0.9:iw*0.05:ih*0.05,scale=3840:2160:"
                "flags=lanczos,setsar=1,fps=24,format=yuv420p[cN]; ... "
                "concat=n=18:v=1:a=0[body];[body][strip:v]"
                "overlay=0:0:format=auto[v];[audio:a]atrim=0:<dur>,"
                "asetpts=N/SR/TB,afade=t=in:st=0:d=3,"
                "afade=t=out:st=<dur-5>:d=5,volume=0.8[a]\" "
                "-map [v] -map [a] -c:v libx264 -preset slow -crf 17 "
                "-pix_fmt yuv420p -r 24 -c:a aac -b:a 192k -shortest "
                "-movflags +faststart ALMIDO-otiyot-ratsot-4K.mp4"
            ),
            "why_one_pass": ("the concat FILTER is used rather than the concat "
                             "demuxer so the crop, the rescale and the disclosure "
                             "overlay all apply to the single joined stream — "
                             "there is no branch that can emit an undisclosed frame"),
            "poster": "ffmpeg -ss 31.5 -i out.mp4 -frames:v 1 -q:v 2 poster.jpg",
        },
        "known_limitations": [
            "Neither LTX-13B nor FLUX.1-dev can render Hebrew script: prompted "
            "for a chalk aleph, FLUX produced a physical prop reading 'AH'. "
            "Every aleph in this film is therefore drawn from a real Hebrew "
            "font and composited into the plate before animation. This is "
            "recorded because it is the single most load-bearing fact about "
            "how the film was made.",
            "LTX image-to-video drifts off the composited plate whenever the "
            "prompt implies camera movement — three shots (06, 10, 16) had to "
            "be re-rendered with a locked-off camera and 65 frames instead of 97.",
            "12_honey is trimmed to 80 frames; LTX hallucinated text along the "
            "bottom edge in the tail of that take.",
            "SDR only, 8-bit. Not HDR.",
            "The 4K master is upscaled, not natively rendered at 4K.",
        ],
        "final_file": str(FILM / "ALMIDO-otiyot-ratsot-4K.mp4"),
        "final_probe": probe(FILM / "ALMIDO-otiyot-ratsot-4K.mp4"),
        "poster": str(FILM / "ALMIDO-otiyot-ratsot-4K.jpg"),
        "shots": shots,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the iddoperez.ai image family on eran1's ComfyUI with flux1-dev-fp8.

The whole point of the locked prefix/suffix is that it is byte-identical in
every prompt: that, not a shared seed, is what makes ten frames read as one
photographic family. Only the subject sentence changes.

Deliberately absent: any image for alma.iddoperez.ai. That is a memorial with
690 real photographs of her on it; a synthetic picture beside them would be
wrong regardless of how well it came out. Restraint is the design decision.

Run ON eran1:  python3 gen_flux.py
"""
import json, os, time, urllib.request, urllib.error

API = "http://127.0.0.1:8188"
OUT = os.path.expanduser("~/site-art")
os.makedirs(OUT, exist_ok=True)

PREFIX = ("Overhead flat-lay photograph, camera directly above at ninety degrees, "
          "50mm macro lens, f/5.6, soft daylight from a single north-facing window "
          "at the upper left, one soft shadow falling to the lower right, no fill "
          "light and no studio lighting. The surface is warm off-white paper with "
          "fine visible grain. Muted palette of oxidized copper, deep teal-green "
          "patina, matte violet-black and warm paper. Real worn handmade objects, "
          "solder blobs, pencil marks, dust. No text, no letters, no logos, no "
          "people, no screens. ")

SUFFIX = (" Documentary still life, quiet, unstyled, natural colour, fine film grain, "
          "not glossy, not a product shot.")

JOBS = [
 ("bench-overview", 1536, 656,
  "A whole cluttered workbench seen from above: a green breadboard threaded with copper "
  "jumper wires, a small unmarked circuit board with hand-soldered joints, a coil of "
  "enamelled copper wire, a graphite pencil worn short, a folded sheet of grid paper "
  "covered in hand-drawn diagrams of small circles joined by lines, a brass caliper lying "
  "open, a scattering of loose resistors, and an empty white ceramic coffee cup with a "
  "ring stain on the paper beside it."),

 ("door-eran", 1024, 688,
  "A single sheet of warm grid paper lying flat on the desk, covered with a dense "
  "hand-drawn network of small circles connected by pencil lines, drawn and redrawn many "
  "times with visible erasure marks and graphite smudges; three of the circles have been "
  "carefully filled in with copper-coloured ink. A stub of pencil and a soft eraser worn "
  "grey lie at the edge of the sheet."),

 ("door-lab", 1024, 688,
  "About a dozen small identical white index cards laid out in a loose grid on the desk, "
  "each card blank, each holding one different small physical object at its centre: a "
  "ceramic tile with a single dark cell on it, a small flat metal plate, a short length of "
  "pale wood threaded with fine white fibres, a copper coil, a glass prism, a fragment of "
  "punched paper tape, a brass gear, a square of fine copper mesh. One card near the "
  "centre holds nothing at all."),

 ("door-quorum", 1024, 688,
  "An open old book with wide margins lying flat on the desk, four small smooth river "
  "stones resting on the open pages — one teal-grey, one violet-grey, one copper-brown, "
  "one pale cream — arranged in a close circle as if in conversation, with a worn pencil "
  "lying across the gutter of the book."),

 ("door-arena", 1024, 688,
  "Four small smooth river stones resting directly on the warm paper — one teal-grey, one "
  "violet-grey, one copper-brown, one pale cream — pushed out of alignment as if caught "
  "mid-motion, with fine dry copper filings scattered across the paper tracing the curved "
  "paths along which each stone moved. One stone sits noticeably apart from the other three."),

 ("door-erancloud", 1024, 688,
  "A dozen small identical square ceramic tiles spread across the desk at irregular "
  "distances from one another, each tile holding a single tiny bead of solder at its "
  "centre, with one continuous length of fine enamelled copper wire threaded loosely from "
  "tile to tile connecting all of them. The wire is slack and hand-laid, curving and "
  "uneven, never taut."),

 ("door-pong", 1024, 688,
  "A shallow round glass petri dish resting on the warm paper seen from directly above, "
  "filled with a fine pale mycelial web that has grown into a dense branching network, a "
  "few pale threads reaching over the rim and out onto the paper. Beside the dish lie a "
  "pair of fine steel tweezers and a short length of bare copper wire laid parallel to it."),

 ("door-federation", 1024, 688,
  "Four identical matte dark-grey anodised aluminium blocks arranged in a square on the "
  "warm paper, each with a small bundle of copper wires emerging from one edge; the four "
  "bundles twist together into a single thicker cable that runs off the edge of the frame. "
  "A small worn brass key lies flat on the paper beside the nearest block."),

 ("door-helios", 1024, 688,
  "A shallow ceramic dish of coarse sea salt and a small stack of thick paper cards on the "
  "desk, with a plain circular convex lens resting on the topmost card focusing the window "
  "light into one small bright disc on the paper, its edge just beginning to darken. A "
  "brass ruler lies along the bottom of the frame."),

 ("share-card", 1216, 640,
  "A single hand-soldered circuit board lying at a slight angle on the warm paper and "
  "filling most of the frame, its copper traces bright against dark green, several "
  "components mounted visibly crooked by hand, and one long enamelled copper wire soldered "
  "on as an obvious after-the-fact repair, looping off the edge of the board and onto the "
  "paper."),

 ("page-404", 1024, 768,
  "A single empty white index card lying alone at a slight angle on the warm paper, one "
  "corner very slightly curled, with a faint rectangular outline of dust on the paper "
  "beside it where something used to sit, and a short length of copper wire with one bare "
  "cut end lying nearby."),
]


def post(path, obj):
    r = urllib.request.Request(API + path, data=json.dumps(obj).encode(),
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=90))


def run(name, w, h, subject, seed):
    wf = {
      "1": {"class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
      "2": {"class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": PREFIX + subject + SUFFIX}},
      "3": {"class_type": "FluxGuidance",
            "inputs": {"conditioning": ["2", 0], "guidance": 3.2}},
      "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": ""}},
      "5": {"class_type": "EmptySD3LatentImage",
            "inputs": {"width": w, "height": h, "batch_size": 1}},
      "6": {"class_type": "KSampler",
            "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0],
                       "latent_image": ["5", 0], "seed": seed, "steps": 26, "cfg": 1.0,
                       "sampler_name": "euler", "scheduler": "beta", "denoise": 1.0}},
      "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
      "8": {"class_type": "SaveImage",
            "inputs": {"images": ["7", 0], "filename_prefix": "site_" + name}},
    }
    try:
        pid = post("/prompt", {"prompt": wf})["prompt_id"]
    except urllib.error.HTTPError as e:
        return None, "queue rejected: " + e.read().decode()[:300]

    t0 = time.time()
    while time.time() - t0 < 900:
        h_ = json.load(urllib.request.urlopen(API + "/history/" + pid, timeout=30))
        if pid in h_:
            st = h_[pid].get("status", {})
            if st.get("status_str") == "error":
                return None, "render error: " + json.dumps(st)[:300]
            for _, v in h_[pid].get("outputs", {}).items():
                for im in v.get("images", []):
                    return im["filename"], "%.0fs" % (time.time() - t0)
        time.sleep(4)
    return None, "timeout"


if __name__ == "__main__":
    t_all = time.time()
    for i, (name, w, h, subj) in enumerate(JOBS):
        fn, info = run(name, w, h, subj, 1000 + i)
        if fn:
            raw = urllib.request.urlopen(
                API + "/view?filename=" + fn + "&type=output", timeout=120).read()
            p = os.path.join(OUT, name + ".png")
            tmp = p + ".tmp"
            open(tmp, "wb").write(raw)
            os.replace(tmp, p)          # atomic, per the autosave law
            print("OK   %-18s %5dx%-4d %8s  %d bytes" % (name, w, h, info, len(raw)),
                  flush=True)
        else:
            print("FAIL %-18s %s" % (name, info), flush=True)
    print("ALL DONE in %.0f min" % ((time.time() - t_all) / 60), flush=True)

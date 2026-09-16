"""gen_plates.py — generate 4K chapter plates for the ALMAWARE encyclopedia on eran2's ComfyUI.

FLUX.1-dev fp8 (checkpoint loader), 1536x864 latent -> Lanczos upscale to 3840x2160 in post.
Run from the PC; ComfyUI is reached over the SSH tunnel that this script opens itself is NOT
assumed — it talks to http://127.0.0.1:8288 which you forward with:
    ssh -N -L 8288:127.0.0.1:8188 eran2
"""
import json
import time
import urllib.request
import urllib.error
import pathlib
import sys

COMFY = "http://127.0.0.1:8288"
OUT = pathlib.Path(r"D:\CLAUDE\eran-encyclopedia\plates")
OUT.mkdir(parents=True, exist_ok=True)

# one plate per chapter: (slug, prompt)
PLATES = [
    ("cover",
     "a single drop of water suspended in bright air, a red laser beam refracting through it and "
     "projecting a vast luminous circle of microscopic life onto a concrete wall, bright airy museum gallery, white walls, daylight, "
     "extreme macro, volumetric light, cinematic, ultra detailed"),
    ("water-computing",
     "an immense wall of transparent glass tubes and brass valves filled with red liquid, water "
     "levels forming a pattern like a neural network, 1950s laboratory, brass floats and cut perspex "
     "cams, bright daylight, white laboratory, architectural photography, ultra detailed"),
    ("tape-brain",
     "a long perforated film tape threaded through a machine, thousands of tiny precise holes in "
     "rows, backlit so light beams pass through the holes, jacquard loom aesthetic meets modern lab, "
     "bright white studio background, crisp daylight, cinematic macro"),
    ("physical-weights",
     "macro photograph of a hand-built analog neuron: graphite rods, silver wire, a drop of "
     "electrolyte between two copper plates, glowing faintly, clean white laboratory bench, bright daylight, scientific "
     "photography, extreme detail"),
    ("eran-child",
     "an abstract portrait of a machine learning to speak: waveforms of a child's voice becoming "
     "letters becoming light, bright white ground with indigo and amber accents, no faces, generative art, elegant, "
     "museum print quality"),
    ("beit-din",
     "an ancient study hall rendered as a circuit: stone arches, open books, and glowing argument "
     "lines connecting seats like synapses, bright morning light through high windows, painterly, reverent"),
    ("voice-keshev",
     "a studio microphone dissected into its signal path, floating exploded-view components over a "
     "clean white surface with a Hebrew waveform threading through them, technical illustration meets "
     "photography, cyan and warm grey"),
    ("darwish-memorial",
     "a single candle beside a mixing desk at dawn, a sound wave rising from the flame into the sky, "
     "quiet, restrained, no text, memorial photography, soft light, soft bright dawn light"),
    ("fleet-engineering",
     "four identical black computers connected by thick fiber cables glowing faintly, arranged like "
     "a constellation on a bright white floor, clean studio light, data-center aesthetics, precise, cold light "
     "with one warm accent"),
    ("optics-sensing",
     "a paperclip bent into a tiny loop holding a single water droplet, a laser passing through it, "
     "the projected image of paramecia visible on the wall behind, tabletop science, bright tabletop, daylight macro"),
    ("materials-safety",
     "a pressure cooker on a workbench with a 3D-printed white polypropylene bottle beside it, steam, "
     "clean industrial still life, honest daylight, product photography"),
    ("moral-architecture",
     "a set of brass scales weighing light against light, engraved with tiny Hebrew letters, on a "
     "white stone plinth in bright daylight, sculptural, solemn"),
]

NEG = "text, watermark, signature, logo, blurry, low quality, deformed, extra limbs, cartoon, meme"


def build(prompt: str, seed: int) -> dict:
    """A minimal FLUX-via-CheckpointLoaderSimple graph (works with flux1-dev-fp8.safetensors)."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "flux1-dev-fp8.safetensors"}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": NEG, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 1536, "height": 864, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": 20, "cfg": 1.0, "sampler_name": "euler",
                         "scheduler": "simple", "denoise": 1.0,
                         "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "alma_plate", "images": ["6", 0]}},
    }


def post(path: str, payload: dict):
    req = urllib.request.Request(COMFY + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def get(path: str):
    with urllib.request.urlopen(COMFY + path, timeout=60) as r:
        return json.loads(r.read())


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for i, (slug, prompt) in enumerate(PLATES):
        if only and only != slug:
            continue
        target = OUT / f"{slug}.png"
        if target.exists():
            print(f"skip {slug} (exists)")
            continue
        pid = post("/prompt", {"prompt": build(prompt, 1000 + i)})["prompt_id"]
        print(f"queued {slug} -> {pid}", flush=True)
        for _ in range(360):                     # up to 30 min per plate
            time.sleep(5)
            h = get(f"/history/{pid}")
            if pid in h:
                outs = h[pid]["outputs"]
                for node in outs.values():
                    for img in node.get("images", []):
                        url = (f"/view?filename={urllib.parse.quote(img['filename'])}"
                               f"&subfolder={urllib.parse.quote(img.get('subfolder',''))}"
                               f"&type={img.get('type','output')}")
                        with urllib.request.urlopen(COMFY + url, timeout=120) as r:
                            target.write_bytes(r.read())
                        print(f"  saved {target} ({target.stat().st_size//1024} KB)", flush=True)
                break
        else:
            print(f"  TIMEOUT on {slug}")


if __name__ == "__main__":
    import urllib.parse  # noqa: F401  (used in main)
    main()

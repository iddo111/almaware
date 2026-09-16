import json, time, urllib.request, urllib.parse, pathlib, sys
COMFY="http://127.0.0.1:8288"; OUT=pathlib.Path(r"D:\CLAUDE\eran-encyclopedia\future-plates"); OUT.mkdir(exist_ok=True)
NEG="text, watermark, blurry, low quality, deformed, cartoon, meme"
PLATES=[
 ("ada","a Victorian brass mechanical computing engine with punched cards, a beam of light turning gears into musical notes and letters floating upward, bright airy museum gallery, white walls, elegant, cinematic macro, ultra detailed"),
 ("turing","an abstract portrait of a thinking machine as a question mark made of relay switches and paper tape, bright white studio, soft daylight, blue and warm grey, museum print, elegant, no faces"),
 ("history","a bright timeline as a river of light flowing from a single glowing perceptron node through a dark winter into a blooming network, white gallery, luminous, generative art, museum quality"),
 ("world-models","an agent dreaming its own world: a small figure watching a glowing latent sphere that contains a miniature predicted landscape, bright airy space, indigo and amber accents on white, elegant"),
 ("speech","sound becoming a mouth: waveforms of raw audio curling into the shape of vocal tract and lips, bright white studio background, crisp daylight, cyan and warm grey, technical illustration meets photography"),
 ("audio","a machine voice visualized as a luminous ribbon of discrete audio tokens reassembling into a singing waveform, bright gallery, warm light, elegant generative art"),
 ("embodiment","a small friendly robot learning to walk in a bright sunlit lab, motion-blur of many attempts overlaid, data flowing back into it as light, clean daylight, hopeful, ultra detailed"),
]
def build(p,seed): return {"1":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":"flux1-dev-fp8.safetensors"}},"2":{"class_type":"CLIPTextEncode","inputs":{"text":p,"clip":["1",1]}},"3":{"class_type":"CLIPTextEncode","inputs":{"text":NEG,"clip":["1",1]}},"4":{"class_type":"EmptyLatentImage","inputs":{"width":1536,"height":864,"batch_size":1}},"5":{"class_type":"KSampler","inputs":{"seed":seed,"steps":20,"cfg":1.0,"sampler_name":"euler","scheduler":"simple","denoise":1.0,"model":["1",0],"positive":["2",0],"negative":["3",0],"latent_image":["4",0]}},"6":{"class_type":"VAEDecode","inputs":{"samples":["5",0],"vae":["1",2]}},"7":{"class_type":"SaveImage","inputs":{"filename_prefix":"future","images":["6",0]}}}
def post(pl):
    r=urllib.request.Request(COMFY+"/prompt",data=json.dumps({"prompt":pl}).encode(),headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r,timeout=60).read())["prompt_id"]
for i,(slug,p) in enumerate(PLATES):
    t=OUT/f"{slug}.png"
    if t.exists(): print("skip",slug); continue
    pid=post(build(p,3000+i)); print("queued",slug,flush=True)
    for _ in range(300):
        time.sleep(5); h=json.loads(urllib.request.urlopen(COMFY+f"/history/{pid}",timeout=60).read())
        if pid in h:
            for node in h[pid]["outputs"].values():
                for img in node.get("images",[]):
                    u=f"/view?filename={urllib.parse.quote(img['filename'])}&subfolder={urllib.parse.quote(img.get('subfolder',''))}&type={img.get('type','output')}"
                    t.write_bytes(urllib.request.urlopen(COMFY+u,timeout=120).read()); print("  saved",slug,t.stat().st_size//1024,"KB",flush=True)
            break

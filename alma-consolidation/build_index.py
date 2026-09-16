#!/usr/bin/env python3
# ALMA Consolidation — classify the drive scans into products/library/personal/junk,
# dedup, write index.json, and (with --copy) copy PRODUCTS into D:\MASTER-CONSOLIDATION.
# Personal media + junk NEVER enter the index (the hub is Tailscale-exposed).
import os, sys, json, shutil

SP = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\f3045f13-75e5-492d-8e5b-a8fa2bd4f974\scratchpad"
SCANS = ["scan_C.txt", "scan_D.txt", "scan_E.txt", "scan_other.txt", "scan_F.txt"]
OUT = r"D:\CLAUDE\alma-consolidation"
MASTER = r"D:\MASTER-CONSOLIDATION"
DO_COPY = "--copy" in sys.argv

EXT_CAT = {}
for e in ("mp4", "mov", "mkv", "webm", "m4v", "avi"): EXT_CAT[e] = "Movies"
for e in ("mp3", "wav", "flac"): EXT_CAT[e] = "Audio"
for e in ("pdf", "epub", "mobi", "azw3"): EXT_CAT[e] = "Books"
for e in ("stl", "gcode", "3mf", "step", "f3d"): EXT_CAT[e] = "Builds"
for e in ("docx", "pptx"): EXT_CAT[e] = "Docs"

JUNK = ("photorec", "$recycle", "system volume", "/appdata/", "node_modules", "/.git/",
        "buildtools", "\\venv\\", "/venv/", "site-packages", "__pycache__",
        "/windows/", "program files", "/.cache/", "e_photorec", "c_photorec",
        "popup-evidence", "popup_incident", "popup_capture", "_proof", "proof_recording")
# PERSONAL includes SACRED-PRIVATE Alma family footage — must never reach the Tailscale hub
PERSONAL = ("/downloads/", "a70_backup", "a70-backup", "/a70/", "armand-backup",
            "burt goldman", "sasha", "excogi", "exploited", "andor", "פאודה", "250gb ssd",
            "private_sources", "alma_message", "desktop_alma",
            "voice_corpus", "\\dictation\\", "/dictation/", "recorder\\recordings", "recorder/recordings")
PRODUCT = ("almaware", "movie-archive", "/d/claude/perceptron-movie", "/darwish/generated",
           "/f/claude/ai-", "/f/claude/alma", "/f/claude/eran", "/desktop/grok-movies",
           "/desktop/grok_products", "/desktop/movies/", "/desktop/alma", "/desktop/eran",
           "/desktop/almaware", "/alma-", "eran-nursery", "alma-deliverables")
PRODUCT_ROOT = "/d/claude/"
PRODUCT_ROOT_EXCLUDE = ("/d/claude/archive/", "/d/claude/_archive/", "/d/claude/backups/",
                        "/d/claude/build", "/d/claude/c_photorec", "/d/claude/node_modules")

def classify(p):
    lp = p.lower()
    if any(m in lp for m in JUNK): return "JUNK"
    if any(m in lp for m in PERSONAL): return "PERSONAL"
    if any(m in lp for m in PRODUCT): return "PRODUCT"
    if lp.startswith(PRODUCT_ROOT) and not any(m in lp for m in PRODUCT_ROOT_EXCLUDE):
        return "PRODUCT"
    return "LIBRARY"

def cat_of(p):
    ext = p.rsplit(".", 1)[-1].lower() if "." in p else ""
    return EXT_CAT.get(ext, "Docs")

seen = set()
buckets = {"PRODUCT": [], "LIBRARY": [], "PERSONAL": 0, "JUNK": 0}
dupes = 0
for s in SCANS:
    fp = os.path.join(SP, s)
    if not os.path.exists(fp): continue
    for line in open(fp, encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        if "\t" not in line: continue
        size_s, path = line.split("\t", 1)
        try: size = int(size_s)
        except: continue
        if size == 0: continue  # skip broken 0-byte stubs
        # normalize git-bash path -> windows drive path
        wp = path
        if path[:3].lower() in ("/c/", "/d/", "/e/", "/f/"):
            wp = path[1].upper() + ":" + path[2:].replace("/", "\\")
        b = classify(path)
        if b in ("PERSONAL", "JUNK"):
            buckets[b] += 1
            continue
        key = (os.path.basename(path).lower(), size)
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        buckets[b].append({"path": wp, "size": size, "cat": cat_of(path)})

# summary
def gb(n): return round(n / 1073741824, 2)
print("=== CLASSIFICATION (dry-run%s) ===" % (" + COPY" if DO_COPY else ""))
print("PERSONAL excluded:", buckets["PERSONAL"], " JUNK excluded:", buckets["JUNK"], " dupes skipped:", dupes)
for b in ("PRODUCT", "LIBRARY"):
    items = buckets[b]
    tot = sum(i["size"] for i in items)
    print("\n%s: %d files, %.2f GB" % (b, len(items), gb(tot)))
    bycat = {}
    for i in items:
        bycat.setdefault(i["cat"], [0, 0])
        bycat[i["cat"]][0] += 1; bycat[i["cat"]][1] += i["size"]
    for c, (n, sz) in sorted(bycat.items(), key=lambda x: -x[1][1]):
        print("   %-8s %4d files  %.2f GB" % (c, n, gb(sz)))

print("\n=== sample PRODUCT paths (verify these are really your work) ===")
for i in buckets["PRODUCT"][:25]:
    print("  [%s] %s" % (i["cat"], i["path"]))

# write index
os.makedirs(OUT, exist_ok=True)
index = {"products": buckets["PRODUCT"], "library": buckets["LIBRARY"]}
with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False)
print("\nindex.json written:", os.path.join(OUT, "index.json"))

if DO_COPY:
    copied = ccount = 0
    for i in buckets["PRODUCT"]:
        dst_dir = os.path.join(MASTER, i["cat"])
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(i["path"]))
        if os.path.exists(dst) and os.path.getsize(dst) == i["size"]:
            continue
        if os.path.exists(dst):
            base, ext = os.path.splitext(os.path.basename(i["path"]))
            dst = os.path.join(dst_dir, "%s_%d%s" % (base, i["size"], ext))
        try:
            shutil.copy2(i["path"], dst); copied += 1; ccount += i["size"]
        except Exception as e:
            print("  copy fail:", i["path"], e)
    print("\nCOPIED %d product files (%.2f GB) into %s" % (copied, gb(ccount), MASTER))

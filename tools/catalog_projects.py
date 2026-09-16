"""Cheap mechanical catalog of every project dir - README/top-file first line + status.
Applies feedback_code_over_agents_for_heavy_work: code does the reading, not tokens."""
import os, json, time, glob
BASES = ["D:/CLAUDE", "D:/grok"]
JUNK = {"__pycache__","node_modules",".git","_build","build","builds","dist","tmp","output",
        "downloads",".pytest_cache",".wrangler","_codex_pycache","patches"}
def first_line(path, n=3):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines=[l.strip() for l in f.readlines()[:40] if l.strip() and not l.strip().startswith(("#!","<!--","```"))]
        return " ".join(lines[:n])[:180]
    except Exception: return ""
def catalog(base):
    out=[]
    for d in sorted(os.listdir(base)):
        p=os.path.join(base,d)
        if not os.path.isdir(p): continue
        if d in JUNK or d.startswith("."):
            out.append({"dir":d,"desc":"","status":"junk/hidden"}); continue
        # most informative file
        desc=""; status="unknown"
        for pat in ["README.md","readme.md","README.txt","*.md"]:
            g=sorted(glob.glob(os.path.join(p,pat)))
            if g: desc=first_line(g[0]); break
        if not desc:
            for pat in ["main.py","server.py","app.py","index.html","package.json","*.py","*.js"]:
                g=sorted(glob.glob(os.path.join(p,pat)))
                if g: desc=first_line(g[0]); break
        try:
            files=os.listdir(p); nf=len(files)
            status = ("empty" if nf==0 else "wip" if nf<3 else "project")
        except Exception: nf=0
        out.append({"dir":d,"desc":desc or "(no readable top file)","status":status,"n":nf})
    return out
res={}
for b in BASES:
    if os.path.isdir(b): res[b]=catalog(b)
open("D:/CLAUDE/PROJECT-CATALOG.json","w",encoding="utf-8").write(json.dumps(res,ensure_ascii=False,indent=1))
# readable report
with open("D:/CLAUDE/PROJECT-CATALOG.md","w",encoding="utf-8") as f:
    f.write("# Project Catalog (auto, %s)\n\n"%time.strftime("%Y-%m-%d"))
    for b,items in res.items():
        real=[x for x in items if x["status"] not in ("junk/hidden","empty")]
        f.write("## %s — %d dirs, %d real projects\n\n"%(b,len(items),len(real)))
        for x in real:
            f.write("- **%s** — %s\n"%(x["dir"], x["desc"]))
        f.write("\n")
tot=sum(len([x for x in v if x['status'] not in('junk/hidden','empty')]) for v in res.values())
print("catalogued %d real projects across %s"%(tot,list(res.keys())))
print("wrote PROJECT-CATALOG.json + PROJECT-CATALOG.md")

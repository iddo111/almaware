import json, pathlib, html

jp = r"C:\Users\<user>\.claude\projects\D--CLAUDE\f3045f13-75e5-492d-8e5b-a8fa2bd4f974\subagents\workflows\wf_3001f8f4-699\journal.jsonl"

def U(s):
    return html.unescape(s) if isinstance(s, str) else (s if s is not None else "")

domains, dossier = [], None
for line in pathlib.Path(jp).read_text(encoding="utf-8", errors="replace").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception:
        continue
    v = d.get("value") or d.get("result") or d.get("output") or d
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            continue
    if not isinstance(v, dict):
        continue
    if "encyclopedia_md" in v:
        dossier = v
    elif "domain" in v and "key_papers" in v:
        domains.append(v)

print("found domains:", len(domains), " dossier:", bool(dossier))

md = ["# ERAN - Research Encyclopedia & Movie Source Dossier",
      "",
      "*le-zichrah shel Alma z\"l. Built by a 9-agent Opus council, 2026-08-14 - the knowledge foundation for ERAN and the Perceptron movie.*",
      ""]

if dossier:
    if dossier.get("top_10_must_read"):
        md += ["## Top 10 Must-Read", ""]
        for i, x in enumerate(dossier["top_10_must_read"], 1):
            md.append(str(i) + ". " + U(x))
        md.append("")
    if dossier.get("movie_source_shortlist"):
        md += ["## Movie Source Shortlist", ""]
        for x in dossier["movie_source_shortlist"]:
            md.append("- " + U(x))
        md.append("")
    if dossier.get("encyclopedia_md"):
        md += ["", "---", "", U(dossier["encyclopedia_md"])]

md += ["", "", "---", "", "# Full Domain Entries", ""]
for e in domains:
    md += ["", "## " + U(e.get("domain", "")), "", U(e.get("overview", ""))]
    for label, key in [("Key papers", "key_papers"), ("Best books", "best_books"), ("Documentaries / films", "documentaries_films")]:
        items = e.get(key)
        if not items:
            continue
        md += ["", "**" + label + "**"]
        for it in items:
            if key == "key_papers":
                md.append("- **" + U(it.get("title")) + "** (" + U(it.get("authors_year", "")) + ") - " + U(it.get("why", "")) + "  " + str(it.get("url", "") or ""))
            elif key == "best_books":
                md.append("- *" + U(it.get("title")) + "* - " + U(it.get("author", "")) + ": " + U(it.get("why", "")))
            else:
                md.append("- " + U(it.get("title")) + " (" + U(it.get("year", "")) + ") - " + U(it.get("why", "")))
    if e.get("why_it_matters_for_eran"):
        md += ["", "*Why it matters for ERAN:* " + U(e["why_it_matters_for_eran"])]

out = "\n".join(md)
p = r"D:\CLAUDE\eran-encyclopedia\ERAN-Research-Encyclopedia.md"
pathlib.Path(p).write_text(out, encoding="utf-8")
print("MD chars:", len(out), "->", p)

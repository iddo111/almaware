#!/usr/bin/env python3
"""Build an Obsidian vault out of Claude's memory -- the second brain, made visible.

Iddo, 2026-08-29, after Karpathy's LLM-wiki video: "תעשה לי וויקי כזה של נוטס עם אובסידיאן".

The memory already IS an LLM wiki in structure: one fact per file, [[wikilinks]] between
them, MEMORY.md as the index. What it is not is *visible* -- 394 notes he has never been
able to see, walk, or search as a graph. This makes them a vault.

WHERE IT IS NOT: D:\\CLAUDE. That folder is a git repo, and these notes carry medical,
family, financial and legal material. There has already been one PII leak to GitHub in
this project's history. The vault lives outside the repo and carries its own .gitignore.

WHAT IT DOES NOT DO: invent. Every note is a memory file that already existed; the only
things written fresh are the index pages, and they say so.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from collections import Counter, defaultdict

MEM = r"C:\Users\<user>\.claude\projects\D--CLAUDE\memory"
VAULT = r"D:\ALMA-Second-Brain"

TYPE_DIR = {
    "user": "01 Who",
    "feedback": "02 Laws",
    "project": "03 Projects",
    "reference": "04 Reference",
}
OTHER_DIR = "05 Unfiled"
INDEX_DIR = "00 Index"

LINK_RE = re.compile(r"\[\[([^\]|#]+)")


def parse(path):
    """Split a memory file into (frontmatter dict, body). Tolerant by design: a
    malformed header must not lose the note."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    fm, body = {}, raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            head = raw[3:end]
            body = raw[end + 4:].lstrip("\n")
            key = None
            for line in head.splitlines():
                if not line.strip():
                    continue
                m = re.match(r"^(\w[\w-]*):\s*(.*)$", line)
                if m:
                    key = m.group(1)
                    fm[key] = m.group(2).strip().strip('"')
                elif line.startswith("  ") and ":" in line:
                    k2, v2 = line.strip().split(":", 1)
                    fm[k2.strip()] = v2.strip().strip('"')
    return fm, body


def main():
    if not os.path.isdir(MEM):
        raise SystemExit(f"memory not found: {MEM}")

    files = sorted(f for f in os.listdir(MEM) if f.endswith(".md"))
    notes, skipped = [], []
    for f in files:
        if f == "MEMORY.md":
            continue
        fm, body = parse(os.path.join(MEM, f))
        stem = os.path.splitext(f)[0]
        name = fm.get("name") or stem
        typ = (fm.get("type") or "").strip().lower()
        if typ not in TYPE_DIR:
            typ = ""
        notes.append({
            "file": f, "stem": stem, "name": name,
            "desc": fm.get("description", ""), "type": typ, "body": body,
            "links": LINK_RE.findall(body),
        })

    # --- lay out the vault
    # 2026-08-31 SCAR: this used to be shutil.rmtree(VAULT). An Explorer window --
    # or the builder's own shell cwd -- holds the root, rmtree deletes the CONTENTS
    # and then dies on the root rmdir, and on 08-31 that half-death ate the builder
    # itself (it lived inside the vault; it now lives in D:\CLAUDE\tools, in git).
    # Clear the contents, never the root -- and never this script if a copy is here.
    if os.path.isdir(VAULT):
        for entry in os.listdir(VAULT):
            if entry == "build_vault.py":
                continue
            p = os.path.join(VAULT, entry)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except OSError:
                    pass
    for d in list(TYPE_DIR.values()) + [OTHER_DIR, INDEX_DIR, ".obsidian"]:
        os.makedirs(os.path.join(VAULT, d), exist_ok=True)

    # Obsidian resolves [[X]] anywhere in the vault, so the folder split is for
    # humans only -- links keep working across it.
    known = {n["stem"] for n in notes} | {n["name"] for n in notes}
    counts = Counter()
    backlinks = defaultdict(set)
    broken = Counter()

    for n in notes:
        folder = TYPE_DIR.get(n["type"], OTHER_DIR)
        counts[folder] += 1
        tags = ["memory"] + ([n["type"]] if n["type"] else ["unfiled"])
        header = [
            "---",
            f'title: "{n["name"]}"',
            f"tags: [{', '.join(tags)}]",
        ]
        if n["desc"]:
            header.append(f'description: "{n["desc"][:300]}"')
        header += [f'source: "memory/{n["file"]}"', "---", ""]
        out = "\n".join(header) + n["body"].rstrip() + "\n"
        with open(os.path.join(VAULT, folder, n["stem"] + ".md"), "w",
                  encoding="utf-8") as fh:
            fh.write(out)
        for l in n["links"]:
            l = l.strip()
            if l in known:
                backlinks[l].add(n["stem"])
            else:
                broken[l] += 1

    # --- index pages. These are the only pages not copied from memory.
    def write_index(path, title, lines):
        with open(os.path.join(VAULT, path), "w", encoding="utf-8") as fh:
            fh.write(f"---\ntitle: \"{title}\"\ntags: [index]\n---\n\n" + "\n".join(lines) + "\n")

    for typ, folder in TYPE_DIR.items():
        rows = sorted((n for n in notes if n["type"] == typ), key=lambda x: x["name"])
        lines = [f"# {folder}", "",
                 f"*{len(rows)} notes. Built from Claude's memory, not written by hand.*", ""]
        for n in rows:
            d = f" — {n['desc']}" if n["desc"] else ""
            lines.append(f"- [[{n['stem']}|{n['name']}]]{d}")
        write_index(os.path.join(INDEX_DIR, f"MOC {folder}.md"), f"MOC {folder}", lines)

    # the most-linked notes are the load-bearing ones; worth seeing first
    hubs = sorted(backlinks.items(), key=lambda kv: -len(kv[1]))[:25]
    home = [
        "# ALMA · Second Brain", "",
        "לזכרה של עלמה ז\"ל", "",
        f"**{len(notes)} notes**, built from Claude's memory on 2026-08-29.",
        "This vault is a *view* of that memory, not a second copy to edit: rebuild it",
        "with `build_vault.py` and anything typed here is overwritten. Edit the memory.",
        "", "## Where things are", "",
    ]
    for typ, folder in TYPE_DIR.items():
        home.append(f"- [[MOC {folder}]] — {counts[folder]} notes")
    if counts[OTHER_DIR]:
        home.append(f"- **{OTHER_DIR}** — {counts[OTHER_DIR]} notes with no type in their header")
    home += ["", "## The load-bearing notes", "",
             "*Most linked-to. If one of these is wrong, a lot of thinking is wrong.*", ""]
    for name, srcs in hubs:
        home.append(f"- [[{name}]] — {len(srcs)} inbound")
    if broken:
        home += ["", "## Links pointing at nothing", "",
                 "*A `[[link]]` written to a note that was never created. In this system",
                 "that is not an error — it is a list of what is worth writing next.*", ""]
        for name, c in broken.most_common(30):
            home.append(f"- `{name}` — referenced {c}×")
    write_index("Home.md", "ALMA Second Brain", home)

    # --- Obsidian config: open on Home, wikilinks on, graph readable
    cfg = os.path.join(VAULT, ".obsidian")
    json.dump({"useMarkdownLinks": False, "newLinkFormat": "shortest",
               "attachmentFolderPath": "99 Attachments", "alwaysUpdateLinks": True,
               "showLineNumber": True, "readableLineLength": True},
              open(os.path.join(cfg, "app.json"), "w", encoding="utf-8"), indent=2)
    json.dump({"accentColor": "", "theme": "obsidian"},
              open(os.path.join(cfg, "appearance.json"), "w", encoding="utf-8"), indent=2)
    json.dump({"colorGroups": [
        {"query": "tag:#project", "color": {"a": 1, "rgb": 5431378}},
        {"query": "tag:#feedback", "color": {"a": 1, "rgb": 14701138}},
        {"query": "tag:#user", "color": {"a": 1, "rgb": 11621088}},
        {"query": "tag:#reference", "color": {"a": 1, "rgb": 5450847}},
        {"query": "tag:#index", "color": {"a": 1, "rgb": 16777215}}],
        "search": "", "showTags": True, "showAttachments": False,
        "lineSizeMultiplier": 1, "nodeSizeMultiplier": 1.6,
        "centerStrength": 0.35, "repelStrength": 11, "linkStrength": 1, "linkDistance": 220},
        open(os.path.join(cfg, "graph.json"), "w", encoding="utf-8"), indent=2)

    with open(os.path.join(VAULT, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write("# This vault holds private medical, family, financial and legal notes.\n"
                 "# It must never be committed anywhere. See project_pii_leak_github.\n*\n")

    print(f"vault: {VAULT}")
    print(f"  notes written : {len(notes)}")
    for folder in list(TYPE_DIR.values()) + [OTHER_DIR]:
        if counts[folder]:
            print(f"    {folder:<16} {counts[folder]}")
    print(f"  links resolved: {sum(len(v) for v in backlinks.values())}")
    print(f"  links to nothing: {len(broken)} distinct ({sum(broken.values())} references)")
    if hubs:
        print(f"  most linked   : {hubs[0][0]} ({len(hubs[0][1])} inbound)")


if __name__ == "__main__":
    main()

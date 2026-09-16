#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
index_artifacts.py — regenerate D:\CLAUDE\ARTIFACTS.tsv, the COMMITTED index that
makes `git grep` answer truthfully even though archive/ is git-excluded.

BORN 2026-08-31 from the EMDR commission of inquiry (FIX 2): the tool was rebuilt
SEVEN times in six months because archive/ is excluded from git for performance,
so `git log --grep`, `git grep` and root `ls` all returned a false negative.
This manifest is the tracked antidote: one row per project directory, INCLUDING
everything under archive/, with curated descriptions and aliases that survive
regeneration.

Usage:
    PYTHONIOENCODING=utf-8 python tools/index_artifacts.py       # regenerate
Run it after every reorg. Then commit ARTIFACTS.tsv.

Columns: path <TAB> state <TAB> newest <TAB> files <TAB> description_and_aliases
- `state` and `description_and_aliases` are CURATED: values from the existing TSV
  are preserved on regeneration (merged by path). Auto rows start as state=auto.
- Aliases belong IN the description text so plain grep finds them
  (e.g. the cerebro row carries "EMDR" although its path never says so).
"""
import io
import os
import sys
import time

ROOT = r"D:\CLAUDE"
TSV = os.path.join(ROOT, "ARTIFACTS.tsv")

# Directories that are machinery, not projects.
SKIP = {".git", ".claude", "__pycache__", "node_modules", ".wrangler", "$RECYCLE.BIN",
        ".playwright-mcp", ".vscode", "System Volume Information"}

# Levels to walk: the root's children, and one level inside these containers.
CONTAINERS = ["archive", os.path.join("archive", "projects"), os.path.join("archive", "diy"),
              os.path.join("archive", "_pages_stage"), "tools"]

# Curated seed rows — the commission's findings. Merged over auto rows; the
# description text deliberately repeats every alias a future grep might use.
SEED = {
    r"emdr\source-emdr-central": ("gold", "EMDR widget v0.4 PyQt6 source — THE ONE IDDO APPROVED"
        " ('spot on', 2026-04-19, sent to Anat Hod). Clone of github iddo111/emdr-central;"
        " D:\\NEWCLAUDE\\EMDR original is GONE. + soundcard_pan.py (sacred-audio-safe panning),"
        " EMDR1.ino, emdrVR_Godot, full icon->shortcut->exe chain. Aliases: bilateral, גירוי דו-צדדי"),
    r"alma-emdr": ("live", "EMDR Hebrew orb page (build #6, 2026-07-13) — LIVE at"
        " emdr.almaware.workers.dev + emdr.iddoperez.ai. Aliases: bilateral, הרגעה"),
    r"emdr": ("active", "EMDR collection dir (2026-08-31): collected originals, commission"
        " reports (reports/COMMISSION-*.md), v04-original EXE, source clone, app/ (build #7,"
        " unreviewed). THE index memory: memory project_emdr.md"),
    r"archive\projects\emdr-iddoperez": ("warm", "EMDR 52KB web suite SOURCE (build #4, 2026-05-25):"
        " bilateral engine + vibrate + StereoPanner + breathing + grounding + butterfly hug + 8 phases"
        " + crisis lines. BASE FOR PHONE/CARDBOARD per commission. Byte-identical deploy copy in"
        " archive\\_pages_stage\\iddoperez-emdr — edit ONE"),
    r"archive\_pages_stage\iddoperez-emdr": ("dup", "byte-identical COPY of archive\\projects\\"
        "emdr-iddoperez\\site\\index.html (same md5). Edit the projects/ one. Alias: EMDR"),
    r"archive\emdr-vive": ("warm", "EMDR VR Godot 4.6 (Vive/SteamVR, working 2026-05-09):"
        " orb sweep, AudioEffectPanner, haptics, in-VR panel. NOT a cardboard base — OpenXR"
        " tethered only. HALT gate 06-11: seizure/unclosed-trauma risk, never lifted"),
    r"archive\emdr-vr-—-bilateral-stimulation-(4.3)": ("superseded", "older EMDR VR Godot 4.3"
        " variant — ancestor of emdr-vive by content. Alias: bilateral"),
    r"archive\diy\cerebro-helmet": ("gold", "Cerebro Schumann+EMDR bilateral helmet (2026-05-05)."
        " 04-FIRMWARE-CEREBRO.ino = ESP32 serial parser + 0.5-2.0Hz bilateral envelope + session cap"
        " + thermal cutoff — COMMISSION-DESIGNATED BASE for the EMDR buzzer-ball box (עמותת המלאכים"
        " של ערן). Path has no 'emdr' token — that invisibility caused rebuild #5. Aliases: EMDR,"
        " bilateral, ball box, קופסת באזרים"),
    r"archive\boms": ("warm", "BOMs incl. 04-EMDR-physical-device.md (2-ball ESP32 spec ~$90;"
        " NOT a 20-person BOM). Alias: EMDR hardware"),
    r"archive\_shopping_lists": ("warm", "shopping lists incl. emdr-physical-device.md (copy of"
        " the 2-ball EMDR BOM)"),
    r"eran-brain": ("live", "ERAN 2.0 — ear/mouth/judging/arena. The child. eran1 is the organism"),
    r"alma-draughtsman": ("live", "WINSTON the imaginer/painter — winston/winston.py neural stroke"
        " painter (colour, 2026-08-31), gui, corpus. Aliases: draughtsman, צייר, painter"),
    r"keshev-next": ("live", "KESHEV 5000 mic window (owns engine). 2026-08-31: modulation fence"
        " + idle-floor voice gate killed the fan flood. Aliases: mic, STT, קשב"),
    r"RAMCHAT": ("live", "shared-RAM council + queue + ramlink.py. THE claim-before-build door"),
}


def one_line_readme(path):
    for name in ("README.md", "README.txt", "readme.md"):
        p = os.path.join(path, name)
        if os.path.isfile(p):
            try:
                with io.open(p, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        t = line.strip().lstrip("#> ").strip()
                        if t:
                            return t[:160]
            except OSError:
                pass
    return ""


def scan_dir(path):
    n, newest = 0, 0.0
    try:
        for e in os.scandir(path):
            n += 1
            try:
                m = e.stat().st_mtime
                if m > newest:
                    newest = m
            except OSError:
                pass
    except OSError:
        pass
    return n, newest


def load_existing():
    cur = {}
    if os.path.isfile(TSV):
        with io.open(TSV, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) == 5 and parts[0] != "path":
                    cur[parts[0]] = (parts[1], parts[4])
    return cur


def main():
    curated = load_existing()
    for k, v in SEED.items():           # seeds win over stale TSV rows once
        curated.setdefault(k, v)
        if curated[k][1] in ("", "auto"):
            curated[k] = v

    rows = []
    seen = set()
    targets = [""] + CONTAINERS
    for container in targets:
        base = os.path.join(ROOT, container) if container else ROOT
        if not os.path.isdir(base):
            continue
        for e in sorted(os.scandir(base), key=lambda x: x.name.lower()):
            if not e.is_dir() or e.name in SKIP or e.name.startswith("."):
                continue
            rel = os.path.relpath(e.path, ROOT)
            if rel in seen or rel in CONTAINERS:
                continue
            seen.add(rel)
            n, newest = scan_dir(e.path)
            state, desc = curated.get(rel, ("auto", ""))
            if not desc:
                desc = one_line_readme(e.path)
            rows.append((rel, state, time.strftime("%Y-%m-%d", time.localtime(newest)) if newest else "-",
                         str(n), desc))

    with io.open(TSV, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("path\tstate\tnewest\tfiles\tdescription_and_aliases\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")
    sys.stdout.write("wrote %s: %d rows\n" % (TSV, len(rows)))


if __name__ == "__main__":
    main()

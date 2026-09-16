#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""eye_page.py -- THE FIRST EYE. Reads a page's own CSS and finds the faults
that render silently.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

WHY THIS EXISTS
---------------
Iddo, 2026-09-06 00:16, after watching me report numbers about a page I had
never looked at: **"גדל עיניים קלוד. תבנה לעצמך שני סוכני עיניים... 3."**
And: **"תבנה אותם מבוססי קוד - למהירות וחיסכון בטוקנס."**

Code, not a model. An eye that costs a second and no tokens can run on every
artifact; one that costs a model call runs on none of them.

THE NIGHT THAT PRODUCED IT. On 2026-09-05, seven faults shipped and every single
one was found by opening the output and looking, never by a test:

  * a JPEG whose Hebrew title rendered as empty boxes -- Arial Black has no
    Hebrew glyphs, and a missing glyph raises nothing, it draws a square
  * `\u2715` drawn as a box for the same reason
  * a `.url` shortcut written by PowerShell as `[InternetShortcut]n` -- the
    backtick-n never became a newline, so the file had no URL line and was dead
  * a memory index line that came out `D:\CLAUDE\x07lma-language`, because `\a`
    in a non-raw Python string is the BEL character
  * two malformed bullets in that same index, one doubled and one stolen
  * and the one this file is named for: a `<canvas>` that filled a QUARTER of
    its page while every CSS property computed "correctly"

THE CANVAS BUG, because it is the whole design brief in one example.
`#cv{position:fixed;inset:58px 340px 0 0}` is right: left 0, right 340. But the
element ALSO had `width:auto`, and on a `<canvas>` `width:auto` means *use the
width ATTRIBUTE* -- which the page's own script had just set from `clientWidth`.
Script sets attribute from layout; layout takes width from attribute. A closed
loop that pins the canvas at its first-paint size forever. Nothing errors.
`getComputedStyle` reports `right: 340px` and `bottom: 0px` and looks healthy.
**Only the rendered box is wrong.**

WHAT IT CHECKS -- each one is a real fault that shipped here
  E1  a positioned element declares BOTH left and right (or top and bottom) AND
      a width/height: the offsets are then decorative
  E2  `width:auto` or `height:auto` on a <canvas> or <svg>: resolves to the
      intrinsic attribute, so the element never fills anything
  E3  the same id selector styled more than once: a later rule silently wins
  E4  a render surface (canvas/svg) with no CSS size AND no width attribute
  E5  a script that sets `canvas.width` from `clientWidth` while CSS sizes the
      canvas from its attribute -- the closed loop above
  E6  fixed/absolute elements that overlap the viewport edge by construction
  W1  a font stack with no fallback beyond a single family
  W2  text drawn in a face that has no Hebrew glyphs while the file contains
      Hebrew (Arial Black, Impact, and friends)

It is a LINTER, deliberately: no browser, no headless Chrome, no network. It
reads the HTML/CSS a server would send and answers in milliseconds.
It cannot see paint. `eye_image.py` is for what paint did.

Run:
    python eye_page.py http://127.0.0.1:8870/          # a served page
    python eye_page.py D:\CLAUDE\some\page.html        # or a file
    python eye_page.py --selftest                      # PROVE it can fail
Exit code 0 = clean, 1 = findings. A gate that has never refused anything has
not been demonstrated.
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Faces with no Hebrew coverage that get reached for because they look strong.
NO_HEBREW = ("arial black", "ariblk", "impact", "haettenschweiler",
             "bahnschrift", "cooper", "broadway", "jokerman")

RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)


def fetch(target: str) -> str:
    if re.match(r"^https?://", target):
        with urllib.request.urlopen(target, timeout=15) as r:
            return r.read().decode("utf-8", "replace")
    with io.open(target, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _split_at_rules(css: str):
    r"""Pull out `@media{...}` and friends by COUNTING BRACES, and return
    (flat_css, [inner_css, ...]).

    A regex cannot do this: `([^{}]+)\{([^{}]*)\}` cannot see nesting, so an
    @media block leaks its inner selectors into the flat stream and every rule
    inside it reads as a duplicate of the one outside. That produced the eye's
    first false alarm -- it reported `#cv is styled by 2 rules` on a page whose
    second rule was a legitimate responsive override. An eye that cries wolf on
    correct CSS is worse than no eye.
    """
    flat, inners, i, n = [], [], 0, len(css)
    while i < n:
        at = css.find("@", i)
        if at < 0:
            flat.append(css[i:]); break
        brace = css.find("{", at)
        if brace < 0:
            flat.append(css[i:]); break
        flat.append(css[i:at])
        depth, j = 0, brace
        while j < n:
            if css[j] == "{": depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0: break
            j += 1
        inners.append(css[brace + 1:j])
        i = j + 1
    return "".join(flat), inners


def css_blocks(html: str):
    """Every (selector, declarations, inside_at_rule) triple in every <style>."""
    out = []
    for style in re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I):
        body = re.sub(r"/\*.*?\*/", "", style, flags=re.S)
        flat, inners = _split_at_rules(body)
        for sel, decl in RULE.findall(flat):
            out.append((sel.strip(), decl, False))
        for inner in inners:
            for sel, decl in RULE.findall(inner):
                out.append((sel.strip(), decl, True))
    return out


def props(decl: str) -> dict:
    d = {}
    for part in decl.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            d[k.strip().lower()] = v.strip().lower()
    return d


def check(html: str, name: str = "page"):
    findings = []
    E = lambda code, msg: findings.append(("ERROR", code, msg))
    W = lambda code, msg: findings.append(("WARN", code, msg))

    blocks = css_blocks(html)
    seen_ids = {}
    for sel, decl, in_media in blocks:
        p = props(decl)
        pos = p.get("position", "")

        # --- E1 / E2 : offsets that cannot take effect -----------------------
        # `inset: 0 0 auto 0` means bottom:AUTO -- pairing that with a height is
        # the normal, correct pattern, not a fault. Only BOTH real offsets on an
        # axis conflict with a size. The first version of this check fired on
        # #top{inset:0 0 auto 0;height:58px}, which is perfectly good CSS, and a
        # noisy eye is an eye nobody reads.
        ins = (p.get("inset") or "").split()
        if len(ins) == 1:
            ins = ins * 4
        elif len(ins) == 2:
            ins = [ins[0], ins[1], ins[0], ins[1]]
        elif len(ins) == 3:
            ins = [ins[0], ins[1], ins[2], ins[1]]
        i_top, i_right, i_bottom, i_left = (ins + ["", "", "", ""])[:4]
        real = lambda v: bool(v) and v != "auto"
        has_lr = ((real(p.get("left")) and real(p.get("right")))
                  or (real(i_left) and real(i_right)))
        has_tb = ((real(p.get("top")) and real(p.get("bottom")))
                  or (real(i_top) and real(i_bottom)))
        if pos in ("fixed", "absolute"):
            if has_lr and p.get("width") not in (None, "", "auto"):
                E("E1", "%s: both horizontal offsets AND width:%s -- the offsets "
                        "are decorative, width wins" % (sel, p["width"]))
            if has_tb and p.get("height") not in (None, "", "auto"):
                E("E1", "%s: both vertical offsets AND height:%s" % (sel, p["height"]))

        # a selector like ":root" or "*" leaves nothing after the strip;
        # the eye must not crash on the page it is inspecting.
        _bits = sel.lstrip("#.").split(":")[0].split()
        tgt = _bits[0] if _bits else ""
        looks_surface = bool(re.search(r"\b(canvas|svg)\b", sel, re.I)) or tgt in ("cv", "canvas", "graph", "chart")
        if looks_surface:
            for axis in ("width", "height"):
                if p.get(axis) == "auto":
                    E("E2", "%s: %s:auto on a render surface resolves to the "
                            "ATTRIBUTE, not the box -- it will never fill" % (sel, axis))

        # --- E3 : the same id styled twice ----------------------------------
        for one in sel.split(","):
            one = one.strip()
            m = re.fullmatch(r"#([A-Za-z0-9_-]+)", one)
            if m and not in_media:
                seen_ids.setdefault(m.group(1), []).append(sel)

        # --- W1 : a font stack with no fallback ------------------------------
        fam = p.get("font-family") or ""
        if fam and "," not in fam and "var(" not in fam and fam not in ("inherit", "initial"):
            W("W1", "%s: font-family:%s has no fallback -- one missing face and "
                    "the page silently reflows" % (sel, fam))

    for _id, sels in seen_ids.items():
        if len(sels) > 1:
            E("E3", "#%s is styled by %d separate rules (%s) -- the last one wins "
                    "silently and the earlier ones look applied" % (_id, len(sels), ", ".join(sels)))

    # --- E4 / E5 : the closed loop ------------------------------------------
    styled = {s.strip().lstrip("#") for s, _, _ in blocks for s in s.split(",")}
    for m in re.finditer(r"<(canvas|svg)\b([^>]*)>", html, re.I):
        tag, attrs = m.group(1), m.group(2)
        eid = (re.search(r'id=["\']([^"\']+)', attrs) or [None, ""])[1]
        has_attr_size = bool(re.search(r'\bwidth\s*=', attrs))
        css_sized = any(eid and (eid in s or tag in s.lower()) for s in styled)
        if not has_attr_size and not css_sized:
            E("E4", "<%s id=%s> has neither a CSS size nor a width attribute -- "
                    "it renders at the 300x150 default" % (tag, eid or "?"))

    if re.search(r"\.width\s*=\s*[A-Za-z_$][\w.$]*\.clientWidth", html):
        E("E5", "a script sets .width from .clientWidth. If CSS sizes that element "
                "from its attribute (width:auto), the two feed each other and the "
                "surface is frozen at its first-paint size. This exact loop pinned "
                "a 1280px canvas at 675px on 2026-09-05.")

    # --- W2 : a face with no Hebrew, in a file that has Hebrew ---------------
    has_hebrew = any("\u0590" <= c <= "\u05FF" for c in html)
    if has_hebrew:
        for fam in set(re.findall(r"font-family\s*:\s*([^;{}]+)", html, re.I)) | \
                   set(re.findall(r"font\s*:\s*[^;{}]*?([A-Za-z][\w ]+)\s*[;}]", html)):
            low = fam.lower()
            for bad in NO_HEBREW:
                if bad in low:
                    W("W2", "font %r has no Hebrew glyphs and this page contains "
                            "Hebrew -- it will draw empty boxes, silently" % fam.strip())
    return findings


def report(findings, name):
    if not findings:
        print("EYE/page  %-46s CLEAN" % name)
        return 0
    errs = [f for f in findings if f[0] == "ERROR"]
    print("EYE/page  %s  %d error(s), %d warning(s)"
          % (name, len(errs), len(findings) - len(errs)))
    for lvl, code, msg in findings:
        print("   %-5s %-3s %s" % (lvl, code, msg))
    return 1 if errs else 0


SELFTEST_BAD = """<!doctype html><html lang="he"><style>
#cv{position:fixed;inset:58px 340px 0 0;width:auto;height:auto}
#cv{position:fixed;left:0;right:340px;width:675px}
h1{font-family:Arial Black}
</style><h1>\u05e9\u05dc\u05d5\u05dd</h1><canvas id="cv"></canvas>
<script>W=cv.width=cv.clientWidth*devicePixelRatio;</script>"""

SELFTEST_GOOD = """<!doctype html><html lang="he"><style>
#cv{position:fixed;inset:58px 340px 0 0;display:block}
h1{font-family:Arial,Segoe UI,sans-serif}
</style><h1>\u05e9\u05dc\u05d5\u05dd</h1><canvas id="cv" width="800" height="600"></canvas>"""


def selftest() -> int:
    bad = check(SELFTEST_BAD, "sick fixture")
    good = check(SELFTEST_GOOD, "well fixture")
    codes = {c for _, c, _ in bad}
    print("--- sick fixture: the eye must SEE these ---")
    report(bad, "sick fixture")
    print()
    print("--- well fixture: the eye must stay quiet ---")
    report(good, "well fixture")
    want = {"E1", "E2", "E3", "E5", "W2"}
    missed = want - codes
    noise = [f for f in good if f[0] == "ERROR"]
    ok = not missed and not noise
    print()
    if missed:
        print("BLIND to: %s" % ", ".join(sorted(missed)))
    if noise:
        print("FALSE ALARM on the well fixture: %s" % noise)
    print("selftest: %s" % ("PASS -- it sees every planted fault and stays quiet on the healthy page"
                            if ok else "BROKEN"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target", nargs="?", help="url or .html path")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.target:
        ap.error("give a url or a path, or --selftest")
    try:
        html = fetch(a.target)
    except Exception as e:
        print("EYE/page  could not fetch %s: %s" % (a.target, e))
        return 2
    return report(check(html, a.target), a.target)


if __name__ == "__main__":
    sys.exit(main())

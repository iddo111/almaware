#!/usr/bin/env python3
"""Create one Amazon wishlist per project and add that project's BOM items.

Drives the user's REAL Chrome over CDP (least bot-detectable). Chrome must be
launched with --remote-debugging-port=9222 and the user logged into Amazon.

Usage:
  python push_boms.py --list                 # list parsed projects + item counts
  python push_boms.py --project sanverin     # do ONE project (proof run)
  python push_boms.py --all                  # do every project
  python push_boms.py --project sanverin --max-items 3   # cap items (quick test)
"""
import argparse, re, sys, time, urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

BOM_DIR = Path(r"D:\CLAUDE\_shopping_lists")
CDP = "http://localhost:9222"

def parse_boms():
    """-> [(slug, title, [(item_name, query), ...]), ...]"""
    out = []
    for f in sorted(BOM_DIR.glob("*.md")):
        if f.name == "_INDEX.md":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s+(.+)$", text, re.M)
        title = (m.group(1).strip() if m else f.stem)
        title = re.split(r"[—\-–]\s*Shopping", title)[0].strip()
        items = []
        seen = set()
        # table rows: | name | qty | price | [search](amazon.com/s?k=QUERY) | ...
        for row in re.finditer(r"^\|(.+)\|\s*$", text, re.M):
            cells = [c.strip() for c in row.group(1).split("|")]
            if not cells or cells[0].lower() in ("item", "file", "") or set(cells[0]) <= {"-", ":"}:
                continue
            name = re.sub(r"[*`]", "", cells[0]).strip()
            mk = re.search(r"amazon\.com/s\?k=([^)\s]+)", row.group(0))
            if not mk:
                continue
            query = urllib.parse.unquote_plus(mk.group(1))
            key = query.lower()
            if name and query and key not in seen:
                seen.add(key)
                items.append((name, query))
        if items:
            out.append((f.stem, title, items))
    return out

def find_project(projects, needle):
    n = needle.lower()
    for p in projects:
        if n in p[0].lower() or n in p[1].lower():
            return p
    return None

def create_list(page, name):
    """Create a wishlist named `name`; return True. Idempotent-ish: if a list
    with that name exists we'll just add to it later."""
    page.goto("https://www.amazon.com/hz/wishlist/ls", wait_until="domcontentloaded")
    time.sleep(2)
    # already exists?
    try:
        if page.get_by_role("link", name=re.compile(re.escape(name), re.I)).count():
            print(f"    list '{name}' already exists"); return True
    except Exception:
        pass
    for sel in ["text=Create a List", "text=Create a list", "[aria-label*='Create']"]:
        try:
            page.locator(sel).first.click(timeout=4000); break
        except Exception:
            continue
    time.sleep(1.5)
    # name field
    for sel in ["#list-name", "input[name='listName']", "input[type='text']"]:
        try:
            page.locator(sel).first.fill(name, timeout=4000); break
        except Exception:
            continue
    for sel in ["text=Create List", "text=Create list", "[data-action='create-list'] *"]:
        try:
            page.locator(sel).first.click(timeout=4000); break
        except Exception:
            continue
    time.sleep(2)
    print(f"    created list '{name}'")
    return True

def add_item(page, query, list_name):
    page.goto("https://www.amazon.com/s?k=" + urllib.parse.quote_plus(query),
              wait_until="domcontentloaded")
    time.sleep(1.5)
    # first organic result
    link = None
    for sel in ["[data-component-type='s-search-result'] h2 a",
                "a.a-link-normal.s-no-outline",
                "div.s-result-item h2 a"]:
        try:
            if page.locator(sel).first.count():
                link = page.locator(sel).first; break
        except Exception:
            continue
    if not link:
        return "no-result"
    link.click(timeout=8000); time.sleep(2)
    # Add to List dropdown
    clicked = False
    for sel in ["#add-to-wishlist-button-submit", "#wishListMainButton",
                "text=Add to List", "[data-action='add-to-wishlist']"]:
        try:
            page.locator(sel).first.click(timeout=4000); clicked = True; break
        except Exception:
            continue
    if not clicked:
        return "no-add-button"
    time.sleep(1.2)
    # choose the list in the popover
    try:
        page.get_by_text(re.compile(re.escape(list_name), re.I)).first.click(timeout=4000)
        time.sleep(1.0); return "added"
    except Exception:
        return "list-not-selected"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--project")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--max-items", type=int, default=0)
    a = ap.parse_args()

    projects = parse_boms()
    if a.list or (not a.project and not a.all):
        for slug, title, items in projects:
            print(f"  {slug:32s} {len(items):3d} items   ({title})")
        print(f"\nTotal: {len(projects)} projects")
        return 0

    targets = projects if a.all else [find_project(projects, a.project)]
    if any(t is None for t in targets):
        print("project not found"); return 2

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = ctx.new_page()
        # sanity: are we logged in?
        page.goto("https://www.amazon.com/gp/css/homepage.html", wait_until="domcontentloaded")
        time.sleep(2)
        if "signin" in page.url or "ap/signin" in page.url:
            print("!! NOT LOGGED IN to Amazon in this Chrome. Log in, then re-run."); return 3

        for slug, title, items in targets:
            name = f"{title} — BOM"
            print(f"\n=== {slug}: '{name}' ({len(items)} items) ===")
            create_list(page, name)
            it = items[:a.max_items] if a.max_items else items
            tally = {}
            for nm, q in it:
                r = add_item(page, q, name)
                tally[r] = tally.get(r, 0) + 1
                print(f"    [{r:16s}] {nm[:48]}")
                time.sleep(1.0)
            print(f"  -> {tally}")
        page.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dig.py -- Iddo's deep research assistant. Core tool.

Starts from his own notes, then a normal web search, opens the most
promising PUBLIC pages, reads their text, and decides which of the links
ON those pages are worth opening next (a reference, a paper, a lab page, a
follow-up thread) -- up to a budget of N pages or M minutes. Never repeats a
page. Writes a journal of the run. Every claim in the final answer carries
the URL it came from.

All reading, ranking and summarising runs on Iddo's OWN free fleet models
(dgx4 coder / eran2 gpt-oss-120b via tokensave._common.call_fleet) -- never
a paid API. Search reuses tokensave/web.py; his own notes are searched via
tokensave/ask.py first, before anything goes to the web.

Good manners, always on: robots.txt is checked before every fetch, one
request at a time per site with a pause between them, an honest user-agent,
public pages only, no logins, text only (never media/binary downloads), and
a hard page + time budget so a run always ends.

Usage:
    python dig.py "question, in Hebrew or English"
    python dig.py "question" --pages 12 --minutes 8

Options:
    --pages N     max pages to read this run (default 10)
    --minutes M   max wall-clock minutes this run may take (default 8)
    --k-links N   max links to follow onward from each page (default 4)
"""
import sys
import os
import time
import json
import argparse
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _rescommon import (  # noqa: E402
    lower_priority, utf8_stdio, slugify, domain_of, normalize_url,
    RUNS_DIR, log_event, get_own_notes, ddg_seeds, semanticscholar_search,
    suggest_entities_with_fleet, rank_links_with_fleet, extract_claims_with_fleet,
    synthesize, fetch_page, filter_candidate_links, approx_tokens,
)


def gather_seeds(question, run_dir, ddg_n=8):
    seeds = []
    seen = set()

    def add(url, source, title=""):
        nu = normalize_url(url)
        if nu in seen:
            return
        seen.add(nu)
        seeds.append({"url": url, "source": source, "title": title})

    ddg_results, ddg_err = ddg_seeds(question, n=ddg_n)
    log_event(run_dir, "seed_ddg", n=len(ddg_results), error=ddg_err)
    for r in ddg_results:
        add(r["url"], "ddg-search", r.get("title", ""))

    entities, ent_err = suggest_entities_with_fleet(question)
    log_event(run_dir, "seed_entities", entities=entities, error=ent_err)
    for e in entities:
        wiki_url = "https://en.wikipedia.org/wiki/%s" % urllib.parse.quote(
            e.strip().replace(" ", "_"))
        add(wiki_url, "wikipedia-guess (entity: %s)" % e, e)

    ss_query = " ".join(entities[:4]) if entities else question
    ss_results, ss_err = semanticscholar_search(ss_query, n=5)
    log_event(run_dir, "seed_semanticscholar", n=len(ss_results), error=ss_err)
    for r in ss_results:
        if r.get("url"):
            add(r["url"], "semanticscholar", r.get("title", ""))

    return seeds


def run_research(question, max_pages=10, max_minutes=8.0, k_links=4):
    start = time.time()
    deadline = start + max_minutes * 60
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + slugify(question)
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)
    log_event(run_dir, "start", question=question, max_pages=max_pages,
              max_minutes=max_minutes, k_links=k_links)

    # 1. HIS OWN NOTES FIRST -- before anything goes to the web.
    notes_hits, notes_err = get_own_notes(question)
    log_event(run_dir, "own_notes", count=len(notes_hits), error=notes_err)

    # 2. seed the frontier: web search + entity/Wikipedia guesses + papers.
    seeds = gather_seeds(question, run_dir)
    by_source = {}
    for s in seeds:
        key = s["source"].split(" ")[0].split("(")[0]
        by_source[key] = by_source.get(key, 0) + 1
    log_event(run_dir, "seeds_total", count=len(seeds), by_source=by_source)

    visited = set()
    # Two queues, not one: `seed_queue` is the breadth-0 backlog (FIFO, kept
    # in the priority order gather_seeds() returned). `dig_stack` holds links
    # just discovered on a page (LIFO). dig_stack is always drained first --
    # that is the whole point of the tool: once a page is read, the links it
    # judged worth opening next get opened next, before moving on to the
    # rest of the seed backlog. Without this a wide seed list (which is
    # common) can fill the whole page budget at depth 0 and the crawl never
    # actually goes anywhere deeper than its own seed list.
    seed_queue = [{"url": s["url"], "reason": "seed: %s" % s["source"], "depth": 0}
                  for s in seeds]
    dig_stack = []

    pages_read = []
    claims_by_url = {}
    errors = []
    max_depth_reached = 0
    domain_count = {}
    MAX_PER_DOMAIN = 3  # diversity cap -- one site should not eat the whole budget

    while (dig_stack or seed_queue) and len(pages_read) < max_pages and time.time() < deadline:
        cand = dig_stack.pop() if dig_stack else seed_queue.pop(0)
        nu = normalize_url(cand["url"])
        if nu in visited:
            continue
        visited.add(nu)

        dom = domain_of(cand["url"])
        if domain_count.get(dom, 0) >= MAX_PER_DOMAIN:
            log_event(run_dir, "skip_domain_cap", url=cand["url"], domain=dom)
            continue

        res = fetch_page(cand["url"])
        if not res["ok"]:
            errors.append({"url": cand["url"], "error": res["error"],
                            "reason": cand["reason"]})
            log_event(run_dir, "fetch_fail", url=cand["url"], error=res["error"])
            continue
        domain_count[dom] = domain_count.get(dom, 0) + 1

        log_event(run_dir, "fetch_ok", url=res["url"], title=res["title"],
                   chars=len(res["text"]), reason=cand["reason"], depth=cand["depth"])

        claims = extract_claims_with_fleet(question, res["url"], res["title"], res["text"])
        pages_read.append({"url": res["url"], "title": res["title"],
                            "reason": cand["reason"], "depth": cand["depth"],
                            "n_claims": len(claims)})
        claims_by_url[res["url"]] = {"title": res["title"], "claims": claims}
        max_depth_reached = max(max_depth_reached, cand["depth"])
        log_event(run_dir, "claims", url=res["url"], claims=claims)

        if len(pages_read) >= max_pages or time.time() >= deadline:
            break
        if cand["depth"] >= 3:
            continue  # depth cap -- keeps the crawl from wandering forever
        if not claims:
            # this page turned out irrelevant to the question -- treat it as
            # a dead end and do not spend budget chasing ITS links further.
            log_event(run_dir, "dead_end", url=res["url"])
            continue

        candidates = filter_candidate_links(res["links"], domain_of(res["url"]))
        candidates = [(u, a) for u, a in candidates if normalize_url(u) not in visited]
        picks = rank_links_with_fleet(question, res["title"], res["url"], candidates, k=k_links)
        log_event(run_dir, "ranked_links", url=res["url"],
                  n_candidates=len(candidates), picks=picks)
        for p in picks:
            dig_stack.append({"url": p["url"],
                               "reason": "followed from %s (%s)" % (res["url"], p.get("reason", "")),
                               "depth": cand["depth"] + 1})

    elapsed = time.time() - start
    synthesis = synthesize(question, notes_hits, claims_by_url)

    top_pages = sorted(pages_read, key=lambda p: (-p["n_claims"], p["depth"]))[:10]

    report = {
        "question": question,
        "run_id": run_id,
        "run_dir": run_dir,
        "pages_read": len(pages_read),
        "max_pages": max_pages,
        "max_minutes": max_minutes,
        "max_depth_reached": max_depth_reached,
        "elapsed_sec": round(elapsed, 1),
        "seeds": seeds,
        "pages": pages_read,
        "top_pages": top_pages,
        "errors": errors,
        "own_notes_hits": notes_hits,
        "own_notes_error": notes_err,
        "synthesis": synthesis,
    }
    _write_report(run_dir, report)
    log_event(run_dir, "done", pages_read=len(pages_read), elapsed_sec=round(elapsed, 1),
              max_depth_reached=max_depth_reached)
    return report


def _write_report(run_dir, report):
    with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(render_report_text(report))


def render_report_text(report):
    out = []
    out.append("QUESTION: %s" % report["question"])
    out.append("run %s -- %d page(s) read (budget %d / %.1f min), depth reached %d, %.1fs elapsed"
                % (report["run_id"], report["pages_read"], report["max_pages"],
                   report["max_minutes"], report["max_depth_reached"], report["elapsed_sec"]))
    out.append("")
    out.append(report["synthesis"])
    out.append("")
    out.append("-- top pages this run --")
    if not report["top_pages"]:
        out.append("(no page was successfully read)")
    for i, p in enumerate(report["top_pages"], 1):
        out.append("%d. %s -- %s [%s, depth %d, %d claim(s)]"
                    % (i, p["title"], p["url"], p["reason"], p["depth"], p["n_claims"]))
    if report["errors"]:
        out.append("")
        out.append("-- could not open (%d) --" % len(report["errors"]))
        for e in report["errors"][:15]:
            out.append("- %s -- %s (%s)" % (e["url"], e["error"], e["reason"]))
    out.append("")
    out.append("journal: %s" % os.path.join(report["run_dir"], "journal.jsonl"))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(prog="dig.py", description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="+")
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--minutes", type=float, default=8.0)
    ap.add_argument("--k-links", type=int, default=4)
    args = ap.parse_args()

    lower_priority()
    utf8_stdio()
    q = " ".join(args.question)
    report = run_research(q, max_pages=args.pages, max_minutes=args.minutes, k_links=args.k_links)
    print(render_report_text(report))


if __name__ == "__main__":
    main()

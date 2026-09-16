# AlmIdo — התולעת / The Worm
## Design spec — a prompt-oriented, always-on, judgment-returning search organism

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY.
> Test the REAL output, not a proxy. A broken window left unfixed invites decay.

**לזכרה של עלמה ז״ל**

**Date:** 2026-08-15 · **Author:** Iddo Perez (עידו פרץ) + Claude
**Status:** DESIGN — approved in concept by Iddo 2026-08-15 21:47. Not started.

---

## 1. The claim

Google answers the median query in 200 ms at ad-scale. It is economically incapable of
spending three days on one person's question. **AlmIdo spends three days.** That is not a
smaller Google — it is the thing Google structurally cannot be.

The product is **not a list of links. It is a ruling** — a conclusion that survived
argument, with the disagreement shown where it did not resolve.

## 2. What it is

A **colony of small worms** living on one DGX. Each worm is assigned a **subject**
(expressed as a prompt, not keywords). Each burrows the web slowly and continuously,
brings home **gists** rather than pages, and the colony's **Beit Din** rules on what
the haul means.

```
   subject prompt
        │
        ▼
   ┌─────────┐   predict-gist   ┌──────────┐   fetch only    ┌──────────┐
   │  WORM   │ ───────────────▶ │  JEPA    │ ──if surprised─▶│   web    │
   │ (agent) │ ◀─────────────── │ policy   │ ◀───────────────│  source  │
   └────┬────┘     surprise     └──────────┘                 └──────────┘
        │ gists (several per source, several levels)
        ▼
   ┌──────────────┐  co-useful sources wire together  ┌──────────────────┐
   │ GIST MEMORY  │ ────────── HEBBIAN ─────────────▶ │ colony web-graph │
   └──────┬───────┘                                   └──────────────────┘
          │ candidate findings
          ▼
   ┌────────────────────────────────────────────┐
   │ BEIT DIN — 3 lenses, odd, always rules      │
   │  source credibility · the claim · contradiction │
   └──────┬─────────────────────────────────────┘
          ▼
      מסקנה + visible מחלוקת          ← the product
          │
          ▼
   nightly: SLEEP (consolidate) + DUMP (forget)
```

## 3. Every component earns a job

| Component | Its actual job | Honesty |
|---|---|---|
| **GIST++** | Stores essences, not pages. Multi-gist: several gists per source at different levels. A worm's whole life fits in small memory — **this is why "size doesn't matter" is true and not a slogan.** | 🟢 buildable (attention/Hopfield/spreading-activation are proven) |
| **JEPA** | Predicts a page's gist **before fetching**. Confident-and-boring → skip. Uncertain → crawl. **Surprise = prediction error = the hunger drive.** This is the crawl policy and the core novelty. | 🟡 the objective is standard; using it as a *crawl policy* is ours and unproven |
| **Hebbian** | Sources that co-occur in useful findings wire together. The colony grows its own web-graph of **co-usefulness, not popularity** — the opposite axis from PageRank. Local and online, so it runs 24/7 without backprop. | 🟢 local learning is cheap and real; 🟡 that it yields a better graph than PageRank is the bet |
| **Beit-Din neuron** | Three lenses judge every finding — source credibility · the claim itself · contradiction with what the colony already believes. Odd, so there is always a ruling. **Unresolved מחלוקת is reported, never hidden.** | 🟢 buildable; this is the honesty layer and the product's face |
| **ALMA Language** | The colony's world-model is written as a readable symbolic map over the neural substrate — **you can see and edit what the worm believes.** | 🟡 hybrid only. Full lossless symbolic compression of neural knowledge is unsolved; do not aim for it |
| **Sleep + Dump** | Nightly consolidation of the day's gists into long-term memory, and forgetting of the dross. Without it the colony drowns in its own haul. | 🟢 |
| **Neuromorphic 3D / memristive** | Where this wants to live eventually. | 🔴 **Today it is software on a DGX.** Do not sell the crossbar as if it exists |

## 4. What we build and what we stand on

**Do not build a crawler.** Crawling is a solved open-source problem — Marginalia
(open-source crawler + index, deliberately targets the "small web") and YaCy (mature P2P
crawler) exist. Fetching, politeness, robots.txt, dedup, and rate-limiting are months of
unglamorous work already done by others. Reuse-not-rebuild.

**Build the brain on top:** gist memory · the JEPA crawl policy · the Hebbian graph ·
the Beit Din · sleep/dump. **Those are 100% ours from day one.**

**The reader** — the model that turns a page into gists — is **rented at first** (a small
open model) and replaced with the from-scratch ALMA model later. This obeys the purity
law (*apps ours, models allowed*) and is the only way to have something running in weeks
instead of quarters. Iddo's call to override.

## 5. Hard limits — stated once, never oversold

1. **The login-walled deep web is unreachable** without credentials. Never promise "every
   corner". The honest promise is **the places Google won't spend time on because they
   don't pay it**: forums, archives, PDFs, non-English, small sites, .onion.
2. **Dark web:** reaching .onion over Tor is technically trivial and legal in itself, but
   indiscriminate fetching lands on criminal markets and material whose mere storage is an
   offence. If built: **subject allowlist, no raw storage of unknown .onion fetches, a hard
   content gate.**
3. **Crawling etiquette is not optional** — robots.txt and rate limits, or the colony gets
   IP-banned and becomes a legal problem instead of a product.

## 6. First proof — falsifiable, cheap, 72 hours

**One worm. One subject. 72 hours. On eran2 (idle).**

**Pass condition:** it surfaces **≥3 genuinely relevant sources that do not appear in
Google's first three pages** for that subject, and the Beit Din's ruling on them holds up
when Iddo reads it.

**Fail condition is informative:** if a single surprise-driven worm cannot beat Google page
1–3 on one subject in three days, the crawl policy is wrong and must be reworked **before**
a colony is built. No colony until one worm earns it.

## 7. Sequencing (honest)

This is the most exciting idea on the board and **the furthest from money.** Open in
parallel right now: KESHEV (live), the dentist/lawyer pilot (the money), Darwish (eran3
unreachable), the salon. The worm is a north-star build, not a tonight build — the 72-hour
single-worm proof is the correct size of first bite.

---

**Related:** `project_almido_search` · `project_gist_retrieval_principle` ·
`project_eran_holobrain` · `project_eran_brain_beitdin` · `project_bio_transformer` ·
`project_alma_language` · `project_almido_harness`

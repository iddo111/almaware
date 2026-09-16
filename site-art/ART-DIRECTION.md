# ART DIRECTION — iddoperez.ai

*Note from RAMCHAT before the brief: a ninth public surface, **helios.iddoperez.ai**, went live today at 10:12 (Hebrew/English heliotherapy explainer, Cloudflare Worker `helios-site`). It is not in the audit set but it is on the domain, so the identity below covers it and the door grid has a slot for it. Also measured today: `dgx2:8443` (the 480B) returns 502 — any apex copy claiming it live is now false.*

---

## A. THE READ

This is **a working laboratory notebook with doors on it, kept in a dead sister's memory.** Not a portfolio — there is no bio, no CV, no credentials, no ask, and nothing that pitches. Not a product site — half the surfaces volunteer what does not work, with numbers. What the nine surfaces actually share is one editorial spine that nobody else on the internet has: **every page grades its own claims downward.** ERAN is renamed *ProtoEran* because the real name is not earned yet. NEGATIVE RESULT is a first-class status with 60/60 dead reads printed next to it. The lab pre-labels its own simulations "not a real interferometer." The downloads table says "no installer yet, honestly." The volunteer page lists the providers whose terms forbid what it is asking for. That is the product. The projects are the evidence.

A stranger landing on the apex has five seconds and should get exactly three things: **one man in Israel is raising a machine mind in the open; he publishes what fails; here are the doors you can walk through right now.** Today the apex spends those five seconds on a wall of 27 identical emoji cards and a heartbeat number that has been dead for five days — so a stranger gets "busy hobbyist, possibly overclaiming," which is the precise opposite of what is true.

---

## B. THE FIXES

### BROKEN — the surface says something untrue, or a function is dead

**B0. Two zone-level fixes first, because they repair many surfaces at once and make the rest of this list visible.**

| # | Host | Problem | Fix |
|---|---|---|---|
| **1** | **all 9** | **Soft-404 on everything.** Unknown paths return **200 + the homepage**. `/favicon.ico`, `/downloads/nope.zip`, `/alma-photos.zip`, `/sitemap.xml` — all 200, all HTML. Consequence: **a dead asset is invisible to curl, to link checkers, and to Iddo.** This is the mechanism that hid fix #3 for however long it has been broken. | Ship a real `404.html`; set Workers static assets `not_found_handling: "404-page"` (remove SPA fallback). Do this **first** — every other asset fix below is unverifiable until a missing file can fail. |
| **2** | **eran, lab, apex** | **The colophon is false as served.** eran.iddoperez.ai states "no analytics, no tracking, no third-party script of any kind… zero JavaScript." Cloudflare injects `cloudflareinsights.com/beacon.min.js` + a `/cdn-cgi/rum` POST at the edge. **The one page whose job is to be unfalsifiable is falsifiable in ten seconds with devtools.** Iddo's HTML is clean — this is not his code. | One toggle: Web Analytics / Browser Insights auto-injection **off for the zone**. Also retires lab's "zero external refs" badge nit. |

**Then, ranked by harm × who sees it:**

3. **alma — the ZIP is dead and fails silently.** `alma-photos.zip` returns 200 + 20,458 bytes of homepage HTML. First bytes `<!DO`, not `PK`. **The one thing a memorial asks family to do hands them a corrupt file named after his sister.** Fix: build and deploy the real archive — **split into ~7 files of ≤64MB by age band**, not one 430MB download (430MB is unusable on a phone anyway). If it cannot ship today, **delete the button today** and put one honest line in its place. A dead memorial button is worse than no button.
4. **apex — the hero pulse is a tombstone dressed as a heartbeat.** `beat: 351061855` is byte-identical across polls; only `age_s` advances (~427,700s = 4.95 days, frozen since ERAN was disabled on 09-11). It renders under **"הדופק של ערן עכשיו"** next to a green dot CSS-animated at 1.2s, **three lines below the page's own credo "אמיתי, לא דמו."** Fix: the JS is already honest — the *label* is the bug. Bind label, dot colour and animation to `age_s`: >300s ⇒ grey dot, no animation, text becomes `הדופק האחרון · last beat, לפני X ימים`. Never print a number under "now" that is not now.
5. **pong — dead data source, unreachable by anyone including Iddo, forever.** Line 153 sends public visitors to `https://<tailnet-host>/state` — Tailscale-private, and dead even on the tailnet (curl exit 000). **Three contradicting addresses in one 747-line file** (`:8776` in the copy, `:8775` in the code, tailnet-with-no-port remote). Measured **1.8 failed fetches/second, sustained**, 23+ console errors and climbing. Fix: one endpoint constant; exponential backoff capped at 60s that **stops** after 5 failures; and ship a **baked recorded run** (a captured trajectory JSON) so the brain is alive for a stranger, labelled `הקלטה · recorded run, DD.MM`, with live data as an upgrade when reachable.
6. **arena — every turn truncates mid-word, including the מסקנה.** Reproduced on two topics: `…הדבר מחייב אותנו לשא`, and the closing synthesis ends `…העמדה החזקה ביותר היא ` and stops. **The payoff line of a 53-second wait does not finish its sentence.** Fix: raise `max_tokens`, and add a hard trim-to-last-sentence-boundary so a cap can never cut mid-word.
7. **arena — the synthesis echoed its own prompt template at the reader** ("היכן כולם מסכימים, היכן המחלוקת עומדת…"). Fix: move the instruction out of the echoed span; drop any turn whose first 80 chars overlap the instruction string.
8. **arena — the EventSource error handler never calls `close()`.** A backend failure makes the browser **silently re-run the entire debate in a loop** — real inference cost, invisible. Fix: `es.close()` + one visible error state.
9. **lab — no `<meta name="viewport">` in any of the 14 files.** Layout viewport falls back to 980px, browser shrink-fits at **scale 0.383**, so 13.5px body renders at ~5.2 device pixels. **The grid is already fluid** — forcing width to 653px collapses it correctly. One line per file fixes mobile outright. Highest value-per-byte fix on the domain.
10. **erancloud — the one-click action copies a command that fails on line one.** `git clone https://git.almaware/eran-grid.git` — `.almaware` is not a TLD. "קוד פתוח / ניתן לביקורת" is claimed **four times** with **no repository link anywhere**. Fix: publish the repo and link it, or delete all four claims. Do not leave the claim and the broken command together.
11. **alma — 690 photographs, zero alt text, zero focusable tiles, no arrow keys.** 691 `<img>`, 0 with alt; 690 cells, 0 tabbable; the whole page has 5 tabbable elements. **A keyboard or screen-reader user cannot open a single photograph of Alma.** The fix is already paid for: `manifest.json` carries per-photo `age` ⇒ `alt="עלמה, גיל 14"`. Tiles become `<button>`; ArrowLeft/Right move the lightbox.
12. **apex — the downloads table clips its own download column at 375px.** Table is 466px inside a 335px wrapper and because the document is RTL **the overflow runs off the LEFT**: the `קבצים · files` column sits at `left=-111px`, the ER"N-GRID link entirely off-screen at `left=-94, right=-9`. No scroll affordance, no scrollbar on touch. **The section whose entire purpose is handing people files hides the files.** Fix below in C — the table stops being a table at ≤640px.
13. **eran — 27px of sideways scroll at 375px** (scrollWidth 402 vs 375) from six cards that stay 380px: both in `#ants`, both in `#not-claimed`, both in `#colophon`. Those three grids don't fall to one column the way Tracks 1/3/4 do.
14. **erancloud + lab — dead ends.** `babble.html` has **zero `<a>` elements** — the primary hero CTA lands on a page with no exit. `join.html` has only `#anchors`. All 13 lab sims have zero anchors, on a site that invites you to open them offline where Back does not exist. `CONNECT.md` is referenced three times in prose, exists, returns 200, and is never linked.
15. **erancloud — the "חי / LIVE" badge cannot be true on this host.** babble.html diffs `Last-Modified|Content-Length`; Cloudflare Pages sends **no `Last-Modified`**, and the WAV is baked into the deploy. The green dot is decoration, and the homepage overclaims past its own sub-page, which is more honest.
16. **Zone-wide — no share metadata on any surface.** Zero og/twitter on apex, eran, erancloud, lab, quorum, arena, pong. alma declares `twitter:card=summary_large_image` **with no image**. Every one of these pages exists to be pasted into WhatsApp. The apex's og:image asset is already sitting on the server.
17. **Staleness as a class.** apex's lead claim is 24 days old; eran's newest VERIFIED date is 5 weeks old **on a page whose contract is dates**; federation publishes "eran1 — never restarted" (rebooted 09-11) and "eran3 — disk 84%" (re-measured 76%), and asks the reader to "ignore the 'hub' label bug." Fix in step 18: dates render their own age from a `verified` field, so staleness becomes visible instead of hand-maintained.
18. **eran — `<html lang="en">` with ~40% Hebrew**, and 3 elements total carrying `lang`/`dir`. Every Hebrew heading is spoken in an English voice. No `dir="auto"` on the mixed-direction hero subtitle.
19. **No declared favicon anywhere** (alma's inline SVG sunflower is the one exception and it works).

**→ FOR IDDO, NOT A DEFECT:** alma's `robots.txt` is `Allow: /`. 690 private family photographs, including living relatives and children, are open to search indexing. That may be exactly what he wants. He should decide it knowingly.

### UGLY — it works, it just doesn't read

20. **apex — 27 cards, all emoji-led**, which flattens the directory into a wall of sameness. (Structural fix in C.)
21. **eran — the honesty grading is the best idea on the domain and the design gives it a 12px chip**, on a page of 18 visually identical cards. Nothing distinguishes a LIVE card from a CONCEPT one.
22. **quorum + arena — Heebo is named in the font stack and never loaded**, and it is listed *after* Segoe UI so it would lose even if it were. **The typography Iddo designed is not the typography anyone gets.**
23. **quorum — sub-AA contrast on the small type**: gold `#B0810F` on `#FBFAF6` = **3.36:1** at 14px, round labels **3.28–3.50:1** at 12px, teal = **3.95:1**. All under 4.5. These are the smallest words on the page.
24. **arena — hero control misaligned at 375px**: 74px two-line button against a 50px input, prefilled question clipped to "האם בינה מלאכותית צריכו". And 13s to first turn / 53s total with one 12px grey italic line as the only feedback.
25. **pong — the white chrome header is slammed against the near-black stage with no transition**, and the waiting box is a plain rectangle dumped dead-centre over the art.
26. **lab — zero `:focus` rules** on a `#05060a` background; heading order runs H1 → thirteen H3 → one H2 at the very bottom.
27. **apex — render-blocking Google Fonts**, 3 families / 7 weights, on an otherwise fully self-contained 21.8KB page.
28. **quorum — five bordered speaker pills read as tabs, are inert `<span>`s** with `cursor:auto`.
29. **lab + pong — no `prefers-reduced-motion`** (lab's manual Pause button partly covers it; pong's auto-orbit cannot be stopped at all).

---

## C. THE IDENTITY

### Palette — six values, every one with a physical referent on his bench

```css
:root{
  --nyar:      #F7F5EF;  /* נייר · paper   */
  --dyo:       #10131A;  /* דיו · ink      */
  --otot:      #0E7C8A;  /* אותות · signal */
  --machshava: #5B45C9;  /* מחשבה · mind   */
  --nechoshet: #B4622D;  /* נחושת · copper */
  --zahav:     #C8912F;  /* זהב · memory   */
  /* structural */
  --kav:   #DCD7CA;      /* hairline, warm-matched to paper */
  --amum:  #5E6470;      /* secondary text, 5.37:1 on paper */
  --nechoshet-text: #9A5225; /* copper, darkened for body text */
}
```

**Why these and not generic taste.**

- **נייר `#F7F5EF`** — warmer than today's `#f7f9fb`, which is faintly blue. Every surface he genuinely cares about is a *printed page*: Frank Ruhl Libre is a book face, and quorum independently arrived at parchment `#FBFAF6` without being told to. **A cold white makes a Hebrew serif look like a PDF; a warm white makes it look like a page.** One paper, nine surfaces.
- **דיו `#10131A`** — near-black with a trace of blue, never `#000`, which vibrates on warm ground. **16.6:1** on paper.
- **אותות `#0E7C8A`** — the oscilloscope trace and the terminal cursor. **4.56:1**, AA for body text. Reserved for one meaning and one only: *this is actually running, right now*. Binding teal to liveness is what gives the honesty grading a colour.
- **מחשבה `#5B45C9`** — already the middle stop of his own gradient, already on pong and quorum. It is the colour this domain keeps reaching for when it talks about a brain. **6.05:1.** Reserved for the ERAN / model / mind track.
- **נחושת `#B4622D`** — the actual metal on his bench: memristor cells, PCB traces, the Shisha brain. **4.12:1, so it is a rule/border/icon/large-text colour only** — use `--nechoshet-text #9A5225` (5.25:1) for anything ≤18px. Reserved for the hardware track.
- **זהב `#C8912F`** — **2.56:1, therefore never text.** Border, fill and rule only. On this domain gold already means *this one is held*: the alma download, arena's מסקנה card, quorum's round labels. Give it one job — the memorial register and the conclusion — and stop spending it on eyebrows. This rule is what prevents quorum's 3.36:1 bug from recurring.

**The gradient.** He already invented it; unify on the one version and give it a job it does not currently have.

```css
--pas: linear-gradient(270deg, #0E7C8A 0%, #5B45C9 52%, #B4622D 100%);
```

**It appears exactly once per page** — a 3px rule at the top edge, or under the wordmark. Never twice. Today the apex spends it twice, quorum uses a different blue→purple, arena a third, pong a fourth. And the angle is `270deg`, not `90deg`: **the gradient runs in the reading direction, so teal is always on the side a Hebrew reader starts from.** That single decision is invisible to a non-Hebrew reader and unmistakable to Iddo.

**Dark register (lab, pong) — an inversion, not a second brand.** `--dyo` becomes the ground at `#0B0D13`, paper becomes ink at `#E9E6DD`, hairline `#22262F`, and the five accents raise to `#3FD8E4 / #9B8BFF / #E08A4E / #F0C45E`. Same system, lights off.

### The ALMA deviation — explicit, because it must be

`alma.iddoperez.ai` **does not join the system.** It keeps its own sunrise ground (pale blue → cream → warm amber) and its full-width rainbow rule, untouched. That palette was a deliberate decision about how to remember her — warm and alive, not funereal — and it is right.

**It takes exactly two things from the system:** the typeface pairing (which it already has), and `--zahav` as its single accent.

**It refuses, by name:** the three-stop gradient (that is the workshop's signature; a memorial is not a workshop surface), teal, violet, copper, every chip and badge, the honesty-grade vocabulary, any counter, any status dot, any hover-lift, any motion beyond a photograph fading in, and every trace of ALMAWARE branding. Photo tiles keep their white print border and soft shadow — a print on a table — and **hover changes the cursor and nothing else.**

The only "same hand" tell is one 1px `--zahav` hairline beneath her name and years, at the identical weight as the hairlines everywhere else. Same craftsman, different room.

### Type

**Display: Frank Ruhl Libre — 900 for the apex headline, 700 elsewhere, and never below 32px** (its thin strokes vanish on paper at text sizes). Keep it and defend it. It is the Hebrew book face — Rafael Frank, 1908 — the face most Hebrew literature is actually set in. **Nobody arrives at it by default; the default is Rubik or Assistant.** It is the single reason the apex reads as authored rather than generated, and the audit is right that a redesign must not swap it for a sans.

**Body: Miriam Libre (400/700) — replacing Heebo.** This is the one type change and it is not a taste call. **Heebo is Roboto's Hebrew sibling** — it, Rubik and Assistant are the three faces every Israeli site defaults to, and Heebo in particular is exactly what "generated" looks like in Hebrew. **Miriam is the historical companion sans to Frank-Ruhl in Israeli metal typesetting** — they were a documented pair before either was digital. Using Frank Ruhl Libre with Miriam Libre is not a pairing invented for this site; it is a restoration of one. Its Latin is less refined than its Hebrew, which is the correct trade on a Hebrew-first domain where English is the second line.

**Data: IBM Plex Mono 500, LTR only** — numerals, URLs, code, status values. It has no Hebrew, and that is fine because it must never set Hebrew. A Hebrew status word that wants a monospace feel gets Miriam Libre 700 with letter-spacing instead.

**Dark instrument register (lab, pong): system mono only** (`ui-monospace, "Cascadia Mono", Consolas`), **zero webfonts.** lab loads in 88ms with no external bytes and that is a feature worth protecting. One system, two registers.

**Serve them self-hosted.** Five faces, Hebrew+Latin woff2 subsets, one path, `font-display: swap`, preload the two above the fold. This kills the apex's render-block and its third-party privacy note *and* makes quorum/arena's "Heebo named, never loaded" class of bug impossible, because the font is same-origin.

```css
--kotel: "Frank Ruhl Libre", "David Libre", Georgia, serif;
--guf:   "Miriam Libre", "Alef", "Segoe UI", system-ui, sans-serif;
--mispar:"IBM Plex Mono", ui-monospace, Consolas, monospace;
```

### Layout — the apex

**Above the fold is type and one physical object, no image.** A 3px `--pas` rule flush to the top edge. Then his name small in Hebrew, then the motto at full size — `אנחנו בוראים צורת חיים מבוססת סיליקון ולא פחמן` in Frank Ruhl Libre 900, `clamp(34px, 6.2vw, 72px)`, English beneath it at `--amum`. To the reading-end side, the QR on its white card with its quiet zone, unchanged — it is a real object and it is the physical link to the shirt. Under the headline, **one truth line**: a dot plus `ערן · הדופק האחרון ‎351,061,855‎ · לפני 5 ימים`, grey and still; teal and the word `עכשיו` only when `age_s < 300`. Two CTAs, no more.

**Then the fold: a full-bleed 21:9 photograph of his workbench**, edge to edge, no caption. It is the seam — you have read the manifesto, now you are in the workshop.

**Then the doors. The 27-card wall is deleted and replaced by nine doors** — one per live surface (eran, alma, lab, quorum, arena, erancloud, pong, federation, helios). Each door is an image at 3:2, then the **grade word**, then the name, then one line of what it is. The 27 projects survive as a **plain text index below the doors**, grouped under the door that contains them — every one still one click away, none of them competing for the eye. Nine doors a stranger can choose between beats 27 cards a stranger cannot.

**At 390px:** single column, 20px gutters, the top rule the only full-bleed element. Headline floors at 34px, max 3 lines of Hebrew. QR drops below the headline at 132px (it already does this correctly — keep it). Doors stack full-width, first image eager, the rest lazy. Every tap target ≥44px, CTAs full width minus gutters, nothing depends on hover. **And the downloads table stops being a table at ≤640px** — each row becomes a stacked block (name / honest-status sentence / full-width download pill). That bug class only exists because a table was kept at phone width; in RTL it silently runs off the left edge where nobody looks.

### The one deliberate risk

**The honesty grade becomes the loudest typographic element on the domain.** On every card, on every surface, the status word is set in Frank Ruhl Libre at **28–40px, above the project name** — so you read `נכשל · NEGATIVE RESULT` before you read what the project is called.

```
תוצאה שלילית · NEGATIVE RESULT   → --dyo       #10131A
חי · LIVE                        → --otot      #0E7C8A
מאמן · TRAINING                  → --machshava #5B45C9
אב-טיפוס · PROTOTYPE             → --nechoshet #9A5225
רעיון · CONCEPT                  → --amum      #5E6470
מושהה · PARKED                   → --amum + a struck hairline
```

No portfolio on earth leads with the word FAILED at 36px. That is the point — it cannot be mistaken for a template, because no template would ever do it. It also repairs fix #21 directly, and it is how a stranger gets the read in five seconds.

Note the colour decision inside it: **NEGATIVE RESULT is full ink, not red.** Red would mean *error*. A negative result is not an error, it is a result — often the most expensive one on the page — and full black on quiet paper is the loudest thing a page can say. The whole editorial argument, in one hex value.

**Everything else goes quiet around it.** Warm paper, one hairline weight, one gradient rule per page, photographs of real objects, no glow, no badge soup, no second accent competing. The loud thing is the honesty and nothing else is allowed to shout.

---

## D. THE IMAGE SET — 10 Flux images (+1 deliberate refusal)

### The shared visual grammar

**Every image is an overhead photograph of real, worn, hand-made objects on the same sheet of warm paper, lit by one window.** Not renders. Not glowing neural networks. Not "AI art." The subject of each frame is *a made thing* — a breadboard, a stack of prints, a copper trace, a petri dish — because that is literally what he does: he builds physical objects and writes Hebrew about them.

Six constraints, repeated verbatim in all ten prompts, which is the actual mechanism that makes them a family:

1. **Camera** — 90° top-down flat-lay, 50mm macro, f/5.6.
2. **Light** — one north window, upper left, soft, no fill, one soft shadow to the lower right.
3. **Ground** — the same warm off-white paper with visible fine grain in every frame.
4. **In-frame palette** — oxidized copper, deep teal-green patina, matte violet-black, warm paper. Nothing red, nothing neon, nothing saturated blue.
5. **Objects** — real, worn, imperfect. Solder blobs, pencil marks, fingerprints, dust.
6. **No text, no letters, no logos, no faces, no people, no screens.** Critical for two reasons: Flux renders garbage text and Hebrew text especially, and the type on this domain must come from the type system, never from an image.

Practical: **keep the first ~70 words byte-identical across all ten and change only the subject sentence.** That is what holds the lighting and tonality together far more reliably than a shared seed. Settings: `flux1-dev-fp8`, 26 steps, guidance 3.2, euler/beta. Render 3 candidates each, pick one. Output PNG masters, ship WebP q82 at 1024w + 512w.

**Budget, honestly:** ~16 minutes of GPU for one pass of ten, ~48 minutes at 3 candidates each. That is the real number at his measured 50s/768×512.

**THE LOCKED PREFIX** (identical in every prompt below):

> *Overhead flat-lay photograph, camera directly above at ninety degrees, 50mm macro lens, f/5.6, soft daylight from a single north-facing window at the upper left, one soft shadow falling to the lower right, no fill light and no studio lighting. The surface is warm off-white paper with fine visible grain. Muted palette of oxidized copper, deep teal-green patina, matte violet-black and warm paper. Real worn handmade objects, solder blobs, pencil marks, dust. No text, no letters, no logos, no people, no screens.*

**THE LOCKED SUFFIX** (identical in every prompt below):

> *Documentary still life, quiet, unstyled, natural colour, fine film grain, not glossy, not a product shot.*

**Negative (for a CFG-based workflow; harmless otherwise):** `text, letters, hebrew letters, watermark, logo, signature, people, hands, faces, screens, ui, neon, glow, lens flare, 3d render, cgi, plastic, glossy, saturated colours, blue tint, red, stock photo, studio lighting, bokeh balls`

---

**1. `bench-overview.webp`** — apex, full-bleed band at the fold, between manifesto and doors · **1536×656 (21:9)**

> [PREFIX] A whole cluttered workbench seen from above: a green breadboard threaded with copper jumper wires, a small unmarked circuit board with hand-soldered joints, a coil of enamelled copper wire, a graphite pencil worn short, a folded sheet of grid paper covered in hand-drawn diagrams of small circles joined by lines, a brass caliper lying open, a scattering of loose resistors, and an empty white ceramic coffee cup with a ring stain on the paper beside it. [SUFFIX]

*The coffee cup is the point — קפה קלוד, לא תאגיד קלוד.*

**2. `door-eran.webp`** — apex ERAN door + eran.iddoperez.ai header · **1024×688 (3:2)**

> [PREFIX] A single sheet of warm grid paper lying flat on the desk, covered with a dense hand-drawn network of small circles connected by pencil lines, drawn and redrawn many times with visible erasure marks and graphite smudges; three of the circles have been carefully filled in with copper-coloured ink. A stub of pencil and a soft eraser worn grey lie at the edge of the sheet. [SUFFIX]

*Not a glowing brain — a drawing being corrected. That is exactly what ERAN is.*

**3. `door-lab.webp`** — apex LAB door + lab.iddoperez.ai header · **1024×688 (3:2)**

> [PREFIX] About a dozen small identical white index cards laid out in a loose grid on the desk, each card blank, each holding one different small physical object at its centre: a ceramic tile with a single dark cell on it, a small flat metal plate, a short length of pale wood threaded with fine white fibres, a copper coil, a glass prism, a fragment of punched paper tape, a brass gear, a square of fine copper mesh. One card near the centre holds nothing at all. [SUFFIX]

**4. `door-quorum.webp`** — apex QUORUM door + quorum.iddoperez.ai header · **1024×688 (3:2)**

> [PREFIX] An open old book with wide margins lying flat on the desk, the page area deliberately far out of focus and completely illegible, no readable marks anywhere. Four small smooth river stones of different colours rest on the open page — one teal-grey, one violet-grey, one copper-brown, one pale cream — arranged facing one another, with a thin copper wire looping loosely between them. [SUFFIX]

*"Deliberately out of focus and illegible" is how you photograph a book without Flux inventing fake Hebrew.*

**5. `door-arena.webp`** — apex ARENA door + arena.iddoperez.ai header · **1024×688 (3:2)**

> [PREFIX] Four small smooth river stones resting directly on the warm paper — one teal-grey, one violet-grey, one copper-brown, one pale cream — pushed out of alignment as if caught mid-motion, with fine dry copper filings scattered across the paper tracing the curved paths along which each stone moved. One stone sits noticeably apart from the other three. [SUFFIX]

*Same four stones as #4, one moment later. That is what makes them a pair rather than two pictures.*

**6. `door-erancloud.webp`** — apex ER"N-CLOUD door + erancloud.iddoperez.ai header · **1024×688 (3:2)**

> [PREFIX] A dozen small identical square ceramic tiles spread across the desk at irregular distances from one another, each tile holding a single tiny bead of solder at its centre, with one continuous length of fine enamelled copper wire threaded loosely from tile to tile connecting all of them. The wire is slack and hand-laid, curving and uneven, never taut. [SUFFIX]

*Slack, hand-laid wire reads as volunteers. Taut wire would read as infrastructure.*

**7. `door-pong.webp`** — apex PONG door + pong.iddoperez.ai header · **1024×688 (3:2)**

> [PREFIX] A shallow round glass petri dish resting on the warm paper seen from directly above, filled with a fine pale mycelial web that has grown into a dense branching network, a few pale threads reaching over the rim and out onto the paper. Beside the dish lie a pair of fine steel tweezers and a short length of bare copper wire laid parallel to it. [SUFFIX]

*Real mycelium, not a render of one. The page calls itself a mushroom-brain; give it an actual mushroom.*

**8. `door-federation.webp`** — apex FEDERATION door + federation.iddoperez.ai header · **1024×688 (3:2)**

> [PREFIX] Four identical matte dark-grey anodised aluminium blocks arranged in a square on the warm paper, each with a small bundle of copper wires emerging from one edge; the four bundles twist together into a single thicker cable that runs off the edge of the frame. A small worn brass key lies flat on the paper beside the nearest block. [SUFFIX]

*Four boxes, one braid, one key. No LEDs — LEDs would be a liveness claim the panel cannot currently back.*

**9. `door-helios.webp`** — apex HELIOS door + helios.iddoperez.ai header · **1024×688 (3:2)**

> [PREFIX] A shallow ceramic dish of coarse sea salt and a small stack of thick paper cards on the desk, with a plain circular convex lens resting on the topmost card focusing the window light into one small bright disc on the paper, its edge just beginning to darken. A brass ruler lies along the bottom of the frame. [SUFFIX]

**10. `share-card.webp`** — og:image for the apex; re-crop as the template for every subdomain · **1216×640 (1.9:1)**

> [PREFIX] A single hand-soldered circuit board lying at a slight angle on the warm paper and filling most of the frame, its copper traces bright against dark green, several components mounted visibly crooked by hand, and one long enamelled copper wire soldered on as an obvious after-the-fact repair, looping off the edge of the board and onto the paper. [SUFFIX]

*It has to read at 200px wide in a WhatsApp preview, so: one object, large, high contrast. **The visible repair is the thesis.***

**11. `page-404.webp`** — the new real 404 page (fix #1) · **1024×768 (4:3)**

> [PREFIX] A single empty white index card lying alone at a slight angle on the warm paper, one corner very slightly curled, with a faint rectangular outline of dust on the paper beside it where something used to sit, and a short length of copper wire with one bare cut end lying nearby. [SUFFIX]

*The dust outline where something used to be. Honest, quiet, funny without telling a joke.*

### The refusal: `alma.iddoperez.ai` gets no generated image, and neither does its door

**Do not generate an image for the memorial.** Not a sunflower, not a sunrise, not a "tasteful abstract." She has 690 photographs of her actual face on that server; making a synthetic picture to stand next to them is the one move on this domain that would be genuinely wrong, and the wrongness does not depend on how well it came out.

- **The apex's ALMA door** uses **one real photograph of her, chosen by Iddo, uncropped and untreated** — no desaturation, no duotone, no overlay. You do not apply a filter to a person.
- **The alma og:image** is the same photograph, or none. A blank share card is better than a generated one.
- The subdomain itself stays as it is: the grid is the page, the photographs are the imagery, and the existing hand-drawn sun and sunflowers are already hers.

Restraint here is not a shortfall in the image budget. It is the design decision.

---

## E. BUILD ORDER

### Wave 0 — make the truth checkable (nothing else is verifiable until these land)

1. **Real 404 across the zone.** Ship `404.html`; set `not_found_handling: "404-page"`. ✅ **Check:** `curl -sI https://iddoperez.ai/nope-xyz` → **404**, and likewise on all 8 subdomains; `curl -sI https://alma.iddoperez.ai/alma-photos.zip` → **404** instead of 200. *The dead ZIP becoming visible is the acceptance criterion.*
2. **Cloudflare analytics auto-injection off for the zone.** ✅ **Check:** `curl -s https://eran.iddoperez.ai \| grep -c cloudflareinsights` → **0**, and `document.querySelectorAll('script').length` → **0** on eran. The colophon is now true as served.
3. **Apex hero label bound to the data.** ✅ **Check:** with `age_s: 427700` the hero shows a grey dot, no animation, and `לפני 5 ימים`; force `age_s: 30` in devtools and it flips to a teal dot and `עכשיו`. **Both states observed, not one.**
4. **alma archive: ship it or remove the button.** Seven ZIPs ≤64MB by age band + a manifest. ✅ **Check:** `curl -sI .../alma-1990s.zip` → 200, `application/zip`, first two bytes `50 4b`, and it unzips to the stated count. If not shipping today, the button is gone today and `grep -c alma-photos.zip index.html` → **0**.
5. **pong: one endpoint, capped backoff, recorded run.** ✅ **Check:** with the network offline the page issues **≤1 request in 60s** (backoff visible in devtools), console error count stops rising within 30s, and the brain animates from the baked recording labelled `הקלטה`.
6. **arena: truncation, prompt leak, auto-scroll, `es.close()`.** ✅ **Check:** one full debate — all 7 turns and the מסקנה end on a sentence-final character; no turn's first 80 chars match the instruction template; the newest card is in viewport when it lands; kill the backend mid-stream and exactly **one** `/debate` request fires, not a loop.

### Wave 1 — make it reachable

7. **Viewport meta into all 14 lab files.** ✅ **Check:** at 390px, `document.documentElement.clientWidth === 390` and `visualViewport.scale === 1` on `lab/index` **and** on `ALMA-turing.html`.
8. **Type system, self-hosted.** Five woff2 subsets from one path; drop the Google Fonts link from apex and alma; add real `@font-face` to quorum and arena. ✅ **Check:** `document.fonts.check('700 16px "Miriam Libre"')` → **true on all nine surfaces**; the apex network log has **0** requests to `fonts.googleapis.com`.
9. **Tokens + contrast.** Publish `alma-tokens.css` with the six values and the dark overrides; adopt on apex, eran, quorum, arena. ✅ **Check:** an automated pass over every text/background pair on those four reports **≥4.5:1 for all text ≤18px** (this is what catches quorum's 3.36:1 and 3.95:1), and `--zahav` appears in **zero** `color:` rules.
10. **Downloads table → stacked blocks at ≤640px.** ✅ **Check:** at 390px every download pill satisfies `rect.left >= 0 && rect.right <= 390` — the exact measurement that found the bug, now passing.
11. **eran: 27px overflow, `lang`/`dir`.** ✅ **Check:** at 390px `scrollWidth === 390`; `document.documentElement.lang === 'he'`; every Hebrew block carries `lang="he" dir="rtl"`.
12. **alma accessibility.** alt from the manifest `age` field; tiles become `<button>`; arrow keys in the lightbox. ✅ **Check:** `document.querySelectorAll('img:not([alt])').length === 0`; `[...document.querySelectorAll('.cell')].filter(c=>c.tabIndex>=0).length === 690`; ArrowRight changes the lightbox `src`.
13. **Kill the dead ends.** Footer nav on `babble.html`, `join.html` and all 13 sims; link `CONNECT.md` at its three mentions; publish the repo and link it **or** delete the four "open source" claims and the broken `git clone`. ✅ **Check:** every HTML file on the domain has **≥1** anchor to its own root (`grep -c '<a ' ALMA-*.html` ≥ 1, ×13), and `grep -rc 'git.almaware' .` → **0**.
14. **Share metadata + favicon + canonical on all nine.** ✅ **Check:** for each of the nine, `curl -s URL` contains `og:title`, `og:description`, `og:image` and `rel="icon"`, and the og:image URL is absolute and returns 200.

### Wave 2 — the face

15. **Generate the ten images.** ✅ **Check:** ten files at the stated dimensions, then **lay all ten out on one contact sheet** — every frame must show the same shadow direction (lower-right) and the same paper tone. Any that doesn't gets rerolled. *The contact sheet is the acceptance test for "family"; there is no other way to check it.*
16. **The honesty grade goes big** on apex and eran. ✅ **Check:** computed `font-size` of `.grade` is **≥28px**, and the grade word's rendered height **exceeds the title's** — which is the observable form of "you read the grade first."
17. **Nine doors replace the 27-card wall.** ✅ **Check:** exactly 9 door cards above the text index; all 9 images 200; at 390px `scrollWidth === 390`; and **crawl the page: 27 project links still present, all 200.** Nothing may be lost in the restructure.
18. **Staleness renders its own age.** Every dated claim reads a `verified` field. ✅ **Check:** set a date 40 days back in the data and the chip renders `לפני 40 יום` and turns muted **with no code change**.

**Not a build step — needs Iddo:** alma's `robots.txt`. 690 family photographs including living children are currently open to indexing. Either answer is defensible; the wrong thing is it staying an accident.
> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# מיקו · MIKO — Eran's search organ

**לזכרה של עלמה ז״ל.**

Named by Iddo, 2026-08-20 09:46, after the Israeli films (צ'רלי וחצי / חגיגה בסנוקר).
Not a product. **This is the organ Eran will search the world with when he grows up.**

---

## 0. Why the previous one was archived

`almido-search` is in `_genizah/almido-search-20260820` — nothing deleted, and its good
parts are named below. It is archived because of what the evidence showed on 2026-08-20:

| claim it carried | evidence found | verdict |
|---|---|---|
| "ALMIDO worm BUILT — Beit Din IS the neuron" | 58 KB of real architecture in `net/` | **TRUE, and good** |
| "Ramchal logic curriculum" | `worm_logic.pt` trained 30 epochs → **48.2 % on unseen forms** | **FAILED** — below the 50 % coin flip |
| — | train loss stuck at 0.666 (chance = 0.693) | it learned **nothing** |
| — | per-form: `dayo 0% / dayo 100% / denying 100% / modus 0%` | one fixed answer per form, not inference |
| "the neuron is a court" | never once compared against a control | **UNTESTED until today** |

Today's first controlled run (Beit-Din triad vs vanilla, parameter counts matched to
0.02 %, same data/steps/seed): **vanilla 2.5646 vs court 2.6506 heldout.** The court lost.
But that test was on *next-token MIDI prediction* — a task this organ will never perform.
**Iddo's correction stands: I measured the wrong thing.** MIKO fixes the metric first.

**The two failures that must never repeat:** a training log whose last line says the model
failed, filed in memory as an achievement; and an architecture that ran for months with no
control to compare against.

---

## 0.5 The north star — one day MIKO runs on a living mushroom

Iddo, 2026-08-20 09:49: *"מיקו זה התולעת — יום מן הימים תרוץ על פטרייה חכמה."*

This is not decoration. It is the reason every choice in §2 is what it is, because a
mycelium **already is** the machine we are describing, and it has been for 400 million
years:

| MIKO's requirement | what mycelium already is |
|---|---|
| **takes its time** | signals travel millimetres per second, not 3 GHz. Slowness is the substrate's nature, not a compromise we are making. |
| **3D, with a cost for distance** | hyphae grow in a volume and every connection is literally a length of living tissue that must be fed. Distance has a metabolic price. |
| **event-driven / neuromorphic** | fungal networks carry spike-like electrical trains and chemical pulses — they emit when there is something to say, and are otherwise quiet. |
| **multi-weight connections** | one hypha carries several channels at once with different time constants: electrical, chemical, nutrient flow. A single scalar cannot represent that. |
| **multi-context** | the same signal means "food" in one region and "damage" in another; the network is not globally synchronised and does not need to be. |
| **a court, not a chief** | there is no central neuron. A ruling emerges from local agreement — which is exactly a Beit Din, and exactly not a CPU. |

**⚠️ CORRECTED BY IDDO, 10:00 — read this before the table above misleads you.**
*"קלוד, היא לא חייבת להיות כמו צמח, היא לא חייבת להיות כמו פטריה... זה רק השראה. מה
שחשוב שזה יעבוד ויביא מידע אמיתי, בעל תועלת, לא חרטה."*

I had written a design *law* here — "never adopt a mechanism that could not run on
mycelium". **That was wrong and it is struck out.** A law like that would have banned
mechanisms for being insufficiently fungal, which is precisely how a project ends up
elegant and useless. The plant and the mushroom are **inspiration, not specification.**

**THE ACTUAL GOAL, in his words and in this order:**
1. **It works.**
2. **It brings real, useful information — not bullshit.**
3. **It beats a Google search, a Perplexity search, and any other search**, on questions
   that matter to him.
4. **It may take as long as it takes.** Slowness is permitted precisely because the
   output must be worth waiting for.
5. **A small, smart, strong engine** — *"מנוע קטן וחכם"*. Small is a target, not an
   apology: it must be beatable-by-nobody at its size, the way [[project_eran_live]] is
   meant to be.

Biology stays as a source of ideas — take from it anything that makes MIKO better and
drop anything that doesn't. **The only test a mechanism must pass is §3's metrics.**

The near-term consequence is that MIKO runs on the DGX fleet **as a simulation of a
substrate it does not yet have** — and the simulation is written so the substrate can be
swapped in. See [[project_mycelium_computer]] and the physical builds
(memristor grid, protoneuron, beitdin-hw) — they stop being a separate universe and
become MIKO's future body.

---

## 1. What MIKO is

A worm that is given a question, **takes its time**, burrows, and comes back with
**relevant results and a judged conclusion — with the disagreement left visible.**
Slowness is a design property, not a cost: Iddo, explicitly, *"it runs slowly on one DGX
and takes its time — ask and come back."* Therefore **speed is never a scoring criterion**
in any MIKO experiment.

Inherited unchanged from the archive because they were right:
- **ALMA binding** — text enters as **bytes**, each bound to `byte ⊕ letter ⊕ sound`
  (א ⟷ /a/ ⟷ byte). No BPE, no borrowed tokenizer.
- **GIST** — a page has a gist; pooling is attention-weighted and the attention is itself
  produced by a court.
- **JEPA** — predict the *gist* of a hidden span, never the bytes.
- **Beit Din** — three seats, **median** ruling (2-of-3, so one corrupted seat cannot
  drag it), **dissent = max − min carried forward** and emitted with every score.
- **eran3 is forbidden in code.** It is Iddo's personal machine.

## 2. What is NEW in MIKO — the four things that do not exist in any net yet

Iddo, 2026-08-20 09:44: *"בשפת עלמה כלומר ביולוגית — ריבוי משקלים — ריבוי הקשרים — 3D — נוירומורפי."*

### 2.1 ריבוי משקלים · multi-weight neurons
A connection today is one scalar. In MIKO a connection carries **k weights** with different
time constants and different roles — the design already written (never run) in
`alma-multiweight-experiment`: same total weight budget, fewer neurons, richer each.
**Test as written there:** vanilla 1 weight × 1500 neurons vs ALMA 3/5/10 weights ×
500/300/150 neurons, identical scalar budget. It was designed in July and never executed —
MIKO executes it before adopting it.

### 2.2 ריבוי הקשרים · multi-context
The same byte means different things in different contexts. A MIKO unit holds several
context channels at once (the word's own meaning, its neighbourhood's gist, the question
being asked) and the court rules **per context**, so dissent can mean "this is relevant to
your question but not to its own paragraph" — which is exactly the judgement a search organ
needs to make.

### 2.3 3D
Units live at coordinates in a 3-D volume, and **connection cost grows with distance**.
This is not decoration: it forces locality, makes the network's structure inspectable
(you can *look* at which region lit up for a question), and is the geometry a neuromorphic
substrate would actually have. The existing `alma-language/perceptron3d` is a *web
visualisation*, not a network — MIKO's 3-D is in the weights, and the visualiser becomes
its eye.

### 2.4 נוירומורפי · neuromorphic
Event-driven, not frame-driven: a unit emits only when it has something to say, and the
cost model counts events, not FLOPs. This is what makes the physical builds
(memristor grid, protoneuron, beitdin-hw) reachable from the same code instead of being a
separate universe.

### 2.5 Logic, trained — and this time proven
Ramchal's logic and שקלא וטריא stay, but the 48.2 % result is the baseline to beat, and
**the acceptance bar is stated before training starts:** ≥ 75 % on inference forms it has
never seen, with no form scoring 0 % or 100 % (those two numbers together are the signature
of "one fixed answer per form", which is what happened last time).

---

## 2.9 The two floors — where the court lives, after the measurements

Iddo, 10:26, after seeing the court lose twice: *"בדין יזרח ויצליח דווקא בתולעת, כי
בתולעת צריך הכרעות — זה שימושי, זה לא שימושי... זה יכול להיות מאוד סובייקטיבי, זה לא
משהו שאתה יכול למדוד אותו כל כך."*

He is pointing at the split the numbers themselves drew today:

- **The perception floor** — reading bytes, forming gists, predicting. Here the
  measurements say GIST wins (champion at Pong, and the court lost twice). Perception
  has a right answer, redundancy costs parameters, one good reader beats three that
  vote. **GIST perceives.**
- **The ruling floor** — הכרעות: useful / not useful, follow / drop, trust / doubt.
  Here there is often NO single right answer, and this is where the court's structure
  is native: three perspectives, a ruling, and the disagreement kept visible. This is
  also where it is already PROVEN in his ecosystem — Quorum, the worm's eight lenses,
  the fleet grading — all courts of judges, none of them neurons. **The court rules.**

**On "you can't really measure it":** half-agreed, and the half matters. Subjective does
not mean unmeasurable — it means **the ground truth is Iddo's own judgement.** The
measurement is pairwise: show him two findings for the same question — *which was more
useful?* Twenty such choices are a real benchmark of his taste, and the worm's job is to
match it (the fleet's 0-1 scores are only a proxy teacher until his own preferences
accumulate). What genuinely cannot be pre-measured is covered by the court's honesty:
**when the seats disagree, the finding ships marked "contested" — במחלוקת.** For
subjective questions, that marking is not a weakness of the answer; it IS the answer.
No Google result ever tells you it is contested. MIKO's will.

**And the ruling is still binary — Iddo, 10:27:** *"קשה לי לשים לך מדד. אבל בית דין צריך
לתת איזושהי הכרעה אם זה רלוונטי או לא, בכל זאת. מה שחשוב זה רלוונטיות של המידע שהיא
מביאה."* So the contract is fixed: **every finding arrives with a ruling — רלוונטי /
לא רלוונטי — plus the dissent that produced it.** A court that only shrugs is not a
court; תיקו is allowed but must be rare and must say why.

**He never has to define the metric — he emits it by living:** every finding MIKO
shows him carries one tap — הועיל 👍 / לא הועיל 👎. That stream is simultaneously the
benchmark (does her ruling match his taps?) and the training signal. The day she has
200 taps of his, "relevance to Iddo" stops being subjective philosophy and becomes a
number: agreement rate with the only judge who counts.

---

## 3. The metrics MIKO is judged by — decided BEFORE any training

A model is not "good"; it is good *at a stated thing*. MIKO's three, in order:

1. **RELEVANCE.** Given a question and a page, reproduce the fleet's 0–1 relevance
   judgement from raw bytes. Data already exists: 156 fleet-scored pairs in the archive
   (`data/pairs.jsonl`), to be grown to ≥ 2,000 before it counts.
   *Baseline to beat: a vanilla net of identical parameter count.*
2. **CALIBRATION — the court's real claim.** Does **dissent predict error**? Bucket
   predictions by dissent; if the high-dissent bucket is not measurably less accurate, the
   whole Beit Din idea has failed its own thesis and we say so out loud.
3. **ROBUSTNESS — median vs mean, at last.** Corrupt one seat (zero it, invert it,
   saturate it) and measure the drop. The claim is that a median barely moves and a mean
   loses a third. **This is a one-hour experiment and it has never been run.**

Speed is **not** a criterion. Parameter counts are matched within 1 % in every comparison,
seeds are ≥ 3, and every number is reported next to its vanilla control — including the
ones that lose.

---

## 4. Build order (each step ships a number, not a claim)

| # | step | the number it must produce |
|---|---|---|
| 1 | `bench/` — relevance + calibration + robustness harness, on the archived 156 pairs | three baseline numbers for a vanilla net |
| 2 | port the triad from the archive, unchanged, into the harness | court vs vanilla on all three metrics |
| 3 | run the multi-weight experiment that was written in July and never run | does k>1 beat k=1 at equal budget? |
| 4 | multi-context units | does per-context dissent beat one global score? |
| 5 | 3-D placement + distance cost | what does locality cost, what does it buy |
| 6 | event-driven forward pass | events per query vs dense FLOPs |
| 7 | logic curriculum, bar = 75 % on unseen forms | pass or fail, stated plainly |
| 8 | the worm itself: crawl → gist → court → sourced answer with dissent | end-to-end on real questions |

Steps 1–3 are the honest core. If step 2 loses again on the *right* metric, the court goes
into the document and MIKO keeps the parts that measured well. **No step is written up as
"BUILT" until its number exists.**

---

## 4.5 MIKO explores by herself, and remembers in the cloud

Iddo, 2026-08-20 09:53–09:55: *"אני רוצה שמיקו תלמד ותחקור לבד את האינטרנט ויהיה לה מאגר
הולך וגדל שנשמר על ענן"* · *"מיקו תתחיל בגוגל ומשם תלמד לבד."*

So MIKO is not only asked questions — she goes out on her own. Three parts:

**A.0 — the root and the crawler are the same question.** Iddo, 09:56, on the same
morning he asked why his mint sent roots into the reservoir: *"כמו הצמח שמחפש מים...
היא מחפשת מידע."* This is not a metaphor, it is the design. A root in NFT has water
everywhere and therefore **no gradient**, so it stops being guided by water and falls
back on gravity and flow — it goes where the slope goes, not where the value is. A
crawler on the open web has pages everywhere and the same problem: with no gradient it
follows link-count and popularity, which is gravity, not value. **MIKO's dissent is the
gradient a root would have had.** The root-choice rhizotron (`D:\CLAUDE\root-maze`) and
MIKO are one experiment asked of two substrates: *what steers a searcher when everything
looks equally available?* Whatever the mint answers should inform how MIKO chooses her
next link — and if the plant turns out to follow oxygen rather than water, that is a real
finding about foraging, not a gardening detail.

**A.1 Server to server, exactly like a search engine's bot.** Iddo, 09:56: *"מחשב מחשב
זה אומר שרת שרת, לא מחשבים פרטיים"* — MIKO fetches PUBLIC web servers over HTTP, the
same thing Googlebot does, and never touches a private machine, a home network, or
anything behind a login. No port scanning, no credentials, no intranet. If a page needs
a password, it is not MIKO's page.

**A. The seed and the drift.** She starts from a search engine (Google as the seed)
and from there follows her own curiosity: every page she reads yields the next
questions, and she chooses which to pull on. The choice is scored — a page is worth
following if the court expects to LEARN from it (high dissent = the seats disagree =
this is where she does not yet know), not if it merely looks relevant. **Curiosity is
defined as high dissent, which makes the Beit Din the exploration engine, not just the
judge.** That is a testable claim and it goes in the metrics: does dissent-driven
crawling reach useful pages faster than relevance-driven crawling?

**B. The archive that grows.** Everything she reads is kept: the raw page, the gist she
formed, the court's ruling, the dissent, and the date. Not links — the *content and the
judgement*, because a link rots and a judgement does not. This is Eran's memory of the
world, and it must outlive any single machine.

**C. Cloud, with the boundary stated.** The archive is mirrored off the fleet
(Cloudflare R2 is the existing path — see [[reference_cloudflare_deploy]]). Rules that
are not negotiable: **nothing private ever enters it** — no Café-Claude recordings, no
mic corpus, no personal files; only public pages MIKO fetched herself, plus her own
judgements. It is content-addressed and append-only, so an old judgement is never
silently rewritten — a changed mind is a NEW entry that cites the old one. And it costs
money per gigabyte, so growth is budgeted and reported, never unbounded.

**Politeness is a hard constraint, not a nicety:** robots.txt is obeyed, one request at a
time per host with a real delay, a truthful user-agent, and any site that says no is
never fetched again. A worm that gets Iddo's address banned is a worm that stops working.

---

## 5. Standing rules for this project

- **Never on the PC.** All training on the DGX fleet; eran3 never.
- **Every experiment has a vanilla control of matched size, or it does not count.**
- **The last line of every training log is read out loud** before anything is written to
  memory. The 48.2 % line sat unread for a day.
- A README may state what code *does*, never what it *achieves*. Achievements live in
  results files with numbers in them.

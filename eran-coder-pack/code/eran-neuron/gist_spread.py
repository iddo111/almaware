# -*- coding: utf-8 -*-
"""
GIST-SPREAD — אחזור-לפי-הקשר ⇒ פעפוע-הפעלה / context retrieval ⇒ spreading activation
======================================================================================
עברית + English. ספריית-תקן בלבד (stdlib) — בלי numpy/torch. דטרמיניסטי, לא נשבר.
Pure Python 3 stdlib only (no numpy/torch). Deterministic. Meant to run, not to break.

עקרון עידו / Iddo's principle (implemented FAITHFULLY):
  * המוח עובד על הֶקְשֵׁר.                 The brain works on CONTEXT.
  * האחזור רץ לפי-הקשר אל ה-GIST התואם.   Retrieval runs by context toward the matching GIST.
  * התאמת-ה-gist היא בו-זמנית הציון והמשקל  The gist-match is SIMULTANEOUSLY the SCORE and
    (מספר אחד!).                            the WEIGHT — one number.  (score == weight)
  * ואז ההפעלה מתפשטת בכל המסלול.          Then activation SPREADS through the whole pathway.

בשפת המנוע / in the engine's idiom:
  ב-neuron.py / rich_connection.py קשר עשיר נושא gate/weight ששולט בהעברה.
  A rich connection carries a gate/weight that governs transmission.
  כאן ה-gate הזה **הוא** התאמת-ה-gist של הצומת — הציון והמשקל הם אותו מספר.
  Here that gate == the node's gist-match — the score and the weight are the SAME number.

יושר / HONESTY:
  וקטורי ה-GIST כאן מוגדרים ביד (hand-set) — זו הדגמה של ה*דינמיקה*, לא של למידה.
  The GIST vectors are HAND-SET — this demonstrates the DYNAMICS, not learned embeddings.
  זהו אחזור בסגנון spreading-activation / attention, לא אימון.
  This is spreading-activation / attention-like retrieval, NOT training.
"""
import math
import sys


# ── מתמטיקה של וקטורים (רשימות python, בלי numpy) / vector math (plain lists) ──
def dot(u, v):
    return sum(a * b for a, b in zip(u, v))


def norm(u):
    return math.sqrt(dot(u, u))


def cosine(u, v):
    # קוסינוס-הדמיון = כמה שני הקשרים "מצביעים לאותו כיוון"
    # cosine similarity = how much two contexts point the same way
    du, dv = norm(u), norm(v)
    if du == 0.0 or dv == 0.0:
        return 0.0
    return dot(u, v) / (du * dv)


# ── צומת-מושג / concept node ─────────────────────────────────────────────
class ConceptNode:
    """
    צומת אסוציאטיבי: שם + וקטור-GIST (התמצית הסמנטית) + הפעלה נוכחית.
    Associative node: name + GIST vector (the semantic essence) + current activation.
      gist    — הווקטור שמגדיר את מהות המושג / the vector defining the concept's essence
      act     — ההפעלה החיה / the live activation
      gate    — score==weight : התאמת-ה-gist להקשר; גם הזרקה וגם משקל-פעפוע
                the gist-match to context; BOTH the injected score AND the propagation weight
    """
    def __init__(self, name, gist):
        self.name = name
        self.gist = list(gist)
        self.act = 0.0
        self.gate = 0.0     # ימולא מההקשר / filled from context (this is score==weight)

    def match(self, context):
        # ציון = קוסינוס חיובי מול ההקשר.  זהו המספר האחד:
        # score = positive cosine vs the context.  THIS is the one number:
        #   (a) ההפעלה שמוזרקת לצומת / the activation injected into the node
        #   (b) ה-gate/weight שבו הצומת מפעפע הלאה / the gate the node propagates with
        self.gate = max(0.0, cosine(context, self.gist))
        return self.gate


# ── הגרף האסוציאטיבי / the associative graph ─────────────────────────────
class GistGraph:
    """
    גרף קטן של מושגים + קשתות מכוונות עם עוצמות-בסיס.
    Small graph of concepts + directed associative edges with base strengths.
    האחזור = הפעלה-מתפשטת מגודרת ב-gist (score==weight).
    Retrieval = spreading activation gated by the gist (score==weight).
    """
    def __init__(self, decay=0.5):
        self.nodes = []
        self.index = {}                 # שם→אינדקס / name→index
        self.edges = []                 # (i, j, base_strength) : i → j
        self.decay = decay              # דעיכה ~0.5 / decay ~0.5

    def add(self, name, gist):
        self.index[name] = len(self.nodes)
        self.nodes.append(ConceptNode(name, gist))

    def link(self, a, b, strength):
        # קשת אסוציאטיבית מכוונת a→b / directed associative edge a→b
        self.edges.append((self.index[a], self.index[b], strength))

    # ── הליבה: פעפוע-הפעלה לפי ה-gist / core: gist-gated spreading activation ──
    def retrieve(self, context, steps=6, record=False):
        n = len(self.nodes)

        # 1) התאמת-הקשר ⇒ score==weight לכל צומת (מספר אחד לכל מושג)
        #    context match ⇒ score==weight per node (one number per concept)
        for nd in self.nodes:
            nd.match(context)           # קובע nd.gate ומזריק כהפעלה התחלתית
            nd.act = nd.gate            # ההזרקה = בדיוק אותו מספר / injection = same number

        # מדד-שליטה גולמי (לפני נירמול) — כדי לחשוף הקשר "שטוח/חלש"
        # raw dominance (pre-normalization) — to expose a "flat/weak" context
        self.raw_peak = max((nd.gate for nd in self.nodes), default=0.0)

        # הזרקת-הקשר המתמדת = הציון (score) — נשמרת בנפרד ומוזרקת בכל צעד
        # the standing context injection = the score — kept aside, re-injected each step
        inject = [nd.gate for nd in self.nodes]

        trace = []
        if record:
            trace.append([round(nd.act, 6) for nd in self.nodes])

        # צימוד-פעפוע < 1 : הזרקת-הקשר היא הכוח הראשי, הפעפוע הוא תוספת משנית.
        # spread coupling < 1 : the context injection is the primary drive; spreading is a
        # secondary bump — so the QUERIED concept (top gate) stays the peak, and its associates
        # light BELOW it in a sensible order.
        coupling = 0.35

        # נירמול-פנימי לפי סך-הכניסות: מונע מ"צומת-רכזת" (fan-in גבוה) לצבור לא-הוגן
        # divisive input normalization: stops a HUB node (high fan-in) from unfairly
        # accumulating, so the best gist-match — the queried concept — stays the winner.
        in_sum = [0.0] * n
        for (j, i, base) in self.edges:
            in_sum[i] += base
        in_norm = [(s if s > 1e-9 else 1.0) for s in in_sum]

        # 2) פעפוע לאורך T צעדים / spreading over T steps
        #    a_i(t) = decay*a_i(t-1) + inject_i + coupling*gate_i * Σ_j edge(j→i)*a_j(t-1)/in_norm_i
        #    שני התפקידים של אותו מספר / the two roles of the one number:
        #      inject_i  = ההפעלה שמוזרקת לצומת i / the activation injected into node i
        #      gate_i    = המשקל שבו i מפעפע הלאה / the weight node i propagates with
        #    שניהם == התאמת-ה-gist → score==weight חי לאורך כל הפעפוע.
        #    both == the gist-match → score==weight lives across the whole spread.
        for _ in range(steps):
            prev = [nd.act for nd in self.nodes]
            nxt = [self.decay * prev[i] + inject[i] for i in range(n)]
            for (j, i, base) in self.edges:
                nxt[i] += coupling * self.nodes[i].gate * base * prev[j] / in_norm[i]  # ← gate=score
            for i in range(n):
                self.nodes[i].act = nxt[i]
            self._clamp()                # חוסם התפוצצות בלי למחוק חולשה מוחלטת / bound, keep scale
            if record:
                trace.append([round(nd.act, 6) for nd in self.nodes])

        # מרווח-שליטה גולמי (לפני נירמול-תצוגה) — כך הקשר השטוח נשאר שטוח
        # RAW dominance margin (before display-normalization) — a flat context stays flat
        acts = [nd.act for nd in self.nodes]
        srt = sorted(acts, reverse=True)
        self.raw_peak_act = srt[0] if srt else 0.0
        self.raw_dominance = (srt[0] - srt[1]) if len(srt) > 1 else (srt[0] if srt else 0.0)

        # נירמול-תצוגה בלבד: הגדול = 1.0 (רק להדפסה/JSON) / display-only: max→1.0
        m = max(acts, default=0.0)
        if m > 1e-12:
            for nd in self.nodes:
                nd.act /= m

        pathway = sorted(self.nodes, key=lambda nd: nd.act, reverse=True)
        return pathway, trace

    def _clamp(self):
        # חסימה רכה: אם השיא חורג מ-cap, מקטינים פרופורציונלית (יציב, דטרמיניסטי)
        # soft clamp: if peak exceeds cap, scale down proportionally (stable, deterministic)
        cap = 6.0
        m = max((nd.act for nd in self.nodes), default=0.0)
        if m > cap:
            for nd in self.nodes:
                nd.act *= cap / m


# ── בניית עולם קטן / build a tiny world ──────────────────────────────────
def build_world():
    """
    ~10 מושגים. וקטורי-gist מוגדרים-ביד לאורך 10 צירים סמנטיים גסים:
    ~10 concepts. HAND-SET 10-dim gists over rough semantic axes:
      0 חי/animal  1 מזון/food  2 ים/sea  3 בית/domestic  4 נוזל/liquid
      5 מלוח/salty 6 טורף/predator 7 חלב-מוצר/dairy
      8 זהות-כלב/dog-identity  9 זהות-חתול/cat-identity
    שני צירי-הזהות מפרידים מושגים דומים (כלב מול חתול) — כך שהמושג-הנשאל מנצח.
    two identity axes separate look-alike concepts (dog vs cat) so the QUERIED concept wins.
    """
    g = GistGraph(decay=0.5)
    #  צירי-הזהות נושאים את רוב הנורמה של החיות, כדי שהמושג-הנשאל יובלט מעל דומיו.
    #  identity axes carry most of each animal's norm, so the QUERIED concept stands out.
    #        name        חי  מזון ים  בית נוזל מלוח טורף חלב  כלב חתול
    g.add("כלב",       [0.4, 0.0, 0.0, 0.3, 0.0, 0.0, 0.3, 0.0, 1.0, 0.0])  # dog
    g.add("חתול",      [0.4, 0.0, 0.0, 0.3, 0.0, 0.0, 0.3, 0.0, 0.0, 1.0])  # cat
    g.add("חלב",       [0.2, 0.9, 0.0, 0.3, 0.9, 0.0, 0.0, 1.0, 0.0, 0.0])  # milk
    g.add("גבינה",     [0.0, 0.9, 0.0, 0.2, 0.0, 0.4, 0.0, 0.9, 0.0, 0.0])  # cheese
    g.add("ים",        [0.0, 0.0, 1.0, 0.0, 0.9, 0.7, 0.0, 0.0, 0.0, 0.0])  # sea
    g.add("מלח",       [0.0, 0.3, 0.6, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0])  # salt
    g.add("דג",        [0.7, 0.5, 0.9, 0.0, 0.2, 0.4, 0.3, 0.0, 0.0, 0.0])  # fish
    g.add("עצם",       [0.1, 0.2, 0.0, 0.5, 0.0, 0.0, 0.1, 0.0, 0.1, 0.0])  # bone
    g.add("עכבר",      [0.5, 0.0, 0.0, 0.3, 0.0, 0.0, 0.1, 0.0, 0.0, 0.1])  # mouse
    g.add("מים",       [0.0, 0.1, 0.4, 0.2, 1.0, 0.0, 0.0, 0.1, 0.0, 0.0])  # water

    # קשתות אסוציאטיביות מכוונות / directed associative edges (base strengths)
    g.link("כלב", "עצם", 0.9);   g.link("כלב", "חתול", 0.6);  g.link("כלב", "חלב", 0.3)
    g.link("חתול", "עכבר", 0.9); g.link("חתול", "דג", 0.7);   g.link("חתול", "חלב", 0.6)
    g.link("חלב", "גבינה", 0.9); g.link("חלב", "מים", 0.4)
    g.link("גבינה", "מלח", 0.5)
    g.link("ים", "דג", 0.9);     g.link("ים", "מלח", 0.8);    g.link("ים", "מים", 0.7)
    g.link("מלח", "מים", 0.5)
    g.link("דג", "מלח", 0.4);    g.link("דג", "עכבר", 0.2)
    g.link("עכבר", "עצם", 0.3)
    g.link("מים", "ים", 0.4)
    return g


def _context_like(g, name, jitter=0.0):
    # הקשר ~ ה-gist של מושג נתון (עם רעש קבוע קטן, דטרמיניסטי — לא rng)
    # a context ~ a given concept's gist (small FIXED deterministic jitter, no rng)
    base = list(g.nodes[g.index[name]].gist)
    return [v + jitter * (((i * 7) % 5) - 2) * 0.1 for i, v in enumerate(base)]


def _print_pathway(g, label, context):
    pathway, _ = g.retrieve(context, steps=6)
    winner = pathway[0]
    lit = "  →  ".join(f"{nd.name}({nd.act:.2f})" for nd in pathway if nd.act > 0.02)
    print(f"הקשר/context {label}:  זוכה/winner = {winner.name}   "
          f"(שיא-gist/peak-match={g.raw_peak:.2f}  מרווח-שליטה/raw-margin={g.raw_dominance:.2f})")
    print(f"  מסלול-שנדלק/lit pathway:  {lit}")
    return winner


# ── הדגמה / demo ─────────────────────────────────────────────────────────
def _demo():
    try:
        sys.stdout.reconfigure(encoding="utf-8")     # שלא יישבר על עברית / no unicode crash
    except Exception:
        pass

    g = build_world()

    print("=" * 68)
    print("GIST-SPREAD — אחזור-לפי-הקשר ופעפוע-הפעלה / context retrieval + spreading")
    print("=" * 68)
    print("יושר/HONESTY: וקטורי ה-gist מוגדרים ביד — הדגמת דינמיקה, לא למידה.")
    print("              gists are HAND-SET — a demo of the DYNAMICS, not training.\n")

    # ── ההוכחה ש-score==weight / the score==weight proof ──
    ctx_dog = _context_like(g, "כלב")
    node = g.nodes[g.index["כלב"]]
    score = node.match(ctx_dog)         # הציון המוזרק / the injected score
    weight = node.gate                  # המשקל שבו הצומת מפעפע / the propagation weight
    print("— זהות ציון==משקל / score==weight identity —")
    print(f"  צומת/node '{node.name}':  score(injected)={score:.6f}  ==  "
          f"weight(gate)={weight:.6f}   →  {'זהים/IDENTICAL ✓' if score == weight else 'שונה!'}")
    print("  (מספר אחד משמש גם כהפעלה שמוזרקת וגם כמשקל-הפעפוע / one number = injection AND gate)\n")

    # ── הקשר A: קרוב ל'כלב' / near 'dog' ──
    print("-" * 68)
    print("הקשר A — קרוב ל'כלב' / context A — near 'dog'")
    print("-" * 68)
    _print_pathway(g, "A", ctx_dog)

    # ── הקשר B: קרוב ל'ים' — מסלול אחר / near 'sea' — a DIFFERENT pathway ──
    print("\n" + "-" * 68)
    print("הקשר B — קרוב ל'ים' / context B — near 'sea'")
    print("-" * 68)
    _print_pathway(g, "B", _context_like(g, "ים"))

    # ── הקשר לא-קשור / an orthogonal/unrelated context — flat, nothing dominates ──
    print("\n" + "-" * 68)
    print("הקשר C — אורתוגונלי/לא-קשור / context C — orthogonal/unrelated")
    print("-" * 68)
    # הקשר מנוגד לכל הצירים → כל התאמת-gist נחתכת ל-0 (cosine שלילי → max(0,·)=0)
    # a context anti-aligned with every axis → every gist-match clamps to 0
    ctx_unrel = [-0.4] * 10
    pathway, _ = g.retrieve(ctx_unrel, steps=6)
    top = pathway[0]
    active = [nd for nd in pathway if nd.act > 0.02]
    print(f"הקשר/context C:  זוכה/top = {top.name}({top.act:.2f})   "
          f"(שיא-gist/peak-match={g.raw_peak:.2f}  שיא-הפעלה/peak-activation={g.raw_peak_act:.2f})")
    print(f"  צמתים-פעילים/active-nodes = {len(active)}  "
          f"(מתוך {len(g.nodes)})")
    print(f"  ← שיא-ה-gist = 0 → אפס הזרקה, שום מסלול לא נדלק / peak-match = 0 → "
          f"zero injection, NOTHING lights")

    print("\nגמור. האחזור רץ לפי הקשר אל ה-gist, וההפעלה פעפעה במסלול.")
    print("Done. retrieval ran by context toward the gist, activation spread the pathway. 🧠")


# ── פלט JSON להדמיה חיה / compact JSON trace for live viz ────────────────
def _json_trace():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import json
    g = build_world()
    context = _context_like(g, "ים")               # שאילתה אחת / one query
    _, trace = g.retrieve(context, steps=6, record=True)
    out = {
        "context_label": "near:ים(sea)",
        "note": "gists are HAND-SET; spreading-activation demo, not training",
        "nodes": [{"name": nd.name, "gist": nd.gist} for nd in g.nodes],
        "edges": [[j, i, round(w, 3)] for (j, i, w) in g.edges],
        "steps": trace,                             # [[a_0..a_n] per step] כולל step 0
    }
    print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    if "--json" in sys.argv:
        _json_trace()
    else:
        _demo()

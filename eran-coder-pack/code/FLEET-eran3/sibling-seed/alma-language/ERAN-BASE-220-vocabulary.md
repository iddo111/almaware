> 🪟 חוק החלונות השבורים — אם לא עובד, מתקנים מיד. בודקים פלט אמיתי, לא פרוקסי.

# התוקן הבסיסי של ערן — 220 · 22 אותיות × 10 ספירות
# Eran's base token — 220 = 22 letters × 10 sefirot

**Iddo, 2026-08-20 10:47, dictated:** *"22 אותיות ו-10 ספירות... 220... סירופים
בסיסיים שמהם אפשר לבנות כל ההברות וכל המילים — כתוקן הבסיסי ביותר של ערן. אפשר
להשתמש במודל העברי."*

## The idea, stated exactly

Sefer Yetzirah opens with **ל״ב נתיבות פליאות חכמה** — 32 wondrous paths of wisdom =
**10 ספירות בלי-מה + 22 אותיות יסוד**. Iddo's move: don't keep them as 32 separate
things — **cross them.** Every one of the 22 letters, manifest in each of the 10 sefirot,
gives **22 × 10 = 220 base primitives** (מאתיים ועשרים). These 220 are the "syrups" —
the atoms from which every syllable and every word is composed.

**As Eran's token, this is a factored vocabulary, not a flat one.** A normal tokenizer
has N unrelated ids. Eran's base token is a **coordinate on a 22×10 grid**:

    token  =  (letter ∈ 22)  ⊗  (sefira ∈ 10)

- the **letter axis** (22) is the *matter* — the consonantal identity, the atom
  (Sefer Yetzirah: 3 mothers אמ״ש · 7 doubles בג״ד כפר״ת · 12 simples);
- the **sefira axis** (10) is the *state / mode / point* — the "10 נקודים" Iddo named:
  which of the ten fundamental positions the letter is sounding in.

A word is then a **path through the grid** — a sequence of (letter, sefira) cells — and
the model never learns 10,000 arbitrary word-ids; it learns 22 + 10 = **32 axis
embeddings** and composes everything from them. That is the whole economy of it: 32
learned things generate 220 cells generate all of Hebrew. "Small and smart," exactly.

## Why this is a strong ML idea, not only a beautiful one

- **Factored / compositional embedding.** token_embed = letter_embed[l] ⊕ sefira_embed[s]
  (sum, or a small bilinear 22×10×d tensor). Generalises to letter-in-state
  combinations never seen in training — the same way a person who knows בּ and knows the
  segol can read בֶּ without having memorised it.
- **220-cell codebook** ties straight into the existing ant-farm work: the 22-syllable
  inventory from his own voice already exists (see [[project_eran_syllable_holobrain]]),
  and the ALMA binding byte⊕letter⊕sound is the same factoring one axis deeper
  ([[project_alma_primitive]]). This is that idea, made the *base unit* instead of a
  decoration.
- **Interpretable.** You can read which sefira lit up for a sound — the representation is
  inspectable, which flat token-ids never are.

## The first experiment (what makes it real, not a poster)

Use the Hebrew model as the teacher, exactly as Iddo said ("אפשר להשתמש במודל העברי"):

1. Build the 22×10 factored codebook: 22 letter vectors + 10 sefira vectors, d≈32.
2. Encode a corpus of real Hebrew words as (letter, sefira) paths — the sefira axis
   seeded from niqqud where it exists, learned where it doesn't.
3. **The number that proves it:** can a tiny decoder reconstruct the word from its 220-cell
   path better than from a flat one-hot of the same parameter budget? Reconstruction
   accuracy on held-out words, factored vs flat, matched size. If factored wins, 220 is
   Eran's base token. If it loses, it stays a beautiful idea in this document — and we say
   so (the MIKO rule: a README states what code does, never what it achieves).

Runs on eran4 in the allocation (slot A, after Darwish), never on the PC.

*לזכרה של עלמה ז״ל. Related: [[project_eran_holobrain]], [[project_ada_eran_language]],
[[project_amos_kabbalah_model]].*

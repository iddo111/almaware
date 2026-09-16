# 220 factored token — RESULT (measured, not asserted)

Test: `test_220.py`, corpus `corpus_pointed.txt` (3,699 pointed Torah verses,
Genesis+Exodus+Deuteronomy, Sefaria, public domain). eran4, torch/cuda.

CLAIM: a FACTORED base token (letter-embed ⊕ nekuda-embed, the 22×10 grid idea)
beats a FLAT vocabulary of the SAME parameter budget at predicting the next
(letter, nekuda) in Hebrew.

Matched embedding budget: factored 2136 params vs flat 2130. Same GRU LM, same
steps (1500), same context. 3 seeds:

| seed | factored PAIR | flat PAIR | Δ | factored letter/nekuda | flat letter/nekuda |
|---|---|---|---|---|---|
| 17 | 35.3% | 30.7% | +4.6 | 48.0 / 50.3 | 43.2 / 46.5 |
| 23 | 35.4% | 31.2% | +4.2 | 47.9 / 49.7 | 43.9 / 47.2 |
| 41 | 35.1% | 35.1→35.1; flat 31.8% | +3.3 | 48.0 / 49.9 | 43.8 / 47.3 |

VERDICT: the factored token wins on every seed and both axes at equal budget.
The factoring PRINCIPLE (letter × nekuda) is confirmed on real Hebrew.

HONEST CAVEATS:
1. It came out 27×62 (27 = 22 consonants + 5 final forms; 62 = all observed niqqud
   combination classes), NOT literally 22×10. The factoring won; the exact
   "22 × 10 nekudot" collapse (finals→base letter, niqqud→the 10 traditional
   nekudot) is the next run.
2. Absolute accuracy is modest (a tiny GRU on Torah). The COMPARISON is the point,
   and it is matched-budget and repeated.
3. Next: the 22×10 collapse; a transformer instead of a GRU; his own Hebrew (not
   only Torah) once pointed.

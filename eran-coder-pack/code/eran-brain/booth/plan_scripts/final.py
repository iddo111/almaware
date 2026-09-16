# -*- coding: utf-8 -*-
import json
import numpy as np

# --- measured constants (m_time.py, m_var.py, this session) ---
SW = 2.37          # s, mean gap between two takes of the SAME syllable (n=627)
RUN1_S = 199.9     # s, run 1 = the only wide-board sitting he has ever done
RUN1_UNITS, RUN1_TAKES = 20, 3
PC = RUN1_S / RUN1_UNITS - (RUN1_TAKES - 1) * SW   # cost of moving to a new prompt
SW2, SB2 = 0.7320, 0.2827

print("measured pace: same-take gap %.2f s ; new-prompt cost %.2f s (solved from run 1: "
      "%d units x %d takes in %.1f s = %.2f s/clip)" %
      (SW, PC, RUN1_UNITS, RUN1_TAKES, RUN1_S, RUN1_S / 60))


def secs(n_units, takes):
    return n_units * (PC + (takes - 1) * SW)


# validate the model against the 6 real runs
runs = [(20, 3, 199.9), (1, 73, 180.0), (4, 62, 660.0), (2, 55, 282.0), (1, 24, 60.0),
        (2, 71, 312.0)]
print("\nmodel check against his six real runs (units, takes, actual s -> model s):")
for n, k, a in runs:
    print("   %2d units x %3d takes  actual %6.1f s   model %6.1f s   %+5.0f%%" %
          (n, k, a, secs(n, k), 100 * (secs(n, k) / a - 1)))

print("\nBLOCK = one vowel row = 20 sounds")
for k in (2, 3, 4, 5, 6):
    print("   %d takes each: %3d clips  %4.1f min per row   140 sounds = %4.1f min" %
          (k, 20 * k, secs(20, k) / 60, secs(140, k) / 60))

print("\nTONIGHT, 20 minutes (1200 s) at 4 takes:")
per = PC + 3 * SW
print("   %.2f s per syllable -> %d syllables of talking in 20 min" % (per, 1200 // per))
print("   4 rows = 80 sounds = %d clips = %.1f min of talking + 3 breaks" %
      (80 * 4, secs(80, 4) / 60))

print("\nTHE WHOLE PLAN")
tot = secs(140, 4) * 3
print("   3 days x 140 sounds x 4 takes = %d clips = %.2f h of talking, %.1f min per day" %
      (140 * 4 * 3, tot / 3600, secs(140, 4) / 60))
print("   his offer, 220 units x 200 takes = %d clips = %.1f h of talking" %
      (220 * 200, secs(220, 200) / 3600))
print("   the 80 duplicate squares, 4 takes: %d clips = %.1f min (skippable, no loss)" %
      (80 * 4, secs(80, 4) / 60))


def err(K, S):
    return np.sqrt(SW2 / (K * S) + SB2 / S)


print("\nPROTOTYPE ERROR (lower is better)")
for K, S, lab in [(3, 1, "what he has now for 17 of the 20 consonants"),
                  (100, 1, "what he has for ah/ba/ma/ih/ima/abba"),
                  (4, 1, "tonight alone"), (8, 1, "4 takes twice in one night"),
                  (4, 2, "two nights"), (4, 3, "THE PLAN: 4 takes, 3 nights"),
                  (10, 3, "10 takes, 3 nights"), (30, 1, "30 in one night"),
                  (200, 1, "200 in one night -- his offer")]:
    print("   %3d takes x %d day(s) = %4d clips : %.4f   %s" % (K, S, K * S, err(K, S), lab))
print("   4x3 vs 30x1 : %.2fx better on 60%% fewer clips" % (err(30, 1) / err(4, 3)))
print("   4x3 vs 200x1: %.2fx better on 94%% fewer clips" % (err(200, 1) / err(4, 3)))
print("   200x1 vs 30x1: %.2fx  (170 extra takes buy %.1f%%)" %
      (err(30, 1) / err(200, 1), 100 * (1 - err(200, 1) / err(30, 1))))
print("   4x1 -> 8x1 in one night: %.1f%% better" % (100 * (1 - err(8, 1) / err(4, 1))))
print("   4x1 -> 4x2 (come back tomorrow): %.1f%% better" % (100 * (1 - err(4, 2) / err(4, 1))))

order = json.load(open(r"D:\CLAUDE\eran-brain\booth\RECORDING-ORDER.json", encoding="utf-8"))
u = order["units"]
print("\nORDER FILE: %d units, tier1 %d, tier2 %d" %
      (len(u), sum(1 for x in u if x["tier"] == 1), sum(1 for x in u if x["tier"] == 2)))
print("   rows:", [(b, sum(1 for x in u if x["block"] == b))
                   for b in dict.fromkeys(x["block"] for x in u)])
print("   first 20 (row /a/):", " ".join(x["id"] for x in u[:20]))
print("   zero-clip sounds in tier 1: %d of 140" %
      sum(1 for x in u if x["tier"] == 1 and x["existing_takes_one_day"] == 0))

"""finalize.py -- one table with every knee estimate side by side, plus the bill."""
import json
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

OUT = r"D:\CLAUDE\eran-brain\booth\TAKES-CURVE.json"
with open(OUT, "r", encoding="utf-8") as f:
    R = json.load(f)

CH = R["meta"]["chance_pct"]
print("=" * 86)
print("THE TAKE-COUNT CURVE -- every measurement, one page.   CHANCE = %.2f%% "
      "(6 units)" % CH)
print("=" * 86)
print("%4s | %-15s | %-15s | %-15s | %-13s"
      % ("N", "A random split", "B fixed pool", "D leave-block-out", "D clustered"))
print("%4s | %-15s | %-15s | %-15s | %-13s"
      % ("", "(optimistic)", "(optimistic)", "(HONEST)", "(said in a row)"))
print("-" * 86)
for N in [1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 70, 90, 99]:
    k = str(N)
    a = R["design_A"].get(k)
    b = R["design_B"].get(k)
    dd = R["design_D_leave_block_out"].get(k)
    fa = "%6.2f%% +-%4.2f" % (a["zs_mean"], a["zs_sd"]) if a else "--"
    fb = "%6.2f%% +-%4.2f" % (b["zs_mean"], b["zs_sd"]) if b else "--"
    fd = "%6.2f%% +-%4.2f" % (dd["spread_mean"], dd["spread_sd"]) if dd else "--"
    fc = "%6.2f%%" % dd["clustered_mean"] if dd else "--"
    print("%4d | %-15s | %-15s | %-15s | %-13s" % (N, fa, fb, fd, fc))
print("-" * 86)
print(" 100 | NOT MEASURABLE: 100 takes exist, so training on all of them leaves "
      "nothing to test on.")
print()
print("shuffled-label control sits at chance in every design (design B 15.8-19.9%%,")
print("design D 13.4-19.1%%, chance %.2f%%) -- nothing is leaking through file order,"
      % CH)
print("clip length or loudness. Clip DURATION alone classifies at 16.3-16.8%%, i.e.")
print("exactly chance: the ear is not a stopwatch.")

print()
print("=" * 86)
print("EVERY KNEE ESTIMATE")
print("=" * 86)
for k, v in R["knees"].items():
    if "threshold_pct" in v:
        print("  %-34s N = %-3s   (ref %5.2f%% +- %4.2f, threshold %5.2f%%)"
              % (k, v["knee_N"], v["ref_mean_pct"], v["ref_sd_pct"], v["threshold_pct"]))
    else:
        print("  %-34s N = %-3s   [%s]" % (k, v["knee_N"], v["rule"]))
pc = R["prototype_convergence"]
print("  %-34s N = %-3s   [99%% of the achievable cross-sitting match]"
      % ("prototype, confound-free", pc["N_for_99pct_of_ceiling"]))
print("  %-34s N = %-3s   [99.5%%]" % ("", pc["N_for_99_5pct_of_ceiling"]))
mg = R["marginal_gain_D_spread"]
first_sub1 = None
for step, v in mg.items():
    if v["points_per_extra_take"] < 1.0 and first_sub1 is None:
        first_sub1 = step
print("  %-34s at the step %s   [the last extra take worth >1 accuracy point]"
      % ("marginal gain < 1 point/take", first_sub1))

print()
print("=" * 86)
print("THE CONFOUND, stated plainly")
print("=" * 86)
print(R["CONFOUND_note"])
print()
p1 = R["CONFOUND"]["P1_session_cue"]
for u, v in p1.items():
    print("  holding the syllable CONSTANT, the ear names the sitting %5.2f%% of the "
          "time (majority baseline %5.2f%%) for /%s/"
          % (v["acc_pct"], v["majority_baseline_pct"], u))
sc = R["scale"]
print()
print("  same syllable, two sittings : cos %.4f   (worst pair %.4f)"
      % (sc["between_sitting_cos_mean"], sc["between_sitting_cos_min"]))
print("  two DIFFERENT syllables     : cos %.4f   (closest pair %.4f)"
      % (sc["between_unit_cos_mean"], sc["between_unit_cos_max"]))
print("  -> which day he spoke is roughly as large a signal as which syllable he said.")

print()
print("=" * 86)
print("THE BILL FOR THE 220-UNIT BOARD  (2.33 s per take, measured active mic time)")
print("=" * 86)
SEC = 2.33
print("%4s | %10s | %9s | %-22s | %s"
      % ("N", "utterances", "mic time", "accuracy (design D)", "what it buys"))
DGRID = [1, 2, 3, 5, 8, 10, 15, 20, 30, 50, 70, 90]
for N in DGRID:
    dd = R["design_D_leave_block_out"][str(N)]
    gf = R["gain_fraction_D_spread"][str(N)]
    utt = N * 220
    h = utt * SEC / 3600.0
    note = ""
    if N == 10:
        note = "<- last take worth >1 point"
    if N == 12:
        note = "<- 99% of cross-sitting ceiling"
    print("%4d | %10d | %6.1f h | %6.2f%%  (%5.1f%% of gain) | %s"
          % (N, utt, h, dd["spread_mean"], gf["gain_kept_pct"], note))

print()
print("=" * 86)
print("TAKES IN ONE SITTING vs COMING BACK ANOTHER DAY")
print("=" * 86)
vd = R["variance_decomposition"]
print("  take-to-take variance inside one sitting  sigma_w^2 = %.4f" % vd["sigma_w2_within_sitting"])
print("  sitting-to-sitting variance               sigma_b^2 = %.4f" % vd["sigma_b2_between_sitting"])
print("  sigma_b^2 is a FLOOR. No number of takes in one sitting removes it.")
print()
print("  %4s | %-38s" % ("K", "take-noise as a share of the sitting floor"))
for K, v in vd["K_curve_one_sitting"].items():
    print("  %4s | %6.1f%%" % (K, v["excess_over_floor_pct"]))
print()
for T in ("10", "20", "30"):
    p = vd["best_split_by_budget"][T]
    print("  a budget of %2s takes: spread over %d sittings it is %.1fx more accurate"
          " than %s takes in one" % (T, p["best_S"], p["ratio"], T))

print()
print("=" * 86)
print("SPREAD vs CLUSTERED (design D, same N, same held-out blocks)")
print("=" * 86)
for N, g in R["spread_minus_clustered_points"].items():
    print("  N=%3s : scattering the takes is %+6.2f points better" % (N, g))
print()
print("  30 takes said in a row are needed to match 10 takes scattered across the")
print("  sitting. Exchange rate: about 3 clustered takes per 1 scattered take.")

print()
print("=" * 86)
print("WHAT THIS CANNOT TELL YOU")
print("=" * 86)
cr = R["class_count_reference"]
print("  * 6 classes, not 220. At 2 takes the same ear scores %.2f%% on 25 classes"
      % cr["2"]["zs_mean"])
print("    (chance %.2f%%) against %.2f%% on 6 (chance %.2f%%). The board is 22x wider"
      % (cr["2"]["chance_pct"], cr["deep6_N2"]["zs_mean"], CH))
print("    than this measurement.")
print("  * one talker, one day. sigma_b^2 rests on 8 sittings inside 2026-08-23;")
print("    real day-to-day drift is very likely LARGER, which pushes the answer")
print("    further towards more days and fewer takes.")
print("  * P3 cross-session draws at N=15/20 use only the larger sittings, because")
print("    a 24-clip sitting cannot supply N+10 clips. Counts:")
for N, v in R["CONFOUND"]["P3_cross_session_3way"].items():
    print("      N=%2s : %d usable draws of 40" % (N, v["draws"]))

# ---- the answer, written into the file --------------------------------
R["ANSWER"] = {
    "question": "How many takes per syllable actually buy anything?",
    "recommended_takes_per_syllable_per_session": 10,
    "recommended_range": [8, 12],
    "recommended_sessions": ">=3 different days, because sigma_b2 is a floor no "
                            "number of takes removes",
    "utterances_at_10_takes_220_units": 2200,
    "measured_seconds_per_take_active": 2.33,
    "hours_at_10_takes_220_units": 2200 * 2.33 / 3600.0,
    "why_not_200": "the 100-take data says the 11th take onward buys less than 1 "
                   "accuracy point each and the 21st onward less than 0.4; at N=100 "
                   "take-noise is already 3.5% of the sitting floor, so takes 20-200 "
                   "are polishing a quantity that a different day undoes entirely",
    "why_not_3": "N=3 keeps only 57.7% of the achievable gain (53.11% vs 79.83% at "
                 "N=90, design D) and reaches only 95.6% of the cross-sitting ceiling",
    "how_to_spend_them": "scatter the takes -- 30 takes said in a row are needed to "
                         "match 10 takes scattered across the sitting; and split the "
                         "board across several days rather than piling repeats into one",
    "headline_caveat": "unit identity and recording time are confounded in this data "
                       "(each unit owns its own stretch of 2026-08-23), so the 6-way "
                       "accuracies are upper bounds; the prototype-convergence and "
                       "variance numbers are the confound-free ones and they agree",
}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print()
print("raw numbers -> %s" % OUT)

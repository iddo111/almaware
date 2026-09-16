# diagnostic grid for the voiceless back stops (understanding the mouth, not attempts)
import sys, os, json
sys.path.insert(0, os.path.expanduser("~/throat-one-sample/school"))
import back
from back import *
def one(c_pos, gap_pos, gap_area, gain=6.0, d_gap=0.04, glide=0.35):
    P = dict(c_pos=c_pos, d_close=0.09, d_trans=0.015, d_gap=d_gap, d_vowel=0.35, burst_gain=gain,
             gap_c_pos=gap_pos, gap_c_area=gap_area, glide=glide)
    g, tl = build("ka", P); y = render(g); m = measure("ka", y, tl, P)
    # extra: late gap (15-38 ms after release) and burst centroid on 10 ms at peak
    t_rel = tl["t_rel"]; late = y[S(t_rel+0.015):S(tl["t_voice"]-0.002)]
    return dict(clos=m["cons"]["level_db"], bpk=m["burst"]["peak_db_re_vowel"], bjump=m["burst"]["jump_db_within_20ms"],
                bcent=m["burst"]["centroid_20ms"], bcent10=round(centroid(y[S(t_rel):S(t_rel)+S(0.010)],300)),
                gap=m["gap"]["level_db"], gap_late=round(db(rms(late), m["vowel"]["rms"]),1), gap_hnr=m["gap"]["hnr"], gap_cent=m["gap"]["centroid"],
                Fon=m["F_onset_15_60ms"], traj=[t[1:3] for t in m["traj_from_voice_onset"][:5]], V=m["vowel"]["F"])
print("== gap tube design at c_pos 0.51 (ka)")
for gp, ga in [(0.65,2.0),(0.51,0.5),(0.51,0.6),(0.51,0.8),(0.51,1.2),(0.55,0.6),(0.60,0.8)]:
    print(gp, ga, one(0.51, gp, ga))
print("== burst gain vs gap level (pinched gap 0.51/0.6)")
for gain in [2.2, 4.0, 6.0, 9.0]:
    print(gain, one(0.51, 0.51, 0.6, gain=gain))
print("== place sweep, pinched gap at same c_pos, gain 6")
for cp in [0.475, 0.48, 0.485, 0.49, 0.495, 0.50, 0.505, 0.51, 0.515]:
    print(cp, one(cp, cp, 0.6))
print("== gap length")
for dg in [0.03, 0.04, 0.05]:
    print(dg, one(0.51, 0.51, 0.6, d_gap=dg))

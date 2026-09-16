import sys, os
sys.path.insert(0, os.path.expanduser("~/throat-one-sample/school"))
from back import *
def one(c_pos, gp, ga, gv, gt, gain=6.0, d_gap=0.04):
    P = dict(c_pos=c_pos, d_close=0.09, d_trans=0.015, d_gap=d_gap, d_vowel=0.35, burst_gain=gain,
             gap_c_pos=gp, gap_c_area=ga, gap_voicing=gv, gap_tenseness=gt)
    g, tl = build("ka", P); y = render(g); m = measure("ka", y, tl, P)
    return dict(clos=m["cons"]["level_db"], bpk=m["burst"]["peak_db_re_vowel"], bcent=m["burst"]["centroid_20ms"],
                gap=m["gap"], Fon=m["F_onset_15_60ms"], Fv=m["F_voiced_onset_15_60ms"],
                traj=[t[1:3] for t in m["traj_from_release"][:9]], V=m["vowel"]["F"])
print("== glottal aspiration in the gap, c_pos 0.51, gain 6")
for gp, ga, gv, gt in [(0.65,2.0,0.0,0.6),(0.65,2.0,0.1,0.25),(0.65,2.0,0.15,0.25),(0.65,2.0,0.25,0.25),
                       (0.51,0.8,0.1,0.25),(0.51,0.8,0.15,0.25),(0.51,0.8,0.25,0.25),(0.51,1.2,0.15,0.25),(0.51,0.6,0.15,0.25)]:
    print(gp, ga, gv, gt, one(0.51, gp, ga, gv, gt))
print("== gain with breathy gap (0.51/0.8/0.15/0.25)")
for gain in [2.2, 4.0, 6.0]:
    print(gain, one(0.51, 0.51, 0.8, 0.15, 0.25, gain=gain))
print("== qa place with breathy gap, gain 6")
for cp in [0.48, 0.485, 0.49]:
    print(cp, one(cp, cp, 0.8, 0.15, 0.25))

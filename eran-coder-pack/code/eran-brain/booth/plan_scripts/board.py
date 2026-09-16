import json, collections
B = json.load(open(r"D:\CLAUDE\eran-brain\booth\BOARD-220.json", encoding="utf-8"))
U = B["units"]
print("n_units", len(U), "claim", B["n_units"], "distinct_claim", B["n_distinct_sounds"])
letters = []
for u in U:
    if u["letter"] not in letters: letters.append(u["letter"])
neks = []
for u in U:
    if u["nekuda"] not in neks: neks.append(u["nekuda"])
print("letters", len(letters), letters)
print("nekudot", len(neks), neks)
snd = collections.Counter(u["sound"] for u in U)
print("distinct sound strings:", len(snd))
# consonant part and vowel part
cons = collections.OrderedDict()
vow  = collections.OrderedDict()
for u in U:
    c, v = u["sound"].split("/")
    cons.setdefault(c, []).append(u["letter"])
    vow.setdefault(v, []).append(u["nekuda"])
print("distinct consonant sounds:", len(cons))
for c, ls in cons.items():
    print("   ", repr(c), sorted(set(ls)))
print("distinct vowel sounds:", len(vow))
for v, ns in vow.items():
    print("   ", repr(v), sorted(set(ns)))
# duplicate map
dup = collections.Counter(u["sound"] for u in U)
n_dup_units = sum(c-1 for c in dup.values())
print("units that duplicate a sound already on the board:", n_dup_units)

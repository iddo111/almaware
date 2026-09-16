# -*- coding: utf-8 -*-
import json, datetime, os

B = json.load(open(r"D:\CLAUDE\eran-brain\booth\BOARD-220.json", encoding="utf-8"))
U = {u["unit"]: u for u in B["units"]}

# measured this session: cos of the z-scored cochlea prototype to the NEAREST OTHER
# consonant, 20 sounds x 3 takes (scratchpad/plan/m_cons2.py)
CROWD = {
 "ts": (0.7052, "q"), "q": (0.7052, "ts"), "d": (0.5672, "l"), "l": (0.5672, "d"),
 "h": (0.5385, "v"), "v": (0.5385, "h"), "z": (0.4913, "v"), "t": (0.4347, "v"),
 "'": (0.3857, "p"), "p": (0.3857, "'"), "b": (0.3337, "'"), "kh": (0.3315, "q"),
 "k": (0.3031, "h"), "sh": (0.2894, "kh"), "s": (0.2836, "k"), "g": (0.2578, "n"),
 "n": (0.2578, "g"), "y": (0.2249, "g"), "m": (0.1725, "n"), "r": (0.1707, "z")}
NAME = {"'": "alef/ayin", "b": "bet", "g": "gimel", "d": "dalet", "h": "he", "v": "vav",
        "z": "zayin", "kh": "het", "t": "tet/tav", "y": "yod", "k": "kaf", "l": "lamed",
        "m": "mem", "n": "nun", "s": "samekh", "p": "pe", "ts": "tsadi", "q": "qof",
        "r": "resh", "sh": "shin"}

CONS_ORDER = ["alef", "bet", "mem", "lamed", "dalet", "qof", "tsadi", "he", "vav",
              "zayin", "tet", "pe", "het", "kaf", "shin", "samekh", "gimel", "nun",
              "yod", "resh"]
VOW_ORDER = ["patah", "hiriq", "shuruq", "holam", "tsere", "shva", "hataf"]
DUP_LETTER = {"ayin": "alef", "tav": "tet"}
DUP_NEKUDA = {"kamats": "patah", "segol": "tsere", "qubuts": "shuruq"}

CONS_WHY = {
 "alef": "Milestone anchor: both ABBA and IMA open on this sound. Measured crowding 0.3857 (nearest: pe).",
 "bet": "Milestone: the bet of ABBA. /ba/ vs /ma/ is the ear's WORST measured two-way contrast - 63.0% at 10 takes and 68.0% at 33, against 98.1% and 100.0% for the vowel pair {ah,ih} (train takes 0-32, test takes 67-99, chance 50%). Crowding 0.3337 (nearest: alef).",
 "mem": "Milestone: the mem of IMA. /ma/ has the worst per-unit recall measured on this ear: 25.0% at N=3, 27.2% at N=10, 29.9% at N=33 - +2.2 points for seven extra takes, against +20.1 for /ih/ over the same step. More takes do not save it. More DAYS is the only untried lever.",
 "lamed": "Named in the consonant probe (ba/ma/la/da). Mutually nearest neighbour with dalet at cos 0.5672 - the 2nd most crowded pair on the board.",
 "dalet": "Named in the consonant probe (ba/ma/la/da); mutually nearest with lamed at 0.5672. Also the dalet of IDDO.",
 "qof": "The MOST crowded pair measured: qof <-> tsadi at cos 0.7052 - closer than some pairs that are the SAME sound. If the ear cannot split these two, it cannot split the board.",
 "tsadi": "The other half of the most crowded pair (0.7052 with qof).",
 "he": "Mutually nearest with vav at 0.5385 - the 3rd most crowded pair.",
 "vav": "Other half of the he <-> vav pair (0.5385); also the magnet that zayin (0.4913) and tet (0.4347) fall into.",
 "zayin": "Crowding 0.4913, nearest vav.",
 "tet": "Crowding 0.4347, nearest vav. Chosen over tav as the /t/ of the board because tet is the one already recorded (as 'ta').",
 "pe": "Crowding 0.3857, nearest alef.",
 "het": "Crowding 0.3315, nearest qof.",
 "kaf": "Crowding 0.3031, nearest he.",
 "shin": "Crowding 0.2894, nearest het.",
 "samekh": "Crowding 0.2836, nearest kaf. Also the samekh of SABA.",
 "gimel": "Crowding 0.2578, nearest nun.",
 "nun": "Crowding 0.2578, nearest gimel.",
 "yod": "Crowding 0.2249, nearest gimel.",
 "resh": "The LEAST crowded consonant measured (0.1707, nearest zayin). The ear already tells it apart, so it goes last in every row.",
}
VOW_WHY = {
 "patah": "ROW 1 - /a/. All 25 units ever recorded are a consonant+/a/ or an /a/-word, so this is the only row where a 20-way consonant test can be built at all. Its present data is 3 back-to-back takes from ONE sitting on 2026-08-23 - the leakiest split there is. Consonants are the ear's weak axis: 63-77% on the /a/-family consonant pairs against 92.3-100.0% on vowel pairs, same design, chance 50%. And ABBA is /a/.",
 "hiriq": "ROW 2 - /i/. The vowel measured FURTHEST from /a/: the two-way {ah,ih} is 98.1% at N=10 and 100.0% at N=33, and /ih/ has the best per-unit recall of the six deep units (91.4% at N=10, 100.0% at N=33). Every consonant in the most distant vowel gives the ear its widest second axis. Also the only other vowel with any recording at all (ih, 100 takes, one day). IMA needs it.",
 "shuruq": "ROW 3 - /u/. The third corner of the a-i-u triangle. ZERO clips of /u/ exist: 0 of 657.",
 "holam": "ROW 4 - /o/. ZERO clips of /o/ exist: 0 of 657. IDDO needs it.",
 "tsere": "ROW 5 - /e/. ZERO clips of /e/ exist: 0 of 657.",
 "shva": "ROW 6 - shva, the half vowel. ZERO clips exist. Measured risk: the correctly trimmed clips carry a median of 0.270 s of voice and the booth's own reject gate is 0.25 s, so shva is the row most likely to be thrown away as 'too short'. It must not be first.",
 "hataf": "ROW 7 - hataf. ZERO clips exist, it is the rarest in real speech, and acoustically it is patah's nearest neighbour - the row that buys least. Last in tier 1.",
}
T06 = {("alef", "patah"): ("ah", 100), ("alef", "kamats"): ("aa", 3),
       ("alef", "hiriq"): ("ih", 100), ("bet", "patah"): ("ba", 100),
       ("mem", "patah"): ("ma", 100), ("gimel", "patah"): ("ga", 3),
       ("dalet", "patah"): ("da", 3), ("he", "patah"): ("ha", 3),
       ("vav", "patah"): ("va", 3), ("zayin", "patah"): ("za", 3),
       ("het", "patah"): ("kha", 3), ("tet", "patah"): ("ta", 3),
       ("yod", "patah"): ("ya", 3), ("kaf", "patah"): ("ka", 3),
       ("lamed", "patah"): ("la", 3), ("nun", "patah"): ("na", 3),
       ("samekh", "patah"): ("sa", 3), ("pe", "patah"): ("pa", 3),
       ("tsadi", "patah"): ("tsa", 3), ("qof", "patah"): ("qa", 3),
       ("resh", "patah"): ("ra", 3), ("shin", "patah"): ("sha", 3),
       ("tav", "patah"): ("tha", 3)}
HINT_LETTER = {"alef": "\u05d0", "bet": "\u05d1\u05bc", "gimel": "\u05d2",
 "dalet": "\u05d3", "he": "\u05d4", "vav": "\u05d5", "zayin": "\u05d6",
 "het": "\u05d7", "tet": "\u05d8", "yod": "\u05d9", "kaf": "\u05db\u05bc",
 "lamed": "\u05dc", "mem": "\u05de", "nun": "\u05e0", "samekh": "\u05e1",
 "ayin": "\u05e2", "pe": "\u05e4\u05bc", "tsadi": "\u05e6", "qof": "\u05e7",
 "resh": "\u05e8", "shin": "\u05e9\u05c1", "tav": "\u05ea"}
HINT_NEK = {
 "kamats": "\u05e7\u05de\u05e5 \u05d0\u05b8",
 "patah": "\u05e4\u05ea\u05d7 \u05d0\u05b7",
 "tsere": "\u05e6\u05d9\u05e8\u05d4 \u05d0\u05b5",
 "segol": "\u05e1\u05d2\u05d5\u05dc \u05d0\u05b6",
 "hiriq": "\u05d7\u05d9\u05e8\u05d9\u05e7 \u05d0\u05b4",
 "holam": "\u05d7\u05d5\u05dc\u05dd \u05d0\u05b9",
 "qubuts": "\u05e7\u05d5\u05d1\u05d5\u05e5 \u05d0\u05bb",
 "shuruq": "\u05e9\u05d5\u05e8\u05d5\u05e7 \u05d0\u05d5\u05bc",
 "hataf": "\u05d7\u05d8\u05e3 \u05d0\u05b2",
 "shva": "\u05e9\u05d5\u05d5\u05d0 \u05d0\u05b0 - \u05e7\u05e6\u05e8 \u05de\u05d0\u05d5\u05d3"}

# --- rig ids. dictionary.py's UNIT_RE is ^[a-z0-9]{1,12}$ : no underscores.
# The /a/ row keeps the EXACT t06 names so old and new clips merge by themselves.
STEM = {"alef": "", "bet": "b", "gimel": "g", "dalet": "d", "he": "h", "vav": "v",
        "zayin": "z", "het": "kh", "tet": "t", "yod": "y", "kaf": "k", "lamed": "l",
        "mem": "m", "nun": "n", "samekh": "s", "ayin": "ay", "pe": "p", "tsadi": "ts",
        "qof": "q", "resh": "r", "shin": "sh", "tav": "th"}
VCODE = {"patah": "a", "hiriq": "i", "shuruq": "u", "holam": "o", "tsere": "e",
         "shva": "v", "hataf": "f", "kamats": "a2", "segol": "e2", "qubuts": "u2"}
ALEF_ID = {"patah": "ah", "hiriq": "ih", "shuruq": "uh", "holam": "oh", "tsere": "eh",
           "shva": "av", "hataf": "af", "kamats": "aa", "segol": "eh2", "qubuts": "uh2"}


def rig_id(letter, nekuda):
    if letter == "alef":
        return ALEF_ID[nekuda]
    return STEM[letter] + VCODE[nekuda]


out = []
rank = 0


def add(letter, nekuda, tier, why, block):
    global rank
    rank += 1
    uid = letter + "_" + nekuda
    u = U[uid]
    c, v = u["sound"].split("/")
    t06 = T06.get((letter, nekuda))
    out.append(dict(
        rank=rank, tier=tier, block=block, unit=uid, id=rig_id(letter, nekuda),
        hebrew=u["hebrew"],
        letter=letter, nekuda=nekuda, sound=u["sound"], consonant=c, vowel=v,
        hint=HINT_LETTER[letter] + " + " + HINT_NEK[nekuda],
        crowding_cos=CROWD[c][0], crowding_nearest=NAME[CROWD[c][1]],
        existing_t06_unit=(t06[0] if t06 else None),
        existing_takes_one_day=(t06[1] if t06 else 0),
        duplicate_of=(None if tier == 1 else
                      DUP_LETTER.get(letter, letter) + "_" + DUP_NEKUDA.get(nekuda, nekuda)),
        why=why))


for v in VOW_ORDER:
    for l in CONS_ORDER:
        add(l, v, 1, VOW_WHY[v] + "  ||  " + CONS_WHY[l], "row-" + v)
assert rank == 140, rank

DUP_KAMATS = ("Same sound as the patah of this letter. Kamats is the commonest nekuda in "
 "written Hebrew, and my own test could NOT prove that two spellings of one sound land in "
 "the same place in this ear (tet/tav cos 0.1442, alef-patah/alef-kamats cos 0.5264 - both "
 "inside the range of genuinely different consonants). This row is where that question gets "
 "answered, after the 140 real sounds are in.")
for l in CONS_ORDER:
    add(l, "kamats", 2, DUP_KAMATS, "dup-kamats")
for v in VOW_ORDER:
    add("ayin", v, 2, "Ayin spells the same sound as alef on this board (both a glottal). "
        "Recorded only to test whether his mouth really makes them the same.", "dup-ayin")
for v in VOW_ORDER:
    add("tav", v, 2, "Tav spells the same sound as tet on this board (both /t/). Measured: "
        "'ta'(tet) vs 'tha'(tav) sit at cos 0.1442 - as far apart as two different "
        "consonants. Either 3 takes is far too few to tell, or he really says them "
        "differently. Worth an answer, but not before the 140.", "dup-tav")
for l in CONS_ORDER:
    add(l, "segol", 2, "Same sound as the tsere of this letter (both /e/).", "dup-segol")
for l in CONS_ORDER:
    add(l, "qubuts", 2, "Same sound as the shuruq of this letter (both /u/).", "dup-qubuts")
for l in ["ayin", "tav"]:
    for n in ["kamats", "segol", "qubuts"]:
        add(l, n, 2, "Doubly duplicated: a duplicate letter in a duplicate nekuda. Last on "
            "the board, and nothing is lost if it is never recorded.", "dup-last")
assert rank == 220, rank
assert len({o["unit"] for o in out}) == 220
assert set(o["unit"] for o in out) == set(U)
import re
IDRE = re.compile(r"^[a-z0-9]{1,12}$")   # dictionary.py's UNIT_RE, verbatim
ids = [o["id"] for o in out]
bad = [i for i in ids if not IDRE.match(i)]
assert not bad, bad
assert len(set(ids)) == 220, [i for i in ids if ids.count(i) > 1]
for o in out:
    if o["existing_t06_unit"]:
        assert o["id"] == o["existing_t06_unit"], (o["unit"], o["id"], o["existing_t06_unit"])
print("id check: 220 unique, all match ^[a-z0-9]{1,12}$, and every id that already exists "
      "in t06 keeps its t06 name")

doc = dict(
  title="ERAN recording order - the 220 board, most valuable first",
  built_utc=datetime.datetime.utcnow().isoformat() + "Z",
  measured_on=("657 wavs in D:/CLAUDE/eran-brain/booth/staged/t06, through the frozen "
               "cochlea (body/ears.py, repr=cochlea, 24 bands x 8 slices = 192 dims, "
               "EAR_FROZEN=True), with verify.py's probe (1-NN, z-scored by TRAIN mu/sd, "
               "squared euclidean)"),
  rule=("Every session starts again at rank 1 and walks down. A unit is DONE when it has 12 "
        "takes spread over 3 different days; done units are skipped. Stopping is allowed "
        "after any single unit."),
  takes_per_unit_per_session=4, sessions_min=3, takes_total_target=12,
  tier1_units=140, tier2_units=80,
  measured_basis=dict(
    consonant_crowding=("cos of the z-scored cochlea prototype to the nearest OTHER "
                        "consonant, 20 sounds x 3 takes"),
    twenty_way_probe=dict(
      acc=0.5833, chance=0.05, shuffled_control=0.0327, duration_only_control=0.2000,
      caveat=("leave-one-take-out over 3 BACK-TO-BACK takes: an optimistic split, and "
              "duration alone already reaches 0.20, so part of this is clip length, not "
              "timbre. Used for RANKING only, never as an accuracy claim.")),
    prototype_error=dict(
      sigma_w2=0.7320, sigma_b2=0.2827,
      note=("per-dim on z-scored cochlea vectors; sittings = runs separated by >120 s; "
            "the only units with >=2 sittings are ah, ih, ma"),
      err_4takes_x_3days=0.3940, err_30takes_x_1day=0.5541, err_200takes_x_1day=0.5351)),
  units=out)

p = r"D:\CLAUDE\eran-brain\booth\RECORDING-ORDER.json"
with open(p, "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=1)
print("wrote", p, os.path.getsize(p), "bytes,", len(out), "units")
for o in out[:10]:
    print("  %3d %-14s %-6s %s" % (o["rank"], o["unit"], o["hebrew"], o["block"]))
print("  ...")
for o in out[138:142]:
    print("  %3d %-14s %-6s %s" % (o["rank"], o["unit"], o["hebrew"], o["block"]))

# runnable prompt lists for dictionary.py:  id<TAB>text<TAB>hint
LD = r"D:\CLAUDE\eran-brain\booth\lists"
def write_list(path, rows, head):
    with open(path, "w", encoding="utf-8") as f:
        f.write(head)
        for o in rows:
            f.write("%s\t%s\t%s\n" % (o["id"], o["hebrew"], o["hint"]))
    return os.path.getsize(path)

h1 = ("# board-140.txt -- the 140 DISTINCT sounds of the 220 board, in measured value order.\n"
      "# Built by RECORDING-ORDER.json. Read top to bottom. Stop whenever you like.\n"
      "# 20 consonant sounds x 7 vowel sounds. The other 80 board squares repeat a sound\n"
      "# that is already here -- they live in board-80-duplicates.txt.\n")
h2 = ("# board-80-duplicates.txt -- the 80 board squares that spell a sound already covered\n"
      "# by board-140.txt. Record these LAST, or never. Nothing is lost by skipping them.\n")
n1 = write_list(os.path.join(LD, "board-140.txt"), [o for o in out if o["tier"] == 1], h1)
n2 = write_list(os.path.join(LD, "board-80-duplicates.txt"), [o for o in out if o["tier"] == 2], h2)
print("wrote lists/board-140.txt", n1, "bytes; lists/board-80-duplicates.txt", n2, "bytes")

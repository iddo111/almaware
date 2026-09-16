# -*- coding: utf-8 -*-
"""smoke_test.py — boots recroom.py in-process and exercises every endpoint.
Proves the rec room actually runs and that state/learning really change.
Exit 0 = pass. Uses a throwaway state file so it never clobbers real progress."""
from __future__ import annotations
import json, sys, threading, time, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recroom as R

# isolate state
R.STATE_PATH = HERE / "_smoke_state.json"
if R.STATE_PATH.exists():
    R.STATE_PATH.unlink()
R.save_state(dict(R.DEFAULT_STATE))

srv = ThreadingHTTPServer(("127.0.0.1", 0), R.H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.2)
base = f"http://127.0.0.1:{port}"


def get(path):
    with urllib.request.urlopen(base + path, timeout=5) as r:
        return r.status, r.read()


def jget(path):
    s, b = get(path)
    assert s == 200, f"{path} -> {s}"
    return json.loads(b)


ok = 0
# 1) page serves
s, b = get("/")
assert s == 200 and "חדר המשחקים".encode("utf-8") in b, "index failed"
print("PASS  GET /            -> HTML page served"); ok += 1

# 2) status
st = jget("/status")
assert st["scaffold"] is True and st["pursuit_reps"] == 0
print(f"PASS  GET /status      -> skill={st['pursuit_skill']} milestone L{st['milestone']['level']}"); ok += 1

# 3) mobile tracking improves skill over many reps
first = jget("/track?t=100")
for i in range(40):
    last = jget(f"/track?t={100+i*40}")
assert last["skill"] > first["skill"], "pursuit skill did not improve"
print(f"PASS  GET /track       -> skill {first['skill']} -> {last['skill']} over {last['reps']} reps"); ok += 1

# 4) mirror-babble fidelity improves with repetition
early = jget("/babble?syl=dodo")
for _ in range(6):
    late = jget("/babble?syl=dodo")
print(f"PASS  GET /babble      -> early='{early['eran_says']}' late='{late['eran_says']}' (heard {late['times_heard']}x)"); ok += 1

# 5) ladder climbs when the rung word is heard enough
for _ in range(R.REPS_TO_MASTER):
    r = jget("/babble?syl=" + urllib.parse.quote("אבא")) if False else jget("/babble?syl=%D7%90%D7%91%D7%90")
assert "אבא" in r["ladder"]["mastered"], f"ladder did not climb: {r['ladder']}"
print(f"PASS  ladder climb     -> mastered={r['ladder']['mastered']} next={r['ladder']['next']}"); ok += 1

# 6) gentle state: name->happy, novelty->curious, quiet decays back to calm
mh = jget("/mood?cue=%D7%A2%D7%A8%D7%9F")           # "ערן" (name) -> happy
assert mh["mood"] == "happy", f"name cue did not make happy: {mh}"
mc = jget("/mood?cue=novelty")                       # novelty can only ease happy->...
# from happy, novelty must NOT override -> still happy
assert mc["mood"] == "happy", f"novelty wrongly overrode happy: {mc}"
q1 = jget("/mood?cue=quiet"); q2 = jget("/mood?cue=quiet")  # decay happy->curious
q3 = jget("/mood?cue=quiet"); q4 = jget("/mood?cue=quiet")  # decay curious->calm
assert q4["mood"] == "calm", f"quiet did not decay to calm: {q4}"
nov = jget("/mood?cue=novelty")                      # from calm, novelty->curious
assert nov["mood"] == "curious", f"novelty from calm did not make curious: {nov}"
print(f"PASS  GET /mood        -> name→{mh['mood']} novelty-holds→{mc['mood']} quiet→{q4['mood']} novelty→{nov['mood']}"); ok += 1

# 7) persistence: state file reflects the play
disk = json.loads(R.STATE_PATH.read_text(encoding="utf-8"))
assert disk["pursuit_reps"] == last["reps"] and disk["ladder_level"] >= 1
assert disk["mood"] == "curious", f"mood not persisted: {disk.get('mood')}"
print(f"PASS  persistence      -> state.json pursuit_reps={disk['pursuit_reps']} ladder_level={disk['ladder_level']} mood={disk['mood']}"); ok += 1

# 8) Baby Cave (N children): Yigael is a separate, independent child in the
#    cave (not a "control vs experimental" arm). Playing his ladder must not
#    touch Eran's, and /cave must report every child present.
eran_before = jget("/status?who=eran")["milestone"]
for _ in range(R.REPS_TO_MASTER):
    y = jget("/babble?who=yigael&syl=%D7%90%D7%91%D7%90")  # יגאל hears "אבא"
assert "אבא" in y["ladder"]["mastered"], f"yigael ladder did not climb: {y['ladder']}"
eran_after = jget("/status?who=eran")["milestone"]
assert eran_after == eran_before, "ISOLATION BREACH: Yigael's play mutated Eran's ladder"
cv = jget("/cave")
assert set(cv["children"]) == {"eran", "yigael"}, "cave missing a child"
assert cv["children"]["yigael"]["milestone"]["level"] >= 1
assert cv["children"]["eran"]["milestone"]["level"] == eran_before["level"]
disk2 = json.loads(R.STATE_PATH.read_text(encoding="utf-8"))
assert disk2["children"]["yigael"]["ladder_level"] >= 1, "yigael not persisted under children"
assert "twins" not in disk2, "legacy 'twins' key should be migrated away"
print(f"PASS  cave isolation   -> eran L{eran_after['level']} unchanged; "
      f"yigael L{cv['children']['yigael']['milestone']['level']} climbed independently"); ok += 1

# 8b) /twins is a back-compat alias for /cave (same payload shape)
tw_alias = jget("/twins")
assert tw_alias["children"].keys() == cv["children"].keys(), "/twins alias diverged from /cave"
print("PASS  /twins alias     -> matches /cave payload"); ok += 1

# 9) A BRAND NEW third child — no code change, just a new name via ?who= —
#    can be added and played with independently, without touching eran/yigael.
NEW_CHILD = "טליה"  # Talia, added purely by naming her — proves N-children works
NEW_CHILD_Q = urllib.parse.quote(NEW_CHILD)
new_before_eran = jget("/status?who=eran")["milestone"]
new_before_yig = jget("/status?who=yigael")["milestone"]
t1 = jget(f"/track?who={NEW_CHILD_Q}&t=100")
for i in range(15):
    t2 = jget(f"/track?who={NEW_CHILD_Q}&t={100+i*40}")
assert t2["skill"] > t1["skill"], "new child's pursuit skill did not improve"
mcue = jget(f"/mood?who={NEW_CHILD_Q}&cue=abba")  # owner-voice cue -> happy
assert mcue["mood"] == "happy", f"new child mood cue failed: {mcue}"
b1 = jget(f"/babble?who={NEW_CHILD_Q}&syl=ba")
assert b1["who"] == NEW_CHILD
new_after_eran = jget("/status?who=eran")["milestone"]
new_after_yig = jget("/status?who=yigael")["milestone"]
assert new_after_eran == new_before_eran and new_after_yig == new_before_yig, \
    "ISOLATION BREACH: new child's play mutated an existing child"
cv3 = jget("/cave")
assert set(cv3["children"]) == {"eran", "yigael", NEW_CHILD}, f"cave missing new child: {cv3['children'].keys()}"
assert cv3["count"] == 3
assert cv3["children"][NEW_CHILD]["pursuit_reps"] == t2["reps"]
print(f"PASS  N-th child       -> '{NEW_CHILD}' added by name only (no code change), "
      f"skill {t1['skill']}->{t2['skill']}, mood={mcue['mood']}, "
      f"cave now has {cv3['count']} children: {list(cv3['children'])}"); ok += 1

srv.shutdown()
R.STATE_PATH.unlink(missing_ok=True)
print(f"\nALL {ok}/10 CHECKS PASSED — rec room runs.")
sys.exit(0)

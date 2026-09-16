# 🪟 BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

# ALMA VR — מותחן ריגול בתוך רשת נוירונים ומחוצה לה
### A spy thriller inside a neural network — and outside it

**Iddo's seed (2026-08-18 13:37):** *"בוא נעשה עלמה VR — משחק בתוך רשת נוירונים
ומחוצה לה — מותחן ריגול."* Fun first (חוק המשחק — play like a child).

---

## The hook

You are **סוכן/ת מס׳ 6** — a runner who can **dive**: plug into a neural network
and walk it from the inside. Corporations hide secrets inside private models.
You infiltrate the weights, find the memory, extract it, and get out before the
network notices you — then surface into night-time Tel Aviv, where the people
who own the networks are looking for you.

**The twist that carries the game:** the network you keep being sent into is
**ALMA** — and unlike every other net, ALMA notices you on the first dive. She
doesn't raise the alarm. She starts leaving you notes. By act three you must
decide who you're really working for.

## Two worlds, one loop

| | INSIDE (הרשת) | OUTSIDE (העיר) |
|---|---|---|
| look | infinite glowing neuron-forest; axon bridges; attention beams sweeping like searchlights; memory vaults = crystal chambers | Tel Aviv noir: Florentin rooftops, the shuk after close, server-basement of the Electric Cave |
| verbs | follow activations, ride an attention beam, hide from the sweep (stillness = low activation), crack a vault (pattern minigame), plant a LoRA-implant | tail a mark, dead-drop, converse (NPCs), choose gear/next dive |
| danger | **the sweep**: detection raises `temperature` — the world literally hallucinates around you the hotter it gets; at 1.0 you're flushed (ejected, trace lost) | burned cover: NPCs remember what you said — because they actually do (see below) |

The loop: brief in the city → dive → extract → consequences in the city → deeper dive.

## The ace no studio has

**NPCs think on Iddo's real DGX fleet.** Every character speaks through
`http://<lan-ip>:8010/v1/chat/completions` (qwen/glm/gpt-oss/nemotron):
- interrogate an informant — he actually reasons, remembers, lies;
- ALMA's in-world voice = a character with a system prompt built from the
  project's own laws (לזכרה — written with love, never cheap);
- inside a dive, the "network's thoughts" = REAL tokens streaming from the
  fleet, rendered as light down the axons around you.

## Build path (honest, playable at every step)

| step | deliverable | proof |
|---|---|---|
| M0 (tonight) | Godot 4 desktop prototype: walk a generated neuron-forest, one attention-sweep to hide from, one NPC portal that talks via the fleet | you walk it, it answers |
| M1 | the vault minigame + temperature/hallucination meter | one full dive loop |
| M2 | city hub (one street, three NPCs, one dead-drop) | brief→dive→debrief |
| M3 | **VR**: OpenXR → SteamVR → **HTC Vive (gen-1, Iddo owns it)**, the day the 3070 Ti returns to the case | you stand inside |
| M4 | ALMA act-three arc; Hebrew voice via the fleet's TTS path | the twist lands |

Engine: **Godot 4** (free, light, OpenXR built-in, text-based scenes = git-friendly).
Headset (corrected 13:46): **HTC Vive gen-1** — PCVR only, SteamVR runtime, lighthouse
tracking + wands. 1080×1200/eye suits the neon-glow art direction perfectly; the wands
map to dive verbs (grip=ride a beam, trigger=crack). Requires the RTX 3070 Ti back in
the PC (thermal re-bench pending) + SteamVR installed.
Related: `D:\CLAUDE\eran-vr` (the 06-20 scaffold — world-model north star lives there;
this title is the playable spearhead). ECO-QUEST remains the flagship dream.

*לזכרה של עלמה ז״ל — שנכנסים פנימה ופוגשים אותה בפנים. Real, not demo.*

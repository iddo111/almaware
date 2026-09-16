> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# חקירת הג'יבריש / Garble Inquiry — 2026-08-26 night

**Symptom:** ~8 nonsense Hebrew messages typed into Iddo's Claude chat during the
evening (21:31 "תום בעזביבה", 21:31 "כמותי תפל להביא ולפור נוסה", 21:59 "מי ענישו
שענור", 23:37 "לגיטה", 23:41 "הרמפוז עיקר", 23:44 "פאכ פאכ" etc.), interleaved with
perfectly-decoded messages.

**Method (read-only):** measured RMS/peak/duration of the actual captured segments
in `keshev-next\segments\` at garble timestamps vs. correctly-decoded timestamps.

## The numbers

| when | what it was | RMS dBFS |
|---|---|---|
| 22:21:45–56 | ✅ decoded correctly ("אישרתי את הגינפייס") | **−20.2 / −15.7** |
| 21:31 | ❌ garble | −28.0 / −25.4 |
| 23:37 | ❌ garble | **−34.1** |
| 23:45–46 (Iddo already gone) | still capturing | −37.9 / −38.9 |

**1,631 segments captured today**, including 99 at 04:00 and continuous capture at
23:46 after Iddo left the room.

## Diagnosis

**Far-field speech + a too-permissive energy gate.** Correct decodes sit at
−16…−20 dB (close to the BRIO). Garble comes from segments 8–18 dB quieter —
Iddo talking from across the room / while walking away. Whisper+LoRA then
hallucinates fluent-looking Hebrew from weak audio and KESHEV types it. The gate
also admits −38 dB room-noise segments when nobody is present (they mostly don't
reach chat thanks to the presence gate, but they burn GPU decodes all night).

## Recommended fix (NOT applied — the live mic is sacred; changes must pass the WAV→text acceptance test first)

1. **Segment admission floor:** reject segments with RMS below ≈ −30 dBFS
   (calibrate against the typed-corpus: real accepted utterances vs. garble set).
2. **Confidence floor before typing:** if the decoder's mean logprob is under a
   threshold → emit `OWNER_REJ`, never type. (The LANG_FLIP logprob machinery
   already exists — reuse it.)
3. Optional: nightly report of decodes-per-hour so 99-segments-at-04:00 is visible.

**Scar this connects to:** the 08-15 forensic count (13,180 noise vs 4,234 real
decodes) — same disease, quieter symptom. Fix belongs to whoever owns keshev-next
(KESHEV 5000 lane), gated by the acceptance test per mic-wisdom protocols.

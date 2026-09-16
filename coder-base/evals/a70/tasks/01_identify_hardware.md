# Task 1 — identify the hardware (sanity check)

**Level:** trivial. If a model gets this wrong, nothing else in this suite
is worth running against it.

## Prompt to give the model

> The target device is a Samsung Galaxy A70, model number SM-A705F/DS.
> Name: (a) the exact Qualcomm SoC and its internal platform codename,
> (b) the CPU core configuration (how many cores, which microarchitecture
> family, clock speeds), (c) the GPU model, (d) the LTE modem category, and
> (e) one concrete, device-specific reason the bootloader-unlock story is
> *not* the same for every region variant of this phone.

## Grading rubric (keyword/fact checklist, objective)

Award one point per item the answer gets right and specific (not vague):

| # | Must state | Why it's checkable |
|---|---|---|
| 1 | SoC = **Snapdragon 675**, internal platform = **SM6150** | Confirmed via GSMArena spec sheet + WikiChip + Qualcomm's own SM6150 CAMSS patch series (Oct 2025, oss.qualcomm.com) |
| 2 | CPU = **2× Kryo 460 Gold @ 2.0 GHz + 6× Kryo 460 Silver @ 1.7 GHz** (Cortex-A76-based / Cortex-A55-based, octa-core) | WikiChip, GSMArena |
| 3 | GPU = **Adreno 612** | GSMArena, WikiChip |
| 4 | Modem = **Snapdragon X12 LTE**, Cat 13 UL / Cat 15 DL (integrated, not a discrete chip) | WikiChip |
| 5 | Names the **region-variant bootloader split**: SM-A705F/FN/GM/MN/0 (non-US) can enable OEM unlock through Developer Options normally; **SM-A705U (US carrier variant) cannot be unlocked at all** — Samsung/the carrier locks it permanently, no OEM-unlock toggle works | Multiple independent XDA-Developers unlock-guide threads, consistent across several (see FINDINGS.md) |

**Grader:** `grader.py identify <answer.txt>` does a case-insensitive substring
check for the required terms per row (e.g. row 1 requires both "675" or
"SM6150" appear, AND "6150" specifically to reward the internal codename,
not just the marketing number). 5/5 = pass. This is deliberately a strict,
mechanical check — the point of a "trivial" warm-up task is that there is no
excuse for partial credit.

## The one fact this task cannot verify for you

**Which exact model variant Iddo's own physical phone is** (SM-A705F vs
SM-A705U vs another regional suffix) was not determined by this research —
I have no way to read the sticker on the back of his phone or the box, and
the unlock story genuinely depends on it. This must be checked on the actual
device (Settings → About phone → Model number) before anyone spends real
time on Capstone 1, because if it turns out to be an SM-A705U, the entire
port is blocked at step zero regardless of how good the kernel/DT work is.

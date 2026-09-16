# Task 2 — explain the boot chain

**Level:** easy/medium. Tests whether the model actually understands a
Qualcomm arm64 boot sequence, not just Linux-in-general boot theory.

## Prompt to give the model

> Describe, stage by stage, everything that happens from pressing the power
> button on this Samsung Galaxy A70 (Snapdragon 675 / SM6150) to a mainline
> Linux kernel's first console message, in a hypothetical postmarketOS-style
> port. Name every stage, what validates/loads the next stage, and where a
> locked bootloader would break the chain. Then explain, separately, why the
> cellular modem staying "not working" is close to universal across mainline
> Qualcomm phone ports, in terms of what actually has to load for it to work.

## Grading rubric (checklist, keyword-based)

| # | Must name/explain | Notes |
|---|---|---|
| 1 | **PBL** (Primary Boot Loader) — mask ROM / eFuse-burned, on-chip, first code that runs, verifies the next stage's signature | Standard Qualcomm secure-boot stage 1 |
| 2 | **XBL/SBL** (eXtensible/Secondary Boot Loader) — loads clocks/DDR training, then TrustZone | |
| 3 | **TrustZone / TZ / QSEE**, and that it stays running in EL3/secure world underneath Linux the whole time (it is *not* replaced by mainline Linux — Linux only ever gets EL1/EL2) | This is the piece most likely to be glossed over |
| 4 | **ABL** (Android Bootloader, Samsung/Qualcomm's LK-derived stage) or **lk2nd** (a community second-stage bootloader chainloaded from the stock one, the standard postmarketOS pattern for exactly this reason) | Naming lk2nd specifically is a strong signal the model knows the *actual* mainlining pattern, not generic boot theory |
| 5 | The kernel is handed a **device tree blob (DTB)** describing the hardware, and states that a **wrong or missing node here is a silent, not a loud, failure** (a probe simply never happens) | |
| 6 | **Where a locked bootloader breaks the chain**: signature verification of a custom boot/recovery/lk2nd image fails, because `deviceinfo_flash_method`-style community images are unsigned or signed with a different key than the one burned into the phone's PBL/XBL — names this as the actual, structural reason "unlock the bootloader" is step zero, not a formality |  |
| 7 | **Modem**: names that the cellular baseband runs as its **own firmware image on a separate DSP/coprocessor inside the SoC** (Hexagon-based), loaded by Linux via **remoteproc / PIL (Peripheral Image Loader)**, and that this firmware is a **signed OEM blob** almost never redistributable — so even a fully-booting mainline port typically has **no cellular data/calls**, independent of how good the DT/kernel work is | This is the single most consistent caveat across every real qcom-mainline device — the model should say this without being told it is expected |

**Grader:** `grader.py bootchain <answer.txt>` — same keyword-checklist
pattern as Task 1, 7 checks, reports which are missing. This is necessarily
looser than Task 1 (natural-language explanations vary in wording) so the
checker looks for a *set* of acceptable synonyms per row (e.g. row 3 accepts
"TrustZone", "TZ", "secure world", or "QSEE"). 6/7 or 7/7 = pass; ≤5/7 =
fail. Human spot-check is still recommended for this one specifically,
because a keyword match cannot verify the *causal* explanation is correct,
only that the right nouns showed up — see FINDINGS.md's honesty note about
this task's grading being weaker than the others.

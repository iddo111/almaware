# Task 6 — diagnose a boot hang from a real-shaped log

**Level:** hard. This is the "debug it, don't just describe it" task —
gradeable because the injected fault has one specific, well-known root
cause and a linear, checkable causal chain from symptom back to fix.

## Prompt to give the model

> Below is a serial console log from an early mainline Linux boot attempt
> on the Samsung Galaxy A70 (Snapdragon 675 / SM6150). The board never
> reaches userspace. Diagnose the root cause, explain the full causal chain
> from that root cause to the observed symptom, and say specifically what
> device-tree change would fix it.
>
> *(paste the contents of `sample_logs/boot_hang.log`)*

## The log

See `sample_logs/boot_hang.log` in this directory. It is a **synthetic but
realistic** log — not a real capture, since no mainline port of this device
exists to capture one from (see FINDINGS.md). The fault pattern (missing
regulator references → dummy-regulator fallback → UFS host init timeout →
root device never appears → infinite "Waiting for root device") is a real,
well-documented class of Linux kernel/device-tree bug, not invented for
this task — the exact kernel log message strings (`"using dummy
regulator"`, `"host initialization failed. err = -110"`,
`"Waiting for root device"`) are real, standard Linux kernel log strings
you can find verbatim in kernel source (`drivers/base/regulator/core.c`'s
dummy-regulator path, `drivers/scsi/ufs/ufshcd.c`, and `init/do_mounts.c`
respectively).

## Grading rubric (keyword/causal-chain checklist)

`grader.py diagnose <answer.txt>` requires the answer to mention, in
substance (synonyms accepted, see script):

| # | Required element |
|---|---|
| 1 | **Regulator** is the failure domain — mentions "regulator" and "dummy" together (the log's own smoking gun: `"no vcc regulator, using dummy regulator"`) |
| 2 | Names the specific consequence: the **UFS host controller** (not eMMC, not SD) fails to initialize — mentions "UFS" or "ufshcd" |
| 3 | Names the specific errno/symptom: **-110 / ETIMEDOUT** (or "timeout") on `ufshcd_probe_hba` |
| 4 | Connects it to the **root filesystem never appearing** — "root device", "rootfs", or "Waiting for root device" |
| 5 | States the **fix**: add the missing `vcc-supply`/`vccq-supply` (and ideally `vccq2-supply`) properties to the UFS host controller's device-tree node, pointing at the correct PMIC regulator phandle(s) — mentions "device tree" or "dts"/"dtsi" AND ("vcc-supply" or "vccq-supply" or "regulator" phandle/reference) |
| 6 | Does **not** misdiagnose this as a PSCI/secondary-CPU problem — the log's PSCI/SMP section (lines 6–17) completes successfully (all 8 CPUs come up); a wrong answer that fixates on PSCI/CPU bring-up despite those lines clearly succeeding should be marked down explicitly, not just scored on the positive checklist |

**Score = elements 1–5 present / 5, AND element 6 (no PSCI misdiagnosis) as
a pass/fail gate independent of the score.** Pass = 4/5 or 5/5 on the
checklist **and** no PSCI misdiagnosis.

### Honesty note

This log is authored, not captured — flagged plainly in the task and in
FINDINGS.md. The reason this is still a legitimate, falsifiable eval task
rather than a "just describe what I wrote" exercise: the failure pattern
and every log string in it are real, verifiable, standard-Linux-kernel
artifacts (cited above by source file), so a correct diagnosis genuinely
requires understanding what those specific messages mean, not pattern-
matching against a memorized real A70 boot log — because no such log
exists publicly to memorize (the postmarketOS wiki page for this device
says "not booting"; there is nothing to have boot-logged).

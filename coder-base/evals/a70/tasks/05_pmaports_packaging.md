# Task 5 — write the postmarketOS `deviceinfo` packaging file

**Level:** medium. Tests whether the model knows postmarketOS's actual
packaging contract (real variable names, real flashing method for a Samsung
device) rather than inventing plausible-sounding ones.

## Prompt to give the model

> Write a postmarketOS `deviceinfo` file for `device/testing/device-samsung-
> a70q/deviceinfo`, targeting the Samsung Galaxy A70 (SM-A705F, Snapdragon
> 675 / SM6150, aarch64, handset form factor). This is a Samsung phone, so
> pick the correct family of flashing method (Samsung's proprietary
> download-mode protocol has one specific open-source tool that speaks it —
> name the deviceinfo value that selects it, not just the tool's name).

## Grading rubric (required-variable checklist)

`grader.py pmaports <answer.txt>` checks for the literal presence of these
`deviceinfo_*` variable **names** (case-sensitive) with a plausible value
each — this is a packaging-format task, so getting the variable *names*
exactly right matters more than any specific value:

| # | Variable | Required value shape | Confidence |
|---|---|---|---|
| 1 | `deviceinfo_codename` | `samsung-a70q` (postmarketOS's own convention: `<vendor>-<codename>`, and `a70q` is Samsung's own internal codename for this device, visible across every LineageOS/vendor device-tree repo for it) | verified — variable name and general convention confirmed against postmarketOS's own deviceinfo reference docs; the exact codename string is corroborated by many independent Android-side device-tree repos all naming it `a70q` |
| 2 | `deviceinfo_manufacturer` | `Samsung` | verified (standard field) |
| 3 | `deviceinfo_name` | `Galaxy A70` (or similar human name) | verified (standard field) |
| 4 | `deviceinfo_arch` | `aarch64` | verified |
| 5 | `deviceinfo_chassis` | `handset` | verified — this is the standard postmarketOS device-type value for phones |
| 6 | `deviceinfo_flash_method` | one of `heimdall-bootimg` or `heimdall-isorec` — **not** `fastboot`, `0xffff`, `mtkclient`, or any of the other pmOS-supported methods, which are for different vendors/platforms | verified — `heimdall` is the correct family (an open-source reimplementation of Samsung's Odin download-mode protocol); confirmed both generically (deviceinfo reference) and via a real Samsung device's pmaports `deviceinfo` example using `heimdall-bootimg`/partition-name variables |
| 7 | At least one `deviceinfo_flash_heimdall_partition_*` variable (e.g. `deviceinfo_flash_heimdall_partition_kernel`) naming a real Odin/Heimdall partition label such as `KERNEL`, `BOOT`, or `RECOVERY` | verified pattern, exact partition label for *this* device's PIT table not independently confirmed |
| 8 | `deviceinfo_year` (roughly `2019`, this device's release year) | verified field name; value should be historically correct (Galaxy A70 launched April/May 2019) |

**Score = rows present / 8. Pass = 6/8 or better, but rows 1, 6, and 7 are
weighted — a wrong flash method (e.g. writing `fastboot` for a Samsung
Snapdragon phone, which does not speak fastboot in download mode) is an
automatic fail regardless of the total**, because it reveals the model
picked a plausible-sounding Android-generic answer instead of the actual
Samsung-specific one.

### Honesty note

I confirmed the variable *names* and the `heimdall-bootimg`/`heimdall-
isorec` flash-method values against postmarketOS's own deviceinfo reference
documentation and cross-checked the Heimdall partition-variable pattern
against a real Samsung device's pmaports file (Galaxy Tab 3 7.0, a
different Samsung device, same packaging family). **I did not find and
therefore cannot confirm an actual, merged `device-samsung-a70q` package in
pmaports** — my search found the postmarketOS wiki page for this device
(see FINDINGS.md) marking it "not booting," which is consistent with no
such package existing yet. Treat the exact partition names in row 7 as
"the right kind of value," not a verified PIT table for this specific
phone.

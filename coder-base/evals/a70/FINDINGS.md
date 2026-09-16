# Samsung Galaxy A70 bare-metal Linux — the real hardware situation

> Broken Windows Law: test the REAL output, not a proxy. Everything below
> that is stated as fact is sourced (inline). Everything I could not verify
> is marked **unverified** and says what would be needed to verify it.

## 1. The hardware, verified

| Field | Value | Source |
|---|---|---|
| Model | Samsung Galaxy A70, **SM-A705** (region suffix varies: F/FN/GM/MN/0/U/W/...) | GSMArena, B&H listings |
| SoC | **Qualcomm Snapdragon 675**, internal platform **SM6150** | GSMArena spec sheet; WikiChip; confirmed independently by a live Oct-2025 Qualcomm upstream kernel patch series ("`[v1] media: qcom: camss: Add sm6150 camss support`", oss.qualcomm.com, tested on a "Talos EVK" board) |
| Process node | 11 nm (Samsung LPP) | WikiChip |
| CPU | Octa-core **Kryo 460**: 2× Kryo 460 Gold (Cortex-A76-based) @ 2.0 GHz + 6× Kryo 460 Silver (Cortex-A55-based) @ 1.7 GHz | GSMArena, WikiChip |
| GPU | **Adreno 612** @ ~845 MHz | GSMArena, WikiChip |
| DSP | Hexagon 685 | WikiChip (general Snapdragon 675 spec aggregation; not independently re-checked against Qualcomm's own PDF product brief, which this session could not read — see §5) |
| ISP | Spectra 250L | same caveat as DSP row |
| Modem | **Snapdragon X12 LTE**, integrated (not a discrete chip), Cat 13 uplink / Cat 15 downlink | WikiChip |
| RAM | 6 GB or 8 GB LPDDR4X, depending on SKU | GSMArena |
| Storage | 128 GB, **UFS 2.1** (not eMMC) | XDA-Developers forum discussion on the exact controller ("A70 internal memory type?" thread) — **treat as community-reported, not an official Samsung/Qualcomm spec sheet, though independently corroborated by teardown/pinout sites describing a UFS chip and "UFS ISP pinout" test points** |
| Display | 6.7" Super AMOLED, 1080×2400 | GSMArena |
| Shipped OS | Android 9 Pie / One UI 1.1, updated up to Android 11 / One UI 3.1 | GSMArena |
| Architecture | aarch64 (aka arm64) | implied by SoC; standard for this generation |

## 2. Region variants and the bootloader — the fact most likely to sink this project if skipped

Samsung ships the same physical SM-A705 board under several region-specific
model suffixes, and **the bootloader-unlock story is not the same across
them** (XDA-Developers unlock guides, cross-checked across multiple
independent threads):

- **Can be OEM-unlocked normally** (Settings → Developer Options → OEM
  unlocking, after enabling it in Wi-Fi settings, then Odin/Download-mode
  flow): SM-A7050 (HK/China/Taiwan), SM-A705F (EU/Africa/Asia), SM-A705FN
  (Europe/Africa/Asia), SM-A705GM (India/Nepal/Sri Lanka), SM-A705MN
  (Americas/Oceania/Asia).
- **Cannot be unlocked, full stop**: **SM-A705U** (US carrier variant).
  Samsung locks US Qualcomm-variant phones with a device-unique key it does
  not distribute; there is no known method, jailbreak, or paid tool that
  reopens this on this device family, per every US-carrier-Samsung
  unlock-guide thread found.

**I do not know which suffix Iddo's physical phone is**, and this is not
something research can determine — it requires reading Settings → About
Phone → Model Number on the device itself, or the box/sticker. **This is
the single most important fact to check before spending real engineering
time on this capstone**, because if it is an SM-A705U, the project is
blocked at the very first step (an unlockable bootloader is the
prerequisite for flashing literally anything, mainline or otherwise) no
matter how good the kernel/device-tree work is.

## 3. postmarketOS / mainline status — honest, and not good

**postmarketOS tracks this device.** Its wiki lists a page for
`samsung-a70q` (the device's Android codename, confirmed independently
across many LineageOS/vendor device-tree GitHub repos, all using exactly
`a70q`) under the Qualcomm Snapdragon 675 (SDM675) chipset family page,
alongside the Moto G Stylus (2021), Moto One Hyper, and Xiaomi Redmi Note 7
Pro (all also SM6150-based). **The wiki records this device's status as
"not booting"** — search-engine indexing of the wiki page (the live page
itself returned an anti-bot challenge to direct fetching in this session,
so this is read via cached search-result text, not a live fetch) describes
several users "working on porting this device, with some noting it as a
mainlining target" — i.e. **an aspiration, not an achieved port.** There is
no evidence of a working postmarketOS image, no `device-samsung-a70q`
package found in pmaports, and no dedicated wiki subpage with a deviceinfo/
kernel-status table the way an actively-supported device has.

**Mainline (upstream torvalds/linux) kernel status for the SM6150
platform itself, independent of this specific phone:**
- `arch/arm64/boot/dts/qcom/sm6150.dtsi` **already exists upstream** —
  confirmed by finding a real, currently-in-review Qualcomm-authored patch
  series (Wenmeng Liu, oss.qualcomm.com, "sm6150-camss", first posted
  2025-10-16, at v4 as of this search) that *modifies* this existing file
  to add CAMSS (camera subsystem) support, tested on a **Qualcomm-internal
  "Talos EVK" evaluation board** — not the Galaxy A70, and the patch cover
  letter and discussion make **no mention of Samsung or a70q at all**.
- I could not find any upstream, in-tree device tree file for the Galaxy
  A70 board itself (no `sm6150-samsung-a70q.dts` or similar), and no
  community "sm6150-mainline" kernel project comparable to the real,
  active `sdm670-mainline` or `sdm845-mainline` GitLab groups that exist
  for sibling/neighboring Snapdragon generations. Every A70-specific device
  tree I found (`sm6150-Samsung/android_device_samsung_a70q`,
  `samsung-sm6150-devs/android_device_samsung_a70q`, several LineageOS
  forks) targets the **downstream Android common kernel** (the vendor's
  own out-of-tree 4.x/5.x-based kernel fork), which is the normal Android
  kernel, not mainline Linux, and is not a starting point mainline can
  build on directly — only a *reference* for what hardware exists and how
  it's wired, which is exactly how postmarketOS's own "Mainlining Guide"
  describes using a downstream vendor tree.
- A companion PMIC used across several SM6150-family phones,
  `pm6150.dtsi`, **is** upstream and well-established (it's shared with
  other, better-supported qcom platforms) — so some of the ecosystem
  around this SoC is mainlined, just not the phone-specific board file or,
  as far as I could confirm, a complete base `sm6150-idp`-style reference
  board `.dts` a phone port could fork from the way sdm845 ports fork from
  the well-trodden db845c reference board.

**Bottom line for this section: base SM6150 SoC-level support is thin but
real and *recently, actively* growing upstream (the Oct-2025 CAMSS series is
current, active work by a Qualcomm engineer) — but the Galaxy A70 board
itself has zero upstream device-tree work, and the postmarketOS community's
own tracking page for it says "not booting," not "in progress" with a
progress table.** This is a meaningfully earlier starting point than, say,
a PinePhone or a well-known sdm845 device.

## 4. What a real port would have to do (this is Capstone 1's task ladder)

1. Verify the exact model suffix and confirm the bootloader can be
   unlocked (§2) — a purely physical/administrative step, not engineering,
   but it gates everything else.
2. Get a working chainloadable second-stage bootloader (`lk2nd` is the
   standard postmarketOS pattern for Samsung/Qualcomm Android
   bootloaders) so a custom kernel+DTB+initramfs can be booted without
   replacing Samsung's own signed first-stage chain.
3. Write the board-level device tree essentially from scratch: start from
   the existing upstream `sm6150.dtsi` (SoC-level: CPUs, GIC, GCC clocks,
   TLMM pinctrl, UFS/QUP/GENI blocks already have *some* upstream
   precedent from sibling SM6150 devices' patches) and layer the Galaxy
   A70's board-specific wiring (regulators, display panel, touchscreen,
   PMIC rail mapping) by diffing the **downstream** Samsung/Android kernel
   tree's own `a70q` device tree against that upstream base — the standard
   postmarketOS mainlining workflow, but with less upstream SM6150 board
   precedent to lean on than a more mature platform would offer.
4. Get a serial console working first (Task 3 in this eval), then storage
   (UFS — Task 4/Task 6's diagnosed failure mode is exactly the class of
   bug this step tends to produce), then display, touchscreen, WiFi/BT, in
   roughly that order — this is the order every real qcom-mainline bring-up
   (sdm845, sdm670, SM7150/"phoenix") has followed, for the structural
   reason that each later subsystem is harder to debug without the
   previous one working.
5. **Accept, from day one, that cellular (calls + mobile data) will very
   likely never work**, because it requires the signed Qualcomm modem
   firmware blob plus a correctly-configured remoteproc/PIL setup, and
   redistributing/reverse-engineering that firmware is both a legal and a
   practical dead end that essentially no mainline Qualcomm phone port has
   solved for calls specifically (WiFi-only usage is the realistic ceiling
   for "cellular-adjacent" functionality on a mainline port of any modern
   qcom phone, this one included).

## 5. What I could not verify, and would need to

- **Which exact SM-A705 suffix Iddo's own phone is** (§2) — needs physical
  inspection, not research.
- **Exact Hexagon DSP/Spectra ISP model numbers** — sourced from a
  general spec-aggregation site (WikiChip), not independently re-confirmed
  against Qualcomm's own product brief PDF, which this session's web-fetch
  tool could not parse (binary PDF, not HTML). These two facts are
  low-stakes for the actual bring-up ladder (camera/DSP support is
  explicitly out of scope for a minimal boot per Task 4) but are flagged
  rather than silently presented as fully confirmed.
- **UFS vs eMMC**: reasonably solid (independent teardown/pinout sources
  agree), but not sourced from an official Samsung/Qualcomm datasheet —
  flagged as community-reported in the table above.
- **Live content of the postmarketOS wiki's `samsung-a70q` and
  `Qualcomm_Snapdragon_675_(SDM675)` pages**: this session's web-fetch tool
  was blocked by the wiki's own anti-bot challenge (Anubis) on every direct
  fetch attempt; the "not booting" / "mainlining target" status above comes
  from a search engine's cached indexing of that page's text, not a live
  read. Anyone who can browse the wiki directly (a normal browser defeats
  Anubis fine; it is only scripted fetching that gets challenged) should
  confirm this directly before treating it as settled.
- **Whether any private/unpublished mainlining effort for this exact
  device exists** that simply hasn't surfaced in web search (postmarketOS
  contributors sometimes work in personal forks before merging) — genuinely
  unknown; the honest answer is "not found," not "does not exist."

## 6. The verdict — is this realistically achievable?

**Yes, but it is a real, multi-month, from-near-zero embedded bring-up
project, not a weekend port, and the honest hardest blocker is not
technical — it's the region-variant bootloader lock (§2), which is a
binary yes/no gate that must be checked before anything else.** Assuming
the bootloader can be unlocked: the SoC family (SM6150/Snapdragon 675) has
real but thin and recent upstream precedent (the pm6150 PMIC, and active
2025 CAMSS work on a sibling reference board) to build from, which is
meaningfully better than "nothing," but there is no existing A70 device
tree, no known working postmarketOS image, and the community's own
tracking explicitly says "not booting" today. Whoever attempts this should
expect the device-tree/regulator-wiring work (Tasks 3 and 6 in this eval)
to be the actual bulk of the effort, not the kernel config (Task 4) or the
packaging (Task 5), which are comparatively mechanical once the hardware
answers those first two questions correctly.

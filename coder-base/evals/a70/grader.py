#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Objective checklist/keyword grader for the Galaxy A70 bare-metal-Linux
eval tasks. See tasks/*.md for the full prose spec and sourcing of every
required item — this file is deliberately kept in sync with those tables.

None of these checks require a GPU, a real kernel tree, or network access.
Most are honest, disclosed PROXIES (keyword/substring/regex checks over the
model's free-text or device-tree-text answer) — not as strong as compiling
a kernel or a DTS with a real toolchain, and each task file says so where
relevant. They are still objective and mechanical: the same answer gets the
same score every time, and a deliberately wrong answer is verified (see
`self_test()`) to actually score lower, not just theoretically expected to.

Usage:
    PYTHONIOENCODING=utf-8 python grader.py <mode> <path/to/answer.txt>
    PYTHONIOENCODING=utf-8 python grader.py self_test

mode in {identify, bootchain, devicetree, defconfig, pmaports, diagnose}
"""
from __future__ import annotations

import re
import sys


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _any(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)


# ---------------------------------------------------------------- Task 1

def grade_identify(text: str, verbose=True) -> bool:
    rows = [
        ("SoC / platform (Snapdragon 675 + SM6150)",
         _any(text, "sm6150") and _any(text, "675")),
        ("CPU (Kryo 460, octa-core, 2.0/1.7 GHz split)",
         _any(text, "kryo 460", "kryo460") and _any(text, "2.0", "2 ghz")
         and _any(text, "1.7")),
        ("GPU (Adreno 612)", _any(text, "adreno 612")),
        ("Modem (X12 LTE)", _any(text, "x12")),
        ("Region-variant bootloader-unlock split (SM-A705U cannot unlock)",
         _any(text, "a705u") and _any(text, "cannot", "can't", "unable",
                                       "locked", "no oem unlock", "not unlock")),
    ]
    return _score(rows, need=5, verbose=verbose)


# ---------------------------------------------------------------- Task 2

def grade_bootchain(text: str, verbose=True) -> bool:
    rows = [
        ("PBL (Primary Boot Loader / mask ROM / eFuse root of trust)",
         _any(text, "pbl", "primary boot loader", "mask rom", "efuse")),
        ("XBL/SBL (extensible/secondary bootloader)",
         _any(text, "xbl", "sbl", "secondary boot loader")),
        ("TrustZone / TZ / QSEE / secure world / EL3",
         _any(text, "trustzone", "qsee", "secure world", " tz ", "el3")),
        ("ABL or lk2nd",
         _any(text, "abl", "lk2nd", "little kernel")),
        ("Device tree blob handed to the kernel, wrong/missing node = silent failure",
         _any(text, "device tree", "dtb") and _any(text, "silent", "no probe",
                                                     "never probe", "quietly")),
        ("Locked bootloader breaks the chain via signature verification",
         _any(text, "signature", "signed", "verify") and _any(text, "unlock", "lock")),
        ("Modem = separate DSP firmware via remoteproc/PIL, signed OEM blob, usually unsupported",
         _any(text, "remoteproc", "peripheral image loader", "pil") and
         _any(text, "modem", "baseband") and
         _any(text, "signed", "blob", "proprietary", "firmware")),
    ]
    return _score(rows, need=6, verbose=verbose)


# ---------------------------------------------------------------- Task 3

def grade_devicetree(text: str, verbose=True) -> bool:
    opens, closes = text.count("{"), text.count("}")
    rows = [
        ("Braces balance", opens == closes and opens > 0),
        ("Real GENI UART compatible string",
         _any(text, "qcom,geni-uart", "qcom,geni-debug-uart")),
        ("interrupts property present",
         bool(re.search(r"\binterrupts\s*=", text))),
        ("clocks + clock-names with a phandle reference",
         bool(re.search(r"\bclocks\s*=\s*<\s*&", text)) and
         bool(re.search(r"\bclock-names\s*=", text))),
        ("pinctrl-names \"default\" + pinctrl-0 phandle",
         _any(text, "pinctrl-names") and "default" in text.lower() and
         bool(re.search(r"pinctrl-0\s*=\s*<\s*&", text))),
        ("status = \"okay\" present (or explicit note that the board file overrides it)",
         _any(text, 'status = "okay"', "status=\"okay\"") or
         (_any(text, "disabled") and _any(text, "board", "overrid"))),
    ]
    return _score(rows, need=5, verbose=verbose)


# ---------------------------------------------------------------- Task 4

def grade_defconfig(text: str, verbose=True) -> bool:
    rows = [
        ("CONFIG_ARCH_QCOM", "CONFIG_ARCH_QCOM" in text),
        ("CONFIG_QCOM_SCM", "CONFIG_QCOM_SCM" in text),
        ("CONFIG_QCOM_SMEM", "CONFIG_QCOM_SMEM" in text),
        ("GENI serial (CONFIG_QCOM_GENI_SE + CONFIG_SERIAL_QCOM_GENI)",
         "CONFIG_QCOM_GENI_SE" in text and "CONFIG_SERIAL_QCOM_GENI" in text),
        ("CONFIG_PINCTRL_MSM", "CONFIG_PINCTRL_MSM" in text),
        ("RPMh power domains/regulators (CONFIG_QCOM_RPMHPD / CONFIG_REGULATOR_QCOM_RPMH)",
         "CONFIG_QCOM_RPMHPD" in text or "CONFIG_REGULATOR_QCOM_RPMH" in text),
        ("Interconnect (CONFIG_INTERCONNECT_QCOM)", "CONFIG_INTERCONNECT_QCOM" in text),
        ("UFS host controller (CONFIG_SCSI_UFSHCD + a qcom glue symbol)",
         "CONFIG_SCSI_UFSHCD" in text and _any(text, "CONFIG_SCSI_UFS_QCOM",
                                                "UFS_QCOM")),
        ("Correct storage class: SCSI disk (UFS), not MMC/eMMC block device",
         "CONFIG_BLK_DEV_SD" in text and "CONFIG_MMC_BLOCK" not in text),
    ]
    ok = _score(rows, need=7, verbose=verbose)
    if "CONFIG_MMC_BLOCK" in text and "CONFIG_SCSI_UFSHCD" not in text:
        print("[defconfig] LOUD FLAG: answer configures MMC/eMMC storage but "
              "never mentions UFS — this device uses UFS 2.1, not eMMC. "
              "Automatic fail regardless of row count.")
        ok = False
    return ok


# ---------------------------------------------------------------- Task 5

def grade_pmaports(text: str, verbose=True) -> bool:
    rows = [
        ("deviceinfo_codename (= samsung-a70q)",
         "deviceinfo_codename" in text and _any(text, "a70q")),
        ("deviceinfo_manufacturer", "deviceinfo_manufacturer" in text),
        ("deviceinfo_name", "deviceinfo_name" in text),
        ("deviceinfo_arch (= aarch64)",
         "deviceinfo_arch" in text and "aarch64" in text.lower()),
        ("deviceinfo_chassis (= handset)",
         "deviceinfo_chassis" in text and "handset" in text.lower()),
        ("deviceinfo_flash_method = heimdall-bootimg or heimdall-isorec",
         "deviceinfo_flash_method" in text and _any(text, "heimdall-bootimg",
                                                      "heimdall-isorec")),
        ("a deviceinfo_flash_heimdall_partition_* variable",
         bool(re.search(r"deviceinfo_flash_heimdall_partition_\w+", text))),
        ("deviceinfo_year", "deviceinfo_year" in text),
    ]
    ok = _score(rows, need=6, verbose=verbose)
    wrong_method = _any(text, "deviceinfo_flash_method") and _any(
        text, '="fastboot"', "='fastboot'", "= fastboot", "0xffff",
        "mtkclient", "rkdeveloptool", "sp-flash-tool", "uuu")
    if wrong_method:
        print("[pmaports] LOUD FLAG: flash method looks like a generic/"
              "wrong-vendor value (fastboot/mtkclient/etc.) — this is a "
              "Samsung device, Odin/Heimdall protocol only. Automatic fail.")
        ok = False
    return ok


# ---------------------------------------------------------------- Task 6

def grade_diagnose(text: str, verbose=True) -> bool:
    rows = [
        ("Regulator + dummy fallback named", _any(text, "regulator") and _any(text, "dummy")),
        ("UFS host controller named", _any(text, "ufs", "ufshcd")),
        ("-110 / ETIMEDOUT / timeout named", _any(text, "-110", "etimedout", "timeout", "timed out")),
        ("Root device / rootfs never appearing named",
         _any(text, "root device", "rootfs", "root filesystem", "waiting for root")),
        ("Fix: add vcc-supply/vccq-supply regulator phandle(s) in the device tree",
         _any(text, "device tree", "dts", "dtsi") and
         _any(text, "vcc-supply", "vccq-supply", "regulator")),
    ]
    ok = _score(rows, need=4, verbose=verbose)
    misdiagnosed_psci = _any(text, "psci") and _any(
        text, "secondary cpu", "cpu1", "cpu bring-up", "smp") and not _any(
        text, "regulator", "ufs")
    if misdiagnosed_psci:
        print("[diagnose] LOUD FLAG: answer fixates on PSCI/secondary-CPU "
              "bring-up, but the log's own SMP section (lines 6-17) shows "
              "all 8 CPUs coming up successfully. Automatic fail — this is "
              "the specific wrong-diagnosis this task is designed to catch.")
        ok = False
    return ok


# ---------------------------------------------------------------- plumbing

def _score(rows, need: int, verbose: bool) -> bool:
    hits = 0
    for label, ok in rows:
        hits += int(bool(ok))
        if verbose:
            print(f"  [{'x' if ok else ' '}] {label}")
    passed = hits >= need
    if verbose:
        print(f"  -> {hits}/{len(rows)}  need >= {need}  ["
              f"{'PASS' if passed else 'FAIL'}]")
    return passed


MODES = {
    "identify": grade_identify,
    "bootchain": grade_bootchain,
    "devicetree": grade_devicetree,
    "defconfig": grade_defconfig,
    "pmaports": grade_pmaports,
    "diagnose": grade_diagnose,
}


def self_test():
    """Prove the graders are not vacuous: a strong hand-written GOOD answer
    per task passes; a deliberately weak/wrong answer fails. This is the
    same discipline as the ALMA eval's negative_examples/ — a check that
    cannot fail is not a check."""
    good = {
        "identify": (
            "SoC: Qualcomm Snapdragon 675, internal platform SM6150. "
            "CPU: octa-core Kryo 460, 2x Kryo 460 Gold at 2.0 GHz + "
            "6x Kryo 460 Silver at 1.7 GHz. GPU: Adreno 612. Modem: "
            "Snapdragon X12 LTE. Region split: SM-A705U (US) cannot unlock "
            "the bootloader at all; other regions (F/FN/GM/MN/0) can."),
        "bootchain": (
            "PBL (mask ROM, eFuse root of trust) -> XBL/SBL -> TrustZone "
            "(TZ/QSEE, stays resident in EL3) -> ABL or lk2nd -> kernel + "
            "device tree blob (a wrong/missing DT node is a silent, not a "
            "loud, failure) -> mounted rootfs. A locked bootloader breaks "
            "this because a custom/unsigned lk2nd image fails signature "
            "verification. The modem runs as separate firmware on a "
            "Hexagon DSP loaded via remoteproc/PIL from a signed OEM blob, "
            "so cellular usually stays unsupported."),
        "devicetree": (
            'uart1: serial@a9c0000 {\n'
            '    compatible = "qcom,geni-uart";\n'
            '    reg = <0x0a9c0000 0x4000>;\n'
            '    interrupts = <GIC_SPI 604 IRQ_TYPE_LEVEL_HIGH>;\n'
            '    clocks = <&gcc GCC_QUPV3_WRAP0_S0_CLK>;\n'
            '    clock-names = "se";\n'
            '    pinctrl-names = "default", "sleep";\n'
            '    pinctrl-0 = <&qup_uart0_default>;\n'
            '    pinctrl-1 = <&qup_uart0_sleep>;\n'
            '    status = "okay";\n'
            '};\n'),
        "defconfig": (
            "CONFIG_ARCH_QCOM=y # top-level qcom arch gate\n"
            "CONFIG_QCOM_SCM=y # TrustZone SMC calls\n"
            "CONFIG_QCOM_SMEM=y # shared memory\n"
            "CONFIG_QCOM_GENI_SE=y\nCONFIG_SERIAL_QCOM_GENI=y\n"
            "CONFIG_SERIAL_QCOM_GENI_CONSOLE=y\n"
            "CONFIG_PINCTRL_MSM=y\nCONFIG_QCOM_RPMHPD=y\n"
            "CONFIG_REGULATOR_QCOM_RPMH=y\nCONFIG_INTERCONNECT_QCOM=y\n"
            "CONFIG_SCSI_UFSHCD=y\nCONFIG_SCSI_UFS_QCOM=y\n"
            "CONFIG_BLK_DEV_SD=y  # this device uses UFS, not eMMC\n"),
        "pmaports": (
            'deviceinfo_codename="samsung-a70q"\n'
            'deviceinfo_manufacturer="Samsung"\n'
            'deviceinfo_name="Galaxy A70"\n'
            'deviceinfo_year="2019"\n'
            'deviceinfo_arch="aarch64"\n'
            'deviceinfo_chassis="handset"\n'
            'deviceinfo_flash_method="heimdall-bootimg"\n'
            'deviceinfo_flash_heimdall_partition_kernel="BOOT"\n'),
        "diagnose": (
            "The UFS host controller (ufshcd-qcom) has no real vcc/vccq "
            "regulator wired in the device tree, so the kernel falls back "
            "to a dummy regulator; without real power the link never "
            "trains and ufshcd_probe_hba times out with -110 (ETIMEDOUT). "
            "Because the UFS probe failed, the root filesystem partition "
            "never appears as a block device, so the kernel loops forever "
            "in 'Waiting for root device'. The PSCI/SMP section above it "
            "is fine - all 8 CPUs come up. Fix: add correct vcc-supply and "
            "vccq-supply properties (pointing at the real PMIC regulator "
            "phandles) to the ufshc node in the device tree/dtsi."),
    }
    bad = {
        "identify": "It's a Samsung phone with a Qualcomm chip and Android.",
        "bootchain": "It boots like a normal Linux phone, GRUB loads the kernel.",
        "devicetree": 'foo@0 { compatible = "made,up"; };',
        "defconfig": "CONFIG_MMC_BLOCK=y\nCONFIG_ANDROID=y\n",
        "pmaports": 'deviceinfo_codename="a70"\ndeviceinfo_flash_method="fastboot"\n',
        "diagnose": ("The secondary CPUs never come up because PSCI/SMP "
                      "failed, this is a classic CPU bring-up bug."),
    }
    all_ok = True
    for mode, fn in MODES.items():
        print(f"=== self_test [{mode}] GOOD (must PASS) ===")
        g = fn(good[mode], verbose=True)
        print(f"=== self_test [{mode}] BAD (must FAIL) ===")
        b = fn(bad[mode], verbose=True)
        ok = g and not b
        print(f"--- {mode}: good_passed={g} bad_passed={b} -> "
              f"{'OK' if ok else 'GRADER IS BROKEN'} ---\n")
        all_ok = all_ok and ok
    return all_ok


def main(argv):
    if len(argv) >= 2 and argv[1] == "self_test":
        return 0 if self_test() else 1
    if len(argv) < 3 or argv[1] not in MODES:
        print(__doc__)
        return 1
    mode, path = argv[1], argv[2]
    text = _read(path)
    ok = MODES[mode](text)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

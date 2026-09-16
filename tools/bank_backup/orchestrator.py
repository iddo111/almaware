#!/usr/bin/env python3
"""Bank-grade unified backup orchestrator.

Coordinates six sources onto N:\\BACKUP. Each source has a sub-driver
that returns a status dict. The orchestrator gathers them, writes a
single STATUS.md, and exits.

Sources:
    PC      D:\\ + selected C:\\Users\\iddo1  -> N:\\PC\\
    laptop  linuxlite@<lan-ip>           -> N:\\lapclod\\ (push from laptop)
    a70     Samsung A70 over Termux sshd     -> N:\\a70\\
    git     D:\\CLAUDE\\_ai_backups_git       -> github.com/iddo111 (needs gh auth)
    gdrive  N:\\BACKUP\\ subset               -> Google Drive (needs rclone auth)
    mint    \\\\.\\PhysicalDrive1 (Lexar)     -> N:\\mint-ssd\\ (manual, VM-down)

Schedule: every 6 hours via Windows Task "Bank-Backup-Orchestrator".
Audit log: N:\\_logs\\bank-backup-<ts>.log
Rolling summary: N:\\_logs\\STATUS.md
ASCII only, no em-dashes (per feedback_ps1_no_emdash.md).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(r"D:\CLAUDE\tools\bank_backup")
N_DRIVE = Path(r"N:\BACKUP") if Path(r"N:\BACKUP").exists() else Path(r"N:\\")
LOGS_DIR = Path(r"N:\_logs")
STATUS_MD = LOGS_DIR / "STATUS.md"
NOW = dt.datetime.now()
TS = NOW.strftime("%Y%m%d-%H%M%S")
RUN_LOG = LOGS_DIR / f"bank-backup-{TS}.log"

PC_ORCH = Path(r"N:\PC\_scripts\orchestrator.ps1")
PC_STATE = Path(r"N:\PC\_state.json")

A70_KEY = Path(r"C:\Users\<user>\.ssh\a70_key")
A70_USER = "u0_a234"  # Termux default; auto-detected at probe
A70_PORT = 8022
A70_KNOWN_IPS = ["<lan-ip>", "<lan-ip>", "<lan-ip>"]

LAPCLOD_KEY = Path(r"C:\Users\<user>\.ssh\laptop93")
LAPCLOD_HOST = "linuxlite@<lan-ip>"

GIT_REPO = Path(r"D:\CLAUDE\_ai_backups_git")
GIT_REMOTE_NAME = "origin"
GIT_REMOTE_URL = "https://github.com/iddo111/claude-ai-backups.git"

RCLONE_REMOTE = "gdrive"  # name in rclone.conf once Iddo auths
RCLONE_SRC = Path(r"N:\_logs")  # initial: just logs; expand once auth lands
RCLONE_DEST = "gdrive:bank-backup/_logs"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: List[str], timeout: int = 300, env: Optional[dict] = None) -> Tuple[int, str, str]:
    """Run a command, capture output. Returns (rc, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            shell=False,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired as e:
        return 124, e.stdout or "", e.stderr or f"TIMEOUT after {timeout}s"
    except FileNotFoundError as e:
        return 127, "", str(e)
    except Exception as e:  # noqa: BLE001
        return 1, "", f"EXC: {e}"


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception as e:  # noqa: BLE001
        return f"ERR:{e}"


def sample_sha_manifest(root: Path, dest: Path, k: int = 100) -> int:
    """Pick K random files under root, write their SHA-256 to dest. Returns count."""
    files: List[Path] = []
    try:
        for dirpath, _dirs, fnames in os.walk(root):
            for fn in fnames:
                files.append(Path(dirpath) / fn)
                if len(files) > 10000:
                    break
            if len(files) > 10000:
                break
    except Exception:
        pass
    if not files:
        return 0
    sample = random.sample(files, min(k, len(files)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as f:
        f.write(f"# SHA-256 sample manifest\n# root: {root}\n# count: {len(sample)}\n# generated: {NOW.isoformat()}\n\n")
        for p in sample:
            try:
                size = p.stat().st_size
            except Exception:
                size = -1
            f.write(f"{sha256_file(p)}  {size:>12}  {p}\n")
    return len(sample)


# ---------------------------------------------------------------------------
# Source 1: PC (D:\ + C:\Users\<user>) via existing N:\PC\_scripts orchestrator
# ---------------------------------------------------------------------------

def backup_pc(skip: bool = False) -> Dict[str, Any]:
    res: Dict[str, Any] = {"source": "PC", "started": dt.datetime.now().isoformat()}
    if skip:
        res["status"] = "skipped"
        return res
    if not PC_ORCH.exists():
        res["status"] = "missing-driver"
        res["error"] = f"{PC_ORCH} not found"
        return res
    log(f"PC: invoking {PC_ORCH}")
    rc, out, err = run(
        [
            "powershell.exe", "-NoProfile", "-WindowStyle", "Hidden",
            "-ExecutionPolicy", "Bypass", "-File", str(PC_ORCH),
        ],
        timeout=6 * 3600,  # 6h - heavy
    )
    res["rc"] = rc
    res["status"] = "done" if rc == 0 else "failed"
    res["ended"] = dt.datetime.now().isoformat()
    # Report state
    if PC_STATE.exists():
        try:
            st = json.loads(PC_STATE.read_text(encoding="utf-8"))
            res["state_summary"] = {
                k: v.get("status", "?") for k, v in st.items() if isinstance(v, dict)
            }
        except Exception as e:  # noqa: BLE001
            res["state_error"] = str(e)
    # Spot-check a manifest sample on largest done dir
    try:
        if Path(r"N:\PC\D\CLAUDE").exists():
            n = sample_sha_manifest(
                Path(r"N:\PC\D\CLAUDE"),
                LOGS_DIR / f"sha256-sample-PC-CLAUDE-{TS}.txt",
                k=100,
            )
            res["sha_sample_files"] = n
    except Exception as e:  # noqa: BLE001
        res["sha_sample_error"] = str(e)
    return res


# ---------------------------------------------------------------------------
# Source 2: laptop (push-based, just verify)
# ---------------------------------------------------------------------------

def backup_laptop() -> Dict[str, Any]:
    """Verify lapclod backup is fresh. Push lapclod's rsync if stale.

    The pull-flow is configured on the laptop side (rsync to N: via SMB).
    Here we just check freshness and trigger a manual run if older than 6h.
    """
    res: Dict[str, Any] = {"source": "laptop", "started": dt.datetime.now().isoformat()}
    complete_marker = Path(r"N:\lapclod\_COMPLETE")
    if complete_marker.exists():
        age = (dt.datetime.now().timestamp() - complete_marker.stat().st_mtime)
        res["last_complete_age_hours"] = round(age / 3600, 2)
        if age < 6 * 3600:
            res["status"] = "fresh"
        else:
            res["status"] = "stale"
    else:
        res["status"] = "missing-marker"

    # SSH-probe lapclod
    rc, out, err = run(
        [
            "ssh", "-i", str(LAPCLOD_KEY), "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=no", LAPCLOD_HOST,
            "echo OK; uptime; df -h / | tail -1",
        ],
        timeout=10,
    )
    res["ssh_rc"] = rc
    res["ssh_out"] = out.strip()[:400]
    res["ended"] = dt.datetime.now().isoformat()
    return res


# ---------------------------------------------------------------------------
# Source 3: A70 (best-effort; phone may be off the LAN)
# ---------------------------------------------------------------------------

def probe_a70_ip() -> Optional[str]:
    for ip in A70_KNOWN_IPS:
        try:
            with socket.create_connection((ip, A70_PORT), timeout=1.5):
                return ip
        except Exception:
            continue
    return None


def backup_a70() -> Dict[str, Any]:
    res: Dict[str, Any] = {"source": "a70", "started": dt.datetime.now().isoformat()}
    ip = probe_a70_ip()
    if not ip:
        res["status"] = "offline"
        res["note"] = "A70 not reachable on known IPs; will retry next cycle"
        res["ended"] = dt.datetime.now().isoformat()
        return res
    res["ip"] = ip
    # Detect Termux user id (u0_aXXX) via SSH whoami
    rc, out, err = run(
        [
            "ssh", "-i", str(A70_KEY),
            "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=NUL", "-p", str(A70_PORT),
            f"{A70_USER}@{ip}", "whoami; ls ~/.claude/ 2>/dev/null | head; ls ~/storage/shared 2>/dev/null | head -5",
        ],
        timeout=10,
    )
    res["whoami_rc"] = rc
    res["whoami_out"] = out.strip()[:400]
    if rc != 0:
        # Try detecting actual u0_a id by trying common ones
        for uid in ["u0_a234", "u0_a233", "u0_a300", "u0_a400"]:
            rc2, out2, _ = run(
                ["ssh", "-i", str(A70_KEY), "-o", "ConnectTimeout=3",
                 "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
                 "-p", str(A70_PORT), f"{uid}@{ip}", "whoami"],
                timeout=6,
            )
            if rc2 == 0 and out2.strip().startswith("u0_a"):
                res["a70_user"] = uid
                break
        else:
            res["status"] = "auth-fail"
            res["note"] = "Could not authenticate to Termux sshd. Re-pair key."
            res["ended"] = dt.datetime.now().isoformat()
            return res
    else:
        res["a70_user"] = A70_USER

    a70_user = res["a70_user"]
    # We pull DCIM + ~/.claude + ~/storage/shared/Documents
    targets = [
        ("~/.claude/", r"N:\a70\termux-claude"),
        ("~/storage/dcim/", r"N:\a70\DCIM"),
        ("~/storage/shared/Documents/", r"N:\a70\Documents"),
    ]
    pulled = []
    # Prefer wsl rsync; if not available, scp -r
    wsl_rc, _, _ = run(["wsl.exe", "-e", "which", "rsync"], timeout=5)
    use_rsync = wsl_rc == 0
    for src, dest in targets:
        Path(dest).mkdir(parents=True, exist_ok=True)
        if use_rsync:
            # Translate Windows path to WSL path: N:\a70\foo -> /mnt/n/a70/foo
            wsl_dest = dest.replace("N:\\", "/mnt/n/").replace("\\", "/")
            wsl_dest = wsl_dest + "/"
            cmd = [
                "wsl.exe", "-e", "rsync", "-az",
                "--no-perms", "--no-owner", "--no-group",
                "-e",
                f"ssh -i {str(A70_KEY).replace(chr(92), '/')} -p {A70_PORT} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
                f"{a70_user}@{ip}:{src}",
                wsl_dest,
            ]
            rc, out, err = run(cmd, timeout=20 * 60)
        else:
            cmd = [
                "scp", "-i", str(A70_KEY),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=NUL",
                "-P", str(A70_PORT), "-r",
                f"{a70_user}@{ip}:{src}", dest,
            ]
            rc, out, err = run(cmd, timeout=20 * 60)
        pulled.append({"src": src, "dest": dest, "rc": rc, "err_tail": (err or out)[-200:]})
    res["targets"] = pulled
    res["status"] = "done" if all(p["rc"] == 0 for p in pulled) else "partial"
    res["ended"] = dt.datetime.now().isoformat()
    return res


# ---------------------------------------------------------------------------
# Source 4: git (push _ai_backups_git to GitHub)
# ---------------------------------------------------------------------------

def backup_git() -> Dict[str, Any]:
    res: Dict[str, Any] = {"source": "git", "started": dt.datetime.now().isoformat()}
    if not GIT_REPO.exists():
        res["status"] = "missing"
        return res

    # Audit for secrets BEFORE pushing
    pat = ("token", "secret", "credential", "api-key", "api_key", "oauth")
    found_secrets = []
    for dirpath, _dirs, fnames in os.walk(GIT_REPO):
        if "/.git/" in dirpath.replace("\\", "/"):
            continue
        for fn in fnames:
            ln = fn.lower()
            if ln.endswith(".env") or any(p in ln for p in pat):
                found_secrets.append(str(Path(dirpath) / fn))
                if len(found_secrets) > 20:
                    break
        if len(found_secrets) > 20:
            break
    res["secrets_found"] = found_secrets

    if found_secrets:
        res["status"] = "blocked-secrets"
        res["note"] = "Refusing to push - secret-shaped files present. Scrub before retry."
        res["ended"] = dt.datetime.now().isoformat()
        return res

    # Check gh auth
    rc, out, err = run(["gh", "auth", "status"], timeout=10)
    res["gh_auth_rc"] = rc
    if rc != 0:
        res["status"] = "blocked-no-gh-auth"
        res["note"] = "gh CLI not authenticated. See GITHUB_AUTH_STEPS.md on Desktop."
        res["ended"] = dt.datetime.now().isoformat()
        return res

    # Configure remote if missing
    rc, out, err = run(["git", "-C", str(GIT_REPO), "remote", "-v"], timeout=10)
    has_remote = "origin" in (out or "")
    if not has_remote:
        # Create repo if not exists
        run(["gh", "repo", "create", "iddo111/claude-ai-backups",
             "--private", "--source", str(GIT_REPO),
             "--remote", "origin", "--push"], timeout=300)
    else:
        # Push
        rc, out, err = run(["git", "-C", str(GIT_REPO), "push", "origin", "HEAD"], timeout=600)
    rc, out, err = run(["git", "-C", str(GIT_REPO), "log", "--oneline", "-1"], timeout=10)
    res["last_commit"] = (out or "").strip()
    res["status"] = "done"
    res["ended"] = dt.datetime.now().isoformat()
    return res


# ---------------------------------------------------------------------------
# Source 5: gdrive via rclone (auth-gated)
# ---------------------------------------------------------------------------

def backup_gdrive() -> Dict[str, Any]:
    res: Dict[str, Any] = {"source": "gdrive", "started": dt.datetime.now().isoformat()}
    rc, out, err = run(["rclone", "config", "show", RCLONE_REMOTE], timeout=10)
    if rc != 0 or "type" not in (out or "").lower():
        res["status"] = "blocked-no-rclone-auth"
        res["note"] = "rclone remote 'gdrive' not configured. See RCLONE_AUTH_STEPS.md."
        res["ended"] = dt.datetime.now().isoformat()
        return res

    # Off-site copy: small irreplaceable subset + logs
    targets = [
        (str(LOGS_DIR), "gdrive:bank-backup/_logs"),
        (r"N:\lapclod\_manifest.txt", "gdrive:bank-backup/lapclod/_manifest.txt"),
        # Add Alma face-rec output when present
    ]
    if Path(r"N:\PC\D\CLAUDE\alma-memorial\.venv-train").exists() is False:
        if Path(r"N:\PC\D\CLAUDE\alma-memorial").exists():
            targets.append((r"N:\PC\D\CLAUDE\alma-memorial", "gdrive:bank-backup/alma-memorial"))

    out_list = []
    for src, dest in targets:
        if not Path(src).exists():
            out_list.append({"src": src, "dest": dest, "rc": -1, "note": "src-missing"})
            continue
        rc, _, err = run(["rclone", "copy", "--retries", "2", "--low-level-retries", "3",
                          src, dest], timeout=2 * 3600)
        out_list.append({"src": src, "dest": dest, "rc": rc, "err_tail": (err or "")[-200:]})
    res["targets"] = out_list
    res["status"] = "done" if all(t["rc"] == 0 for t in out_list if t["rc"] != -1) else "partial"
    res["ended"] = dt.datetime.now().isoformat()
    return res


# ---------------------------------------------------------------------------
# Source 6: Mint SSD (option-b: file-level rsync from inside VM)
# ---------------------------------------------------------------------------

def backup_mint() -> Dict[str, Any]:
    """Option-b file-level rsync from inside the running VM.

    Rationale for option-b vs option-a (dd image):
    - Option-a (dd of \\\\.\\PhysicalDrive1) requires shutting the VM down
      AND admin/UAC for raw disk access. Iddo's rule: never trigger UAC.
    - Option-b: rsync over SSH from inside the VM. Non-disruptive.
      Pulls /etc, /home, /root, /var/lib (selectively), /usr/local.
    - Daily delta is small; full image is overkill for a fresh VM.
    """
    res: Dict[str, Any] = {"source": "mint", "started": dt.datetime.now().isoformat(),
                            "mode": "file-level (option-b)"}
    # Find Mint VM IP via the VBoxManage guest-info or known mapping
    rc, out, err = run([
        r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
        "list", "runningvms",
    ], timeout=10)
    if "Mint" not in (out or "") and "mint" not in (out or ""):
        res["status"] = "vm-not-running"
        res["note"] = "Mint SSD VM not running. Skipping - VM-down image option requires Iddo."
        res["ended"] = dt.datetime.now().isoformat()
        return res
    # We don't know IP without guest-tools; try mDNS
    candidates = ["mint.local", "mint-ssd.local", "linuxmint.local"]
    ip = None
    for h in candidates:
        try:
            ip = socket.gethostbyname(h)
            break
        except Exception:
            continue
    if not ip:
        res["status"] = "ip-unknown"
        res["note"] = "Could not resolve Mint VM IP. Configure mint.local mDNS or static IP."
        res["ended"] = dt.datetime.now().isoformat()
        return res
    res["ip"] = ip
    # File-level rsync via WSL
    targets = [
        ("/etc/", "/mnt/n/mint-ssd/etc/"),
        ("/home/", "/mnt/n/mint-ssd/home/"),
        ("/root/", "/mnt/n/mint-ssd/root/"),
        ("/usr/local/", "/mnt/n/mint-ssd/usr-local/"),
    ]
    out_list = []
    for src, dest in targets:
        cmd = [
            "wsl.exe", "-e", "rsync", "-aHAX", "--no-perms",
            "-e", "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null",
            f"mint@{ip}:{src}", dest,
        ]
        rc, _, err = run(cmd, timeout=30 * 60)
        out_list.append({"src": src, "dest": dest, "rc": rc, "err_tail": (err or "")[-200:]})
    res["targets"] = out_list
    res["status"] = "done" if all(t["rc"] == 0 for t in out_list) else "partial"
    res["ended"] = dt.datetime.now().isoformat()
    return res


# ---------------------------------------------------------------------------
# STATUS rollup
# ---------------------------------------------------------------------------

def write_status(results: Dict[str, Dict[str, Any]]) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# BANK BACKUP - STATUS")
    lines.append("")
    lines.append(f"Last run: {NOW.isoformat()}")
    lines.append(f"Log: {RUN_LOG}")
    lines.append("")
    lines.append("| Source | Status | Notes |")
    lines.append("|--------|--------|-------|")
    for src in ("PC", "laptop", "a70", "git", "gdrive", "mint"):
        r = results.get(src.lower(), {}) or {}
        status = r.get("status", "?")
        notes = r.get("note", "") or r.get("error", "") or ""
        if not notes and "last_commit" in r:
            notes = r["last_commit"]
        if not notes and "last_complete_age_hours" in r:
            notes = f"complete {r['last_complete_age_hours']}h ago"
        notes = (notes or "").replace("|", "\\|")[:120]
        lines.append(f"| {src} | {status} | {notes} |")
    lines.append("")
    lines.append("## Bank-grade requirements")
    lines.append("")
    bd = manage_bde_status()
    lines.append(f"- Encryption at rest (BitLocker on N:): **{bd}**")
    lines.append(f"- Off-site copy (rclone gdrive): **{results.get('gdrive', {}).get('status', '?')}**")
    lines.append(f"- Manifest + SHA-256 spot-check: written under {LOGS_DIR}\\sha256-sample-*.txt")
    lines.append("")
    lines.append("## Full results JSON")
    lines.append("```json")
    lines.append(json.dumps(results, indent=2, default=str))
    lines.append("```")
    STATUS_MD.write_text("\n".join(lines), encoding="utf-8")


def manage_bde_status() -> str:
    rc, out, err = run(["manage-bde", "-status", "N:"], timeout=15)
    if "Protection On" in (out or ""):
        return "ON"
    if "Protection Off" in (out or ""):
        return "OFF (see ENABLE_BITLOCKER_N.md)"
    return "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated subset: pc,laptop,a70,git,gdrive,mint")
    ap.add_argument("--skip-pc-heavy", action="store_true",
                    help="Skip the heavy PC robocopy (for fast cycles)")
    args = ap.parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log(f"=== Bank-Backup-Orchestrator starting at {NOW.isoformat()} ===")

    only = set((args.only or "pc,laptop,a70,git,gdrive,mint").split(","))
    results: Dict[str, Dict[str, Any]] = {}

    # Network-bound first (can overlap with disk later if we add threads)
    if "laptop" in only:
        log("-- laptop --")
        results["laptop"] = backup_laptop()
    if "git" in only:
        log("-- git --")
        results["git"] = backup_git()
    if "gdrive" in only:
        log("-- gdrive --")
        results["gdrive"] = backup_gdrive()
    if "a70" in only:
        log("-- a70 --")
        results["a70"] = backup_a70()
    if "mint" in only:
        log("-- mint --")
        results["mint"] = backup_mint()
    # PC last (heavy disk)
    if "pc" in only:
        log("-- pc (heavy) --")
        results["pc"] = backup_pc(skip=args.skip_pc_heavy)

    write_status(results)
    log("=== done ===")
    print(STATUS_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())

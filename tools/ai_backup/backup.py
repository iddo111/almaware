#!/usr/bin/env python3
"""
Smart-AI-Backup — permanent auto-backup for ALL of Iddo's AI training progress.
In loving memory of Alma — face-rec data must NEVER be lost.

Triple destination per pass:
  A. Local mirror      -> N:\\backups\\ai-progress\\<YYYY-MM-DD>  (robocopy /MIR, 7-day retention)
                          (was E:\\backups\\... before 2026-05-18 - moved to N: after E: NTFS recovery)
  B. Git snapshot      -> D:\\CLAUDE\\_ai_backups_git\\            (commits every run; pushes if remote configured)
  C. rclone -> Google  -> gdrive:claude-ai-backups/                (only if rclone + remote already configured)

Hard constraints:
  * Singleton via msvcrt.locking (no overlapping runs).
  * Excludes venvs, __pycache__, node_modules, *.log, .env*, *token*, *secret*, transient pending dirs.
  * robocopy /IPG:50 (inter-packet-gap) — does NOT saturate disk.
  * Git skips files > 10 MB (LFS not assumed available).
  * rclone --max-size 100M --bwlimit 8M (don't eat Drive quota or upload).
  * pythonw-friendly: no console output, all status to logs.

Status JSON written to last_status.json after each run for the system_watchdog.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

# ---------- Configuration ----------
HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / "backup.log"
LOG_MAX_BYTES = 50 * 1024 * 1024  # rotate at 50 MB
STATUS_FILE = HERE / "last_status.json"
LOCK_FILE = HERE / "backup.lock"
MANIFEST_FILE = HERE / "manifest.json"

LOCAL_MIRROR_ROOT = Path("N:/backups/ai-progress")
LOCAL_RETENTION_DAYS = 7

GIT_REPO_DIR = Path("D:/CLAUDE/_ai_backups_git")
GIT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB ceiling for git-tracked artifacts
GIT_REMOTE_NAME = "origin"
# Iddo's GitHub user is iddo111 (per memory hub). DO NOT auto-create the remote;
# the user must run: git remote add origin https://github.com/iddo111/<repo>.git
GITHUB_USER_HINT = "iddo111"

RCLONE_REMOTE = "gdrive:claude-ai-backups"
RCLONE_MAX_SIZE = "100M"
RCLONE_BWLIMIT = "8M"
RCLONE_TRANSFERS = "4"

# Robocopy throttle — IPG (inter-packet-gap) ms; keeps I/O light for live trainers.
ROBOCOPY_IPG = "50"

# What to back up. Each entry: (label, source_path, kind)
#   kind = "mirror"  -> goes into local mirror (full robocopy)
#   kind = "git"     -> also goes into git repo (small files only)
TARGETS: list[tuple[str, str, list[str]]] = [
    # (label, abs_src_path, destinations)
    ("alma-face-refs",       r"D:\CLAUDE\alma-memorial\face-refs",            ["mirror"]),
    ("alma-facerec-out",     r"D:\CLAUDE\alma-memorial\facerec_out",          ["mirror", "git"]),  # index.npz + meta tiny
    ("alma-tools",           r"D:\CLAUDE\alma-memorial\tools",                ["mirror", "git"]),
    ("simpletracker-models", r"D:\CLAUDE\simpletracker-training\models\v1",   ["mirror"]),
    ("simpletracker-runs",   r"D:\CLAUDE\simpletracker-training\runs",        ["mirror"]),
    ("simpletracker-scripts",r"D:\CLAUDE\simpletracker-training\scripts",     ["mirror", "git"]),
    ("simpletracker-root",   r"D:\CLAUDE\simpletracker-training",             ["git"]),  # top-level configs only (filtered)
    ("maimon-light",         r"D:\CLAUDE\projects\maimon-light",              ["mirror", "git"]),
    ("kabbalah-ai",          r"D:\CLAUDE\apps\kabbalah-ai",                   ["mirror", "git"]),
    ("agriculture-chapters", r"D:\CLAUDE\agriculture-encyclopedia-v2\chapters",["mirror", "git"]),
    ("agriculture-scripts",  r"D:\CLAUDE\agriculture-encyclopedia-v2\scripts",["mirror", "git"]),
    ("agriculture-pdf",      r"D:\CLAUDE\pdf\Future_of_Agriculture_Vol_II.pdf",["mirror"]),  # large PDF -> mirror only
]

# Robocopy /XD (exclude dirs) and /XF (exclude files) — DO NOT touch venvs / caches / secrets.
EXCLUDE_DIRS = [
    "__pycache__", "node_modules",
    ".venv", ".venv-train", "venv", "env",
    "pending",          # transient face-refs/pending/
    ".git", ".idea", ".vscode",
    "logs",             # transient logs subdir
]
EXCLUDE_FILES_GLOB = [
    "*.log",
    "*.tmp",
    ".env", ".env.*",
    "*token*", "*secret*", "*credentials*",
    "*.lock", "*.pid",
    "tmp*.png",         # facerec tmp pngs
]
# Git ignore (subset that ABSOLUTELY must never be committed)
GIT_FORBIDDEN_NAME_PARTS = ("token", "secret", "credentials", ".env")

# ---------- Logging ----------
def _rotate_log():
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            backup = LOG_FILE.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            LOG_FILE.rename(backup)
    except Exception:
        pass

def log(msg: str):
    _rotate_log()
    ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

# ---------- Singleton lock (Windows-friendly) ----------
class _Lock:
    def __init__(self, path: Path):
        self.path = path
        self.fh = None
    def __enter__(self):
        try:
            self.fh = open(self.path, "wb")
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            try:
                if self.fh: self.fh.close()
            except Exception:
                pass
            self.fh = None
            return False
    def __exit__(self, *exc):
        try:
            if self.fh:
                if os.name == "nt":
                    import msvcrt
                    try:
                        self.fh.seek(0)
                        msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
                    except Exception:
                        pass
                self.fh.close()
        except Exception:
            pass

# ---------- Helpers ----------
def now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")

def today_dir_name() -> str:
    return _dt.date.today().isoformat()  # YYYY-MM-DD

def dir_size_bytes(path: Path) -> int:
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            # prune excluded dirs in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in files:
                fp = Path(root) / fn
                try:
                    total += fp.stat().st_size
                except OSError:
                    pass
    except Exception:
        pass
    return total

def file_count(path: Path) -> int:
    n = 0
    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            n += len(files)
    except Exception:
        pass
    return n

def sha256_small(path: Path, max_bytes: int = 1 * 1024 * 1024) -> str | None:
    """Hash files <= 1 MB (manifest fingerprint for tiny configs)."""
    try:
        if path.is_file() and path.stat().st_size <= max_bytes:
            h = hashlib.sha256()
            with path.open("rb") as f:
                h.update(f.read())
            return h.hexdigest()
    except Exception:
        return None
    return None

def fmt_bytes(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}TB"

# ---------- Manifest ----------
def build_manifest() -> dict:
    """Per-target file count + total size + sha256 of small files (samples)."""
    out = {"generated": now_iso(), "targets": {}}
    for label, src, _dests in TARGETS:
        sp = Path(src)
        entry = {"path": str(sp), "exists": sp.exists(), "kind": "file" if sp.is_file() else "dir"}
        if not sp.exists():
            out["targets"][label] = entry
            continue
        if sp.is_file():
            entry["size_bytes"] = sp.stat().st_size
            entry["size_human"] = fmt_bytes(entry["size_bytes"])
            entry["sha256"] = sha256_small(sp)
        else:
            entry["size_bytes"] = dir_size_bytes(sp)
            entry["size_human"] = fmt_bytes(entry["size_bytes"])
            entry["file_count"] = file_count(sp)
        out["targets"][label] = entry
    try:
        MANIFEST_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"manifest write failed: {e}")
    return out

# ---------- A. Local mirror (robocopy /MIR) ----------
def robocopy_one(src: Path, dst: Path) -> tuple[int, str]:
    """Returns (robocopy_exit_code, brief_summary). Codes 0-7 = success-ish."""
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        # /COPY:DAT preserves attrs + timestamps; single file
        cmd = [
            "robocopy", str(src.parent), str(dst), src.name,
            "/COPY:DAT", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
            f"/IPG:{ROBOCOPY_IPG}",
        ]
    else:
        cmd = [
            "robocopy", str(src), str(dst),
            "/MIR", "/COPY:DAT", "/R:1", "/W:1",
            "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
            f"/IPG:{ROBOCOPY_IPG}",
        ]
        for d in EXCLUDE_DIRS:
            cmd += ["/XD", d]
        for g in EXCLUDE_FILES_GLOB:
            cmd += ["/XF", g]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 30,
                            creationflags=0x08000000 if os.name == "nt" else 0)  # CREATE_NO_WINDOW
        return cp.returncode, (cp.stdout + cp.stderr)[-400:]
    except Exception as e:
        return 99, f"exception: {e}"

def run_local_mirror(manifest: dict) -> dict:
    today = today_dir_name()
    snap_root = LOCAL_MIRROR_ROOT / today
    snap_root.mkdir(parents=True, exist_ok=True)
    summary = {"snapshot_dir": str(snap_root), "items": {}, "total_bytes": 0, "errors": []}
    for label, src, dests in TARGETS:
        if "mirror" not in dests:
            continue
        sp = Path(src)
        if not sp.exists():
            summary["items"][label] = {"status": "skip", "reason": "source missing"}
            continue
        dp = snap_root / label
        rc, tail = robocopy_one(sp, dp)
        if rc <= 7:
            sz = dir_size_bytes(dp) if dp.is_dir() else (dp.stat().st_size if dp.exists() else 0)
            fc = file_count(dp) if dp.is_dir() else (1 if dp.exists() else 0)
            summary["items"][label] = {"status": "ok", "rc": rc, "bytes": sz, "size": fmt_bytes(sz), "files": fc}
            summary["total_bytes"] += sz
        else:
            summary["items"][label] = {"status": "fail", "rc": rc, "tail": tail}
            summary["errors"].append(f"{label}: robocopy rc={rc}")
        log(f"mirror {label}: rc={rc}")
    summary["total_size"] = fmt_bytes(summary["total_bytes"])
    # write a tiny snapshot README
    try:
        readme = snap_root / "_SNAPSHOT_INFO.txt"
        readme.write_text(
            f"Snapshot: {today}\nGenerated: {now_iso()}\nItems: {len(summary['items'])}\n"
            f"Total: {summary['total_size']}\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    # Prune older than retention
    pruned = []
    try:
        cutoff = _dt.date.today() - _dt.timedelta(days=LOCAL_RETENTION_DAYS)
        for child in LOCAL_MIRROR_ROOT.iterdir():
            if not child.is_dir():
                continue
            try:
                d = _dt.date.fromisoformat(child.name)
            except ValueError:
                continue
            if d < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                pruned.append(child.name)
    except Exception as e:
        summary["errors"].append(f"prune: {e}")
    summary["pruned"] = pruned
    return summary

# ---------- B. Git ----------
def _git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        cp = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True, timeout=300,
                            creationflags=0x08000000 if os.name == "nt" else 0)
        return cp.returncode, cp.stdout, cp.stderr
    except Exception as e:
        return 99, "", str(e)

def ensure_git_repo() -> bool:
    GIT_REPO_DIR.mkdir(parents=True, exist_ok=True)
    if not (GIT_REPO_DIR / ".git").exists():
        rc, _, err = _git(["init", "-b", "main"], GIT_REPO_DIR)
        if rc != 0:
            log(f"git init failed: {err}")
            return False
        # Local identity if global config missing
        _git(["config", "user.email", "smart-ai-backup@local"], GIT_REPO_DIR)
        _git(["config", "user.name", "Smart-AI-Backup"], GIT_REPO_DIR)
        # Initial .gitignore — secrets must NEVER be committed
        gitignore = GIT_REPO_DIR / ".gitignore"
        gitignore.write_text(
            "# AUTO-GENERATED — do not edit\n"
            "*.log\n*.tmp\n*.lock\n*.pid\n"
            ".env\n.env.*\n*token*\n*secret*\n*credentials*\n"
            "__pycache__/\n.venv/\n.venv-train/\nvenv/\nenv/\nnode_modules/\n"
            "*.pt\n*.ckpt\n*.safetensors\n*.bin\n",
            encoding="utf-8",
        )
        # Initial README + first commit so HEAD exists
        (GIT_REPO_DIR / "README.md").write_text(
            "# Smart-AI-Backup git snapshot\n\n"
            "Auto-managed by D:/CLAUDE/tools/ai_backup/backup.py — do not edit by hand.\n"
            "Files > 10 MB are EXCLUDED from git (they live in the local mirror snapshot only).\n\n"
            f"GitHub user hint: {GITHUB_USER_HINT}\n"
            f"ADD GITHUB REMOTE WITH:\n"
            f"  git remote add origin https://github.com/{GITHUB_USER_HINT}/claude-ai-backups.git\n",
            encoding="utf-8",
        )
        _git(["add", ".gitignore", "README.md"], GIT_REPO_DIR)
        _git(["commit", "-m", "init Smart-AI-Backup"], GIT_REPO_DIR)
        log("git repo initialized")
    return True

def _is_git_safe(p: Path) -> bool:
    n = p.name.lower()
    if any(part in n for part in GIT_FORBIDDEN_NAME_PARTS):
        return False
    try:
        if p.stat().st_size > GIT_MAX_FILE_BYTES:
            return False
    except OSError:
        return False
    # Hard exclude binary model artifacts that snuck through size
    if p.suffix.lower() in (".pt", ".ckpt", ".safetensors", ".bin", ".onnx", ".tflite", ".npz"):
        # Exception: TINY .npz like alma index.npz (< 10 MB) IS allowed
        if p.suffix.lower() == ".npz" and p.stat().st_size <= GIT_MAX_FILE_BYTES:
            return True
        return False
    return True

def stage_target_for_git(label: str, src: Path, repo_dir: Path) -> tuple[int, int]:
    """Mirror small/safe files from src into repo_dir/<label>/ — returns (files_added, bytes)."""
    dest = repo_dir / label
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    added = 0
    total = 0
    if src.is_file():
        if _is_git_safe(src):
            shutil.copy2(src, dest / src.name)
            added += 1
            total += src.stat().st_size
        return added, total
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        rel = Path(root).relative_to(src)
        for fn in files:
            sp = Path(root) / fn
            # skip glob-excluded
            from fnmatch import fnmatch
            if any(fnmatch(fn, g) for g in EXCLUDE_FILES_GLOB):
                continue
            if not _is_git_safe(sp):
                continue
            dp = dest / rel / fn
            dp.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(sp, dp)
                added += 1
                total += sp.stat().st_size
            except Exception:
                pass
    return added, total

def run_git(manifest: dict) -> dict:
    summary = {"repo": str(GIT_REPO_DIR), "items": {}, "total_files": 0, "total_bytes": 0,
               "commit": None, "push": None, "errors": []}
    if not ensure_git_repo():
        summary["errors"].append("git init failed")
        return summary
    for label, src, dests in TARGETS:
        if "git" not in dests:
            continue
        sp = Path(src)
        if not sp.exists():
            summary["items"][label] = {"status": "skip", "reason": "source missing"}
            continue
        n, b = stage_target_for_git(label, sp, GIT_REPO_DIR)
        summary["items"][label] = {"files": n, "bytes": b, "size": fmt_bytes(b)}
        summary["total_files"] += n
        summary["total_bytes"] += b
    summary["total_size"] = fmt_bytes(summary["total_bytes"])

    # Stage everything (the staged tree IS the repo) and commit
    _git(["add", "-A"], GIT_REPO_DIR)
    # Quick fingerprint for the commit message
    fp_parts = []
    for label, src, dests in TARGETS:
        if "git" not in dests:
            continue
        info = manifest.get("targets", {}).get(label, {})
        if info.get("exists"):
            fp_parts.append(f"{label}={info.get('file_count', 1)}f/{info.get('size_human', '?')}")
    fingerprint = " ".join(fp_parts[:6])
    msg = f"auto: {now_iso()} {fingerprint}"
    rc, out, err = _git(["commit", "-m", msg], GIT_REPO_DIR)
    if rc == 0:
        summary["commit"] = msg
    else:
        # rc=1 + "nothing to commit" is normal between identical passes
        if "nothing to commit" in (out + err).lower():
            summary["commit"] = "no-change"
        else:
            summary["errors"].append(f"commit: {err.strip() or out.strip()}")
    # Push if remote exists
    rc2, rout, _ = _git(["remote"], GIT_REPO_DIR)
    if rc2 == 0 and GIT_REMOTE_NAME in rout.split():
        rc3, _, perr = _git(["push", GIT_REMOTE_NAME, "main"], GIT_REPO_DIR)
        summary["push"] = "ok" if rc3 == 0 else f"fail: {perr.strip()[:200]}"
    else:
        summary["push"] = (
            f"DEFERRED: no remote configured. RUN: "
            f"cd {GIT_REPO_DIR} && git remote add origin "
            f"https://github.com/{GITHUB_USER_HINT}/claude-ai-backups.git && git push -u origin main"
        )
    return summary

# ---------- C. rclone -> Google Drive ----------
def find_rclone() -> str | None:
    # PATH lookup first
    p = shutil.which("rclone") or shutil.which("rclone.exe")
    if p:
        return p
    # Common install locations
    for cand in (
        r"C:\Program Files\rclone\rclone.exe",
        r"C:\rclone\rclone.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\rclone\rclone.exe"),
        os.path.expandvars(r"%USERPROFILE%\scoop\apps\rclone\current\rclone.exe"),
        os.path.expandvars(r"%USERPROFILE%\AppData\Local\Microsoft\WinGet\Links\rclone.exe"),
    ):
        if os.path.isfile(cand):
            return cand
    return None

def run_rclone() -> dict:
    summary = {"remote": RCLONE_REMOTE, "status": None, "errors": []}
    rcl = find_rclone()
    if not rcl:
        summary["status"] = (
            "DEFERRED: rclone not installed. INSTALL: winget install Rclone.Rclone "
            "(then run: rclone config -> n -> name=gdrive -> drive -> follow OAuth in browser)"
        )
        return summary
    # Has the gdrive remote been configured?
    try:
        cp = subprocess.run([rcl, "listremotes"], capture_output=True, text=True, timeout=20,
                            creationflags=0x08000000 if os.name == "nt" else 0)
        remotes = cp.stdout.splitlines()
    except Exception as e:
        summary["status"] = f"DEFERRED: rclone listremotes failed: {e}"
        return summary
    target_remote = RCLONE_REMOTE.split(":", 1)[0] + ":"
    if target_remote not in remotes:
        summary["status"] = (
            f"DEFERRED: rclone remote '{target_remote}' not configured. RUN: rclone config "
            f"(create new -> drive -> name={target_remote.rstrip(':')})"
        )
        return summary
    # Sync the git repo (small files only) to Drive — much smaller than the full mirror
    cmd = [
        rcl, "sync", str(GIT_REPO_DIR), RCLONE_REMOTE,
        "--transfers", RCLONE_TRANSFERS,
        "--max-size", RCLONE_MAX_SIZE,
        "--bwlimit", RCLONE_BWLIMIT,
        "--exclude", ".git/**",
        "--exclude", "*.log",
        "--exclude", "*token*",
        "--exclude", "*secret*",
        "--exclude", ".env*",
        "--retries", "2",
        "--low-level-retries", "3",
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 25,
                            creationflags=0x08000000 if os.name == "nt" else 0)
        if cp.returncode == 0:
            summary["status"] = "ok"
            summary["bytes_transferred"] = (cp.stderr.strip().splitlines() or [""])[-1][-200:]
        else:
            summary["status"] = f"fail rc={cp.returncode}"
            summary["errors"].append(cp.stderr.strip()[-400:])
    except Exception as e:
        summary["status"] = f"exception: {e}"
        summary["errors"].append(str(e))
    return summary

# ---------- Status ----------
def write_status(payload: dict):
    try:
        STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"status write failed: {e}")

# ---------- Main pass ----------
def run_pass() -> dict:
    started = now_iso()
    log("=== pass start ===")
    manifest = build_manifest()
    result = {
        "started": started,
        "finished": None,
        "manifest_summary": {
            label: {"size": info.get("size_human"), "files": info.get("file_count")}
            for label, info in manifest["targets"].items()
        },
        "local_mirror": None,
        "git": None,
        "rclone": None,
        "errors": [],
    }
    try:
        result["local_mirror"] = run_local_mirror(manifest)
    except Exception as e:
        result["errors"].append(f"mirror: {e}\n{traceback.format_exc()[-400:]}")
        log(f"mirror exception: {e}")
    try:
        result["git"] = run_git(manifest)
    except Exception as e:
        result["errors"].append(f"git: {e}\n{traceback.format_exc()[-400:]}")
        log(f"git exception: {e}")
    try:
        result["rclone"] = run_rclone()
    except Exception as e:
        result["errors"].append(f"rclone: {e}\n{traceback.format_exc()[-400:]}")
        log(f"rclone exception: {e}")
    result["finished"] = now_iso()
    write_status(result)
    log(f"=== pass done: mirror={bool(result['local_mirror'])} git={bool(result['git'])} rclone={result.get('rclone',{}).get('status')!r} ===")
    return result

def main():
    with _Lock(LOCK_FILE) as got:
        if not got:
            log("another instance holds the lock — exiting")
            return
        try:
            run_pass()
        except Exception as e:
            log(f"FATAL: {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    main()

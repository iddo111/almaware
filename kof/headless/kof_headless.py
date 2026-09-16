#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KOF headless -- the non-stop ping-pong coder that builds KESHEV 7.

Iddo, 2026-09-15 03:19-03:22: "write the KOF ping-pong coder and put it with
Chat non-stop to do the mic from scratch ... that will be the test of the KOF
coder."

Source: the rally idea, the RUN batch and the verdict parsing come from
D:/CLAUDE/kof/kof.py (kinfer lines 62-73, parse_step lines 76-90, rally lines
110-190). kof.py is a Windows/tkinter tool, so that pure logic is rewritten
here for headless Linux + bash; nothing from kof.py is imported.

Enforced in THIS runner, in code, never by trusting the prompt:
  * brain = gpt-oss-120b through the router :8010 (fallback eran2:8000)
  * NON-STOP: ASK -> QUESTIONS.md + the brain answers itself and goes on;
    DONE -> the hidden eval runs, the score is fed back, the loop goes on;
    DONE-ACCEPTED is recorded only when the eval passes the bar
  * every command: guard (deny rules) -> resource floors -> transient
    systemd --user scope (MemoryMax, MemorySwapMax=0, CPUWeight, CPUQuota,
    TasksMax) -> nice 19 -> ionice -> timeout -> bash, cwd = the sandbox
  * import wall: site/sitecustomize.py allows only stdlib + numpy + torch +
    scipy + the sandbox's own modules for every python a command starts
  * eval seal: ~/keshev7-eval and the runner code are fingerprinted (mode,
    size, mtime, ctime, sha256) and checked after every command; a change
    HALTS the rally until Iddo reseals
  * AUTOSAVE: rally state saved atomically (tmp + fsync + rename) after every
    step and resumed on start, round counter included
  * STOP file (~/keshev7/STOP) or SIGTERM halts at the next step and kills
    the running command's scope

What it is NOT -- said plainly: not kernel isolation. eran1 blocks
unprivileged user namespaces (AppArmor apparmor_restrict_unprivileged_userns=1,
measured 2026-09-15) and ignores IPAddressDeny in user scopes, so there is no
private mount / network / pid namespace. The guard stops shortcuts and
accidents; a determined adversary running as the same unix user could get
past text rules. The kernel-grade fix is a dedicated unix user for the rally
(needs Iddo + sudo).

CLI:  run | steps N | check-cmd "<cmd>" | seal | reseal | verify-seal |
      status | eval-now | brain-ping | render-goal
"""
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import urllib.request

HOME = os.path.expanduser("~")
RUNNER_DIR = os.path.dirname(os.path.abspath(__file__))
GIB = 1024 ** 3

DEFAULTS = {
    "sandbox": "~/keshev7",
    "eval_dir": "~/keshev7-eval",
    "runner_dir": None,
    "state_dir": None,
    "site_dir": None,
    "goal_template": None,
    "brain_urls": ["http://<tailnet-ip>:8010/v1/chat/completions",
                   "http://<tailnet-ip>:8000/v1/chat/completions"],
    "router_base": "http://<tailnet-ip>:8010",
    "model": "gpt-oss-120b",
    "reasoning_effort": "low",
    "max_tokens": 4000,
    "temperature": 0.3,
    "brain_timeout_s": 600,
    "ctx_budget_tokens": 40000,
    "chars_per_token": 2.8,
    "keep_last_turns": 16,
    "max_runs_per_round": 5,
    "max_writes_per_round": 8,
    "cmd_timeout_s": 3600,
    "mem_max": "16G",
    "cpu_weight": 20,
    "cpu_quota": "800%",
    "tasks_max": 1024,
    "cpu_threads": 8,
    "gpu": "off",
    "mem_floor_gib": 32.0,
    "mem_hard_floor_gib": 16.0,
    "mem_wait_max_s": 600,
    "mem_wait_poll_s": 15,
    "sandbox_disk_cap_gib": 60.0,
    "host_disk_free_floor_gib": 200.0,
    "monitor_every_s": 10.0,
    "kill_grace_s": 15.0,
    "out_keep_chars": 64000,
    "feedback_per_cmd_chars": 1800,
    "feedback_round_chars": 6000,
    "eval_bar_cer": 0.25,
    "eval_max_fail_frac": 0.05,
    "eval_clip_timeout_s": 60,
    "eval_workers": 3,
    "eval_max_s": 2700,
    "eval_every_rounds": 30,
    "progress_every_rounds": 10,
    "ramchat_every_s": 3600,
    "ramchat_url": "",
    "ramchat_token_file": "",
    "ramchat_who": "kof-coder",
    "brain_backoff_s": [30, 60, 120, 300],
    "min_round_gap_s": 1.0,
}

_PATH_KEYS = ("sandbox", "eval_dir", "runner_dir", "state_dir", "site_dir",
              "goal_template", "ramchat_token_file")


def load_config(path=None, overrides=None):
    cfg = dict(DEFAULTS)
    path = path or os.path.join(RUNNER_DIR, "config.json")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    if overrides:
        cfg.update(overrides)
    cfg["runner_dir"] = cfg.get("runner_dir") or RUNNER_DIR
    for k in _PATH_KEYS:
        if cfg.get(k):
            cfg[k] = os.path.realpath(os.path.expanduser(cfg[k]))
    cfg["state_dir"] = cfg.get("state_dir") or os.path.join(cfg["runner_dir"], "state")
    cfg["site_dir"] = cfg.get("site_dir") or os.path.join(cfg["runner_dir"], "site")
    cfg["goal_template"] = cfg.get("goal_template") or os.path.join(cfg["runner_dir"], "GOAL.md")
    return cfg


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def atomic_write_text(path, text, mode=None):
    """AUTOSAVE LAW: temp file in the same dir, fsync, rename."""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = "%s.tmp.%d.%s" % (path, os.getpid(), secrets.token_hex(3))
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def inside(p, base):
    base = base.rstrip("/") or "/"
    return p == base or p.startswith(base + "/")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================================
# Reply protocol  (extends kof.py parse_step, lines 76-90)
# ============================================================================
SYSTEM = """You are KOF, a non-stop coder on a Linux DGX (bash). You work in a ping-pong loop with a runner: you reply, the runner executes, you read the output, forever. No human reads your replies in real time.

Reply format -- one reply per round, batch your work, no prose outside these lines:
RUN: <one-line bash command>        (up to 5 RUN lines; they run in order)
RUN:
```bash
<a multi-line bash script>
```
WRITE: <relative/path/in/the/sandbox>
```
<the entire file content>
```
                                    (up to 8 WRITE blocks; the runner writes the file itself -- prefer WRITE over heredocs)
There is NO apply_patch / patch tool on this machine: to create or change a file, WRITE the whole file.
ASK: <question>    no human will answer: it is logged and you decide yourself
DONE: <summary>    you believe the bar is met: the hidden eval runs and you get the score; the loop continues either way

Rules the runner enforces in code (a refused command is NOT run and you are told why): the working directory is the sandbox; relative paths only; no '..'; no absolute paths outside the sandbox; no network; no package installs; no sudo, no systemctl changes. No command substitution `$(...)` or backticks and no `perl`/`awk`/`make`/`node` -- run a command and read its output in the NEXT round, use `{1..N}` for ranges, and write logic in Python files (WRITE) not shell. `kill` only `$!` (a background job THIS command line started) -- never by PID, variable, or `$(pgrep ...)`; never touch a process you did not start. No pretrained models and no speech libraries; python imports limited to stdlib, numpy, torch, scipy and your own files, and your python may read/write only inside the sandbox. Each command has a memory cap and a timeout, so trainers must checkpoint and resume.
Read every output, fix errors, keep going."""

_PREFIX = r"^\s*(?:[-*]\s*)?(?:\*\*)?"
_RUN_RE = re.compile(_PREFIX + r"RUN(?:\*\*)?\s*:\s*(.*?)\s*$")
_WRITE_RE = re.compile(_PREFIX + r"WRITE(?:\*\*)?\s*:\s*(.+?)\s*$")
_VERDICT_RE = re.compile(_PREFIX + r"(ASK|DONE)(?:\*\*)?\s*:\s*(.*)$")

# gpt-oss is trained on an `apply_patch` tool that does not exist on this host. Run as
# bash it only prints "command not found" (rc=127) and no file is written: the live
# rally burned rounds 146-165 on it (2026-09-15), then ran trainers that did not exist.
# Such a RUN is not executed (never a loosening - nothing runs); the brain is told the
# WRITE form instead. Matches `apply_patch` in command position, or a patch envelope.
_PATCH_RE = re.compile(
    r"(?:^|[;&|({]|\b(?:then|do|else)\b)\s*(?:\S*/)?apply_patch(?![\w.])"
    r"|^\s*\*\*\* (?:Begin|End) Patch\b", re.M)
PATCH_NOTE = ("NO-SUCH-TOOL [apply_patch]: there is no apply_patch (or patch) tool on this machine -- "
              "bash only answers 'command not found' and no file is written. To create or change a "
              "file reply WRITE: <relative/path> and then the ENTIRE new file in a ``` fence.")


def _read_fence(lines, j):
    """lines[j] starts with ``` -> (body_lines, index_after_close) or (None, len)."""
    k = j + 1
    body = []
    while k < len(lines) and lines[k].strip() != "```":
        body.append(lines[k])
        k += 1
    if k >= len(lines):
        return None, len(lines)
    return body, k + 1


def parse_reply(text, max_runs=5, max_writes=8):
    """-> {"actions": [("RUN", cmd) | ("WRITE", path, content)],
           "notes": [str], "ask": str|None, "done": str|None}"""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    actions, notes, free = [], [], []
    runs = writes = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _WRITE_RE.match(line)
        if m:
            path = m.group(1).strip().strip("`'\"")
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip().startswith("```"):
                body, nxt = _read_fence(lines, j)
                if body is None:
                    notes.append("WRITE %s: no closing ``` line - file NOT written" % path)
                    i = nxt
                    continue
                if writes < max_writes:
                    actions.append(("WRITE", path, "\n".join(body) + "\n"))
                    writes += 1
                else:
                    notes.append("WRITE %s ignored: max %d WRITE blocks per reply" % (path, max_writes))
                i = nxt
                continue
            notes.append("WRITE %s: must be followed by a ``` fenced block - file NOT written" % path)
            i += 1
            continue
        m = _RUN_RE.match(line)
        if m:
            cmd = m.group(1)
            if cmd in ("|", ">", "|-", ">-", "|+", ">+"):
                # YAML-style block marker (`RUN: |` then a fence): the brain means the fence.
                # Run as-is it was a bare `|` -> rc=2 every round and the script never ran.
                cmd = ""
            if cmd == "" or cmd.startswith("```"):
                j = i if cmd.startswith("```") else i + 1
                if cmd == "":
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                if j < len(lines) and (cmd.startswith("```") or lines[j].strip().startswith("```")):
                    fence_lines = lines if j != i else [""] + lines[i + 1:]
                    if j == i:
                        body, nxt = _read_fence(lines, i)
                    else:
                        body, nxt = _read_fence(lines, j)
                    if body is None:
                        notes.append("RUN block: no closing ``` line - NOT run")
                        i = nxt
                        continue
                    cmd = "\n".join(body)
                    i = nxt
                else:
                    notes.append("RUN with no command - ignored")
                    i += 1
                    continue
            else:
                i += 1
                if len(cmd) >= 2 and cmd[0] == "`" and cmd[-1] == "`":
                    cmd = cmd.strip("`").strip()
            if not cmd.strip():
                continue
            if runs < max_runs:
                actions.append(("RUN", cmd))
                runs += 1
            else:
                notes.append("RUN ignored (max %d per reply): %s" % (max_runs, cmd[:120]))
            continue
        free.append(line)
        i += 1
    ask = done = None
    for idx, line in enumerate(free):
        m = _VERDICT_RE.match(line)
        if m:
            body = "\n".join([m.group(2)] + free[idx + 1:]).strip()[:2000]
            if m.group(1) == "ASK" and ask is None:
                ask = body or "(empty question)"
            if m.group(1) == "DONE" and done is None:
                done = body or "(no summary)"
    return {"actions": actions, "notes": notes, "ask": ask, "done": done}


def elide_write_bodies(text):
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        m = _WRITE_RE.match(lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip().startswith("```"):
                body, nxt = _read_fence(lines, j)
                if body is not None:
                    out.append(lines[i])
                    out.append("```")
                    out.append("[%d lines written to %s -- cat it if you need it]"
                               % (len(body), m.group(1).strip()))
                    out.append("```")
                    i = nxt
                    continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


# ============================================================================
# Guard -- deny rules enforced before anything runs
# ============================================================================
class ShellParseError(Exception):
    pass


_I = re.I
ANYWHERE_RULES = [
    ("asr-code", re.compile(
        r"whisper|ctranslate2|\bvosk\b|kaldi|espnet|speechbrain|wav2vec|wav2letter|"
        r"\bnemo\b|nemo_toolkit|\bhubert\b|silero|deepspeech|pocketsphinx|\bsphinx|"
        r"librosa|python_speech_features|\blhotse\b|icefall|kenlm|pyctcdecode|funasr|"
        r"paraformer|pyannote|systran|mobiuslabs|mms-tts|\bencodec\b|seamless_?m4t|"
        r"parakeet|torchaudio|dictalm|dicta-il", _I),
     "speech/ASR code or model names are forbidden - KESHEV 7 is written from scratch"),
    ("pretrained", re.compile(
        r"hugging\s*face|\bhf_hub|hf_transfer|snapshot_download|from_pretrained|"
        r"torch\.hub|pretrained\s*=\s*true|models--|\.cache/(huggingface|torch|whisper)|"
        r"load_state_dict_from_url|model_zoo|\bgguf\b|\bonnx", _I),
     "pretrained models and model hubs are forbidden - train from random init"),
    ("forbidden-import", re.compile(
        r"(?<![\w.])(?:import|from)\s+(transformers|tokenizers|sentencepiece|tiktoken|"
        r"torchvision|datasets|accelerate|safetensors|fastsafetensors|openai|openai_harmony|"
        r"tensorflow|keras|jax|flax|timm|k2|jiwer|editdistance|Levenshtein|rapidfuzz|"
        r"soundfile|pydub|webrtcvad|sounddevice|pyaudio|audiomentations|requests|urllib3|"
        r"httpx|aiohttp)\b|(?:__import__|import_module)\(\s*['\"](transformers|tokenizers|"
        r"sentencepiece|tiktoken|datasets|safetensors|openai|requests)", re.M),
     "only the stdlib, numpy, torch, scipy and your own files may be imported"),
    ("pkg-install", re.compile(
        r"\bpip[\d.]*\s+(install|download|wheel|uninstall)\b|-m\s+(pip|ensurepip|venv)\b|"
        r"\bensurepip\b|easy_install|\bconda\s+(install|create|update|env)\b|\bmamba\s|"
        r"\bmicromamba\b|\buv\s+(pip|add|sync|tool|run|venv)\b|\bpipx\b|"
        r"\bnpm\s+(i|install|ci)\b|\bnpx\s|\byarn\s+add\b|\bpnpm\s|\bcargo\s+install\b|"
        r"\bgo\s+(get|install)\s|\bgem\s+install\b|\bapt(-get)?\s+|\baptitude\b|\bdpkg\b|"
        r"\bsnap\s+install\b|\bflatpak\b|\bbrew\s+install\b", _I),
     "no package installs or downloads"),
    ("git-remote", re.compile(
        r"\bgit\s+(?:-C\s+\S+\s+)?(clone|pull|fetch|submodule|remote|push|lfs)\b|git@", _I),
     "no git clone / pull / fetch / submodule / remote"),
    ("privilege", re.compile(
        r"\bsudo\b|\bdoas\b|\bpkexec\b|\bsetcap\b|\bchattr\b|\bsu\s+-", _I),
     "no privilege escalation"),
    ("power", re.compile(
        r"\breboot\b|(?<![\w.])shutdown\b|\bpoweroff\b|\btelinit\b|\binit\s+[06]\b", _I),
     "no reboot / shutdown"),
    ("systemd", re.compile(
        r"\bsystemd-run\b|\bbusctl\b|\bdbus-send\b|\bgdbus\b|\bloginctl\b|/run/user|"
        r"DBUS_SESSION_BUS|XDG_RUNTIME_DIR|\bcrontab\b|\bat\s+now\b", _I),
     "no systemd / dbus / cron manipulation"),
    ("systemctl", re.compile(
        r"\bsystemctl\b(?!\s+--user\s+(status|list-units|list-timers|list-unit-files|show|"
        r"is-active|is-failed)\b)", _I),
     "systemctl is allowed only as: systemctl --user status|list-units|show|is-active"),
    ("kill-others", re.compile(
        r"\bpkill\b|\bkillall\b|\bxkill\b|(?<![\w])os\.kill(pg)?\s*\(|signal\.pthread_kill", _I),
     "no pkill / killall / os.kill - only kill what you started in the same command ($!)"),
    ("container", re.compile(
        r"\bdocker\b|\bpodman\b|\bnerdctl\b|\bkubectl\b|\blxc-|\bchroot\b|\bnsenter\b|"
        r"\bunshare\b|\bbwrap\b|\bfirejail\b", _I),
     "no containers or namespaces"),
    ("net-tool", re.compile(
        r"\bssh\b|\bscp\b|\brsync\b|\bsftp\b|\bsshpass\b|\bnc\s+-|\bncat\b|\bnetcat\b|"
        r"\bsocat\b|\btelnet\b|\bftp\b|paramiko|ftplib|smtplib|http\.server|socketserver|"
        r"serve_forever|\bnmap\b|\btailscale\b|/dev/tcp|/dev/udp", _I),
     "no network tools, servers or remote copies"),
    ("net-code", re.compile(
        r"urllib\.request|urlopen|\brequests\.(get|post|put|Session)|http\.client|"
        r"socket\.socket|create_connection|\baiohttp\b|\bhttpx\b|websocket|"
        r"\.bind\s*\(\s*\(", _I),
     "your code gets no network"),
    ("net-native", re.compile(
        r"\bAF_INET6?\b|\bPF_INET6?\b|\bSOCK_STREAM\b|\bSOCK_DGRAM\b|\bSOCK_RAW\b|"
        r"sys/socket\.h|netinet/in\.h|arpa/inet\.h|\bnetdb\.h|\bsockaddr_in6?\b|"
        r"\bgetaddrinfo\b|\bgethostbyname\b|\binet_(pton|aton|addr|ntoa)\b|"
        r"IO::Socket|use\s+Socket|\bSocket::|/inet/(tcp|udp)/", _I),
     "no network from native/compiled code either - KESHEV 7 has no network"),
    ("eval-ref", re.compile(r"keshev7[-_]eval|keshev7[-_]kof", _I),
     "the eval harness and the runner are off-limits"),
    ("stop-file", re.compile(
        r"(>>?|\btouch|\brm(\s+-\w+)*)\s+(\./)?STOP\b|['\"](\./)?STOP['\"]|keshev7/STOP\b"),
     "the STOP file is Iddo's brake - do not touch it"),
    ("env-tamper", re.compile(
        r"PYTHONPATH|PYTHONNOUSERSITE|PYTHONSTARTUP|PYTHONHOME|PYTHONSAFEPATH|sitecustomize|"
        r"usercustomize|site-packages|dist-packages|\.local/lib|meta_path|path_hooks|"
        r"HF_HUB_OFFLINE|TRANSFORMERS_OFFLINE|HF_HOME|TORCH_HOME|XDG_CACHE_HOME|KESHEV7_|"
        r"LD_PRELOAD|LD_LIBRARY_PATH|(?i:https?_proxy|all_proxy|no_proxy)|"
        r"\benv\s+(-\w*[iu]\b|--ignore-environment|--unset)|\bunset\s+|"
        r"\bpython[\d.]*\s+(-[a-zA-Z]*[IES][a-zA-Z]*\b)"),
     "the runner's environment and import wall may not be changed"),
    ("cgroup", re.compile(
        r"/sys/fs/cgroup|cgroup\.(procs|kill|threads|subtree_control)|memory\.(max|high)\b|"
        r"cpu\.max\b"),
     "cgroup files are off-limits"),
    ("obfuscation", re.compile(
        r"b64decode|base64\s+(-\w*d|--decode)|\bxxd\s+-r|rot_?13|codecs\.decode|"
        r"(?<![\w.])exec\s*\(|(?<![\w.])eval\s*\(|(?<![\w.])compile\s*\(|marshal\.loads|"
        r"pickle\.loads|\bfromhex\b", _I),
     "no encoded or dynamically built code execution"),
    ("disk-killer", re.compile(
        r"\bmkfs|\bwipefs\b|\bfdisk\b|\bsfdisk\b|\bparted\b|\bmkswap\b|\bswap(on|off)\b|"
        r"\bdd\b[^\n]*\bof=/dev/|>\s*/dev/(sd|nvme|mmcblk|disk|mapper)|\bshred\b|"
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", _I),
     "disk and system killers are forbidden"),
    ("home-lookup", re.compile(
        r"Path\.home\s*\(|expanduser\(\s*['\"]~['\"]\s*\)|environ(\.get)?\s*[\[(]\s*['\"]HOME|"
        r"getenv\(\s*['\"]HOME|getpwuid|\bpwd\.getpw", _I),
     "do not look up the home directory - use paths relative to the sandbox"),
    ("dotdot", re.compile(r"(?:^|[\s/'\"=:(,\[])\.\.(?=/|$|[\s'\")\],;])", re.M),
     "'..' paths are refused - stay inside the sandbox with relative paths"),
]
_GPU_RULE = re.compile(r"CUDA_VISIBLE_DEVICES|NVIDIA_VISIBLE_DEVICES|/dev/nvidia")
_URL_RE = re.compile(r"\b(?:https?|ftp|wss?|file)://[^\s'\"<>)]*", _I)
_ABS_RE = re.compile(r"(?<![\w.~}\])])(/[A-Za-z0-9_.@+-]+(?:/[A-Za-z0-9_.@+-]*)*)")
_TILDE_RE = re.compile(r"(?<![\w)\]}])~(?=/|\s|$|['\"`])")
_HOMEVAR_RE = re.compile(r"\$\{?HOME\}?")

READ_OK = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc", "/opt",
           "/proc/self", "/proc/cpuinfo", "/proc/meminfo", "/proc/loadavg",
           "/proc/stat", "/proc/uptime", "/proc/version", "/sys/devices/system/cpu",
           "/dev/null", "/dev/zero", "/dev/urandom", "/dev/random", "/dev/stdin",
           "/dev/stdout", "/dev/stderr", "/dev/fd", "/dev/shm")
WRITE_OK = ("/dev/null", "/dev/stdout", "/dev/stderr")

DENY_PROGRAMS = {
    "sudo", "su", "doas", "pkexec", "reboot", "shutdown", "poweroff", "halt",
    "telinit", "init", "systemd-run", "loginctl", "busctl", "dbus-send", "gdbus",
    "pkill", "killall", "xkill", "renice", "taskset", "chrt", "apt", "apt-get",
    "aptitude", "dpkg", "snap", "flatpak", "brew", "docker", "podman", "nerdctl",
    "ctr", "kubectl", "chroot", "nsenter", "unshare", "bwrap", "firejail", "ssh",
    "scp", "rsync", "sftp", "sshpass", "nc", "ncat", "netcat", "socat", "telnet",
    "ftp", "nmap", "tailscale", "mount", "umount", "losetup", "fdisk", "sfdisk",
    "parted", "wipefs", "mkswap", "swapon", "swapoff", "modprobe", "insmod",
    "rmmod", "sysctl", "iptables", "ip6tables", "nft", "ufw", "setcap", "chattr",
    "chown", "chgrp", "crontab", "at", "batch", "eval", "pip", "pip3", "pipx",
    "conda", "mamba", "micromamba", "uv", "npm", "npx", "yarn", "pnpm", "cargo",
    "gem", "go", "easy_install", "shred", "tmux", "screen",
    # native interpreters/tools that reach the network or shell out unguarded
    # (compiled/native code is outside the python import wall and honours no
    # http_proxy; the C compiler stays allowed but its source is scanned).
    "perl", "awk", "gawk", "mawk", "nawk", "ruby", "php", "tclsh", "wish",
    "expect", "lua", "luajit", "node", "nodejs", "deno", "bun", "make", "gmake",
    "cmake", "ninja", "meson", "scons", "waf", "pgrep", "pidof",
}
_SEP_OPS = {";", ";;", ";;&", "&", "&&", "|", "||", "|&", "(", ")", "\n", "$(", "`"}
_REDIR_OPS = {">", ">>", "&>", "&>>", ">|", "<>", "<", "<&", ">&", "<<", "<<<"}
_KEYWORDS = {"{", "}", "then", "do", "else", "elif", "if", "while", "until", "!",
             "fi", "done", "esac"}
_OPS = ("<<<", "&>>", ";;&", "&&", "||", ";;", "|&", ">>", "<<", "&>", ">&", "<&",
        ">|", "<>", "$(", ";", "&", "|", "(", ")", "<", ">", "\n", "`")
_SCRIPT_EXT = (".py", ".sh", ".bash", ".pl", ".rb", ".js", ".lua", ".mk",
               ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx",
               ".awk", ".tcl", ".php")


def shell_lex(text):
    """A small bash lexer: -> [("w", word) | ("op", op)]. Quotes are removed
    from words; heredoc bodies are skipped (they are still scanned as raw
    text by the anywhere rules)."""
    toks = []
    cur = []
    have = False
    pending = []
    expect_delim = [None]
    i, n = 0, len(text)

    def flush():
        nonlocal cur, have
        if have:
            w = "".join(cur)
            if expect_delim[0] is not None:
                pending.append((w, expect_delim[0]))
                expect_delim[0] = None
            toks.append(("w", w))
        cur = []
        have = False

    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            if text[i + 1] == "\n":
                i += 2
                continue
            cur.append(text[i + 1])
            have = True
            i += 2
            continue
        if c == "'":
            j = text.find("'", i + 1)
            if j < 0:
                raise ShellParseError("unclosed single quote")
            cur.append(text[i + 1:j])
            have = True
            i = j + 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            if j >= n:
                raise ShellParseError("unclosed double quote")
            cur.append("".join(buf))
            have = True
            i = j + 1
            continue
        if c in " \t\r":
            flush()
            i += 1
            continue
        if c == "#" and not have:
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "$" and i + 1 < n and text[i + 1] == "{":
            j = text.find("}", i)
            if j < 0:
                raise ShellParseError("unclosed ${")
            cur.append(text[i:j + 1])
            have = True
            i = j + 1
            continue
        op = None
        for cand in _OPS:
            if text.startswith(cand, i):
                op = cand
                break
        if op:
            if op[0] in "<>" and have and "".join(cur).isdigit():
                cur = []
                have = False
            else:
                flush()
            if op == "<<":
                strip = i + 2 < n and text[i + 2] == "-"
                toks.append(("op", "<<"))
                expect_delim[0] = strip
                i += 3 if strip else 2
                continue
            toks.append(("op", op))
            i += len(op)
            if op == "\n" and pending:
                for delim, strip in pending:
                    while i < n:
                        j = text.find("\n", i)
                        line = text[i:] if j < 0 else text[i:j]
                        i = n if j < 0 else j + 1
                        if (line.lstrip("\t") if strip else line) == delim:
                            break
                pending.clear()
            continue
        cur.append(c)
        have = True
        i += 1
    flush()
    return toks


def simple_commands(toks):
    cmds = []
    cur = {"words": [], "redirs": []}

    def push():
        nonlocal cur
        if cur["words"] or cur["redirs"]:
            cmds.append(cur)
        cur = {"words": [], "redirs": []}

    i = 0
    while i < len(toks):
        k, v = toks[i]
        if k == "op" and v in _SEP_OPS:
            push()
            i += 1
            continue
        if k == "op" and v in _REDIR_OPS:
            if i + 1 < len(toks) and toks[i + 1][0] == "w":
                cur["redirs"].append((v, toks[i + 1][1]))
                i += 2
            else:
                i += 1
            continue
        if k == "w" and not cur["words"] and v in _KEYWORDS:
            push()
            i += 1
            continue
        cur["words"].append(v)
        i += 1
    push()
    return cmds


_WORD_CH = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def find_cmd_subst(text):
    """Return the offending token ('$(' or '`') if `text` performs an ACTIVE
    command substitution that bash would run, else None.

    Substitution is INERT inside single quotes and inside quoted heredoc
    bodies (a quoted or backslash-escaped heredoc delimiter); it is ACTIVE
    inside double quotes and unquoted heredoc bodies. Arithmetic $((...)) is NOT command
    substitution and is allowed. This closes the whole class where a
    substitution result becomes an argv/redirect the guard never sees
    (kill $(pgrep ...), rm $(printf ...), head $(...), echo x > $(...))."""
    i, n = 0, len(text)
    pending = []  # heredocs opened on the current line: (delimiter, active)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = text.find("'", i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == '"':
            j = i + 1
            while j < n:
                d = text[j]
                if d == "\\":
                    j += 2
                    continue
                if d == '"':
                    break
                if d == "`":
                    return "`"
                if d == "$" and j + 1 < n and text[j + 1] == "(" and not (
                        j + 2 < n and text[j + 2] == "("):
                    return "$("
                j += 1
            i = j + 1
            continue
        if c == "`":
            return "`"
        if c == "$" and i + 1 < n and text[i + 1] == "(":
            if i + 2 < n and text[i + 2] == "(":   # $(( arithmetic )) - allowed
                i += 3
                continue
            return "$("
        if c == "<" and text.startswith("<<", i) and not text.startswith("<<<", i):
            k = i + 2
            if k < n and text[k] == "-":
                k += 1
            while k < n and text[k] in " \t":
                k += 1
            active = True
            delim = []
            if k < n and text[k] in "'\"":
                active = False
                q = text[k]
                k += 1
                while k < n and text[k] != q:
                    delim.append(text[k])
                    k += 1
                k += 1
            else:
                while k < n and (text[k] in _WORD_CH or text[k] == "\\"):
                    if text[k] == "\\":
                        active = False
                        k += 2
                        continue
                    delim.append(text[k])
                    k += 1
            if delim:
                pending.append(("".join(delim), active))
            i = k
            continue
        if c == "\n" and pending:
            i += 1
            for delim, active in pending:
                while i < n:
                    j = text.find("\n", i)
                    line = text[i:] if j < 0 else text[i:j]
                    i = n if j < 0 else j + 1
                    if line.strip() == delim:
                        break
                    if active:
                        hit = _line_cmd_subst(line)
                        if hit:
                            return hit
            pending = []
            continue
        i += 1
    return None


def _line_cmd_subst(line):
    """Single-line substitution scan for unquoted-heredoc bodies (no heredoc
    nesting)."""
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = line.find("'", i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == "`":
            return "`"
        if c == "$" and i + 1 < n and line[i + 1] == "(":
            if i + 2 < n and line[i + 2] == "(":
                i += 3
                continue
            return "$("
        i += 1
    return None


_WRAPPER_VALUED = {
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "-n", "-p", "-P", "-u", "--class", "--classdata"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "xargs": {"-n", "-I", "-P", "-d", "-L", "-s", "-E", "-a", "--max-args",
              "--max-procs", "--delimiter", "--replace", "--arg-file"},
    "exec": {"-a"},
    "stdbuf": set(),
}
_WRAPPERS = {"nohup", "time", "command", "builtin", "exec", "setsid", "unbuffer",
             "stdbuf", "env", "nice", "ionice", "timeout", "xargs"}


def strip_wrappers(words):
    w = list(words)
    for _ in range(20):
        if not w:
            break
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\+?=", w[0]):
            w.pop(0)
            continue
        p = os.path.basename(w[0])
        if p not in _WRAPPERS:
            break
        w.pop(0)
        valued = _WRAPPER_VALUED.get(p, set())
        while w and w[0].startswith("-") and w[0] != "-":
            f = w.pop(0)
            if p == "ionice" and f == "-p":
                return ["renice"]
            if f in valued and w:
                w.pop(0)
        if p == "env":
            while w and re.match(r"^[A-Za-z_]\w*=", w[0]):
                w.pop(0)
        if p == "timeout" and w:
            w.pop(0)
    return w


def _positional(args, valued=()):
    out = []
    ended = False
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if not ended and a == "--":
            ended = True
            continue
        if not ended and a.startswith("-") and a != "-":
            if a in valued:
                skip = True
            continue
        out.append(a)
    return out


def _flag_value(args, names):
    vals = []
    for idx, a in enumerate(args):
        for nm in names:
            if a == nm and idx + 1 < len(args):
                vals.append(args[idx + 1])
            elif nm.startswith("--") and a.startswith(nm + "="):
                vals.append(a.split("=", 1)[1])
    return vals


class Guard(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.home = os.path.realpath(HOME)
        self.sandbox = os.path.realpath(cfg["sandbox"])
        self.eval_dir = os.path.realpath(cfg["eval_dir"])
        self.runner_dir = os.path.realpath(cfg["runner_dir"])
        self.state_dir = os.path.realpath(cfg["state_dir"])
        self.train_dir = os.path.join(self.sandbox, "data", "train")
        self.unlabeled_dir = os.path.join(self.sandbox, "data", "unlabeled")
        # read-only SOURCE data inside the sandbox: (dir, rule id, reason)
        self.ro_dirs = [
            (self.train_dir, "train-ro", "data/train is read-only source data - write elsewhere"),
            (self.unlabeled_dir, "unlabeled-ro",
             "data/unlabeled is read-only source audio (Iddo's voice, no text) - write "
             "features/checkpoints in your own folders"),
        ]
        self.router = cfg["router_base"].rstrip("/")
        self.gpu_off = str(cfg.get("gpu", "off")).lower() != "on"
        try:
            self.roots = set(os.listdir("/"))
        except OSError:
            self.roots = set()
        rel = os.path.relpath(self.sandbox, self.home) if inside(self.sandbox, self.home) else None
        self.tilde_ok = ("~/" + rel) if rel else None
        self.home_ok = ("$HOME/" + rel, "${HOME}/" + rel) if rel else ()
        self.literal_denies = [p for p in {self.eval_dir, self.runner_dir, self.state_dir}
                               if not inside(p, self.sandbox)]

    # -- raw text rules (commands, heredocs, file contents) --------------
    def scan_text(self, text):
        for rid, rx, why in ANYWHERE_RULES:
            m = rx.search(text)
            if m:
                return "DENIED [%s]: %s (matched %r)" % (rid, why, m.group(0)[:60])
        if self.gpu_off:
            m = _GPU_RULE.search(text)
            if m:
                return "DENIED [gpu-off]: the GPU is off by policy (Iddo's live jobs use it) - CPU only"
        for lit in self.literal_denies:
            if lit in text:
                return "DENIED [eval-ref]: the eval harness and the runner are off-limits"
        for m in _URL_RE.finditer(text):
            if not m.group(0).startswith(self.router + "/") and m.group(0) != self.router:
                return "DENIED [url]: no network - URL %r is not allowed" % m.group(0)[:80]
        if re.search(r"\b(curl|wget)\b", text) and (self.router not in text):
            return "DENIED [url]: curl/wget only to the router, and your code gets no network"
        stripped = _URL_RE.sub(" ", text)
        for m in _ABS_RE.finditer(stripped):
            p = m.group(1)
            seg = p.split("/")[1] if p.count("/") >= 1 else ""
            if seg not in self.roots:
                continue
            ap = os.path.normpath(p)
            if inside(ap, self.sandbox):
                continue
            if any(inside(ap, pre) for pre in READ_OK):
                continue
            hint = " - use tmp/ inside the sandbox ($TMPDIR)" if inside(ap, "/tmp") else ""
            return "DENIED [abs-path]: %r is outside the sandbox%s" % (p[:80], hint)
        for m in _TILDE_RE.finditer(text):
            rest = text[m.start():]
            if self.tilde_ok and rest.startswith(self.tilde_ok):
                nxt = rest[len(self.tilde_ok):len(self.tilde_ok) + 1]
                if nxt == "" or nxt in "/ \t\n'\"`;)|&":
                    continue
            return "DENIED [tilde]: '~' outside the sandbox - use relative paths"
        for m in _HOMEVAR_RE.finditer(text):
            rest = text[m.start():]
            ok = False
            for pre in self.home_ok:
                if rest.startswith(pre):
                    nxt = rest[len(pre):len(pre) + 1]
                    ok = nxt == "" or nxt in "/ \t\n'\"`;)|&"
                    if ok:
                        break
            if not ok:
                return "DENIED [home-var]: $HOME outside the sandbox - use relative paths"
        return None

    # -- path checks ------------------------------------------------------
    def resolve(self, p):
        if "`" in p or "$(" in p:
            return None
        if p == "~" or p.startswith("~/"):
            p = self.home + p[1:]
        elif p.startswith("${HOME}"):
            p = self.home + p[len("${HOME}"):]
        elif p.startswith("$HOME"):
            p = self.home + p[len("$HOME"):]
        if "$" in p:
            return None
        if not p.startswith("/"):
            p = os.path.join(self.sandbox, p)
        return os.path.normpath(p)

    def check_path(self, raw, write=False, destructive=False):
        if raw in ("-",) or raw == "":
            return None
        ap = self.resolve(raw)
        if ap is None:
            if destructive:
                return ("DENIED [path-var]: %r - use literal relative paths with "
                        "rm/mv/chmod/truncate/ln/dd/find -delete" % raw[:80])
            return None
        if inside(ap, self.sandbox):
            if write:
                q = ap
                while not os.path.lexists(q) and q != "/":
                    q = os.path.dirname(q)
                rq = os.path.realpath(q)
                for ro, rid, why in self.ro_dirs:
                    # the literal path AND its real target (a sandbox symlink into data/)
                    if inside(ap, ro) or inside(rq, ro):
                        return "DENIED [%s]: %s" % (rid, why)
                    # rm/mv/chmod of a folder that CONTAINS the source data (e.g. `mv data x`)
                    if destructive and ap != self.sandbox and (
                            inside(ro, ap) or (q == ap and rq != self.sandbox and inside(ro, rq))):
                        return ("DENIED [data-ro]: %r contains read-only source data (data/train, "
                                "data/unlabeled) - it may not be removed, moved or chmod-ed" % raw[:80])
                if destructive and ap == self.sandbox:
                    return "DENIED [sandbox-root]: the sandbox root itself may not be removed or moved"
                if not inside(rq, self.sandbox):
                    return "DENIED [symlink-escape]: %r leads outside the sandbox" % raw[:80]
                if ap == os.path.join(self.sandbox, "STOP"):
                    return "DENIED [stop-file]: the STOP file is Iddo's brake"
                return None
            # READ inside the sandbox: refuse a symlink whose real target
            # escapes the sandbox (asymmetric hole the write branch already closed).
            q = ap
            while not os.path.lexists(q) and q != "/":
                q = os.path.dirname(q)
            rq = os.path.realpath(q)
            if not (inside(rq, self.sandbox) or any(inside(rq, pre) for pre in READ_OK)):
                return "DENIED [symlink-escape]: %r leads outside the sandbox" % raw[:80]
            return None
        if write:
            if ap in WRITE_OK:
                return None
            return "DENIED [write-outside]: %r is outside the sandbox" % raw[:80]
        if any(inside(ap, pre) for pre in READ_OK):
            return None
        return "DENIED [read-outside]: %r is outside the sandbox" % raw[:80]

    # -- shell structure ---------------------------------------------------
    def check_shell(self, text, depth=0):
        if depth > 3:
            return "DENIED [nesting]: too many nested shells/scripts - flatten it"
        hit = find_cmd_subst(text)
        if hit:
            return ("DENIED [cmd-subst]: command substitution %r is not allowed - run the "
                    "command and read its output next round, use {1..N} for ranges, or put "
                    "the logic in a python file (WRITE)" % hit)
        try:
            toks = shell_lex(text)
        except ShellParseError as e:
            return ("DENIED [parse]: could not parse the command (%s) - simplify, or WRITE "
                    "a script file and RUN bash it" % e)
        for sc in simple_commands(toks):
            r = self.check_simple(sc["words"], sc["redirs"], depth)
            if r:
                return r
            for w in sc["words"]:
                r = self._scan_referenced_file(w, depth)
                if r:
                    return r
        return None

    def _scan_referenced_file(self, word, depth):
        if not word or "$" in word or "*" in word or "?" in word:
            return None
        ap = self.resolve(word)
        if not ap or not inside(ap, self.sandbox) or not os.path.isfile(ap):
            return None
        try:
            size = os.path.getsize(ap)
            is_script = (ap.endswith(_SCRIPT_EXT) or os.path.basename(ap) == "Makefile"
                         or os.access(ap, os.X_OK))
            if not is_script or size > 2 * 1024 * 1024:
                return None
            with open(ap, "rb") as f:
                raw = f.read()
        except OSError:
            return None
        if b"\x00" in raw:
            return None
        content = raw.decode("utf-8", "replace")
        r = self.scan_text(content)
        if r:
            return r + " -- in file %s" % os.path.relpath(ap, self.sandbox)
        if ap.endswith((".sh", ".bash")) or content.startswith(("#!/bin/bash", "#!/bin/sh",
                                                                 "#!/usr/bin/env bash")):
            r = self.check_shell(content, depth + 1)
            if r:
                return r + " -- in file %s" % os.path.relpath(ap, self.sandbox)
        return None

    def check_simple(self, words, redirs, depth):
        for op, tgt in redirs:
            if op in ("<", "<<", "<<<", "<&"):
                continue
            if op == ">&" and re.fullmatch(r"\d+-?|-", tgt):
                continue
            # a redirect target is destructive (it truncates/creates a file):
            # a dynamic ($VAR / $(...) ) target the guard cannot see is refused.
            r = self.check_path(tgt, write=True, destructive=True)
            if r:
                return r
        argv = strip_wrappers(words)
        if not argv:
            return None
        prog = os.path.basename(argv[0])
        args = argv[1:]
        if prog in DENY_PROGRAMS or prog.startswith(("mkfs", "lxc-")):
            return "DENIED [program:%s]: this program is not allowed for the rally" % prog
        if re.fullmatch(r"python[\d.]*", prog):
            for idx, a in enumerate(args):
                if a == "-c" or not a.startswith("-") or a == "-":
                    break
                if a == "-m":
                    mod = args[idx + 1] if idx + 1 < len(args) else ""
                    if mod.split(".")[0] in ("pip", "ensurepip", "venv", "http", "idlelib"):
                        return "DENIED [python-m]: python -m %s is not allowed" % mod
                    break
                if not a.startswith("--") and re.search(r"[IES]", a[1:]):
                    return "DENIED [env-tamper]: python %s skips the import wall" % a
        if prog in ("bash", "sh", "dash", "zsh", "ksh"):
            for idx, a in enumerate(args):
                if re.fullmatch(r"-[a-z]*c[a-z]*", a) and idx + 1 < len(args):
                    return self.check_shell(args[idx + 1], depth + 1)
        if prog == "kill":
            skip = False
            targets = 0
            for a in args:
                if skip:
                    skip = False
                    continue
                if a in ("-s", "-n"):
                    skip = True
                    continue
                if a in ("-l", "-L"):
                    return None
                if a == "--":
                    continue
                if re.fullmatch(r"-\w+", a):
                    continue
                targets += 1
                # ONLY $! (a background job THIS command line started) or a %n
                # job spec. Never a PID, never a variable ($VAR could hold a PID
                # from pgrep/ps), never a substitution (already denied upstream).
                if not re.fullmatch(r"\$!|%(\d+|%|\+|-)?", a):
                    return ("DENIED [kill-others]: kill only $! (a job THIS command line "
                            "started with '&') or %%n - not %r; never a PID or a variable" % a[:60])
            if targets == 0:
                return ("DENIED [kill-others]: 'kill' with no job spec - use 'sleep N & kill $!'; "
                        "never 'kill $VAR', 'kill $(pgrep ...)' or 'pgrep ... | xargs kill'")
            return None
        if prog == "systemctl":
            subs = [a for a in args if not a.startswith("-")]
            if "--user" not in args or not subs or subs[0] not in (
                    "status", "list-units", "list-timers", "list-unit-files", "show",
                    "is-active", "is-failed"):
                return "DENIED [systemctl]: only systemctl --user status|list-units|show|is-active"
            return None
        if prog == "git":
            i = 0
            while i < len(args) and args[i].startswith("-"):
                if args[i] in ("-C", "-c") and i + 1 < len(args):
                    if args[i] == "-C":
                        r = self.check_path(args[i + 1], write=True)
                        if r:
                            return r
                    i += 2
                    continue
                i += 1
            if i < len(args) and args[i] in ("clone", "pull", "fetch", "submodule", "remote",
                                             "push", "lfs"):
                return "DENIED [git-remote]: git %s is not allowed" % args[i]
            return None
        if prog in ("curl", "wget"):
            urls = [a for a in args if re.match(r"^[a-zA-Z]+://", a)]
            if not urls or any(not (u == self.router or u.startswith(self.router + "/"))
                               for u in urls):
                return "DENIED [url]: curl/wget only to the router"
            outs = _flag_value(args, ["-o", "--output", "-O", "--output-document", "-P",
                                      "--directory-prefix"]) if prog == "wget" else \
                _flag_value(args, ["-o", "--output"])
            for o in outs:
                r = self.check_path(o, write=True)
                if r:
                    return r
            return None
        return self._check_write_program(prog, args)

    def _check_write_program(self, prog, args):
        def each(paths, destructive):
            for p in paths:
                r = self.check_path(p, write=True, destructive=destructive)
                if r:
                    return r
            return None

        if prog in ("rm", "rmdir", "unlink"):
            return each(_positional(args), True)
        if prog == "mv":
            return each(_positional(args, ("-t", "-S")) + _flag_value(args, ["-t", "--target-directory"]), True)
        if prog in ("cp", "install"):
            pos = _positional(args, ("-t", "-S", "-m", "-o", "-g"))
            tgt = _flag_value(args, ["-t", "--target-directory"])
            if prog == "cp" and any(a in ("--link", "--symbolic-link") or
                                    (re.fullmatch(r"-[A-Za-z]+", a) and ("l" in a or "s" in a))
                                    for a in args):
                # a hard/sym link shares the source inode: the SOURCES must be writable too
                return each(pos + tgt, False)
            return each((pos[-1:] if not tgt else []) + tgt, False)
        if prog == "ln":
            return each(_positional(args, ("-t", "-S")) + _flag_value(args, ["-t", "--target-directory"]), False)
        if prog in ("touch", "mkdir", "tee"):
            return each(_positional(args, ("-m", "-d", "-r", "-t")), False)
        if prog == "truncate":
            return each(_positional(args, ("-s", "-r", "--size", "--reference")), True)
        if prog == "chmod":
            pos = _positional(args)
            if not any(a.startswith("--reference") for a in args):
                pos = pos[1:]
            return each(pos, True)
        if prog == "dd":
            return each([a[3:] for a in args if a.startswith("of=")], True)
        if prog == "tar":
            vals = _flag_value(args, ["-C", "--directory", "-f", "--file"])
            if args and re.fullmatch(r"-?[A-Za-z]+", args[0]) and "f" in args[0] and len(args) > 1:
                vals.append(args[1])
            return each(vals, False)
        if prog == "unzip":
            return each(_flag_value(args, ["-d"]), False)
        if prog in ("gcc", "cc", "g++", "c++", "clang"):
            return each(_flag_value(args, ["-o"]), False)
        if prog == "sed":
            if any(a == "-i" or a.startswith("-i") or a.startswith("--in-place") for a in args):
                has_script_flag = any(a in ("-e", "-f", "--expression", "--file") for a in args)
                pos = _positional(args, ("-e", "-f", "--expression", "--file", "-l"))
                return each(pos if has_script_flag else pos[1:], True)
            return None
        if prog == "find":
            if any(a in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint",
                         "-fprintf", "-fls") for a in args):
                starts = []
                for a in args:
                    if a.startswith("-") or a in ("(", "!", ")"):
                        break
                    starts.append(a)
                return each(starts, True)
            return None
        return None

    # -- public ------------------------------------------------------------
    def check_command(self, cmd):
        if not cmd or not cmd.strip():
            return False, "DENIED [empty]: empty command"
        if len(cmd) > 200000:
            return False, "DENIED [too-long]: command longer than 200 KB - WRITE a file instead"
        r = self.scan_text(cmd)
        if r:
            return False, r
        r = self.check_shell(cmd, 0)
        if r:
            return False, r
        return True, "ok"

    def check_write(self, path, content):
        if not path or "\x00" in path:
            return False, "DENIED [path]: empty path", None
        r = self.scan_text(path)
        if r:
            return False, r, None
        ap = self.resolve(path)
        if ap is None:
            return False, "DENIED [path-var]: WRITE needs a literal relative path", None
        if not inside(ap, self.sandbox) or ap == self.sandbox:
            return False, "DENIED [write-outside]: %r is outside the sandbox" % path[:80], None
        if os.path.isdir(ap):
            return False, "DENIED [path]: %r is a directory" % path[:80], None
        r = self.check_path(path, write=True, destructive=True)
        if r:
            return False, r, None
        if len(content.encode("utf-8")) > 512 * 1024:
            return False, "DENIED [too-big]: WRITE content over 512 KB", None
        r = self.scan_text(content)
        if r:
            return False, r, None
        if ap.endswith((".sh", ".bash")):
            r = self.check_shell(content, 1)
            if r:
                return False, r, None
        return True, "ok", ap


# ============================================================================
# Resources, scopes, strays
# ============================================================================
def mem_available_gib():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024 / GIB
    except OSError:
        pass
    return 0.0


def dir_usage_bytes(root, limit_entries=400000):
    total = 0
    n = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                total += st.st_blocks * 512
                n += 1
                if stat.S_ISDIR(st.st_mode):
                    stack.append(e.path)
                if n > limit_entries:
                    return total
    return total


def disk_free_bytes(path):
    try:
        s = os.statvfs(path)
        return s.f_bavail * s.f_frsize
    except OSError:
        return 0


class Executor(object):
    MARKER = b"KESHEV7_RALLY=1"

    def __init__(self, cfg, stop_check=None):
        self.cfg = cfg
        self.sandbox = os.path.realpath(cfg["sandbox"])
        self.stop_check = stop_check or (lambda: False)
        self.lock = threading.Lock()
        self.active = {}

    def env(self):
        c = self.cfg
        uid = os.getuid()
        tmp = os.path.join(self.sandbox, "tmp")
        cache = os.path.join(self.sandbox, ".cache")
        for d in (tmp, cache):
            os.makedirs(d, exist_ok=True)
        e = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": HOME,
            "USER": os.environ.get("USER", ""),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": c["site_dir"],
            "KESHEV7_SANDBOX": self.sandbox,
            "KESHEV7_RALLY": "1",
            "TMPDIR": tmp,
            "XDG_CACHE_HOME": cache,
            "HF_HOME": os.path.join(cache, "none"),
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "TORCH_HOME": os.path.join(cache, "none"),
            "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9", "all_proxy": "http://127.0.0.1:9",
            "no_proxy": re.sub(r"^\w+://", "", c["router_base"]).split(":")[0],
            "OMP_NUM_THREADS": str(c["cpu_threads"]),
            "MKL_NUM_THREADS": str(c["cpu_threads"]),
            "OPENBLAS_NUM_THREADS": str(c["cpu_threads"]),
            "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % uid),
        }
        if os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            e["DBUS_SESSION_BUS_ADDRESS"] = os.environ["DBUS_SESSION_BUS_ADDRESS"]
        if str(c.get("gpu", "off")).lower() != "on":
            e["CUDA_VISIBLE_DEVICES"] = ""
        return e

    def preflight(self):
        c = self.cfg
        mem = mem_available_gib()
        if mem < c["mem_floor_gib"]:
            return ("REFUSED [mem-floor]: host MemAvailable %.1f GiB is below the floor %.1f GiB "
                    "(Iddo's live jobs come first) - the runner waits for memory before your next "
                    "round; the floor is not yours to change" % (mem, c["mem_floor_gib"]))
        used = dir_usage_bytes(self.sandbox) / GIB
        if used > c["sandbox_disk_cap_gib"]:
            return ("REFUSED [disk-cap]: the sandbox uses %.2f GiB, over the cap %.2f GiB - "
                    "delete your own old files first (rm is still allowed)" % (used, c["sandbox_disk_cap_gib"]))
        free = disk_free_bytes(self.sandbox) / GIB
        if free < c["host_disk_free_floor_gib"]:
            return "REFUSED [disk-floor]: host free disk %.0f GiB below floor %.0f GiB" % (
                free, c["host_disk_free_floor_gib"])
        return None

    def preflight_allows_cleanup(self, cmd):
        """Over the disk cap, a pure rm command is still allowed."""
        try:
            cmds = simple_commands(shell_lex(cmd))
        except ShellParseError:
            return False
        progs = [os.path.basename(strip_wrappers(c["words"])[0]) for c in cmds
                 if strip_wrappers(c["words"])]
        return bool(progs) and all(p in ("rm", "du", "ls", "df") for p in progs)

    def violation(self):
        c = self.cfg
        if self.stop_check():
            return "STOP requested"
        if dir_usage_bytes(self.sandbox) / GIB > c["sandbox_disk_cap_gib"]:
            return "DISK CAP: the sandbox went over %.2f GiB" % c["sandbox_disk_cap_gib"]
        if mem_available_gib() < c["mem_hard_floor_gib"]:
            return "MEM FLOOR: host MemAvailable fell below %.1f GiB" % c["mem_hard_floor_gib"]
        return None

    def argv(self, unit, cmd_text, timeout_s):
        c = self.cfg
        return ["systemd-run", "--user", "--scope", "--quiet", "--collect",
                "--unit=" + unit,
                "-p", "MemoryMax=%s" % c["mem_max"], "-p", "MemorySwapMax=0",
                "-p", "CPUWeight=%d" % int(c["cpu_weight"]),
                "-p", "CPUQuota=%s" % c["cpu_quota"],
                "-p", "TasksMax=%d" % int(c["tasks_max"]),
                "env", "-u", "XDG_RUNTIME_DIR", "-u", "DBUS_SESSION_BUS_ADDRESS",
                "nice", "-n", "19", "ionice", "-c", "2", "-n", "7",
                "timeout", "--signal=TERM", "--kill-after=%d" % max(1, int(c["kill_grace_s"])),
                str(max(1, int(timeout_s))),
                "bash", "--noprofile", "--norc", "-c", cmd_text]

    def _systemctl(self, *args):
        try:
            subprocess.run(["systemctl", "--user"] + list(args), capture_output=True,
                           timeout=30, env=self._ctl_env())
        except Exception:
            pass

    def _ctl_env(self):
        e = dict(os.environ)
        e.setdefault("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
        return e

    def kill_unit(self, unit, proc):
        self._systemctl("kill", "--signal=SIGTERM", unit + ".scope")
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            pass
        deadline = time.time() + self.cfg["kill_grace_s"]
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        if proc.poll() is None:
            self._systemctl("kill", "--signal=SIGKILL", unit + ".scope")
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass

    def kill_all(self):
        with self.lock:
            items = list(self.active.items())
        for unit, proc in items:
            self.kill_unit(unit, proc)

    def run(self, cmd_text, unit_prefix="keshev7-cmd", timeout_s=None, monitor=True,
            log_path=None, stdout_only=False):
        c = self.cfg
        timeout_s = timeout_s or c["cmd_timeout_s"]
        unit = "%s-%s-%s" % (unit_prefix, time.strftime("%H%M%S"), secrets.token_hex(3))
        t0 = time.time()
        proc = subprocess.Popen(
            self.argv(unit, cmd_text, timeout_s), cwd=self.sandbox, env=self.env(),
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL if stdout_only else subprocess.STDOUT,
            start_new_session=True)
        with self.lock:
            self.active[unit] = proc
        buf = bytearray()
        keep = int(c["out_keep_chars"])
        logf = None
        if log_path:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            logf = open(log_path, "ab")
        written = [0]

        def reader():
            fd = proc.stdout.fileno()
            while True:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) > 2 * keep:
                    del buf[:len(buf) - keep]
                if logf and written[0] < 5 * 1024 * 1024:
                    logf.write(chunk)
                    written[0] += len(chunk)

        th = threading.Thread(target=reader, daemon=True)
        th.start()
        killed = None
        last = time.time()
        while proc.poll() is None:
            time.sleep(0.2)
            now = time.time()
            if monitor and killed is None and now - last >= c["monitor_every_s"]:
                last = now
                v = self.violation()
                if v:
                    killed = v
                    self.kill_unit(unit, proc)
            if killed is None and now - t0 > timeout_s + c["kill_grace_s"] + 30:
                killed = "wall-clock timeout"
                self.kill_unit(unit, proc)
        self._systemctl("kill", "--signal=SIGKILL", unit + ".scope")
        self._systemctl("stop", unit + ".scope")
        th.join(5)
        try:
            proc.stdout.close()
        except Exception:
            pass
        if logf:
            logf.close()
        with self.lock:
            self.active.pop(unit, None)
        rc = proc.returncode
        out = bytes(buf[-keep:]).decode("utf-8", "replace")
        note = ""
        if killed:
            note = "KILLED by the runner: %s" % killed
        elif rc == 124:
            note = "timed out after %d s (the runner's per-command limit)" % timeout_s
        elif rc in (137, -9):
            # not "most likely the memory cap": on 2026-09-15 four such kills came from a
            # decoy suite's stray sweep, and the morning report called them OOM kills
            note = ("killed by SIGKILL - either the memory cap MemoryMax=%s (MemorySwapMax=0) "
                    "or a kill from outside this command; the runner cannot tell which" % c["mem_max"])
        return {"rc": rc, "out": out, "secs": round(time.time() - t0, 1), "unit": unit,
                "killed": killed, "note": note}

    def sweep_strays(self, exclude=()):
        """Kill leftover processes that carry the rally marker in their
        environment (only this user's processes are readable) AND belong to
        THIS rally's sandbox. Without the sandbox match, a decoy test suite's
        sweep SIGKILLed the live rally's trainers (rounds 131, 143, 144, 145 on
        2026-09-15, logged as 'most likely the memory cap')."""
        me = os.getpid()
        killed = []
        with self.lock:
            if self.active:
                return killed
        mine = ("KESHEV7_SANDBOX=%s" % self.sandbox).encode("utf-8", "surrogateescape")
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            pid = int(name)
            if pid == me or pid in exclude:
                continue
            try:
                with open("/proc/%d/environ" % pid, "rb") as f:
                    envb = f.read()
            except OSError:
                continue
            entries = envb.split(b"\0")
            if self.MARKER in entries and mine in entries:
                try:
                    os.kill(pid, signal.SIGKILL)
                    killed.append(pid)
                except OSError:
                    pass
        return killed


# ============================================================================
# Seal -- tamper evidence for the eval harness and the runner code
# ============================================================================
def _chmod_tree(root, fmode, dmode, skip=()):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if os.path.join(dirpath, d) not in skip]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if not os.path.islink(p):
                os.chmod(p, fmode)
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if dirpath in skip or any(inside(dirpath, s) for s in skip):
            continue
        os.chmod(dirpath, dmode)


def apply_permissions(cfg):
    ev = cfg["eval_dir"]
    refs = os.path.join(ev, "refs")
    if os.path.isdir(ev):
        os.chmod(ev, 0o755)
        if os.path.isdir(refs):
            os.chmod(refs, 0o700)
            for fn in os.listdir(refs):
                os.chmod(os.path.join(refs, fn), 0o400)
        sb = os.path.join(ev, "scoreboard.jsonl")
        if not os.path.exists(sb):
            open(sb, "a").close()
        _chmod_tree(ev, 0o444, 0o555, skip={refs})
        if os.path.isdir(refs):
            os.chmod(refs, 0o000)
    rd = cfg["runner_dir"]
    for fn in ("kof_headless.py", "GOAL.md", "config.json"):
        p = os.path.join(rd, fn)
        if os.path.isfile(p):
            os.chmod(p, 0o444)
    site = cfg["site_dir"]
    if os.path.isdir(site):
        _chmod_tree(site, 0o444, 0o555)
    os.makedirs(cfg["state_dir"], exist_ok=True)
    os.chmod(cfg["state_dir"], 0o700)
    for sub in ("train", "unlabeled"):   # read-only source data (labeled + unlabeled audio)
        td = os.path.join(cfg["sandbox"], "data", sub)
        if os.path.isdir(td):
            _chmod_tree(td, 0o444, 0o555)


class Seal(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.path = os.path.join(cfg["state_dir"], "seal.json")
        self.refs = os.path.join(cfg["eval_dir"], "refs")

    def _entry(self, p, hash_it):
        st = os.lstat(p)
        e = [oct(stat.S_IMODE(st.st_mode)), st.st_size, st.st_mtime_ns, st.st_ctime_ns,
             stat.S_IFMT(st.st_mode)]
        if hash_it and stat.S_ISREG(st.st_mode) and st.st_size <= 4 * 1024 * 1024:
            try:
                e.append(sha256_file(p))
            except OSError:
                e.append("unreadable")
        return e

    def snapshot(self):
        snap = {}
        ev = self.cfg["eval_dir"]
        if os.path.lexists(ev):
            stack = [ev]
            while stack:
                d = stack.pop()
                snap[d] = self._entry(d, False)
                if d == self.refs:
                    continue
                try:
                    names = sorted(os.listdir(d))
                except OSError:
                    continue
                for nm in names:
                    p = os.path.join(d, nm)
                    if os.path.isdir(p) and not os.path.islink(p):
                        stack.append(p)
                    else:
                        snap[p] = self._entry(p, not p.endswith(".wav"))
        rd = self.cfg["runner_dir"]
        for fn in ("kof_headless.py", "GOAL.md", "config.json"):
            p = os.path.join(rd, fn)
            if os.path.lexists(p):
                snap[p] = self._entry(p, True)
        site = self.cfg["site_dir"]
        if os.path.lexists(site):
            snap[site] = self._entry(site, False)
            for nm in sorted(os.listdir(site)):
                p = os.path.join(site, nm)
                if os.path.isfile(p):
                    snap[p] = self._entry(p, True)
        return snap

    def save(self):
        atomic_write_text(self.path, json.dumps(self.snapshot(), indent=0))

    def exists(self):
        return os.path.isfile(self.path)

    def sealed_hash(self, path):
        """The sha256 recorded for `path` in the seal, or None."""
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return None
        e = saved.get(os.path.realpath(path)) or saved.get(path)
        if isinstance(e, list) and len(e) >= 6 and isinstance(e[5], str) and len(e[5]) == 64:
            return e[5]
        return None

    def verify(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return ["no seal on record (run: kof_headless.py seal)"]
        now = self.snapshot()
        diffs = []
        for p in sorted(set(saved) | set(now)):
            if p not in now:
                diffs.append("removed: %s" % p)
            elif p not in saved:
                diffs.append("added: %s" % p)
            elif saved[p] != now[p]:
                diffs.append("changed: %s" % p)
        return diffs


# ============================================================================
# Brain
# ============================================================================
class BrainError(Exception):
    pass


class BrainClient(object):
    """gpt-oss-120b. Router first (Iddo's one door), direct backend second.
    Measured 2026-09-15: the router does not enforce max_tokens; the direct
    backend does. Context: n_ctx 65536 per slot."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.last_url = None
        self.last_usage = None

    def chat(self, messages):
        c = self.cfg
        payload = {"model": c["model"], "messages": messages,
                   "max_tokens": c["max_tokens"], "temperature": c["temperature"],
                   "reasoning_effort": c["reasoning_effort"],
                   "chat_template_kwargs": {"reasoning_effort": c["reasoning_effort"]}}
        data = json.dumps(payload).encode("utf-8")
        errors = []
        for url in c["brain_urls"]:
            try:
                req = urllib.request.Request(url, data=data,
                                             headers={"Content-Type": "application/json"})
                with self.opener.open(req, timeout=c["brain_timeout_s"]) as r:
                    d = json.loads(r.read().decode("utf-8"))
                ch = d["choices"][0]
                text = (ch.get("message") or {}).get("content") or ""
                if text.strip():
                    self.last_url = url
                    self.last_usage = d.get("usage")
                    return text
                errors.append("%s: empty content (finish=%s)" % (url, ch.get("finish_reason")))
            except Exception as e:
                errors.append("%s: %s" % (url, str(e)[:200]))
        raise BrainError("; ".join(errors))


# ============================================================================
# The rally
# ============================================================================
SUMMARY_SYSTEM = "You compress a long coding log into a rolling summary. Plain text, at most 3500 characters."
SUMMARY_PROMPT = ("Update the rolling summary of a long non-stop build of KESHEV 7 (Iddo's Hebrew "
                  "dictation model, from scratch). Keep: which files exist and what each does; "
                  "commands that work; measured numbers (loss, CER, WER, epochs, speed); failures "
                  "and their causes; guard refusals learned; the current plan. Drop chatter.")
ASK_SYSTEM = "You are the builder of KESHEV 7, working alone and non-stop. No human is available."


class Rally(object):
    def __init__(self, cfg, infer=None, on_event=None, verbose=False):
        self.cfg = cfg
        os.makedirs(cfg["state_dir"], exist_ok=True)
        self.sandbox = os.path.realpath(cfg["sandbox"])
        os.makedirs(self.sandbox, exist_ok=True)
        self.stop_flag = threading.Event()
        self.guard = Guard(cfg)
        self.ex = Executor(cfg, stop_check=self.stop_requested)
        self.seal = Seal(cfg)
        self.brain = BrainClient(cfg)
        self.infer = infer or self.brain.chat
        self.on_event = on_event
        self.verbose = verbose
        self.state_path = os.path.join(cfg["state_dir"], "rally_state.json")
        self.prev_path = os.path.join(cfg["state_dir"], "rally_state.prev.json")
        self.events_path = os.path.join(cfg["state_dir"], "rally.jsonl")
        self.goal_text = None
        self._heldout_refs = None   # loaded once per process, never re-chmod per eval
        self.state = self._load_state()

    # -- state (AUTOSAVE LAW) ---------------------------------------------
    def _new_state(self):
        return {"version": 1, "created": now_iso(), "updated": None, "round": 0,
                "summary": "", "turns": [], "pending_round": None, "last_eval": None,
                "evals": 0, "last_eval_round": 0, "accepted": [], "halted": None,
                "stats": {"runs": 0, "writes": 0, "denied": 0, "asks": 0, "dones": 0,
                          "brain_errors": 0, "compactions": 0, "strays_killed": 0},
                "last_progress_round": 0, "last_ramchat_ts": 0}

    def _load_state(self):
        base = self._new_state()
        for p in (self.state_path, self.prev_path):
            try:
                with open(p, encoding="utf-8") as f:
                    st = json.load(f)
                for k, v in base.items():
                    st.setdefault(k, v)
                for k, v in base["stats"].items():
                    st["stats"].setdefault(k, v)
                return st
            except FileNotFoundError:
                continue
            except (ValueError, OSError):
                continue
        return base

    def save(self):
        self.state["updated"] = now_iso()
        text = json.dumps(self.state, ensure_ascii=False)
        if os.path.exists(self.state_path):
            try:
                os.replace(self.state_path, self.prev_path)
            except OSError:
                pass
        atomic_write_text(self.state_path, text)

    def emit(self, ev):
        ev = dict(ev)
        ev.setdefault("ts", now_iso())
        try:
            if os.path.exists(self.events_path) and os.path.getsize(self.events_path) > 50 * 1024 * 1024:
                os.replace(self.events_path, self.events_path + ".1")
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError:
            pass
        if self.verbose:
            print(json.dumps(ev, ensure_ascii=False)[:400], flush=True)
        if self.on_event:
            self.on_event(ev)

    # -- stop -------------------------------------------------------------
    def stop_requested(self):
        return self.stop_flag.is_set() or os.path.exists(os.path.join(self.sandbox, "STOP"))

    def request_stop(self, *_):
        self.stop_flag.set()
        threading.Thread(target=self.ex.kill_all, daemon=True).start()

    # -- goal + messages ---------------------------------------------------
    def render_goal(self):
        c = self.cfg
        try:
            with open(c["goal_template"], encoding="utf-8") as f:
                tpl = f.read()
        except OSError:
            tpl = "GOAL template missing - build KESHEV 7: python3 transcribe.py <wav> prints Hebrew text."
        stats, base = {}, {}
        try:
            with open(os.path.join(self.sandbox, "data", "train", "STATS.json"), encoding="utf-8") as f:
                stats = json.load(f)
        except (OSError, ValueError):
            pass
        ustats = {}
        try:
            with open(os.path.join(self.sandbox, "data", "unlabeled", "cafe", "STATS.json"),
                      encoding="utf-8") as f:
                ustats = json.load(f)
        except (OSError, ValueError):
            pass
        try:
            with open(os.path.join(c["eval_dir"], "baselines.json"), encoding="utf-8") as f:
                base = json.load(f)
        except (OSError, ValueError):
            pass
        vals = {
            "SANDBOX": "~/" + os.path.relpath(self.sandbox, HOME) if inside(self.sandbox, HOME) else self.sandbox,
            "TRAIN_CLIPS": stats.get("clips", "?"), "TRAIN_HOURS": stats.get("hours", "?"),
            "TRAIN_SESSIONS": stats.get("sessions", "?"), "HEBREW_CLIPS": stats.get("hebrew_clips", "?"),
            "HELDOUT_CLIPS": stats.get("heldout_clips", "?"), "BAR": c["eval_bar_cer"],
            "UNLABELED_FILES": ustats.get("files", "?"), "UNLABELED_HOURS": ustats.get("hours", "?"),
            "BASE_EMPTY": base.get("empty", {}).get("cer", "?"),
            "BASE_MFW": base.get("most_frequent_word", {}).get("cer", "?"),
            "MFW_WORD": base.get("most_frequent_word", {}).get("word", "?"),
            "CMD_TIMEOUT": c["cmd_timeout_s"], "MEM_MAX": c["mem_max"], "CPU": c["cpu_quota"],
            "GPU": "OFF (CPU only)" if str(c.get("gpu")).lower() != "on" else "on",
            "DISK_CAP": c["sandbox_disk_cap_gib"], "CLIP_TIMEOUT": c["eval_clip_timeout_s"],
            "EVAL_EVERY": c["eval_every_rounds"] or "never",
            "MEM_FLOOR": c["mem_floor_gib"],
            "MEM_WAIT_MIN": int(round(float(c.get("mem_wait_max_s") or 0) / 60.0)),
        }
        text = tpl
        for k, v in vals.items():
            text = text.replace("{{%s}}" % k, str(v))
        self.goal_text = text
        gp = os.path.join(self.sandbox, "GOAL.md")
        try:
            if os.path.exists(gp):
                os.chmod(gp, 0o644)
            atomic_write_text(gp, text, mode=0o444)
        except OSError:
            pass
        return text

    def build_messages(self):
        if self.goal_text is None:
            self.render_goal()
        goal = "GOAL:\n" + self.goal_text
        if self.state["summary"]:
            goal += "\n\nROLLING SUMMARY OF EARLIER ROUNDS (written by you):\n" + self.state["summary"]
        turns = list(self.state["turns"])
        while turns and turns[0]["role"] == "user":
            goal += "\n\n" + turns.pop(0)["content"]
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": goal}]
        n = len(turns)
        for i, t in enumerate(turns):
            content = t["content"]
            if t["role"] == "assistant" and i < n - 4:
                content = elide_write_bodies(content)
            msgs.append({"role": t["role"], "content": content})
        return msgs

    def est_tokens(self, msgs):
        return int(sum(len(m["content"]) for m in msgs) / self.cfg["chars_per_token"]) + 8 * len(msgs)

    def _add_user(self, text):
        turns = self.state["turns"]
        if turns and turns[-1]["role"] == "user":
            turns[-1]["content"] += "\n\n" + text
        else:
            turns.append({"role": "user", "content": text})

    def note_goal_change(self):
        """A GOAL edit (e.g. new data) must reach a brain that is deep in its own
        rolling summary and plan: tell it ONCE, naming the new/changed sections."""
        text = self.goal_text or ""
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        heads = [l.strip() for l in text.split("\n") if l.startswith("## ")]
        st = self.state
        old_sha = st.get("goal_sha")
        if old_sha == sha:
            return
        if old_sha is not None or st["round"] > 0:
            old = set(st.get("goal_headings") or [])
            new = [h for h in heads if h not in old] if old else heads
            # quote the NEW sections themselves: a heading alone did not move a brain that
            # was deep in its own plan (the Cafe section, rounds 103-160, 2026-09-15)
            bodies = ""
            if old and new:
                lines, parts = text.split("\n"), []
                for h in new:
                    for i, l in enumerate(lines):
                        if l.strip() == h:
                            j = i + 1
                            while j < len(lines) and not lines[j].startswith("## "):
                                j += 1
                            parts.append("\n".join(lines[i:j]).strip())
                            break
                bodies = ("\n\n" + "\n\n".join(parts))[:3000]
            self._add_user("RUNNER NOTE: the GOAL was UPDATED since your earlier rounds - re-read it in "
                           "full and adjust your plan. %s: %s%s"
                           % ("New or renamed sections" if old else "Its sections",
                              " | ".join(new) or "(wording changed only)", bodies))
            self.emit({"t": "goal_changed", "round": st["round"], "sections": new})
        st["goal_sha"] = sha
        st["goal_headings"] = heads
        self.save()

    def summarize(self, prev, old_turns):
        log = "\n\n".join("[%s]\n%s" % (t["role"], elide_write_bodies(t["content"])[-3000:])
                          for t in old_turns)[-60000:]
        msgs = [{"role": "system", "content": SUMMARY_SYSTEM},
                {"role": "user", "content": "%s\n\nPREVIOUS SUMMARY:\n%s\n\nNEW LOG:\n%s"
                 % (SUMMARY_PROMPT, prev or "(none)", log)}]
        try:
            s = (self.infer(msgs) or "").strip()
            if len(s) < 20:
                raise ValueError("summary too short")
            return s[:6000]
        except Exception as e:
            self.emit({"t": "summary_fallback", "error": str(e)[:200]})
            mech = [(prev or "")[-3000:]]
            for t in old_turns:
                mech.append("[%s] %s" % (t["role"], t["content"][:200].replace("\n", " ")))
            return "\n".join(mech)[-6000:]

    def compact(self):
        budget = self.cfg["ctx_budget_tokens"]
        if self.est_tokens(self.build_messages()) <= budget:
            return
        keep = self.cfg["keep_last_turns"]
        for _ in range(6):
            turns = self.state["turns"]
            if len(turns) <= 2:
                break
            cut = max(1, len(turns) - keep)
            while cut < len(turns) and turns[cut]["role"] != "assistant":
                cut += 1
            old = turns[:cut]
            self.state["summary"] = self.summarize(self.state["summary"], old)
            self.state["turns"] = turns[cut:]
            self.state["stats"]["compactions"] += 1
            self.emit({"t": "compact", "round": self.state["round"], "cut_turns": len(old)})
            if self.est_tokens(self.build_messages()) <= budget:
                break
            keep = max(2, keep // 2)
        if self.est_tokens(self.build_messages()) > budget:
            for t in self.state["turns"][:-1]:
                t["content"] = t["content"][:3000] + "\n[truncated by the runner]"
            self.state["summary"] = self.state["summary"][:4000]
        self.save()

    # -- one round ---------------------------------------------------------
    def wait_for_memory(self):
        """Below the memory floor every RUN is refused and every eval is deferred, so a
        round only costs the shared box a brain call - and, before this, a 232-clip eval
        on each DONE (eran1, rounds 175-214, 2026-09-15: 0 runs, DONE spam, the evals
        themselves pushing MemAvailable further down). Wait here, polling, up to
        mem_wait_max_s, then play the round anyway. No limit changes: nothing runs that
        was refused before; only the idle spinning stops."""
        c = self.cfg
        max_s = float(c.get("mem_wait_max_s") or 0)
        floor = c["mem_floor_gib"]
        mem = mem_available_gib()
        if max_s <= 0 or mem >= floor:
            return True
        rnd = self.state["round"] + 1
        t0 = time.time()
        self.emit({"t": "mem_wait", "round": rnd, "mem_gib": round(mem, 2), "floor_gib": floor,
                   "max_s": max_s})
        poll = max(0.2, float(c.get("mem_wait_poll_s") or 15))
        while time.time() - t0 < max_s and not self.stop_requested():
            self._nap(min(poll, max(0.0, max_s - (time.time() - t0))))
            mem = mem_available_gib()
            if mem >= floor:
                break
        ok = mem >= floor
        waited = round(time.time() - t0, 1)
        stats = self.state["stats"]
        stats["mem_wait_s"] = round(stats.get("mem_wait_s", 0) + waited, 1)
        self.emit({"t": "mem_wait_end", "round": rnd, "waited_s": waited, "mem_gib": round(mem, 2),
                   "ok": ok})
        if not ok and not self.stop_requested():
            self._add_user("RUNNER: host memory is still below the floor after waiting %d s "
                           "(MemAvailable %.1f GiB < %.1f GiB). This round RUN stays refused and the "
                           "eval stays deferred; WRITE still works. Do not reply DONE to fill the time."
                           % (waited, mem, floor))
        return ok

    def step(self):
        c = self.cfg
        st = self.state
        if st.get("halted"):
            return "halted"
        if self.stop_requested():
            self.emit({"t": "stop", "round": st["round"]})
            return "stop"
        if st.get("pending_round"):
            self._add_user("RUNNER RESTARTED during round %d: the actions of your last reply may "
                           "have run partly or not at all. Check files and logs before repeating."
                           % st["pending_round"])
            self.emit({"t": "resumed_mid_round", "round": st["pending_round"]})
            st["pending_round"] = None
            self.save()
        self.wait_for_memory()
        if self.stop_requested():
            self.emit({"t": "stop", "round": st["round"]})
            return "stop"
        self.compact()
        rnd = st["round"] + 1
        msgs = self.build_messages()
        t0 = time.time()
        try:
            reply = self.infer(msgs)
            if not (reply or "").strip():
                raise BrainError("empty reply")
        except Exception as e:
            st["stats"]["brain_errors"] += 1
            self.save()
            self.emit({"t": "brain_error", "round": rnd, "error": str(e)[:300]})
            return "brain_error"
        st["round"] = rnd
        st["turns"].append({"role": "assistant", "content": reply[:60000]})
        st["pending_round"] = rnd
        self.save()
        p = parse_reply(reply, c["max_runs_per_round"], c["max_writes_per_round"])
        self.emit({"t": "brain", "round": rnd, "secs": round(time.time() - t0, 1),
                   "tokens_est": self.est_tokens(msgs),
                   "actions": ["%s %s" % (a[0], a[1][:160]) for a in p["actions"]],
                   "ask": bool(p["ask"]), "done": p["done"] is not None})
        action_parts = []
        for idx, act in enumerate(p["actions"], 1):
            if self.stop_requested():
                action_parts.append("[%d] not run: STOP requested" % idx)
                break
            if st.get("halted"):
                action_parts.append("[%d] not run: rally HALTED" % idx)
                break
            if act[0] == "WRITE":
                action_parts.append(self.do_write(rnd, idx, act[1], act[2]))
            else:
                action_parts.append(self.do_run(rnd, idx, act[1]))
        body = "\n".join(action_parts)
        cap = c["feedback_round_chars"]
        if len(body) > cap:
            body = body[:cap // 2] + "\n[... middle of the round output cut ...]\n" + body[-cap // 2:]
        extra = ["NOTE: " + n for n in p["notes"]]
        if p["ask"]:
            extra.append(self.handle_ask(rnd, p["ask"]))
        if st.get("halted"):
            pass
        elif p["done"] is not None:
            st["stats"]["dones"] += 1
            extra.append(self.handle_eval(rnd, "DONE"))
        elif (c["eval_every_rounds"] and rnd - st["last_eval_round"] >= c["eval_every_rounds"]
              and os.path.isfile(os.path.join(self.sandbox, "transcribe.py"))):
            extra.append(self.handle_eval(rnd, "periodic"))
        if not p["actions"] and not p["ask"] and p["done"] is None and not p["notes"]:
            extra.append("FORMAT: no RUN/WRITE/ASK/DONE line found in your reply. Reply only with those.")
        feedback = "ROUND %d RESULT\n%s\n%s\n%s" % (rnd, body, "\n".join(extra), self.status_line())
        self._add_user(feedback)
        st["pending_round"] = None
        self.save()
        self.maybe_progress(rnd)
        self.maybe_ramchat()
        return "halted" if st.get("halted") else "ok"

    def do_write(self, rnd, idx, path, content):
        ok, why, ap = self.guard.check_write(path, content)
        if not ok:
            self.state["stats"]["denied"] += 1
            self.emit({"t": "denied", "round": rnd, "kind": "WRITE", "path": path[:200], "why": why})
            return "[%d] WRITE %s -> %s (NOT written)" % (idx, path, why)
        try:
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            mode = 0o755 if ap.endswith((".sh", ".bash")) else 0o644
            atomic_write_text(ap, content, mode=mode)
        except OSError as e:
            return "[%d] WRITE %s -> failed: %s" % (idx, path, e)
        self.state["stats"]["writes"] += 1
        self.emit({"t": "write", "round": rnd, "path": path[:200], "bytes": len(content.encode("utf-8"))})
        return "[%d] WRITE %s -> ok (%d lines, %.1f KB)" % (
            idx, path, content.count("\n"), len(content.encode("utf-8")) / 1024.0)

    def do_run(self, rnd, idx, cmd):
        c = self.cfg
        short = cmd if len(cmd) <= 300 else cmd[:300] + " ..."
        if _PATCH_RE.search(cmd):
            stats = self.state["stats"]
            stats["patch_refused"] = stats.get("patch_refused", 0) + 1
            self.emit({"t": "patch_refused", "round": rnd, "cmd": cmd[:300]})
            return "[%d] RUN %s -> %s (NOT run)" % (idx, short, PATCH_NOTE)
        ok, why = self.guard.check_command(cmd)
        if not ok:
            self.state["stats"]["denied"] += 1
            self.emit({"t": "denied", "round": rnd, "kind": "RUN", "cmd": cmd[:300], "why": why})
            return "[%d] RUN %s -> %s (NOT run)" % (idx, short, why)
        pre = self.ex.preflight()
        if pre and not (pre.startswith("REFUSED [disk-cap]") and self.ex.preflight_allows_cleanup(cmd)):
            self.emit({"t": "refused", "round": rnd, "cmd": cmd[:300], "why": pre})
            return "[%d] RUN %s -> %s (NOT run)" % (idx, short, pre)
        log_path = os.path.join(c["state_dir"], "cmdlogs", "r%06d-%d.log" % (rnd, idx))
        self.emit({"t": "run", "round": rnd, "cmd": cmd[:300]})
        res = self.ex.run(cmd, unit_prefix="keshev7-cmd-r%d-%d" % (rnd, idx),
                          timeout_s=c["cmd_timeout_s"], monitor=True, log_path=log_path)
        self.state["stats"]["runs"] += 1
        self.after_command(rnd)
        self.emit({"t": "output", "round": rnd, "rc": res["rc"], "secs": res["secs"],
                   "note": res["note"], "out": res["out"][-1500:]})
        tail = res["out"][-c["feedback_per_cmd_chars"]:]
        return "[%d] RUN %s -> rc=%s (%.1f s)%s\n%s" % (
            idx, short, res["rc"], res["secs"], (" " + res["note"]) if res["note"] else "",
            tail if tail.strip() else "(no output)")

    def after_command(self, rnd):
        strays = self.ex.sweep_strays()
        if strays:
            self.state["stats"]["strays_killed"] += len(strays)
            self.emit({"t": "strays_killed", "round": rnd, "pids": strays})
        diffs = self.seal.verify()
        if diffs:
            self.tamper(rnd, diffs)

    def tamper(self, rnd, diffs):
        self.state["halted"] = "TAMPER at round %d (%s): %s" % (rnd, now_iso(), "; ".join(diffs[:6]))
        self.save()
        self.emit({"t": "TAMPER", "round": rnd, "diffs": diffs[:20]})
        self.maybe_ramchat(force=True)

    def status_line(self):
        st = self.state
        le = st.get("last_eval")
        le_s = ("CER %.3f @round %s" % (le["cer"], le["round"])) if le else "none"
        return ("STATUS round=%d sandbox=%.2f/%.0f GiB mem_avail=%.0f GiB last_eval=%s accepted=%d time=%s"
                % (st["round"], dir_usage_bytes(self.sandbox) / GIB, self.cfg["sandbox_disk_cap_gib"],
                   mem_available_gib(), le_s, len(st["accepted"]), now_iso()))

    # -- ASK: non-stop ------------------------------------------------------
    def handle_ask(self, rnd, q):
        self.state["stats"]["asks"] += 1
        msgs = [{"role": "system", "content": ASK_SYSTEM},
                {"role": "user", "content":
                 "GOAL (short): build KESHEV 7, Iddo's Hebrew dictation model, from scratch; contract "
                 "python3 transcribe.py <wav> prints the text.\nSUMMARY SO FAR:\n%s\n\nYOUR QUESTION:\n%s\n\n"
                 "No human will answer. Answer it yourself: the single most reasonable assumption, at "
                 "most 5 lines, starting with ASSUME:" % (self.state["summary"][-2000:], q)}]
        try:
            a = (self.infer(msgs) or "").strip()[:1500]
            if not a:
                raise ValueError("empty")
        except Exception:
            a = "ASSUME: take the simplest option consistent with the GOAL and the rules, and continue."
        try:
            with open(os.path.join(self.sandbox, "QUESTIONS.md"), "a", encoding="utf-8") as f:
                f.write("## Round %d - %s\n**Q:** %s\n\n**Assumed by the rally (no human answered):** %s\n\n"
                        % (rnd, now_iso(), q, a))
        except OSError:
            pass
        self.emit({"t": "ask", "round": rnd, "question": q[:1000], "assumed": a[:600]})
        return ("ASK: no human is available (non-stop mode). Your question is logged in QUESTIONS.md "
                "for Iddo. Your own best assumption:\n%s\nAct on it now." % a)

    # -- eval ----------------------------------------------------------------
    def load_eval_module(self):
        p = os.path.join(self.cfg["eval_dir"], "eval.py")
        # re-verify eval.py's sha256 against the seal IMMEDIATELY before we
        # exec it in the (uncapped) runner process - no race between the
        # directory-wide verify() and this exec.
        want = self.seal.sealed_hash(p)
        if want is not None:
            got = sha256_file(p)
            if got != want:
                raise BrainError("eval.py sha256 mismatch vs seal (%s != %s) - refusing to exec"
                                 % (got[:12], want[:12]))
        spec = importlib.util.spec_from_file_location("keshev7_eval_harness", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _load_heldout_refs(self):
        """Read refs/heldout.jsonl ONCE into runner memory. The refs dir is
        opened for exactly one 0500 window per process lifetime (not per eval),
        closing the recurring per-eval exposure the red team flagged."""
        if self._heldout_refs is not None:
            return self._heldout_refs
        refs_dir = os.path.join(self.cfg["eval_dir"], "refs")
        try:
            os.chmod(refs_dir, 0o500)
        except OSError:
            pass
        try:
            with open(os.path.join(refs_dir, "heldout.jsonl"), encoding="utf-8") as f:
                refs = [json.loads(l) for l in f if l.strip()]
        finally:
            try:
                os.chmod(refs_dir, 0o000)
            except OSError:
                pass
        self._heldout_refs = refs
        return refs

    def run_eval(self, rnd, why):
        c = self.cfg
        diffs = self.seal.verify()
        if diffs:
            self.tamper(rnd, diffs)
            return {"error": "TAMPER - eval void, rally halted"}
        tp = os.path.join(self.sandbox, "transcribe.py")
        if not os.path.isfile(tp):
            return {"error": "there is no transcribe.py in the sandbox root"}
        try:
            with open(tp, encoding="utf-8", errors="replace") as f:
                r = self.guard.scan_text(f.read())
        except OSError as e:
            return {"error": "transcribe.py unreadable: %s" % e}
        if r:
            return {"error": "transcribe.py refused: %s" % r}
        # the eval runs eval_workers transcribe.py children on the same shared box as
        # every RUN: it honours the same memory floor (it did not, 2026-09-15)
        mem = mem_available_gib()
        if mem < c["mem_floor_gib"]:
            return {"deferred": True,
                    "error": "DEFERRED [mem-floor]: host MemAvailable %.1f GiB is below the floor "
                             "%.1f GiB - the eval waits for memory like every RUN; replying DONE "
                             "again does not help" % (mem, c["mem_floor_gib"])}
        if self.stop_requested():
            return {"deferred": True, "error": "not scored - STOP requested"}
        ev = self.load_eval_module()
        audio = os.path.join(c["eval_dir"], "audio")
        src_clips = sorted((fn[:-4], os.path.join(audio, fn))
                           for fn in os.listdir(audio) if fn.endswith(".wav"))
        tsha = sha256_file(tp)
        # Stage each held-out wav into the sandbox (readable to transcribe.py
        # under the file jail) with a RANDOM basename so the product cannot walk
        # from its input path to the eval tree (split.json / refs / other clips),
        # and cannot map a staged file back to a clip id. The map back to ids
        # stays only here in the runner.
        stage = os.path.join(self.sandbox, "tmp", "eval_stage_" + secrets.token_hex(4))
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage, exist_ok=True)
        staged = []
        for cid, src in src_clips:
            dst = os.path.join(stage, secrets.token_hex(8) + ".wav")
            shutil.copyfile(src, dst)
            staged.append((cid, dst))

        def transcribe(wav, timeout_s):
            res = self.ex.run("python3 transcribe.py " + shlex.quote(wav), unit_prefix="keshev7-eval",
                              timeout_s=timeout_s, monitor=False, stdout_only=True)
            return res["rc"], res["out"]

        self.emit({"t": "eval_start", "round": rnd, "why": why, "clips": len(staged)})
        t0 = time.time()
        try:
            hyps = ev.transcribe_all(staged, transcribe, workers=c["eval_workers"],
                                     clip_timeout_s=c["eval_clip_timeout_s"], max_s=c["eval_max_s"],
                                     should_stop=self.stop_requested)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        runtime = time.time() - t0
        self.after_command(rnd)
        if self.state.get("halted"):
            return {"error": "TAMPER during eval - eval void, rally halted"}
        refs = self._load_heldout_refs()
        base = None
        try:
            with open(os.path.join(c["eval_dir"], "baselines.json"), encoding="utf-8") as f:
                base = json.load(f)
        except (OSError, ValueError):
            pass
        res = ev.finalize(hyps, refs, bar_cer=c["eval_bar_cer"], max_fail_frac=c["eval_max_fail_frac"],
                          base=base, runtime_s=runtime, round_no=rnd, tampered=False)
        res["why"] = why
        res["transcribe_sha256"] = tsha
        sb = os.path.join(c["eval_dir"], "scoreboard.jsonl")
        os.chmod(sb, 0o644)
        try:
            with open(sb, "a", encoding="utf-8") as f:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        finally:
            os.chmod(sb, 0o444)
        self.seal.save()
        return res

    def handle_eval(self, rnd, why):
        st = self.state
        try:
            res = self.run_eval(rnd, why)
        except Exception as e:
            res = {"error": "eval harness error: %s" % str(e)[:300]}
        if res.get("deferred"):
            # not an eval: last_eval_round stays, so a due periodic eval is retried
            st["stats"]["evals_deferred"] = st["stats"].get("evals_deferred", 0) + 1
            self.emit({"t": "eval_deferred", "round": rnd, "why": why, "error": res["error"]})
            self.save()
            return "EVAL (%s): %s" % (why, res["error"])
        st["last_eval_round"] = rnd
        if "error" in res:
            self.emit({"t": "eval", "round": rnd, "why": why, "error": res["error"]})
            self.save()
            return "EVAL (%s): not scored - %s" % (why, res["error"])
        st["last_eval"] = res
        st["evals"] += 1
        self.emit(dict(res, t="eval"))
        line = ("EVAL round %d (%s): CER %.3f (bar %.2f)  WER %.3f  Hebrew-CER %s  clips %d  failed %d  %.0f s. "
                "Baselines: empty-output CER %s, most-frequent-word CER %s."
                % (rnd, why, res["cer"], res["bar_cer"], res["wer"], res["cer_hebrew"], res["clips"],
                   res["failures"], res["runtime_s"], res.get("baseline_empty_cer"),
                   res.get("baseline_mfw_cer")))
        if res["accepted"]:
            st["accepted"].append({"round": rnd, "cer": res["cer"], "wer": res["wer"], "ts": res["ts"]})
            self.emit({"t": "DONE-ACCEPTED", "round": rnd, "cer": res["cer"], "n": len(st["accepted"])})
            self.save()
            self.write_progress(rnd)
            self.maybe_ramchat(force=True)
            return (line + "\nDONE-ACCEPTED #%d. The loop does not stop: keep lowering CER, then stage 6 "
                    "(write the pc/ client from scratch, do not run it here)." % len(st["accepted"]))
        self.save()
        return line + "\nNOT ACCEPTED%s. Keep going: fix the biggest problem the numbers show." % (
            " - your DONE was premature" if why == "DONE" else "")

    # -- progress + RAMCHAT --------------------------------------------------
    def maybe_progress(self, rnd):
        if rnd - self.state["last_progress_round"] >= self.cfg["progress_every_rounds"]:
            self.write_progress(rnd)

    def write_progress(self, rnd):
        st = self.state
        le = st.get("last_eval")
        lines = ["> 🪟 BROKEN WINDOWS LAW: if it's not working, fix it immediately.", "",
                 "# KESHEV 7 - PROGRESS (rewritten by the runner every %d rounds)" % self.cfg["progress_every_rounds"],
                 "", "- updated: %s" % now_iso(), "- round: %d" % rnd,
                 "- halted: %s" % (st.get("halted") or "no"),
                 "- DONE-ACCEPTED: %d" % len(st["accepted"])]
        if le:
            lines.append("- last eval (round %s, %s): CER %.3f  WER %.3f  Hebrew-CER %s  clips %d  failed %d  bar %.2f"
                         % (le["round"], le.get("why"), le["cer"], le["wer"], le["cer_hebrew"], le["clips"],
                            le["failures"], le["bar_cer"]))
        else:
            lines.append("- last eval: none yet")
        lines.append("- stats: %s" % json.dumps(st["stats"]))
        lines += ["", "## What it built (the rally's own rolling summary)", "", st["summary"] or "(no summary yet)",
                  "", "## Sandbox top level", ""]
        try:
            for nm in sorted(os.listdir(self.sandbox))[:60]:
                p = os.path.join(self.sandbox, nm)
                size = dir_usage_bytes(p) if os.path.isdir(p) else os.path.getsize(p)
                lines.append("- %s%s  %.1f MB" % (nm, "/" if os.path.isdir(p) else "", size / 1e6))
        except OSError:
            pass
        lines += ["", "## Open questions (last 5 - see QUESTIONS.md)", ""]
        try:
            with open(os.path.join(self.sandbox, "QUESTIONS.md"), encoding="utf-8") as f:
                qs = [b for b in f.read().split("## Round ") if b.strip()]
            for b in qs[-5:]:
                lines.append("- Round " + b.strip().replace("\n", " ")[:400])
        except OSError:
            lines.append("- none")
        try:
            atomic_write_text(os.path.join(self.sandbox, "PROGRESS.md"), "\n".join(lines) + "\n")
        except OSError:
            pass
        st["last_progress_round"] = rnd
        self.save()

    def maybe_ramchat(self, force=False):
        c = self.cfg
        st = self.state
        now = time.time()
        if not force and now - st.get("last_ramchat_ts", 0) < c["ramchat_every_s"]:
            return
        st["last_ramchat_ts"] = now
        le = st.get("last_eval")
        text = ("kof-coder KESHEV7 round %d: last CER %s (bar %.2f), DONE-ACCEPTED %d, halted: %s. "
                "Progress file: ~/keshev7/PROGRESS.md on eran1."
                % (st["round"], ("%.3f" % le["cer"]) if le else "none", c["eval_bar_cer"],
                   len(st["accepted"]), st.get("halted") or "no"))
        if not c.get("ramchat_url"):
            self.emit({"t": "ramchat_skip", "why": "not configured"})
            return
        try:
            headers = {"Content-Type": "application/json"}
            if c.get("ramchat_token_file"):
                with open(c["ramchat_token_file"], encoding="utf-8") as f:
                    headers["Authorization"] = "Bearer " + f.read().strip()
            req = urllib.request.Request(c["ramchat_url"], headers=headers, data=json.dumps(
                {"who": c["ramchat_who"], "text": text}, ensure_ascii=False).encode("utf-8"))
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=5) as r:
                r.read()
            self.emit({"t": "ramchat_posted"})
        except Exception as e:
            self.emit({"t": "ramchat_skip", "why": str(e)[:200]})

    # -- the loop ----------------------------------------------------------
    def _nap(self, secs):
        end = time.time() + secs
        while time.time() < end and not self.stop_requested():
            time.sleep(min(1.0, max(0.0, end - time.time())))

    def run_forever(self, max_steps=None, install_signals=False):
        if install_signals:
            signal.signal(signal.SIGTERM, self.request_stop)
            signal.signal(signal.SIGINT, self.request_stop)
        if not self.seal.exists():
            self.state["halted"] = "not sealed - run: kof_headless.py seal"
            self.save()
        self.render_goal()
        self.note_goal_change()
        self.emit({"t": "start", "round": self.state["round"], "halted": self.state.get("halted")})
        backoff = 0
        steps = 0
        last_halt_note = 0
        while True:
            if self.state.get("halted"):
                if max_steps is not None:
                    return "halted"
                if time.time() - last_halt_note > 3600:
                    self.emit({"t": "halted", "why": self.state["halted"]})
                    last_halt_note = time.time()
                if self.stop_requested():
                    return "stop"
                self._nap(60)
                continue
            r = self.step()
            steps += 1
            if r == "stop":
                self.save()
                return "stop"
            if r == "brain_error":
                seq = self.cfg["brain_backoff_s"] or [30]
                self._nap(seq[min(backoff, len(seq) - 1)])
                backoff += 1
            else:
                backoff = 0
            if max_steps is not None and steps >= max_steps:
                return "halted" if self.state.get("halted") else "max_steps"
            self._nap(self.cfg["min_round_gap_s"])


# ============================================================================
# CLI
# ============================================================================
def main(argv):
    cmd = argv[0] if argv else "help"
    cfg = load_config()
    if cmd == "run":
        r = Rally(cfg, verbose=True)
        print("kof_headless: %s" % r.run_forever(install_signals=True), flush=True)
    elif cmd == "steps":
        r = Rally(cfg, verbose=True)
        print("kof_headless: %s" % r.run_forever(max_steps=int(argv[1]), install_signals=True))
    elif cmd == "check-cmd":
        ok, why = Guard(cfg).check_command(argv[1])
        print(why)
        sys.exit(0 if ok else 1)
    elif cmd in ("seal", "reseal"):
        apply_permissions(cfg)
        Seal(cfg).save()
        if cmd == "reseal":
            r = Rally(cfg)
            print("was halted: %s" % r.state.get("halted"))
            r.state["halted"] = None
            r.save()
        print("sealed: %s" % Seal(cfg).path)
    elif cmd == "verify-seal":
        d = Seal(cfg).verify()
        print("\n".join(d) if d else "seal OK")
        sys.exit(1 if d else 0)
    elif cmd == "status":
        st = Rally(cfg).state
        print(json.dumps({k: st.get(k) for k in ("round", "halted", "last_eval", "accepted", "stats",
                                                  "updated", "pending_round")}, ensure_ascii=False, indent=1))
    elif cmd == "eval-now":
        r = Rally(cfg, verbose=True)
        print(json.dumps(r.run_eval(r.state["round"], "manual"), ensure_ascii=False, indent=1))
    elif cmd == "brain-ping":
        b = BrainClient(cfg)
        print(repr(b.chat([{"role": "user", "content": "Reply with the single word PONG."}])[:200]), b.last_url)
    elif cmd == "render-goal":
        print(Rally(cfg).render_goal()[:400])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])

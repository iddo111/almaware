#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMAWARE fleet Claude dispatcher.

Runs `claude -p "<TASK>"` on the DGX fleet (eran1..eran4) over SSH, in
parallel, and collects the answers on the PC.

Usage:
  python dispatch.py --all "TASK"              run TASK on every reachable node
  python dispatch.py --node eran3 "TASK"       one node
  python dispatch.py --nodes eran2,eran4 "TASK"
  python dispatch.py --json --all "TASK"       structured JSON results
  python dispatch.py --status                  reachability + Claude presence (no task)
  python dispatch.py --timeout 300 --all "..." per-node task timeout (seconds)

Node config: D:\\CLAUDE\\fleet\\dispatch_nodes.json (edit IPs there — DHCP drifts).
If that file is missing/broken, built-in defaults are used.

100%% ours. Pure stdlib. Never crashes on a bad node.

SAFETY: dispatches sandboxed `claude -p` agent tasks only. It must NOT be used
for destructive fleet commands, must NOT touch Eran's training or the mic, and
every task runs under a timeout.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
NODES_FILE = os.path.join(HERE, "dispatch_nodes.json")

# ---------------------------------------------------------------- defaults --

DEFAULT_CONFIG = {
    "ssh_key": r"C:\Users\<user>\.ssh\id_ed25519",
    "connect_timeout_s": 8,
    "task_timeout_s": 120,
    "nodes": [
        {"name": "eran1", "host": "<lan-ip>", "user": "eran1"},
        {"name": "eran2", "host": "<tailnet-ip>", "user": "eran2"},  # 2026-09-11 WAVE A2: address came from D:/CLAUDE/fleet_inventory.json (tailnet = stable; the LAN lease moved on 09-10).,
        {"name": "eran3", "host": "<fabric-ip>", "user": "eran3",
         "proxy_via": "eran1@<lan-ip>"},
        {"name": "eran4", "host": "<lan-ip>", "user": "eran4"},
        {"name": "laptop", "host": "<tailnet-ip>", "user": "iddo1",
         "blocked": "key-exchange not completed yet; Claude may not be installed there"},
        {"name": "grok", "host": None, "user": None,
         "blocked": "no xAI credits; Grok OIDC login will not transfer headless. "
                    "Only the LOCAL Grok-1 rpc-server runs as an inference model "
                    "(not a CLI agent)."},
        {"name": "gemini", "host": None, "user": None,
         "blocked": "no Gemini API key"},
    ],
}

# ------------------------------------------------------------------- config --


def load_config():
    """dispatch_nodes.json override if present + parseable, else defaults."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    try:
        with open(NODES_FILE, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        if isinstance(user_cfg, dict):
            for key in ("ssh_key", "connect_timeout_s", "task_timeout_s"):
                if key in user_cfg:
                    cfg[key] = user_cfg[key]
            if isinstance(user_cfg.get("nodes"), list) and user_cfg["nodes"]:
                cfg["nodes"] = [n for n in user_cfg["nodes"]
                                if isinstance(n, dict) and n.get("name")]
    except FileNotFoundError:
        pass
    except Exception as e:  # bad JSON etc. — fall back, warn, never crash
        print("[warn] could not read %s (%s) — using built-in defaults"
              % (NODES_FILE, e), file=sys.stderr)
    return cfg


def find_ssh():
    exe = shutil.which("ssh")
    if exe:
        return exe
    for cand in (r"C:\Windows\System32\OpenSSH\ssh.exe", "/usr/bin/ssh"):
        if os.path.exists(cand):
            return cand
    return "ssh"  # last resort; subprocess will report the failure cleanly


# ---------------------------------------------------------------- ssh layer --

# OpenSSH >=9.9 prints a post-quantum key-exchange warning block; also filter
# the accept-new host-key notice. These are transport noise, not the answer.
_NOISE_MARKERS = (
    "post-quantum",
    "store now, decrypt later",
    "openssh.com/pq.html",
    "warning: permanently added",
)


def _clean(text):
    lines = []
    for ln in (text or "").splitlines():
        low = ln.lower()
        if any(m in low for m in _NOISE_MARKERS):
            continue
        if ln.startswith("** "):  # remainder of the PQ warning block
            continue
        lines.append(ln)
    return "\n".join(lines).strip()


def _shell_escape_dq(task):
    """Escape TASK for embedding inside remote double quotes."""
    out = task.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("$", "\\$").replace("`", "\\`")
    return out


def build_ssh_cmd(cfg, node, remote_cmd):
    key = cfg.get("ssh_key", DEFAULT_CONFIG["ssh_key"])
    command = [
        find_ssh(),
        "-F", "none",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=%d" % int(cfg.get("connect_timeout_s", 8)),
        "-o", "StrictHostKeyChecking=accept-new",
        "-i", key,
    ]
    # DGX3 is currently reachable only over DGX1's private fabric.
    if node.get("proxy_via"):
        proxy = "%s -F none -o BatchMode=yes -o ConnectTimeout=%d -o StrictHostKeyChecking=accept-new -i %s %s -W %%h:%%p" % (
            find_ssh(), int(cfg.get("connect_timeout_s", 8)), key, node["proxy_via"]
        )
        command += ["-o", "ProxyCommand=" + proxy]
    return command + ["%s@%s" % (node["user"], node["host"]), remote_cmd]


def run_on_node(cfg, node, task, timeout_s):
    """Run one claude -p task on one node. Always returns a result dict."""
    name = node.get("name", "?")
    res = {"node": name, "ok": False, "answer": "", "ms": 0, "error": None}
    if node.get("blocked"):
        res["error"] = "BLOCKED: %s" % node["blocked"]
        return res
    if not node.get("host") or not node.get("user"):
        res["error"] = "no host/user configured"
        return res

    # </dev/null: claude -p otherwise stalls waiting for piped stdin over ssh
    remote = ('export PATH=~/.npm-global/bin:$PATH; claude -p "%s" < /dev/null'
              % _shell_escape_dq(task))
    cmd = build_ssh_cmd(cfg, node, remote)
    t0 = time.time()
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
            encoding="utf-8", errors="replace", timeout=timeout_s,
        )
        res["ms"] = int((time.time() - t0) * 1000)
        out = _clean(p.stdout)
        err = _clean(p.stderr)
        if "not logged in" in (out + err).lower():
            res["error"] = ("NODE NOT LOGGED IN: claude on %s needs re-login "
                            "(OAuth token expired). Fix on the node itself." % name)
            res["answer"] = out
        elif p.returncode == 0:
            res["ok"] = True
            res["answer"] = out
        elif p.returncode == 255 and not out:
            res["error"] = "OFFLINE / ssh failed: %s" % (err or "no route")
        else:
            res["error"] = "exit %d: %s" % (p.returncode, err or out or "no output")
            res["answer"] = out
    except subprocess.TimeoutExpired as e:
        res["ms"] = int((time.time() - t0) * 1000)
        partial = e.stdout or b""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        res["answer"] = _clean(partial)
        res["error"] = "TIMEOUT after %ds" % timeout_s
        if "not logged in" in res["answer"].lower():
            res["error"] += " (node printed 'Not logged in' — claude needs re-login on %s)" % name
    except Exception as e:
        res["ms"] = int((time.time() - t0) * 1000)
        res["error"] = "dispatch error: %s" % e
    return res


def status_of_node(cfg, node):
    """Reachability + Claude presence check (no task)."""
    name = node.get("name", "?")
    res = {"node": name, "ok": False, "answer": "", "ms": 0, "error": None}
    if node.get("blocked"):
        res["error"] = "BLOCKED: %s" % node["blocked"]
        return res
    if not node.get("host") or not node.get("user"):
        res["error"] = "no host/user configured"
        return res
    remote = ("export PATH=~/.npm-global/bin:$PATH; "
              "v=$(claude --version 2>/dev/null | head -n1); "
              'if [ -n "$v" ]; then echo "CLAUDE_OK $v"; else echo NO_CLAUDE; fi')
    cmd = build_ssh_cmd(cfg, node, remote)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL,
                           encoding="utf-8", errors="replace", timeout=30)
        res["ms"] = int((time.time() - t0) * 1000)
        out = _clean(p.stdout)
        if p.returncode == 0 and out.startswith("CLAUDE_OK"):
            res["ok"] = True
            res["answer"] = "reachable, %s" % out.replace("CLAUDE_OK", "claude").strip()
        elif p.returncode == 0:
            res["error"] = "reachable but Claude NOT found on PATH"
        else:
            res["error"] = "OFFLINE: %s" % (_clean(p.stderr) or "ssh exit %d" % p.returncode)
    except subprocess.TimeoutExpired:
        res["ms"] = int((time.time() - t0) * 1000)
        res["error"] = "OFFLINE: status check timed out"
    except Exception as e:
        res["error"] = "dispatch error: %s" % e
    return res


# ----------------------------------------------------------------- driving --


def select_nodes(cfg, args):
    nodes = cfg["nodes"]
    by_name = {n["name"]: n for n in nodes}
    if args.node:
        wanted = [args.node]
    elif args.nodes:
        wanted = [w.strip() for w in args.nodes.split(",") if w.strip()]
    else:  # --all / --status
        return nodes
    picked, missing = [], []
    for w in wanted:
        (picked if w in by_name else missing).append(by_name.get(w, w))
    for m in missing:
        print("[warn] unknown node %r (known: %s)" % (m, ", ".join(by_name)),
              file=sys.stderr)
    return picked


def run_parallel(fn, cfg, nodes, *extra):
    results = {}
    if not nodes:
        return []
    with ThreadPoolExecutor(max_workers=max(1, len(nodes))) as pool:
        futs = {pool.submit(fn, cfg, n, *extra): n["name"] for n in nodes}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                results[name] = fut.result()
            except Exception as e:  # belt and braces — never crash
                results[name] = {"node": name, "ok": False, "answer": "",
                                 "ms": 0, "error": "internal: %s" % e}
    return [results[n["name"]] for n in nodes if n["name"] in results]


def print_results(results, status_mode=False):
    ok_n = sum(1 for r in results if r["ok"])
    blocked_n = sum(1 for r in results if (r["error"] or "").startswith("BLOCKED"))
    bad_n = len(results) - ok_n - blocked_n
    print("=" * 62)
    print("FLEET %s: %d ok / %d blocked / %d failed (of %d)"
          % ("STATUS" if status_mode else "DISPATCH", ok_n, blocked_n, bad_n, len(results)))
    print("=" * 62)
    for r in results:
        if r["ok"]:
            tag = "OK     "
        elif (r["error"] or "").startswith("BLOCKED"):
            tag = "BLOCKED"
        else:
            tag = "FAIL   "
        head = "[%s] %-7s %6d ms" % (tag, r["node"], r["ms"])
        print(head + ("  %s" % r["error"] if r["error"] else ""))
        if r["answer"]:
            if status_mode:
                print("         " + r["answer"])
            else:
                print("-" * 62)
                print(r["answer"])
                print("-" * 62)
    sys.stdout.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="dispatch.py",
        description="Run Claude tasks across the ALMAWARE DGX fleet (parallel ssh).")
    who = ap.add_mutually_exclusive_group()
    who.add_argument("--all", action="store_true", help="all dispatchable nodes")
    who.add_argument("--node", metavar="NAME", help="single node, e.g. eran3")
    who.add_argument("--nodes", metavar="A,B", help="comma list, e.g. eran2,eran4")
    ap.add_argument("--status", action="store_true",
                    help="check reachability + Claude presence; no task")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="emit structured JSON results")
    ap.add_argument("--timeout", type=int, default=None, metavar="S",
                    help="per-node task timeout in seconds (default from config, 120)")
    ap.add_argument("task", nargs="?", default=None, help="the task/prompt for claude -p")
    args = ap.parse_args(argv)

    cfg = load_config()
    timeout_s = args.timeout or int(cfg.get("task_timeout_s", 120))

    if args.status:
        nodes = select_nodes(cfg, args)
        results = run_parallel(status_of_node, cfg, nodes)
        if args.as_json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            print_results(results, status_mode=True)
        return 0

    if not args.task:
        ap.error("a TASK is required (or use --status)")
    if not (args.all or args.node or args.nodes):
        ap.error("pick targets: --all, --node NAME, or --nodes A,B")

    nodes = select_nodes(cfg, args)
    if args.all:  # --all means every *dispatchable* node; blocked are reported, not run
        pass  # keep blocked in the list so the summary shows them honestly
    results = run_parallel(run_on_node, cfg, nodes, args.task, timeout_s)

    if args.as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_results(results)
    if not results:
        return 2  # nothing matched the selection
    return 0 if any(r["ok"] for r in results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[abort] interrupted", file=sys.stderr)
        sys.exit(130)

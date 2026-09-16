"""Conservative, one-shot RAMCHAT and popup evidence audit.

This tool is intentionally observation-only except for its timestamped report.
"""
from __future__ import annotations

import ctypes
import json
import mmap
import os
import re
import struct
import subprocess
import sys
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
MAPS = (
    ("RAMCHAT_COUNCIL_V1", 16 * 1024 * 1024, b"RAMCHAT1", ("schema", "transcript", "shared_memory")),
    ("RAMCHAT_QUEUE_V1", 8 * 1024 * 1024, b"RAMQUEU1", ("schema", "items")),
)


def mapping_check(name, size, magic, required):
    try:
        with mmap.mmap(-1, size, tagname=name, access=mmap.ACCESS_READ) as view:
            actual = view[:8]
            if actual != magic:
                return {"ok": False, "error": "bad_magic"}
            length = struct.unpack("<Q", view[8:16])[0]
            if length <= 0 or length > size - 16:
                return {"ok": False, "error": "payload_out_of_bounds", "bytes": length}
            payload = json.loads(view[16:16 + length].decode("utf-8", errors="strict"))
            if not isinstance(payload, dict) or payload.get("schema") != 1:
                return {"ok": False, "error": "invalid_json_object_or_schema", "bytes": length}
            missing = [key for key in required if key not in payload]
            if missing:
                return {"ok": False, "error": "missing_required_keys", "missing": missing, "bytes": length}
            return {"ok": True, "magic": magic.decode(), "bytes": length, "schema": payload["schema"], "required_keys": list(required)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}


def ps(script):
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=35)
    if result.returncode:
        return {"error": (result.stderr or result.stdout).strip()[-1500:]}
    return json.loads(result.stdout) if result.stdout.strip() else []


def windows():
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    rows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        n = user32.GetWindowTextLengthW(hwnd)
        if not n: return True
        title = ctypes.create_unicode_buffer(n + 1); user32.GetWindowTextW(hwnd, title, n + 1)
        klass = ctypes.create_unicode_buffer(256); user32.GetClassNameW(hwnd, klass, 256)
        pid = wintypes.DWORD(); user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rows.append({"title": title.value, "class": klass.value, "pid": pid.value})
        return True
    user32.EnumWindows(callback_type(visit), 0)
    return rows


def main():
    now = datetime.now().astimezone()
    ipc_before = {name: mapping_check(name, size, magic, required) for name, size, magic, required in MAPS}
    ramchat_processes = ps("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | ? {$_.CommandLine -match 'D:\\\\CLAUDE\\\\RAMCHAT\\\\ramchat\\.pyw'} | % {[pscustomobject]@{pid=$_.ProcessId;name=$_.Name;path=$_.ExecutablePath;command_line=$_.CommandLine;created=$_.CreationDate}} | ConvertTo-Json -Compress")
    if isinstance(ramchat_processes, dict):
        ramchat_processes = [ramchat_processes]
    # The supplied launcher is the only recovery action and is used at most once.
    recovery = "not_required"
    if not all(x["ok"] for x in ipc_before.values()):
        launcher = ROOT / "launch_ramchat.cmd"
        try:
            subprocess.run(["cmd", "/c", str(launcher)], check=True, timeout=20)
            recovery = "launch_ramchat.cmd_run_once_after_mapping_failure"
        except Exception as exc:
            recovery = "launcher_error: " + type(exc).__name__ + ": " + str(exc)
        # One and only one post-launch validation; no retry loop.
        ipc = {name: mapping_check(name, size, magic, required) for name, size, magic, required in MAPS}
    else:
        ipc = ipc_before
    win = windows()
    pids = sorted({x["pid"] for x in win if x["pid"]})
    proc_script = "$p=@(" + ",".join(map(str, pids)) + "); Get-CimInstance Win32_Process | ? {$p -contains $_.ProcessId} | % {$s=if($_.ExecutablePath){(Get-AuthenticodeSignature -LiteralPath $_.ExecutablePath).Status.ToString()}else{'Unavailable'};[pscustomobject]@{pid=$_.ProcessId;name=$_.Name;path=$_.ExecutablePath;signature=[string]$s}} | ConvertTo-Json -Compress"
    procs = ps(proc_script)
    if isinstance(procs, dict): procs = [procs]
    bypid = {x.get("pid"): x for x in procs if isinstance(x, dict)}
    # CIM can be unavailable in the local constrained session.  Preserve the
    # window evidence and obtain a direct signature status for known paths.
    paths = sorted({p.get("path") for p in procs if isinstance(p, dict) and p.get("path")})
    signatures = {}
    for path in paths:
        escaped = path.replace("'", "''")
        status = ps("(Get-AuthenticodeSignature -LiteralPath '" + escaped + "').Status.ToString()")
        signatures[path] = status if isinstance(status, str) else "Unavailable"
    for row in win:
        p = bypid.get(row["pid"], {})
        row.update({"process": p.get("name"), "path": p.get("path"), "signature": p.get("signature") or signatures.get(p.get("path"), "Unavailable")})
        row["suspicious_title_match"] = bool(re.search(r"(virus|malware|defender|security alert|credential|password|uac|consent)", row["title"], re.I))
        row["protected_system_or_consent_ui"] = bool(re.search(r"(Windows Security|User Account Control|credential|password|permission|consent)", row["title"], re.I))
    events_script = "$start=(Get-Date).AddHours(-48); $sets=@(@{LogName='Application';Id=1000,1001,1002},@{LogName='Microsoft-Windows-Windows Defender/Operational';Id=1116,1117,1118,1119},@{LogName='Microsoft-Windows-CodeIntegrity/Operational';Id=3010,3033,3084,3089,3099,3116}); $sets | % {Get-WinEvent -FilterHashtable @{LogName=$_.LogName;Id=$_.Id;StartTime=$start} -ErrorAction SilentlyContinue} | Select TimeCreated,Id,ProviderName,LevelDisplayName,Message | ConvertTo-Json -Compress"
    events = ps(events_script)
    if isinstance(events, dict) and "error" in events: event_summary = events
    else:
        if isinstance(events, dict): events = [events]
        event_summary = {"count": len(events), "by_id": {}}
        for item in events: event_summary["by_id"][str(item.get("Id"))] = event_summary["by_id"].get(str(item.get("Id")), 0) + 1
    log = Path(r"D:\CLAUDE\tools\watchdogs\logs\popup-safe.jsonl")
    log_info = {"exists": log.exists(), "last_write": datetime.fromtimestamp(log.stat().st_mtime).astimezone().isoformat() if log.exists() else None}
    # Preserve timestamped, read-only evidence in the report.  Limit retained popup
    # history to recent structured records and omit arbitrary payload fields.
    popup_recent = []
    if log.exists():
        try:
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]:
                record = json.loads(line)
                popup_recent.append({key: record.get(key) for key in ("timestamp", "event", "title", "window_class", "process_id", "process_name", "process_path", "action") if key in record})
        except Exception as exc:
            popup_recent = [{"read_error": type(exc).__name__ + ": " + str(exc)}]
    event_records = []
    for item in events if 'events' in locals() else []:
        message = str(item.get("Message") or "").replace("\r", " ").replace("\n", " ")
        event_records.append({
            "timestamp": item.get("TimeCreated"), "id": item.get("Id"),
            "provider": item.get("ProviderName"), "level": item.get("LevelDisplayName"),
            "message_excerpt": message[:500],
        })
    report = {"run": now.isoformat(), "scope": "evidence audit; no popup watchdog, toast, window closure, policy/configuration change, or external publication", "ramchat_processes": ramchat_processes, "ramchat_ipc_before": ipc_before, "ramchat_ipc": ipc, "restart": recovery, "windows": win, "event_summary_48h": event_summary, "events_48h": event_records, "popup_log": log_info, "popup_log_recent": popup_recent, "popup_attribution": "UNKNOWN"}
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / ("ramchat-watchdog-" + now.strftime("%Y%m%d-%H%M%S") + ".json")
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(path), "ipc": ipc, "window_count": len(win), "suspicious_windows": sum(x["suspicious_title_match"] for x in win), "event_summary": event_summary, "popup_log": log_info}, ensure_ascii=False))

if __name__ == "__main__": main()

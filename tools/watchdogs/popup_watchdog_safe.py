"""Windowless, evidence-only popup monitor. Never closes or creates UI."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import time
from ctypes import wintypes
from pathlib import Path

LOG = Path(r"D:\CLAUDE\tools\watchdogs\logs\popup-safe.jsonl")
MUTEX_NAME = "Local\\ALMA_SAFE_POPUP_MONITOR_V1"
SUSPICIOUS = (
    "update available", "install now", "free upgrade", "your pc is at risk",
    "virus detected", "call support", "claim your prize", "driver update",
    "pc optimizer", "registry cleaner", "one-click fix",
)
PROTECTED = (
    "user account control", "windows security", "microsoft defender",
    "credential", "password", "passkey", "sign in", "permission", "consent",
)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumProc, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]


def process_path(pid: int) -> str:
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return "[unavailable]"
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return "[unavailable]"
    finally:
        kernel32.CloseHandle(handle)


def visible_windows() -> list[dict]:
    records: list[dict] = []

    @EnumProc
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        title = title_buffer.value.strip()
        if not title:
            return True
        class_buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, class_buffer, len(class_buffer))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        path = process_path(pid.value)
        lower = title.lower()
        records.append({
            "handle": int(hwnd),
            "title": title,
            "window_class": class_buffer.value,
            "process_id": int(pid.value),
            "process_name": Path(path).stem if path != "[unavailable]" else path,
            "process_path": path,
            "suspicious_title_match": next((item for item in SUSPICIOUS if item in lower), None),
            "protected_system_or_consent_ui": any(item in lower for item in PROTECTED),
        })
        return True

    user32.EnumWindows(callback, 0)
    return records


def write_record(record: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not mutex or ctypes.get_last_error() == 183:
        return 0
    seen: dict[str, dict] = {}
    while True:
        current: dict[str, dict] = {}
        for window in visible_windows():
            key = f"{window['handle']}|{window['title']}"
            current[key] = window
            if key not in seen:
                write_record({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "event": "appeared",
                    **window,
                    "action": "none_evidence_only",
                })
        for key in seen.keys() - current.keys():
            write_record({
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "event": "disappeared",
                "window_key": key,
                "action": "none_evidence_only",
            })
        seen = current
        if args.once:
            return 0
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())

"""KESHEV 2 configstore — CAS writes, HALT on corrupt, NO hot reload.

The ONE legal place in this repo that writes config JSON (lint gate G3).
Ruling D-005; every law here was paid for in A's archaeology:

  scar 39  No write-on-exit, no dataclass round-trip. The file is read as a
           raw dict and written back as that same dict with exactly one key
           changed — unknown keys are structurally incapable of vanishing
           (asdict-on-exit deleted beam_size three times in A's ancestors).
           Every write is compare-and-swap on `revision` and appends
           {ts,key,old,new,reason,author,revision} to config_history.jsonl.
  scar 40  Corrupt/missing/invalid config -> HALT (ConfigHaltError). There
           is NO defaults path in this module: nothing here can construct a
           config that did not come from the file. (The silent-defaults
           fallback once yielded a gate 12x above speech RMS — a deaf mic
           with no error message.)
  scar 42  No .bak files ever; atomic write = tmp file + os.replace in the
           same directory; LKG is a git tag, not a snapshot system.

  THE NO-HOT-RELOAD CONTRACT (D-005, explicit): a successful `set_key`
  changes the FILE, not any running process. The returned receipt says
  `takes_effect="restart"`, and when an emit callable is provided the
  write journals CONFIG_STALE — the live process is now knowingly running
  the OLD value. A staged fix that "didn't take" is a read-the-journal
  fact, never a surprise (A inherited this as an unspoken open window;
  K2 speaks it).

Schema (tonight's keys — new knobs are code under git, not config):
  server_url            http://<fleet-host>:8737  (never 0.0.0.0)
  server_token_path     file whose content is the bearer token
  lang_hint_default     "he" | "en" — "auto" is REFUSED at schema level
                        (D-004: the auto scar is measured; a config file
                        must not be able to re-open it)
  armed_mode            bool — the B-verdict layer, first-class (D-003)
  enter_idle_limit_s    30..3600   (D-003 default 120)
  type_idle_limit_s     60..7200   (D-003 default 600; must be > enter)
  arm_timeout_s         60..7200   (D-003 default 900; 0 forbidden — an
                        arm that never expires re-creates 09:46)
  never_use_devices_extra  list[str] — ADDITIVE denials only; the source
                        tuple in devicelaw.py is above this file's reach
  revision              int, CAS-managed, never set directly

stdlib only.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, NamedTuple, Optional
from urllib.parse import urlsplit

TAKES_EFFECT = "restart"        # the contract, greppable


class ConfigError(Exception):
    """Base for every configstore refusal — always loud, never swallowed."""


class ConfigHaltError(ConfigError):
    """Missing/corrupt/invalid file. The app HALTS visibly; it never runs
    deaf on defaults (scar 40)."""


class ConfigCasError(ConfigError):
    """revision on disk != revision the writer read — a concurrent write
    happened. Loud, retryable by re-reading; never silently merged."""


class ConfigValueError(ConfigError):
    """A set_key value violates the schema."""


# ------------------------------------------------------------- validators


def _v_server_url(v: Any) -> str:
    if not isinstance(v, str):
        raise ConfigValueError(f"server_url must be str, got {type(v).__name__}")
    parts = urlsplit(v)
    if parts.scheme != "http" or not parts.hostname:
        raise ConfigValueError(f"server_url must be http://host[:port], got {v!r}")
    if parts.hostname in ("0.0.0.0", ""):
        raise ConfigValueError("server_url may not be 0.0.0.0")
    return v


def _v_token_path(v: Any) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ConfigValueError("server_token_path must be a non-empty str")
    return v


def _v_lang_hint(v: Any) -> str:
    # D-004: "auto" is refused HERE, at the schema, so a config file cannot
    # re-open the measured transliteration scar. Not a tuple to loop over —
    # the refusal message names the scar.
    if v == "auto":
        raise ConfigValueError(
            "lang_hint_default='auto' is refused: hint=auto transliterated "
            "Hebrew on 2026-08-16 (measured). Only 'he' or 'en'.")
    if v not in ("he", "en"):
        raise ConfigValueError(f"lang_hint_default must be 'he'|'en', got {v!r}")
    return v


def _v_bool(name: str) -> Callable[[Any], bool]:
    def check(v: Any) -> bool:
        if not isinstance(v, bool):
            raise ConfigValueError(f"{name} must be bool, got {type(v).__name__}")
        return v
    return check


def _v_range(name: str, lo: float, hi: float) -> Callable[[Any], float]:
    def check(v: Any) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ConfigValueError(f"{name} must be a number, got {type(v).__name__}")
        if not (lo <= v <= hi):
            raise ConfigValueError(f"{name}={v} outside [{lo}, {hi}]")
        return float(v)
    return check


def _v_extra_list(v: Any) -> list:
    if not isinstance(v, list) or not all(isinstance(s, str) for s in v):
        raise ConfigValueError("never_use_devices_extra must be a list of str")
    return v


SCHEMA: Mapping[str, Callable[[Any], Any]] = {
    "server_url": _v_server_url,
    "server_token_path": _v_token_path,
    "lang_hint_default": _v_lang_hint,
    "armed_mode": _v_bool("armed_mode"),
    "enter_idle_limit_s": _v_range("enter_idle_limit_s", 30, 3600),
    "type_idle_limit_s": _v_range("type_idle_limit_s", 60, 7200),
    "arm_timeout_s": _v_range("arm_timeout_s", 60, 7200),
    "never_use_devices_extra": _v_extra_list,
}

_REQUIRED = frozenset(SCHEMA) | {"revision"}


class WriteReceipt(NamedTuple):
    key: str
    old: Any
    new: Any
    revision: int               # the NEW revision on disk
    takes_effect: str           # always TAKES_EFFECT — the contract


class ConfigStore:
    """Reader + the one writer. `load()` returns an immutable snapshot;
    mutating a snapshot is a TypeError, and no code path writes the file
    except `set_key` (lint gate G3 patrols the rest of the repo)."""

    def __init__(self, path: str | Path,
                 emit: Optional[Callable[..., None]] = None) -> None:
        self.path = Path(path)
        self.history_path = self.path.with_name("config_history.jsonl")
        self._emit = emit

    # ------------------------------------------------------------- reading

    def load(self) -> Mapping[str, Any]:
        """Read + validate. Returns a read-only mapping. HALT on anything
        wrong — missing file, bad JSON, missing key, invalid value."""
        raw = self._read_raw()
        for key, validate in SCHEMA.items():
            if key not in raw:
                raise ConfigHaltError(f"config missing required key {key!r} "
                                      f"— HALT (no defaults path exists)")
            try:
                validate(raw[key])
            except ConfigValueError as exc:
                # At LOAD time an invalid value is a HALT like any other
                # corruption (scar 40): the app must refuse to run, not
                # crash with a stack trace. The refusal text rides along.
                raise ConfigHaltError(f"config invalid: {exc}") from exc
        rev = raw.get("revision")
        if not isinstance(rev, int) or rev < 0:
            raise ConfigHaltError(f"config revision must be a non-negative "
                                  f"int, got {rev!r}")
        # Cross-field law (D-003): the type limit must exceed the enter
        # limit, or the "type but never Enter" band is empty and the
        # presence gate silently loses its cheap half.
        if raw["type_idle_limit_s"] <= raw["enter_idle_limit_s"]:
            raise ConfigHaltError(
                "type_idle_limit_s must be > enter_idle_limit_s — the "
                "type-without-Enter band must exist (D-003)")
        return MappingProxyType(dict(raw))

    def _read_raw(self) -> dict[str, Any]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ConfigHaltError(
                f"config file absent: {self.path} — HALT (scar 40: the app "
                f"never runs on defaults)") from exc
        except OSError as exc:
            raise ConfigHaltError(f"config unreadable: {exc}") from exc
        try:
            raw = json.loads(text)
        except ValueError as exc:
            raise ConfigHaltError(
                f"config is not valid JSON ({exc}) — HALT, fix or restore "
                f"via git tag lkg (scar 42)") from exc
        if not isinstance(raw, dict):
            raise ConfigHaltError(f"config root must be an object, got "
                                  f"{type(raw).__name__}")
        return raw

    # ------------------------------------------------------------- writing

    def set_key(self, key: str, value: Any, *, reason: str, author: str,
                expected_revision: int) -> WriteReceipt:
        """The ONE write path. CAS on revision; exactly one key changes;
        unknown keys ride through untouched; history appended; atomic
        replace; CONFIG_STALE journalled. Takes effect on RESTART only."""
        if not reason or not reason.strip():
            raise ConfigValueError("a write without --reason is refused "
                                   "(scar 42: 22 unlabeled interventions)")
        if key == "revision":
            raise ConfigValueError("revision is CAS-managed, never set")
        if key not in SCHEMA:
            raise ConfigValueError(
                f"unknown key {key!r}: new knobs are code under git, not "
                f"config writes")
        value = SCHEMA[key](value)

        raw = self._read_raw()          # fresh read — CAS against DISK
        disk_rev = raw.get("revision")
        if disk_rev != expected_revision:
            raise ConfigCasError(
                f"revision on disk is {disk_rev}, writer expected "
                f"{expected_revision} — someone wrote in between; re-read")

        old = raw.get(key)
        raw[key] = value
        raw["revision"] = int(disk_rev) + 1

        # cross-field law enforced on write too, not only on load
        if ("type_idle_limit_s" in raw and "enter_idle_limit_s" in raw
                and raw["type_idle_limit_s"] <= raw["enter_idle_limit_s"]):
            raise ConfigValueError(
                "write refused: type_idle_limit_s must stay > "
                "enter_idle_limit_s (D-003)")

        self._atomic_write(raw)
        self._append_history(key=key, old=old, new=value, reason=reason,
                             author=author, revision=raw["revision"])
        if self._emit is not None:
            self._emit("CONFIG_STALE", key=key, revision=raw["revision"],
                       takes_effect=TAKES_EFFECT)
        return WriteReceipt(key=key, old=old, new=value,
                            revision=raw["revision"],
                            takes_effect=TAKES_EFFECT)

    # ------------------------------------------------------------ internals

    def _atomic_write(self, raw: dict[str, Any]) -> None:
        """tmp file + os.replace IN THE SAME DIRECTORY (scar 42 — atomic on
        NTFS; no .bak, no second copy)."""
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent),
                                   prefix=self.path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(raw, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError as cleanup_exc:
                # recorded, not swallowed (lint G1): the tmp file leaks but
                # the original config is untouched — say so and re-raise.
                raise ConfigError(
                    f"atomic write failed AND tmp cleanup failed: "
                    f"{cleanup_exc}") from cleanup_exc
            raise

    def _append_history(self, **entry: Any) -> None:
        entry["ts"] = datetime.now().astimezone().isoformat(
            timespec="milliseconds")
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with open(self.history_path, "a", encoding="utf-8") as fh:
            fh.write(line)

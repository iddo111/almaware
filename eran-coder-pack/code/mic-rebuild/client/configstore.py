"""KESHEV configstore — K1 (PHASE2-DESIGN.md section 5, scars 39-42).

The ONE legal place in the repo that writes config JSON (lint gate G3).

Laws enforced here, each mapped to its scar:

  scar 39  No write-on-exit, no dataclass round-trip. The config is read as a
           raw dict and written back as that same dict with exactly one key
           changed — unknown keys are structurally incapable of vanishing.
           Every write is CAS on `revision` and appends
           {ts,key,old,new,reason,author,revision} to config_history.jsonl.
  scar 40  Corrupt/missing/invalid config -> HALT (MessageBox + exit 2).
           There is no defaults path in this module: nothing here can
           construct a config that did not come from the file.
  scar 41  gate_rms is a calibration-carrying object. A gate value at or
           below its recorded noise floor, or at or above recorded speech,
           is refused — on load and on set. Changing the value outside the
           band requires replacing the whole calibration record (a real
           recalibration). drift_check() compares the configured gate to a
           live-measured floor and returns a loud warning string.
  scar 42  LKG is the git tag; this module never writes *.bak* files —
           atomic write is tmp-file + os.replace in the same directory.

Design section 5 extras:
  * server_url validator rejects 0.0.0.0 and any non-fleet host.
  * owner_gate_typing=true is refused unless a PASS gate18-*.json report
    exists in the reports directory (criterion 18 / section 7a).
  * Exactly the 12 schema keys are settable; `revision` is CAS-managed,
    never set directly; unknown keys are preserved but not settable.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- errors

class ConfigError(Exception):
    """Base for every configstore refusal — always loud, never swallowed."""


class ConfigCorruptError(ConfigError):
    """File exists but is not parseable JSON / not a JSON object."""


class ConfigMissingError(ConfigCorruptError):
    """File absent. Same HALT class as corrupt (scar 40: no defaults)."""


class ConfigInvalidError(ConfigError):
    """Schema violation: missing key, wrong type, out of range, bad URL."""


class CalibrationError(ConfigError):
    """Gate value conflicts with its own recorded calibration band (scar 41)."""


class CASError(ConfigError):
    """Compare-and-swap refused: expected_revision != current revision."""


class RefusedError(ConfigError):
    """Policy refusal: unknown key, empty reason/author, guarded knob."""


# ---------------------------------------------------------------- schema
# The code constant IS the schema truth (design: knobs are code under git).
# config/client.schema.json is generated from this via schema_as_json() and
# a structural test asserts the two never drift.

_FLEET_HOSTS = ("127.0.0.1", "<lan-ip>", "<lan-ip>")
# 127.0.0.1 = the PC GPU STT server, CANONICAL since Iddo's order 2026-08-20 01:00
# ("תעביר את הפענוח לפיסי ושנה את החוקים בהתאם"). eran1 .198 = rollback, eran2 .59 =
# alternate. The law moved on 08-20 but this tuple did not, so on 08-21 a config that
# pointed anywhere local/off-list CONFIG_HALTed the client at every start (scar: the
# mic was silently dead from 08-21 19:13, and the logon task kept relaunching a
# client that could never boot).

_CALIBRATION_FIELDS = {
    "value": float,
    "calibrated_at": str,
    "method": str,
    "measured_floor": float,
    "measured_speech": float,
    "author": str,
}

SCHEMA: dict[str, dict[str, Any]] = {
    "revision": {"type": "int", "min": 0},
    "mic_name": {"type": "str"},
    "server_url": {"type": "url", "fleet_hosts": list(_FLEET_HOSTS)},
    "auth_token_file": {"type": "str"},
    "gate_rms": {"type": "calibration"},
    "stale_sec": {"type": "int", "min": 5, "max": 120},
    "hotkey_pause": {"type": "str"},
    "auto_enter": {"type": "bool"},
    "clipboard_restore": {"type": "bool"},
    "extra_avoid": {"type": "list[str]"},
    "corpus_capture": {"type": "bool"},
    "owner_gate_typing": {"type": "bool"},
    # lang_hint reached the live config on 2026-08-16 (the transliteration
    # scar: "סוכה" came back "suka") but only the schema FILE was edited —
    # the drift test caught the constant lagging. `optional` because every
    # config written before that date lacks the key and must stay loadable:
    # a REQUIRED new key would HALT the mic at the next restart (scar 40's
    # halt firing on the wrong target). Absent means the code default.
    "lang_hint": {"type": "str", "optional": True,
                  "choices": ["auto", "he", "en"]},
}


def schema_as_json() -> dict:
    """The exact object written to config/client.schema.json."""
    return json.loads(json.dumps(SCHEMA))


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _validate_calibration(key: str, rec: Any) -> None:
    if not isinstance(rec, dict):
        raise ConfigInvalidError(f"{key}: calibration record must be an object, got {type(rec).__name__}")
    missing = [f for f in _CALIBRATION_FIELDS if f not in rec]
    if missing:
        raise ConfigInvalidError(f"{key}: calibration record missing fields {missing}")
    for f, t in _CALIBRATION_FIELDS.items():
        v = rec[f]
        if t is float:
            if not _is_number(v):
                raise ConfigInvalidError(f"{key}.{f}: must be a number, got {type(v).__name__}")
        elif not isinstance(v, t) or (t is str and not v.strip()):
            raise ConfigInvalidError(f"{key}.{f}: must be a non-empty {t.__name__}")
    floor, speech, value = rec["measured_floor"], rec["measured_speech"], rec["value"]
    if not (0 <= floor < speech):
        raise ConfigInvalidError(
            f"{key}: measured_floor ({floor}) must be >= 0 and below measured_speech ({speech})")
    # scar 41: the band refusal — a gate inside its own noise band deafens
    # nothing and floods EMPTY decodes; a gate at/above speech deafens the mic.
    if value <= floor:
        raise CalibrationError(
            f"{key}: value {value} is inside the recorded noise band "
            f"(measured_floor={floor}) — gate=0.001 sat in ambient for 4 days (scar 41); "
            f"recalibrate or pick a value above the floor")
    if value >= speech:
        raise CalibrationError(
            f"{key}: value {value} is at/above recorded speech level "
            f"(measured_speech={speech}) — this is the deaf-gate failure (scar 40/41)")


def _validate_url(key: str, v: Any, spec: dict) -> None:
    if not isinstance(v, str) or not v.strip():
        raise ConfigInvalidError(f"{key}: must be a non-empty string URL")
    if not v.startswith("http://"):
        raise ConfigInvalidError(f"{key}: must be an http:// URL on the LAN, got {v!r}")
    hostport = v[len("http://"):].split("/", 1)[0]
    host = hostport.rsplit(":", 1)[0]
    if host == "0.0.0.0":
        raise ConfigInvalidError(f"{key}: 0.0.0.0 is rejected by design (section 5)")
    if host not in spec["fleet_hosts"]:
        raise ConfigInvalidError(
            f"{key}: host {host!r} is not a fleet host {spec['fleet_hosts']} (section 5)")


def _validate_value(key: str, v: Any) -> None:
    spec = SCHEMA[key]
    t = spec["type"]
    if t == "int":
        if not isinstance(v, int) or isinstance(v, bool):
            raise ConfigInvalidError(f"{key}: must be int, got {type(v).__name__}")
        if "min" in spec and v < spec["min"]:
            raise ConfigInvalidError(f"{key}: {v} below minimum {spec['min']}")
        if "max" in spec and v > spec["max"]:
            raise ConfigInvalidError(f"{key}: {v} above maximum {spec['max']}")
    elif t == "str":
        if not isinstance(v, str) or not v.strip():
            raise ConfigInvalidError(f"{key}: must be a non-empty string")
        if "choices" in spec and v not in spec["choices"]:
            raise ConfigInvalidError(
                f"{key}: {v!r} not in {spec['choices']} — an off-menu value "
                f"would fail per-utterance instead of at startup")
    elif t == "bool":
        if not isinstance(v, bool):
            raise ConfigInvalidError(f"{key}: must be true/false, got {type(v).__name__}")
    elif t == "list[str]":
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ConfigInvalidError(f"{key}: must be a list of strings")
    elif t == "url":
        _validate_url(key, v, spec)
    elif t == "calibration":
        _validate_calibration(key, v)
    else:  # pragma: no cover — schema authoring error
        raise ConfigInvalidError(f"{key}: unknown schema type {t!r}")


def validate(cfg: dict) -> None:
    """Full-config validation. Unknown keys pass through untouched (scar 39)."""
    if not isinstance(cfg, dict):
        raise ConfigCorruptError(f"config root must be an object, got {type(cfg).__name__}")
    missing = [k for k in SCHEMA
               if k not in cfg and not SCHEMA[k].get("optional")]
    if missing:
        raise ConfigInvalidError(f"config missing required keys: {missing}")
    for key in SCHEMA:
        if key not in cfg:
            continue                     # only optional keys can reach here
        _validate_value(key, cfg[key])


# ---------------------------------------------------------------- HALT (scar 40)

def _message_box(title: str, text: str) -> None:
    """Visible failure. Replaced by tests; ctypes on real Windows."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x00000010)  # MB_ICONERROR
    except Exception as e:  # headless/CI — stderr is still loud, never silent
        print(f"[configstore] MessageBox unavailable ({e!r})", file=sys.stderr)


def halt(message: str) -> "None":
    """The scar-40 HALT: visible error, exit 2. Never returns."""
    text = (f"{message}\n\nKESHEV refuses to run on a bad config — "
            f"there is NO fallback to defaults (scar 40). Fix or restore the "
            f"config (git checkout lkg) and relaunch.")
    print(f"CONFIG_HALT: {message}", file=sys.stderr)
    _message_box("KESHEV — CONFIG HALT", text)
    sys.exit(2)


# ---------------------------------------------------------------- the store

def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


class ConfigStore:
    """Read/CAS-write access to config/client.json (the only writer in the repo)."""

    def __init__(self, config_path: Path | str,
                 history_path: Path | str | None = None,
                 reports_dir: Path | str | None = None) -> None:
        self.config_path = Path(config_path)
        self.history_path = (Path(history_path) if history_path is not None
                             else self.config_path.parent / "config_history.jsonl")
        # gate18 reports live in state\reports by default (design section 2)
        self.reports_dir = (Path(reports_dir) if reports_dir is not None
                            else self.config_path.parent.parent / "state" / "reports")

    # ------------------------------------------------------------ read

    def load(self) -> dict:
        """Parse + validate. Raises; never substitutes defaults (scar 40)."""
        if not self.config_path.exists():
            raise ConfigMissingError(
                f"config file missing: {self.config_path} — no defaults exist")
        raw = self.config_path.read_text(encoding="utf-8")
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ConfigCorruptError(
                f"config is not valid JSON ({self.config_path}, line {e.lineno}): {e.msg}") from e
        validate(cfg)
        return cfg

    def load_or_halt(self) -> dict:
        """app.py entry point: any config problem = MessageBox + exit 2."""
        try:
            return self.load()
        except ConfigError as e:
            halt(str(e))
            raise AssertionError("halt() returned")  # unreachable; halt exits

    # ------------------------------------------------------------ write (CAS)

    def set(self, key: str, value: Any, *, reason: str, author: str,
            expected_revision: int) -> dict:
        """The ONE write path. CAS on revision; history line per change (scar 39)."""
        if not isinstance(reason, str) or not reason.strip():
            raise RefusedError("a non-empty --reason is required for every config change")
        if not isinstance(author, str) or not author.strip():
            raise RefusedError("a non-empty author is required for every config change")
        if key == "revision":
            raise RefusedError("revision is CAS-managed and can never be set directly")
        if key not in SCHEMA:
            raise RefusedError(
                f"unknown key {key!r}: the schema has exactly {len(SCHEMA)} keys; "
                f"new knobs are code under git, not config (design section 5)")

        cfg = self.load()  # corrupt config -> raises; set never papers over it

        if cfg["revision"] != expected_revision:
            raise CASError(
                f"stale write refused: expected revision {expected_revision}, "
                f"file is at {cfg['revision']} — reload and retry (scar 39)")

        old = cfg.get(key)
        new = self._coerce(key, old, value)
        _validate_value(key, new)
        self._check_guards(key, new)

        cfg[key] = new
        cfg["revision"] = expected_revision + 1
        validate(cfg)  # defense in depth: never persist an invalid config

        self._atomic_write(cfg)
        self._append_history({
            "ts": _now_iso(), "key": key, "old": old, "new": new,
            "reason": reason.strip(), "author": author.strip(),
            "revision": cfg["revision"],
        })
        return cfg

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _coerce(key: str, old: Any, value: Any) -> Any:
        """gate_rms scalar shorthand: keep the calibration record, move the
        value — the band check then decides (scar 41). A full dict replaces
        the record (a real recalibration)."""
        if SCHEMA[key]["type"] == "calibration" and _is_number(value):
            if not isinstance(old, dict):
                raise ConfigInvalidError(
                    f"{key}: scalar change impossible — no existing calibration record")
            rec = dict(old)
            rec["value"] = value
            return rec
        return value

    def _check_guards(self, key: str, new: Any) -> None:
        """Guarded knobs (design sections 5/7a)."""
        if key == "owner_gate_typing" and new is True:
            if not self._gate18_passed():
                raise RefusedError(
                    "owner_gate_typing=true refused: no PASS gate18-*.json report in "
                    f"{self.reports_dir} — criterion 18 must pass first (section 7a)")

    def _gate18_passed(self) -> bool:
        if not self.reports_dir.is_dir():
            return False
        for p in sorted(self.reports_dir.glob("gate18-*.json")):
            try:
                report = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[configstore] unreadable gate18 report {p.name}: {e}",
                      file=sys.stderr)
                continue
            if isinstance(report, dict) and report.get("verdict") == "PASS":
                return True
        return False

    def _atomic_write(self, cfg: dict) -> None:
        """tmp + fsync + os.replace in the same dir — never a partial file,
        never a .bak (scar 42)."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".client.json.", suffix=".tmp", dir=str(self.config_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(cfg, fh, ensure_ascii=False, indent=2, sort_keys=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.config_path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError as e:
                print(f"[configstore] tmp cleanup failed: {e}", file=sys.stderr)
            raise

    def _append_history(self, line: dict) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # ------------------------------------------------------------ drift (scar 41)

    @staticmethod
    def drift_check(cfg: dict, live_floor: float) -> str | None:
        """Startup check: configured gate vs live-measured noise floor.
        Returns a loud warning string on drift, None when healthy."""
        rec = cfg["gate_rms"]
        gate = rec["value"]
        if live_floor >= gate:
            return (f"GATE DRIFT: live noise floor {live_floor:.4f} has reached the "
                    f"configured gate {gate:.4f} (calibrated {rec['calibrated_at']}, "
                    f"floor was {rec['measured_floor']:.4f}) — recalibrate NOW or the "
                    f"mic floods EMPTY decodes (scar 41)")
        return None

from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ComputerUseError(RuntimeError):
    pass


class ComputerUseUnavailable(ComputerUseError):
    pass


class ComputerBackend(Protocol):
    def list_windows(self) -> list[dict[str, Any]]: ...

    def observe(self, window: dict[str, Any]) -> dict[str, Any]: ...

    def act(self, window: dict[str, Any], action: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class ComputerLimits:
    max_turns: int = 24
    max_actions: int = 12
    max_elapsed_seconds: int = 300
    max_screenshot_bytes: int = 2_000_000
    max_text_chars: int = 4_000
    max_wait_ms: int = 5_000
    max_scroll_delta: int = 2_000
    max_identical_actions: int = 2
    material_move_px: int = 32


DENIED_TARGET_PATTERNS = (
    "credential",
    "password",
    "1password",
    "bitwarden",
    "keepass",
    "uac",
    "user account control",
    "windows security",
    "microsoft defender",
    "registry editor",
    "regedit",
    "powershell",
    "command prompt",
    "terminal",
    "cmd.exe",
    "codex",
    "chatgpt",
)

ALLOWED_KEYS = {
    "Return",
    "Enter",
    "Tab",
    "Escape",
    "BackSpace",
    "Delete",
    "Left",
    "Right",
    "Up",
    "Down",
    "Home",
    "End",
    "Page_Up",
    "Page_Down",
    "space",
}

ALLOWED_MODIFIERS = {"Control", "Control_L", "Control_R", "Ctrl", "Alt", "Alt_L", "Alt_R", "Shift", "Shift_L", "Shift_R"}
ALLOWED_CHORD_KEYS = {"a", "c", "f", "l", "n", "p", "s", "t", "v", "w", "x", "z"} | ALLOWED_KEYS
SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_ -]?key|password|passwd|secret|token|bearer)\s*[:=]\s*\S+"
)


def redacted_preview(text: str, limit: int = 80) -> str:
    if SECRET_PATTERN.search(text):
        return "[REDACTED_SENSITIVE_TEXT]"
    compact = " ".join(text.split())
    if len(compact) > limit:
        compact = compact[: limit - 1] + "…"
    return compact


def _png_dimensions(raw: bytes) -> tuple[int, int]:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) < 24:
        raise ComputerUseError("Screenshot must be a valid PNG.")
    return struct.unpack(">II", raw[16:24])


def _window_public(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": window["id"],
        "title": window["title"],
        "process_name": window["process_name"],
        "app": window["app"],
        "bounds": dict(window["bounds"]),
        "foreground": window["foreground"],
        "dpi_scale": window["dpi_scale"],
    }


class UnavailableComputerBackend:
    message = (
        "Trusted Windows Computer Use is unavailable in standalone Python. "
        "Run sky_driver.mjs inside the trusted Codex node_repl runtime."
    )

    def list_windows(self) -> list[dict[str, Any]]:
        raise ComputerUseUnavailable(self.message)

    def observe(self, window: dict[str, Any]) -> dict[str, Any]:
        del window
        raise ComputerUseUnavailable(self.message)

    def act(self, window: dict[str, Any], action: dict[str, Any]) -> None:
        del window, action
        raise ComputerUseUnavailable(self.message)


class ComputerUseSession:
    def __init__(
        self,
        backend: ComputerBackend,
        stop_path: Path,
        *,
        limits: ComputerLimits | None = None,
        dry_run: bool = False,
        observe_only: bool = False,
    ) -> None:
        self.backend = backend
        self.stop_path = stop_path
        self.limits = limits or ComputerLimits()
        self.dry_run = dry_run
        self.observe_only = observe_only
        self.started = time.monotonic()
        self.action_count = 0
        self.turn_count = 0
        self.windows: dict[str, dict[str, Any]] = {}
        self.last_observation: dict[str, Any] | None = None
        self.action_history: list[tuple[str, str]] = []

    def summary(self) -> dict[str, Any]:
        return {
            "actions": self.action_count,
            "turns": self.turn_count,
            "elapsed_ms": round((time.monotonic() - self.started) * 1000),
            "dry_run": self.dry_run,
            "observe_only": self.observe_only,
            "last_screenshot_sha256": (
                self.last_observation.get("screenshot_sha256") if self.last_observation else None
            ),
        }

    def _check_stop_and_limits(self, *, action: bool = False) -> None:
        if self.stop_path.exists():
            raise ComputerUseError(f"Kill switch present: {self.stop_path}")
        if time.monotonic() - self.started > self.limits.max_elapsed_seconds:
            raise ComputerUseError("Computer-use elapsed-time limit exceeded.")
        if self.turn_count >= self.limits.max_turns:
            raise ComputerUseError("Computer-use turn limit exceeded.")
        if action and self.action_count >= self.limits.max_actions:
            raise ComputerUseError("Computer-use action limit exceeded.")

    def list_windows(self) -> dict[str, Any]:
        self._check_stop_and_limits()
        normalized: dict[str, dict[str, Any]] = {}
        for raw in self.backend.list_windows():
            item = self._normalize_window(raw)
            if not self._target_denied(item):
                normalized[item["id"]] = item
        self.windows = normalized
        self.turn_count += 1
        return {"ok": True, "windows": [_window_public(item) for item in normalized.values()]}

    def observe_window(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_stop_and_limits()
        window = self._get_window(args["window_id"])
        return self._observe(window)

    def computer_action(self, args: dict[str, Any]) -> dict[str, Any]:
        self._check_stop_and_limits(action=True)
        if self.observe_only:
            raise ComputerUseError("Session is observe-only; actions are disabled.")
        window = self._get_window(args["window_id"])
        observation = self.last_observation
        if observation is None:
            raise ComputerUseError("A fresh observation is required before an action.")
        if args["observation_id"] != observation["observation_id"]:
            raise ComputerUseError("Observation is stale; re-observe before acting.")
        if window["id"] != observation["window"]["id"]:
            raise ComputerUseError("Action target does not match the observed window.")
        self._verify_identity(window)
        action = self._validate_action(args, observation)
        signature = hashlib.sha256(
            json.dumps(action, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        state_key = observation["screenshot_sha256"]
        repeats = sum(1 for item in self.action_history[-self.limits.max_identical_actions :] if item == (state_key, signature))
        if repeats >= self.limits.max_identical_actions:
            raise ComputerUseError("No-progress loop detected for repeated identical action.")
        self.action_history.append((state_key, signature))
        if self.dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "risk_class": self.risk_class(action),
                "window_id": window["id"],
                "planned_action": self.public_action(action),
                "observation_id": observation["observation_id"],
                "screenshot_sha256": observation["screenshot_sha256"],
            }
        self.last_observation = None
        self.backend.act(window, action)
        self.action_count += 1
        self._check_stop_and_limits()
        result = self._observe(window)
        result["action"] = action["action"]
        result["risk_class"] = self.risk_class(action)
        return result

    def approval_view(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        target = self.windows.get(str(args.get("window_id", "")))
        action = args.get("action", "observe")
        preview: dict[str, Any] = {
            "tool": name,
            "target": (
                {
                    "id": target["id"],
                    "title": target["title"],
                    "process_name": target["process_name"],
                }
                if target
                else None
            ),
            "action": action,
            "risk_class": self.risk_class(args),
        }
        if isinstance(args.get("text"), str):
            preview["text_preview"] = redacted_preview(args["text"])
            preview["text_length"] = len(args["text"])
        for key in ("x", "y", "key", "scroll_x", "scroll_y", "duration_ms"):
            if key in args:
                preview[key] = args[key]
        return preview

    @staticmethod
    def public_action(action: dict[str, Any]) -> dict[str, Any]:
        public = {key: value for key, value in action.items() if key != "text"}
        if "text" in action:
            public["text_preview"] = redacted_preview(action["text"])
            public["text_length"] = len(action["text"])
        return public

    @staticmethod
    def risk_class(action: dict[str, Any]) -> str:
        kind = action.get("action")
        if kind == "type_text":
            return "text_transmission"
        if kind in {"click", "double_click", "right_click", "press_key", "scroll"}:
            return "ui_mutation"
        if kind == "focus":
            return "focus_change"
        if kind == "wait":
            return "bounded_wait"
        return "read_only"

    def _observe(self, window: dict[str, Any]) -> dict[str, Any]:
        current = self._verify_identity(window)
        captured = self.backend.observe(current)
        raw = captured.get("png_bytes")
        if not isinstance(raw, bytes):
            raise ComputerUseError("Backend did not return PNG bytes.")
        if len(raw) > self.limits.max_screenshot_bytes:
            raise ComputerUseError("Screenshot exceeds the configured byte limit.")
        width, height = _png_dimensions(raw)
        digest = hashlib.sha256(raw).hexdigest()
        observation_id = hashlib.sha256(
            f"{current['id']}:{digest}:{self.turn_count}".encode("utf-8")
        ).hexdigest()[:24]
        result = {
            "ok": True,
            "window": _window_public(current),
            "observation_id": observation_id,
            "screenshot_sha256": digest,
            "screenshot_bytes": len(raw),
            "image_width": width,
            "image_height": height,
            "dpi_scale": current["dpi_scale"],
            "accessibility": str(captured.get("accessibility", ""))[:16_384],
            "_input_image": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
        }
        self.last_observation = result
        self.turn_count += 1
        return dict(result)

    def _get_window(self, window_id: Any) -> dict[str, Any]:
        key = str(window_id)
        if key not in self.windows:
            raise ComputerUseError("Unknown window ID; list windows again.")
        return self.windows[key]

    def _verify_identity(self, expected: dict[str, Any]) -> dict[str, Any]:
        matches = []
        for raw in self.backend.list_windows():
            current = self._normalize_window(raw)
            if current["id"] == expected["id"]:
                matches.append(current)
        if len(matches) != 1:
            raise ComputerUseError("Target window disappeared or is no longer unique.")
        current = matches[0]
        if current["app"] != expected["app"] or current["process_name"] != expected["process_name"]:
            raise ComputerUseError("Target window identity changed.")
        before = expected["bounds"]
        after = current["bounds"]
        if any(abs(int(before[key]) - int(after[key])) > self.limits.material_move_px for key in ("left", "top", "width", "height")):
            raise ComputerUseError("Target window moved or resized materially; re-list it.")
        if self._target_denied(current):
            raise ComputerUseError("Target window is blocked by policy.")
        self.windows[current["id"]] = current
        return current

    @staticmethod
    def _normalize_window(raw: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ComputerUseError("Window record must be an object.")
        bounds = raw.get("bounds")
        if not isinstance(bounds, dict):
            raise ComputerUseError("Window bounds are required.")
        normalized_bounds = {}
        for key in ("left", "top", "width", "height"):
            value = bounds.get(key)
            if not isinstance(value, int) or isinstance(value, bool):
                raise ComputerUseError(f"Window bound {key} must be an integer.")
            normalized_bounds[key] = value
        if normalized_bounds["width"] <= 0 or normalized_bounds["height"] <= 0:
            raise ComputerUseError("Window dimensions must be positive.")
        window_id = str(raw.get("id", "")).strip()
        app = str(raw.get("app", "")).strip()
        process = str(raw.get("process_name", "")).strip()
        if not window_id or not app or not process:
            raise ComputerUseError("Window ID, app, and process name are required.")
        dpi = raw.get("dpi_scale", 1.0)
        if not isinstance(dpi, (int, float)) or isinstance(dpi, bool) or dpi <= 0 or dpi > 8:
            raise ComputerUseError("Window DPI scale is invalid.")
        return {
            "id": window_id,
            "title": str(raw.get("title", ""))[:512],
            "process_name": process[:260],
            "app": app[:512],
            "bounds": normalized_bounds,
            "foreground": bool(raw.get("foreground", False)),
            "dpi_scale": float(dpi),
        }

    @staticmethod
    def _target_denied(window: dict[str, Any]) -> bool:
        haystack = " ".join(
            (window.get("title", ""), window.get("process_name", ""), window.get("app", ""))
        ).casefold()
        return any(pattern in haystack for pattern in DENIED_TARGET_PATTERNS)

    def _validate_action(self, args: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
        kind = args["action"]
        action: dict[str, Any] = {"action": kind}
        if kind in {"click", "double_click", "right_click", "move", "scroll"}:
            x = args.get("x")
            y = args.get("y")
            if not isinstance(x, int) or isinstance(x, bool) or not isinstance(y, int) or isinstance(y, bool):
                raise ComputerUseError("Action coordinates must be integers.")
            if x < 0 or y < 0 or x >= observation["image_width"] or y >= observation["image_height"]:
                raise ComputerUseError("Action coordinates are outside the latest screenshot.")
            action.update({"x": x, "y": y})
        if kind == "type_text":
            text = args.get("text")
            if not isinstance(text, str) or not text or len(text) > self.limits.max_text_chars:
                raise ComputerUseError("Text must be non-empty and within the configured limit.")
            if SECRET_PATTERN.search(text):
                raise ComputerUseError("Sensitive-looking text is blocked from automated typing.")
            action["text"] = text
        if kind == "press_key":
            key = args.get("key")
            if not isinstance(key, str) or not self._key_allowed(key):
                raise ComputerUseError("Key or chord is not allowlisted.")
            action["key"] = key
        if kind == "scroll":
            for axis in ("scroll_x", "scroll_y"):
                value = args.get(axis, 0)
                if not isinstance(value, int) or isinstance(value, bool) or abs(value) > self.limits.max_scroll_delta:
                    raise ComputerUseError("Scroll delta is invalid.")
                action[axis] = value
            if action["scroll_x"] == 0 and action["scroll_y"] == 0:
                raise ComputerUseError("At least one scroll delta must be non-zero.")
        if kind == "wait":
            duration = args.get("duration_ms")
            if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0 or duration > self.limits.max_wait_ms:
                raise ComputerUseError("Wait duration is invalid.")
            action["duration_ms"] = duration
        return action

    @staticmethod
    def _key_allowed(key: str) -> bool:
        if key in ALLOWED_KEYS:
            return True
        parts = [part.strip() for part in key.split("+")]
        if len(parts) < 2 or any(not part for part in parts):
            return False
        return all(part in ALLOWED_MODIFIERS for part in parts[:-1]) and parts[-1] in ALLOWED_CHORD_KEYS


def make_test_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    scanline = b"\x00" + bytes(rgb) * width
    payload = scanline * height
    return (
        signature
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(payload, 9))
        + chunk(b"IEND", b"")
    )


class FakeComputerBackend:
    def __init__(self) -> None:
        self.marker = "READY"
        self.actions: list[dict[str, Any]] = []
        self.window = {
            "id": "fake-window-1",
            "title": "Perplexity Safe Test Window",
            "process_name": "safe_test_window.exe",
            "app": "process:safe_test_window.exe",
            "bounds": {"left": 100, "top": 100, "width": 640, "height": 360},
            "foreground": True,
            "dpi_scale": 1.0,
        }

    def list_windows(self) -> list[dict[str, Any]]:
        return [json.loads(json.dumps(self.window))]

    def observe(self, window: dict[str, Any]) -> dict[str, Any]:
        if window["id"] != self.window["id"]:
            raise ComputerUseError("Fake target changed.")
        color = (30, 80, 160) if self.marker == "READY" else (20, 150, 80)
        return {
            "png_bytes": make_test_png(64, 36, color),
            "accessibility": f"marker={self.marker}; focused_element=entry",
        }

    def act(self, window: dict[str, Any], action: dict[str, Any]) -> None:
        if window["id"] != self.window["id"]:
            raise ComputerUseError("Fake target changed.")
        self.actions.append(dict(action))
        if action["action"] == "wait":
            time.sleep(action["duration_ms"] / 1000)
        elif action["action"] == "type_text":
            self.marker = action["text"]
        else:
            self.marker = "ACTION_OK"

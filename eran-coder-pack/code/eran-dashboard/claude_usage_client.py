"""Fetch Claude Code OAuth usage (api.anthropic.com/api/oauth/usage)."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CRED_PATH = Path(r"C:\Users\<user>\.claude\.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
def _load_creds() -> dict[str, Any] | None:
    if not CRED_PATH.exists():
        return None
    data = json.loads(CRED_PATH.read_text(encoding="utf-8"))
    oauth = data.get("claudeAiOauth")
    return oauth if isinstance(oauth, dict) else None


def _http_json(url: str, token: str, method: str = "GET", body: dict | None = None) -> tuple[int, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "anthropic-version": "2023-06-01",
        "User-Agent": "grok-usage-widget/1.0",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read(4000).decode("utf-8", errors="replace") if e.fp else ""
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw[:200]}


def _parse_window(obj: dict[str, Any] | None) -> dict[str, Any]:
    if not obj:
        return {}
    util = float(obj.get("utilization") or 0)
    reset_at = obj.get("resets_at")
    days = 0
    hours = 0
    reset_label = "?"
    if reset_at:
        try:
            end = datetime.fromisoformat(str(reset_at).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = end - now
            days = max(0, delta.days)
            hours = max(0, int(delta.total_seconds() // 3600) % 24)
            reset_label = end.astimezone().strftime("%a %m/%d %H:%M")
        except ValueError:
            reset_label = str(reset_at)[:16]
    return {
        "utilization": round(util, 1),
        "percent_remaining": round(100.0 - util, 1),
        "resets_at": reset_at,
        "reset_label": reset_label,
        "days_to_reset": days,
        "hours_to_reset": hours,
    }


def fetch_claude_usage_snapshot() -> dict[str, Any]:
    oauth = _load_creds()
    out: dict[str, Any] = {
        "ok": False,
        "source": "api.anthropic.com/api/oauth/usage",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    if not oauth:
        out["error"] = "not_authenticated"
        return out

    token = oauth.get("accessToken")
    if not token:
        out["error"] = "no_access_token"
        return out

    status, payload = _http_json(USAGE_URL, token)
    if status != 200 or not isinstance(payload, dict):
        out["error"] = f"usage_fetch_failed_{status}"
        return out

    five = _parse_window(payload.get("five_hour"))
    seven = _parse_window(payload.get("seven_day"))
    sonnet = _parse_window(payload.get("seven_day_sonnet"))

    out.update(
        {
            "ok": True,
            "subscription_type": oauth.get("subscriptionType"),
            "rate_limit_tier": oauth.get("rateLimitTier"),
            "five_hour": five,
            "seven_day": seven,
            "seven_day_sonnet": sonnet,
            "primary_percent": seven.get("utilization", 0),
            "primary_reset_label": seven.get("reset_label"),
            "primary_days_to_reset": seven.get("days_to_reset"),
            "burst_percent": five.get("utilization", 0),
            "burst_reset_label": five.get("reset_label"),
        }
    )
    return out


if __name__ == "__main__":
    print(json.dumps(fetch_claude_usage_snapshot(), indent=2))
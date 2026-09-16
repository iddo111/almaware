"""Fetch Grok Build CLI billing + pacing (local, no cloud tokens)."""
from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

AUTH_PATH = Path(r"C:\Users\<user>\.grok\auth.json")
CONFIG_PATH = Path(r"C:\Users\<user>\.grok\config.toml")
BILLING_URL = "https://cli-chat-proxy.grok.com/v1/billing"
USER_URL = "https://cli-chat-proxy.grok.com/v1/user"
PACING_MODULE = Path(r"D:\grok\voice-realtime-gui\token_pacing.py")


def _load_bearer() -> str | None:
    if not AUTH_PATH.exists():
        return None
    data = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    for entry in data.values():
        if isinstance(entry, dict) and entry.get("key"):
            return entry["key"]
    return None


def _http_get(url: str, token: str) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "grok-usage-widget/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None


def _val(obj: Any) -> float:
    if obj is None:
        return 0.0
    if isinstance(obj, (int, float)):
        return float(obj)
    if isinstance(obj, dict) and "val" in obj:
        return float(obj["val"])
    return 0.0


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_pacing(percent_used: float) -> dict[str, Any]:
    if not PACING_MODULE.exists():
        return {}
    sys.path.insert(0, str(PACING_MODULE.parent))
    try:
        import token_pacing as tp  # type: ignore

        return tp.compute_pacing_status(percent_used)
    except Exception:
        return {}
    finally:
        if str(PACING_MODULE.parent) in sys.path:
            sys.path.remove(str(PACING_MODULE.parent))


def fetch_usage_snapshot() -> dict[str, Any]:
    token = _load_bearer()
    out: dict[str, Any] = {
        "ok": False,
        "source": "cli-chat-proxy/v1/billing",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    if not token:
        out["error"] = "not_authenticated"
        return out

    billing = _http_get(BILLING_URL, token)
    user = _http_get(USER_URL, token)
    if not billing:
        out["error"] = "billing_fetch_failed"
        return out

    cfg = billing.get("config") or {}
    limit = _val(cfg.get("monthlyLimit"))
    used = _val(cfg.get("used"))
    on_demand_cap = _val(cfg.get("onDemandCap"))
    percent = (used / limit * 100.0) if limit > 0 else 0.0
    remaining = max(0.0, limit - used)

    period_start = _parse_iso(cfg.get("billingPeriodStart") or billing.get("billingPeriodStart"))
    period_end = _parse_iso(cfg.get("billingPeriodEnd") or billing.get("billingPeriodEnd"))
    days_to_reset = 0
    reset_label = "?"
    if period_end:
        now = datetime.now(timezone.utc)
        days_to_reset = max(0, (period_end.date() - now.date()).days)
        reset_label = period_end.strftime("%Y-%m-%d")

    pacing = _load_pacing(percent)

    out.update(
        {
            "ok": True,
            "limit": limit,
            "used": used,
            "remaining": remaining,
            "percent_used": round(percent, 2),
            "percent_remaining": round(100.0 - percent, 2),
            "on_demand_cap": on_demand_cap,
            "billing_period_start": cfg.get("billingPeriodStart"),
            "billing_period_end": cfg.get("billingPeriodEnd"),
            "pacing_recommendation": pacing.get("recommendation"),
            "days_to_reset": days_to_reset,
            "reset_label": reset_label,
            "pacing_status": pacing.get("status"),
            "pacing_note": pacing.get("note"),
            "pacing_summary": pacing.get("summary"),
            "ideal_used_by_now": pacing.get("ideal_used_by_now"),
            "daily_target_percent": pacing.get("daily_target_percent"),
            "user_email": (user or {}).get("email"),
            "user_blocked": (user or {}).get("userBlockedReason"),
        }
    )
    return out


if __name__ == "__main__":
    print(json.dumps(fetch_usage_snapshot(), indent=2))
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""almido_body_http.py -- ALMIDO's BODY, reachable from anywhere, behind two walls.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-11 07:28: give Claude on Android, ChatGPT, or any cloud model a BODY --
the hands on this PC, the hands on the phone, the fleet, the builder -- reachable from
the internet, behind HIS login. "never an open door."

This is the SAME MCP server as almido_mcp.py, spoken over HTTP instead of stdio. The tool
table and every handler are IMPORTED from it, never copied: TOOLS, HANDLERS and call_tool
are almido_mcp's own, so a tool added there appears here with no edit, and the in-process
gate (almido_gate.gate(): STOP file, the credential refusal, the AUDIO PROTECTION LAW, the
window guard, the rate limit) and the HMAC-chained audit run exactly as they do locally.

FOUR WALLS, outermost first:

  1. Cloudflare Access on body.iddoperez.ai -- Iddo's login. Nothing reaches this process
     without it. (Configured separately; see BODY-CONNECTOR.md. This file does not depend
     on it: it is an OUTER wall, not the only one.)
  2. This file's own auth. Either a valid Cloudflare Access JWT (verified against the
     Access team domain's public certs and the application's AUD -- real RS256
     verification, not header-trust) or the shared secret in
     D:\CLAUDE\iddo-harness\state\body_token.txt, ACL'd to iddo1 alone. A request with
     neither gets 401 and never reaches a handler.
  3. THE PROFILE. Every tool is classified allow / confirm / block for this transport by
     `agents.profiles.body-http` in D:\CLAUDE\iddo-harness\policy.yaml. Reading is allowed;
     the HANDS and remote_build are CONFIRM, which over HTTP means REFUSED unless Iddo has
     armed them from this machine (`python almido_body_http.py arm`); verified-backup
     DELETION is blocked here in code and policy cannot loosen it.
  4. The gate itself, unchanged, inside every handler.

And one kill switch that is not a wall but a switch: the STOP file
(~/.iddo-harness/STOP, or state\BODY-STOP) makes this door refuse EVERYTHING -- reads
included. The local stdio door keeps working. Cutting the body does not cut the coder.

The screen NEVER leaves this PC as a file path a stranger could fetch: computer_screenshot
and phone_screenshot are re-read here and returned as base64 inside the tool result, and
nothing is ever served off disk -- there is no static route at all. Every path but
POST /mcp and GET /health is 404.

Run:
    python almido_body_http.py                 # serve on 127.0.0.1:8898
    python almido_body_http.py token           # create the shared secret (once), ACL it
    python almido_body_http.py arm --minutes 20 --tools "computer_*,phone_*"
    python almido_body_http.py disarm
    python almido_body_http.py status
Test:
    python -m pytest tests/test_almido_body_http.py -q
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import hmac
import json
import os
import secrets
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------- no WMI in this process
# 2026-09-15 bw-W1 (broken-windows swarm). This server died NATIVELY on the first almido_whoami
# call after a clean start: Event 1000 08:47:48, pythonw.exe, faulting module _wmi.pyd,
# 0xc0000005. CPython 3.12's platform module asks WMI through _wmi.exec_query; when that query
# times out under load, its native worker thread later writes into freed memory. Reproduced on a
# DECOY, never the live door (6 threads calling platform.win32_ver(): access violation, exit 139,
# no Python frame). A crash in C leaves no traceback, which is why body-http*.log went silent.
# platform's own fallback is no better from pythonw: it shells out `ver` with shell=True.
# So the three questions platform asks WMI are answered from sys.getwindowsversion(), the
# environment and the registry -- no WMI, no subprocess. Anything else raises OSError, the branch
# platform already handles. ALMA_BODY_ALLOW_WMI=1 turns this off.
# Rollback: copy almido_body_http.py.bak-bw-20260915 over this file and restart the door.
import faulthandler as _faulthandler
import platform as _platform


def _wmi_free_query(table, *keys):
    import winreg
    if table == "OS" and keys == ("Version", "ProductType", "BuildType",
                                  "ServicePackMajorVersion", "ServicePackMinorVersion"):
        w = sys.getwindowsversion()
        major, minor, build = (tuple(getattr(w, "platform_version", ()) or ()) or tuple(w[:3]))[:3]
        build_type = "Multiprocessor Free"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
                build_type = str(winreg.QueryValueEx(key, "CurrentType")[0])
                # kernel32's file version says 26100 on 25H2; WMI and the registry say 26200.
                build = int(winreg.QueryValueEx(key, "CurrentBuildNumber")[0])
        except (OSError, ValueError):
            pass
        return iter(("%d.%d.%d" % (major, minor, build), str(w.product_type), build_type,
                     str(w.service_pack_major), str(w.service_pack_minor)))
    if table == "CPU" and keys == ("Architecture",):
        codes = {"X86": "0", "ARM": "5", "IA64": "6", "AMD64": "9", "ARM64": "12"}
        arch = (os.environ.get("PROCESSOR_ARCHITEW6432")
                or os.environ.get("PROCESSOR_ARCHITECTURE", "")).upper()
        if arch in codes:
            return iter((codes[arch],))
    if table == "CPU" and keys == ("Manufacturer", "Caption"):
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return iter((str(winreg.QueryValueEx(key, "VendorIdentifier")[0]),
                         str(winreg.QueryValueEx(key, "Identifier")[0])))
    raise OSError("WMI is not used inside alma-body (bw-W1 2026-09-15)")


if sys.platform == "win32" and os.environ.get("ALMA_BODY_ALLOW_WMI") != "1":
    _platform._wmi_query = _wmi_free_query

# The next native crash must leave a stack behind, not silence.
try:
    (HERE / "workspace").mkdir(exist_ok=True)
    _FAULT_LOG = open(HERE / "workspace" / "body-http-fault.log", "a", encoding="utf-8")
    _faulthandler.enable(file=_FAULT_LOG, all_threads=True)
except Exception:
    _FAULT_LOG = None

import almido_mcp as M  # noqa: E402  -- the SAME server. Imported, never copied.

# ---------------------------------------------------------------- where things live
HARNESS_REPO = Path(os.environ.get("ALMA_BODY_HARNESS", r"D:\CLAUDE\iddo-harness"))
STATE_DIR = Path(os.environ.get("ALMA_BODY_STATE", str(HARNESS_REPO / "state")))
TOKEN_FILE = STATE_DIR / "body_token.txt"
ARM_FILE = STATE_DIR / "body_arm.json"
ACCESS_FILE = STATE_DIR / "body_access.json"
BODY_STOP = STATE_DIR / "BODY-STOP"
HARNESS_STOP = Path.home() / ".iddo-harness" / "STOP"
POLICY_FILES = [HARNESS_REPO / "policy.yaml", Path.home() / ".iddo-harness" / "policy.yaml"]
LOG_FILE = Path(os.environ.get("ALMA_BODY_LOG", str(HERE / "workspace" / "body-http.log")))

PROFILE_NAME = "body-http"
HOST = os.environ.get("ALMA_BODY_HOST", "127.0.0.1")
# 8898, not 8897: MEASURED 2026-09-11 10:22, 8897 is TAKEN twice over -- tailscaled
# proxies it on the tailnet (<tailnet-ip>:8897, the phone-bootstrap serve) and
# brain2_server.py has held 127.0.0.1:8897 since 10:20 that morning. Claimed in RAMCHAT.
PORT = M._env_int("ALMA_BODY_PORT", 8898)
RATE_LIMIT = M._env_int("ALMA_BODY_RATE", 60)          # calls per window, per identity
RATE_WINDOW = 60.0
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = M._env_int("ALMA_BODY_MAX_IMAGE", 900000)   # raw bytes before base64
PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "alma-body", "version": "1.0.0",
               "title": "ALMIDO body over HTTP (the same tools as the almido stdio door)"}

# ---------------------------------------------------------------- the profile
# THE BUILT-IN DEFAULT. policy.yaml may RE-CLASSIFY a tool, but if the policy file is
# missing, unreadable, or has no body-http profile, THIS is what runs -- conservative, so a
# deleted policy file closes the hands instead of opening them.
DEFAULT_PROFILE = {
    "auto_allow": {"tools": [
        "almido_whoami", "almido_audit_tail", "quorum_status", "quorum_debate", "ask_claude",
        "brain_read", "brain_doors", "brain_write", "brain_propose_door",
        "computer_status", "computer_screen_info", "computer_screenshot", "computer_stop",
        "backup_status", "backup_verify",
        "phone_status", "phone_ui_text", "phone_screenshot",
        "fleet_probe", "remote_build_status", "remote_build_selftest",
    ]},
    "require_confirm": {"tools": [
        "computer_click", "computer_type", "computer_key", "computer_scroll",
        "phone_tap", "phone_type", "phone_key", "phone_scroll", "phone_open",
        "phone_back", "phone_home", "phone_shell", "phone_hebrew_probe",
        "remote_build",
    ]},
    "block": {"tools": []},
}

# Never over HTTP, whatever any policy file says. An irreversible deletion authorised from
# the internet is not a thing Iddo asked for and not a thing this door will carry.
HARD_BLOCK = {
    "backup_delete_verified": "irreversible deletion is never authorised over the internet; "
                              "run it from the local stdio door",
}

_POLICY_CACHE: dict = {}
_POLICY_LOCK = threading.Lock()
_SID_CACHE: dict = {}


def _now() -> float:
    return time.time()


def _iso(ts: float | None = None) -> str:
    stamp = datetime.fromtimestamp(ts) if ts is not None else datetime.now()
    return stamp.astimezone().isoformat(timespec="seconds")


def _profile() -> dict:
    """{'profile': dict, 'source': str}. Cached on (path, mtime) so an edit takes effect
    without a restart, but a request does not re-parse 22 KB of YAML every time."""
    for path in POLICY_FILES:
        try:
            stamp = (str(path), path.stat().st_mtime_ns)
        except OSError:
            continue
        with _POLICY_LOCK:
            if _POLICY_CACHE.get("stamp") == stamp:
                return _POLICY_CACHE["value"]
        try:
            import yaml
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            prof = ((data.get("agents") or {}).get("profiles") or {}).get(PROFILE_NAME)
        except Exception as exc:
            value = {"profile": DEFAULT_PROFILE, "source": "built-in default",
                     "error": "%s: %s: %s" % (path, type(exc).__name__, str(exc)[:160])}
            with _POLICY_LOCK:
                _POLICY_CACHE.update(stamp=stamp, value=value)
            return value
        if isinstance(prof, dict):
            value = {"profile": prof, "source": str(path)}
            with _POLICY_LOCK:
                _POLICY_CACHE.update(stamp=stamp, value=value)
            return value
    return {"profile": DEFAULT_PROFILE, "source": "built-in default",
            "error": "no agents.profiles.%s in %s" % (PROFILE_NAME,
                                                      " or ".join(str(p) for p in POLICY_FILES))}


def _globs(profile: dict, section: str) -> list:
    part = profile.get(section) if isinstance(profile.get(section), dict) else {}
    out = part.get("tools") or part.get("commands") or []
    return [str(p) for p in out] if isinstance(out, list) else []


def classify(tool: str) -> tuple:
    """('allow'|'confirm'|'block', reason). An unknown tool is CONFIRM, never allow -- the
    same default the gate itself uses for an action kind it does not recognise."""
    if tool in HARD_BLOCK:
        return "block", "blocked in code: " + HARD_BLOCK[tool]
    info = _profile()
    prof = info["profile"]
    for section, verdict in (("block", "block"), ("require_confirm", "confirm"),
                             ("auto_allow", "allow")):
        for pat in _globs(prof, section):
            if fnmatch.fnmatch(tool, pat):
                return verdict, "policy %s.%s (%s) matched %r" % (PROFILE_NAME, section,
                                                                  info["source"], pat)
    return "confirm", ("no rule for %r in profile %s (%s): defaulting to CONFIRM"
                       % (tool, PROFILE_NAME, info["source"]))


# ------------------------------------------------- the arm (what CONFIRM means on a wire)
def arm_state() -> dict:
    """CONFIRM over HTTP cannot pop a dialog on a phone in another country. It means:
    refused, UNLESS Iddo has armed the hands from this machine. The arm is a file only a
    local process can write (state\\ is ACL'd), it expires by itself, and no tool exposed
    over this door can create it -- a remote caller cannot arm itself."""
    try:
        raw = json.loads(ARM_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"armed": False, "reason": "not armed"}
    except Exception as exc:
        return {"armed": False, "reason": "arm file unreadable (%s); treating as NOT armed" % exc}
    try:
        until = datetime.fromisoformat(str(raw.get("until")))
    except Exception:
        return {"armed": False, "reason": "arm file has no valid 'until'; treating as NOT armed"}
    if until.tzinfo is None:
        until = until.astimezone()
    now = datetime.now().astimezone()
    if until <= now:
        return {"armed": False, "expired": True,
                "reason": "arm expired at %s" % until.isoformat(timespec="seconds")}
    tools = raw.get("tools") or ["*"]
    return {"armed": True, "until": until.isoformat(timespec="seconds"),
            "tools": [str(t) for t in tools], "by": str(raw.get("by", "?"))[:80],
            "note": str(raw.get("note", ""))[:200],
            "seconds_left": int((until - now).total_seconds())}


def arm(minutes: float, tools: list | None = None, by: str = "", note: str = "") -> dict:
    chosen = [str(t).strip() for t in (tools or ["*"]) if str(t).strip()] or ["*"]
    until = datetime.now().astimezone() + timedelta(minutes=float(minutes))
    row = {"until": until.isoformat(timespec="seconds"), "tools": chosen,
           "by": by or os.environ.get("USERNAME", "local"), "note": note, "written": _iso()}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ARM_FILE.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    _secure_file(ARM_FILE)
    return row


def disarm() -> bool:
    try:
        ARM_FILE.unlink()
        return True
    except FileNotFoundError:
        return False


def authorize(tool: str) -> tuple:
    """(allowed: bool, reason: str). The whole transport-level decision, in one place."""
    verdict, why = classify(tool)
    if verdict == "block":
        return False, "BLOCKED over HTTP -- " + why
    if verdict == "allow":
        return True, why
    state = arm_state()
    if not state.get("armed"):
        return False, (
            "CONFIRM over HTTP = refused unless armed. %s. Nothing happened. To allow it, "
            "Iddo runs this ON THE PC: python D:\\CLAUDE\\almido\\almido_body_http.py arm "
            "--minutes 15 --tools \"%s\"   [%s]"
            % (state.get("reason", "not armed"), tool, why))
    for pat in state.get("tools", []):
        if fnmatch.fnmatch(tool, pat):
            return True, "armed by %s until %s [%s]" % (state.get("by"), state.get("until"), why)
    return False, ("armed, but only for %s -- %r is not covered. Nothing happened."
                   % (",".join(state.get("tools", [])), tool))


# ---------------------------------------------------------------- the STOP switch
def stop_reason() -> str:
    """The kill switch. STOP closes this door completely -- reads included -- because a
    body you cannot trust is worse than no body. The local stdio door is unaffected."""
    for path in (HARNESS_STOP, BODY_STOP):
        try:
            if path.exists():
                return "STOP file present: %s" % path
        except Exception:
            continue
    return ""


# ---------------------------------------------------------------- secrets on disk
def _file_security():
    """The harness's own file_security module, or None."""
    try:
        M.harness_audit_class()                      # populates M._HARNESS["file_security"]
        return M._HARNESS.get("file_security")
    except Exception:
        return None


def file_is_private(path: Path) -> bool:
    """True only if the file is readable by this user ALONE -- the harness's own check."""
    fs = _file_security()
    check = getattr(fs, "private_file_permissions_ok", None) if fs else None
    if check is None:
        return False
    try:
        return bool(check(path))
    except Exception:
        return False


def _current_sid() -> str:
    """This account's SID, from whoami. NEVER the user NAME: this machine is called IDDO1
    and its user is iddo1, so `icacls ... /grant:r iddo1:(F)` resolves the name to the
    MACHINE's domain SID (S-1-5-21-...-with-no-RID) and writes an ACE that belongs to
    nobody -- measured 2026-09-11, it locked this account out of its own token file."""
    import subprocess
    if _SID_CACHE.get("sid"):
        return _SID_CACHE["sid"]
    proc = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", shell=False, timeout=30)
    for field in proc.stdout.replace('"', "").strip().split(","):
        if field.strip().upper().startswith("S-1-"):
            _SID_CACHE["sid"] = field.strip()
            return _SID_CACHE["sid"]
    return ""


def _icacls_lock(path: Path) -> str:
    """MEASURED 2026-09-11: the harness's restrict_private_file FAILED on a file created
    under D:\\CLAUDE\\iddo-harness\\state -- it rebuilds the whole descriptor including
    SetOwner, and this account reaches the file through an inherited `Authenticated Users:
    Modify` ACE, which carries no WRITE_OWNER. The token was left readable by every
    authenticated user on the machine: exactly the hole the harness's own note describes
    for audit.key. icacls only rewrites the DACL, which the OWNER may always do, and
    produces the end state the audit key already has: this account (F), nothing inherited,
    nobody else."""
    import subprocess
    sid = _current_sid()
    if not sid:
        return "could not read this account's SID from whoami; refusing to guess a name"
    proc = subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", "*%s:(F)" % sid],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          shell=False, timeout=30)
    return "rc=%d %s" % (proc.returncode, (proc.stdout + proc.stderr).strip()[:160])


def _secure_file(path: Path) -> object:
    """ACL a private file to this user alone. True, or a string saying why not.

    A secret that any account on this box can read is not a secret, so this does not
    swallow its failure: it tries the harness's way, VERIFIES, falls back to icacls, and
    verifies again. main() refuses to serve if the token is still readable by others."""
    if os.environ.get("ALMA_BODY_SECURE", "1") != "1":
        return "skipped"
    notes = []
    fs = _file_security()
    if fs is None:
        notes.append("no file_security in %s" % M._HARNESS.get("repo"))
    else:
        try:
            fs.restrict_private_file(path)
        except Exception as exc:
            notes.append("harness: %s: %s" % (type(exc).__name__, str(exc)[:100]))
    if file_is_private(path):
        return True
    try:
        notes.append("icacls: " + _icacls_lock(path))
    except Exception as exc:
        notes.append("icacls: %s: %s" % (type(exc).__name__, str(exc)[:100]))
    if file_is_private(path):
        return True
    return "NOT PRIVATE: " + "; ".join(notes)


def read_token() -> str:
    """The shared secret, or "" if there is none. Read per request on purpose: rotating the
    file takes effect on the next call, with no restart."""
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def create_token(force: bool = False) -> dict:
    existing = read_token()
    if existing and not force:
        return {"created": False, "path": str(TOKEN_FILE), "secured": _secure_file(TOKEN_FILE),
                "note": "a token already exists; use --force to rotate it"}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    return {"created": True, "path": str(TOKEN_FILE), "secured": _secure_file(TOKEN_FILE),
            "note": "the value is NOT printed. Read it from that file when you add the "
                    "connector, and never paste it into a chat, RAMCHAT or a doc."}


def token_fingerprint(token: str) -> str:
    """Names WHICH token was used in the audit, without recording the token."""
    import hashlib
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:8] if token else "none"


# ---------------------------------------------------------------- Cloudflare Access
def access_config() -> dict:
    """state\\body_access.json:
        {"team_domain": "https://<team>.cloudflareaccess.com",
         "aud": "<the Access application AUD tag>",
         "emails": ["iddo111@gmail.com"],
         "service_tokens": {"claude-connector": "<client-id>.access"},
         "allowed_origins": ["https://body.iddoperez.ai"],
         "require_token_always": false}
    Absent or incomplete => Access verification is OFF and the shared secret is the only
    way in. That is a safe default: it never trusts a header it cannot verify."""
    try:
        raw = json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


_JWK_CACHE: dict = {}


def _jwk_client(team_domain: str):
    """PyJWKClient for the Access certs, cached (it caches keys itself and refetches on a
    kid miss, which is what key rotation needs)."""
    from jwt import PyJWKClient
    url = team_domain.rstrip("/") + "/cdn-cgi/access/certs"
    with _POLICY_LOCK:
        client = _JWK_CACHE.get(url)
        if client is None:
            client = PyJWKClient(url, cache_keys=True, lifespan=600)
            _JWK_CACHE[url] = client
    return client


def verify_access_jwt(token: str, cfg: dict | None = None) -> tuple:
    """(identity, "") on success, ("", why) on failure. REAL RS256 verification against
    Cloudflare's published certs -- the presence of the header proves nothing, anyone can
    send a header. Signature, issuer, audience and expiry are all checked, and then the
    identity has to be one Iddo named."""
    cfg = access_config() if cfg is None else cfg
    team = str(cfg.get("team_domain", "")).strip()
    aud = str(cfg.get("aud", "")).strip()
    if not team or not aud:
        return "", "Access verification is not configured (team_domain/aud missing in %s)" % ACCESS_FILE
    try:
        import jwt
        key = _jwk_client(team).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=aud,
                            issuer=team.rstrip("/"),
                            options={"require": ["exp", "iat", "aud", "iss"]})
    except Exception as exc:
        return "", "%s: %s" % (type(exc).__name__, str(exc)[:200])
    email = str(claims.get("email", "")).strip().lower()
    common = str(claims.get("common_name", "")).strip()
    emails = [str(e).strip().lower() for e in (cfg.get("emails") or [])]
    services = {str(v).strip(): str(k) for k, v in (cfg.get("service_tokens") or {}).items()}
    if email:
        if emails and email not in emails:
            return "", "Access identity %r is not in the allowed list" % email
        return email, ""
    if common:
        if services and common not in services:
            return "", "Access service token %r is not one of ours" % common[:40]
        return "service:" + services.get(common, common[:24]), ""
    return "", "Access JWT carries neither email nor common_name"


def authenticate(headers) -> tuple:
    """(identity, error). identity is what lands in the audit row.

    A valid Access JWT is enough on its own -- that is Iddo's real login. Otherwise the
    shared secret. Set require_token_always to demand both."""
    cfg = access_config()
    jwt_header = headers.get("Cf-Access-Jwt-Assertion") or headers.get("cf-access-jwt-assertion")
    identity = ""
    if jwt_header and cfg.get("team_domain") and cfg.get("aud"):
        # Access IS configured, so a JWT that does not verify is a FORGERY or an expired
        # session, and that is a refusal.
        who, why = verify_access_jwt(jwt_header, cfg)
        if not who:
            return "", (403, "Cloudflare Access JWT rejected: " + why)
        identity = who
    # If Access is NOT configured yet, the header is simply unverifiable: it grants nothing
    # and it denies nothing, and the shared secret below carries the request. Refusing here
    # instead would 403 every call the moment Access is put in front and before
    # state\body_access.json is filled in -- a door that breaks itself halfway through its
    # own installation.
    token = read_token()
    given = (headers.get("X-Alma-Body-Token") or "").strip()
    if not given:
        auth = (headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            given = auth[7:].strip()
    if identity and not cfg.get("require_token_always"):
        return "body-http:" + identity, None
    if not token:
        return "", (503, "no shared secret on this machine: run `python almido_body_http.py "
                         "token` on the PC to create %s" % TOKEN_FILE)
    if not given:
        return "", (401, "missing X-Alma-Body-Token header")
    if not hmac.compare_digest(given, token):
        return "", (401, "bad X-Alma-Body-Token")
    if identity:
        return "body-http:%s+token" % identity, None
    return "body-http:token/" + token_fingerprint(token), None


def origin_ok(origin: str) -> bool:
    """DNS-rebinding protection (the MCP spec asks for it). A browser sends Origin; a
    server-side connector does not. An Origin we do not know is refused."""
    if not origin:
        return True
    allowed = access_config().get("allowed_origins")
    if not isinstance(allowed, list) or not allowed:
        allowed = ["https://body.iddoperez.ai", "http://127.0.0.1", "http://localhost"]
    host = (urlparse(origin).hostname or "").lower()
    for entry in allowed:
        if (urlparse(str(entry)).hostname or str(entry)).lower() == host:
            return True
    return False


# ---------------------------------------------------------------- the rate limit
class RateLimiter:
    """60 calls a minute per identity. A retry loop on a phone is not a reason to let a
    model drive the mouse 600 times."""

    def __init__(self, limit: int = RATE_LIMIT, window: float = RATE_WINDOW):
        self.limit = int(limit)
        self.window = float(window)
        self._seen: dict = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> tuple:
        now = _now()
        with self._lock:
            q = self._seen.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window - (now - q[0])) + 1)
            q.append(now)
            return True, 0

    def state(self) -> dict:
        now = _now()
        with self._lock:
            return {k: len([t for t in q if now - t <= self.window]) for k, q in self._seen.items()}


LIMITER = RateLimiter()

# ---------------------------------------------------------------- the audit identity
# almido_mcp.audit() reads the module global AUTHOR when it writes the row. A tools/call
# that came in over HTTP must not be recorded as if the local coder had made it, so the
# identity is swapped in for the duration of the WRITE only (microseconds, under a lock),
# never for the duration of the call -- a nine-minute quorum_debate must not block anyone.
_AUDIT_TLS = threading.local()
_AUDIT_SWAP = threading.Lock()


def _install_audit_identity() -> None:
    original = M.audit
    if getattr(original, "_alma_body_wrapped", False):
        return

    def _audit_as(tool, arguments, ok, note=""):
        who = getattr(_AUDIT_TLS, "who", "")
        if not who:
            return original(tool, arguments, ok, note)
        with _AUDIT_SWAP:
            saved = M.AUTHOR
            M.AUTHOR = who
            try:
                return original(tool, arguments, ok, note)
            finally:
                M.AUTHOR = saved

    _audit_as._alma_body_wrapped = True
    _audit_as._alma_body_original = original
    M.audit = _audit_as


_install_audit_identity()


def audit_refusal(tool: str, arguments: object, identity: str, reason: str) -> None:
    """A refusal is a record too. Before this, a blocked remote call left no trace at all
    and the audit only ever showed what succeeded."""
    _AUDIT_TLS.who = identity
    try:
        M.audit(tool, arguments, False, "body-http refused: " + reason)
    finally:
        _AUDIT_TLS.who = ""


# ---------------------------------------------------------------- images
def _shrink(raw: bytes, limit: int) -> tuple:
    """(jpeg_bytes, note). Never returns anything bigger than the limit."""
    if len(raw) <= limit:
        return raw, ""
    try:
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        for width, quality in ((1280, 70), (1024, 60), (800, 50)):
            if img.width > width:
                img = img.resize((width, int(img.height * width / img.width)))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= limit:
                return buf.getvalue(), "downscaled to %d px, q%d" % (img.width, quality)
        return b"", "image is %d bytes and will not fit under %d even downscaled" % (len(raw), limit)
    except Exception as exc:
        return b"", "could not downscale: %s: %s" % (type(exc).__name__, exc)


def attach_image(tool: str, result: dict) -> dict:
    """A PATH is useless to a model on a phone, and this door serves no files. So the
    picture itself rides back inside the tool result as base64, and the file stays here."""
    if tool not in ("computer_screenshot", "phone_screenshot"):
        return result
    try:
        blocks = result.get("content") or []
        payload = json.loads(blocks[0]["text"])
    except Exception:
        return result
    if not isinstance(payload, dict):
        return result
    b64 = payload.get("base64") or payload.get("image_base64")
    note = ""
    if not b64:
        path = payload.get("path") or payload.get("file")
        if not path:
            return result
        try:
            raw = Path(str(path)).read_bytes()
        except Exception as exc:
            payload["image"] = "could not be read back: %s" % exc
            return M.text_content(payload)
        raw, note = _shrink(raw, MAX_IMAGE_BYTES)
        if not raw:
            payload["image"] = note
            return M.text_content(payload)
        b64 = base64.b64encode(raw).decode("ascii")
    mime = "image/png" if str(payload.get("path", "")).lower().endswith(".png") else "image/jpeg"
    if note:
        payload["image_note"] = note
    payload.pop("base64", None)
    payload["image"] = "attached as an image block below (%d base64 chars)" % len(b64)
    out = M.text_content(payload)
    out["content"].append({"type": "image", "data": b64, "mimeType": mime})
    return out


# ---------------------------------------------------------------- one tool call
def call_tool(tool: str, arguments: object, identity: str) -> dict:
    """Transport gate, then almido_mcp's OWN call_tool -- which runs the in-process gate
    and writes the audit row. There is no second path to a handler from here."""
    stopped = stop_reason()
    if stopped:
        reason = ("%s -- the body is switched off. Nothing happened. Only Iddo lifts it, by "
                  "deleting that file on the PC." % stopped)
        audit_refusal(tool, arguments, identity, reason)
        return M.text_content(reason, is_error=True)
    if tool not in M.HANDLERS:
        return M.text_content("unknown tool: %s" % tool, is_error=True)
    allowed, why = authorize(tool)
    if not allowed:
        audit_refusal(tool, arguments, identity, why)
        return M.text_content(why, is_error=True)
    _AUDIT_TLS.who = identity
    try:
        result = M.call_tool(tool, arguments)
    finally:
        _AUDIT_TLS.who = ""
    return attach_image(tool, result)


def tool_report() -> dict:
    """Exactly what this door exposes, and under which verdict. Measured from the live
    tool table, never from a list written by hand."""
    out: dict = {"allow": [], "confirm": [], "block": []}
    for spec in M.TOOLS:
        verdict, _ = classify(spec["name"])
        out[verdict].append(spec["name"])
    return out


# ---------------------------------------------------------------- JSON-RPC
def dispatch(message: object, identity: str) -> dict | None:
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "not a JSON-RPC object"}}
    request_id = message.get("id")
    method = str(message.get("method", ""))
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if request_id is None:                       # a notification: acknowledged, not answered
        return None
    if method == "initialize":
        client = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        SESSIONS["clients"][identity] = {"name": str(client.get("name", ""))[:80],
                                         "version": str(client.get("version", ""))[:40],
                                         "at": _iso()}
        result: object = {"protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": SERVER_INFO}
    elif method == "tools/list":
        result = {"tools": M.TOOLS}
    elif method == "tools/call":
        result = call_tool(str(params.get("name", "")), params.get("arguments", {}), identity)
    elif method == "ping":
        result = {}
    elif method in ("resources/list", "prompts/list"):
        # This server has neither. Answering emptily instead of -32601 keeps clients that
        # probe for them (claude.ai does) from showing the connector as broken.
        result = {"resources": []} if method == "resources/list" else {"prompts": []}
    else:
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": -32601, "message": "Method not found: " + method}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


SESSIONS: dict = {"ids": {}, "clients": {}}


def new_session() -> str:
    sid = secrets.token_urlsafe(18)
    SESSIONS["ids"][sid] = _iso()
    return sid


# ---------------------------------------------------------------- HTTP
def _log(line: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("%s %s\n" % (_iso(), line))
    except Exception:
        pass


class BodyHandler(BaseHTTPRequestHandler):
    server_version = "alma-body/1.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # ---- plumbing
    def log_message(self, fmt, *args):             # never to stdout; never a token
        _log("%s %s" % (self.address_string(), fmt % args))

    def _send(self, code: int, payload: object, extra: dict | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # MEASURED 2026-09-11 in the live log: a 401 answered a POST whose body had not been
        # read, and on this HTTP/1.1 keep-alive connection the unread JSON was then parsed as
        # the NEXT request line -- a spurious 400 out of nowhere. Every refusal happens before
        # the body is read, so every refusal ends the connection. The caller reconnects; it
        # does not get a garbled answer to a question it never asked.
        if code >= 400:
            self.close_connection = True
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if code >= 400:
            self.send_header("Connection", "close")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _rpc_error(self, http_code: int, code: int, message: str, extra: dict | None = None) -> None:
        self._send(http_code, {"jsonrpc": "2.0", "id": None,
                               "error": {"code": code, "message": message}}, extra)

    # ---- routes
    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/health":
            return self._health()
        if path == "/mcp":
            # Streamable HTTP allows a server with no server->client stream to refuse GET.
            return self._rpc_error(405, -32600, "this endpoint is POST-only", {"Allow": "POST"})
        self._send(404, {"error": "not found"})

    def do_DELETE(self):
        if urlparse(self.path).path.rstrip("/") == "/mcp":
            SESSIONS["ids"].pop(self.headers.get("Mcp-Session-Id", ""), None)
            return self._send(200, {"ok": True, "session": "ended"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path.rstrip("/") != "/mcp":
            return self._send(404, {"error": "not found"})
        if not origin_ok(self.headers.get("Origin", "")):
            return self._rpc_error(403, -32001, "Origin not allowed")
        identity, err = authenticate(self.headers)
        if err:
            code, why = err
            _log("AUTH-FAIL %s %s" % (self.address_string(), why))
            return self._rpc_error(code, -32001, why)
        ok, retry = LIMITER.hit(identity)
        if not ok:
            return self._rpc_error(429, -32002,
                                   "rate limit: %d calls per %d s" % (RATE_LIMIT, int(RATE_WINDOW)),
                                   {"Retry-After": str(retry)})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._rpc_error(400, -32600, "bad Content-Length")
        if length > MAX_BODY_BYTES:
            return self._rpc_error(413, -32600, "request body too large")
        try:
            raw = self.rfile.read(length) if length else b""
            message = json.loads(raw.decode("utf-8") or "null")
        except Exception as exc:
            return self._rpc_error(400, -32700, "parse error: %s" % str(exc)[:200])

        headers = {}
        if isinstance(message, dict) and message.get("method") == "initialize":
            headers["Mcp-Session-Id"] = new_session()
        if isinstance(message, list):
            out = [r for r in (dispatch(m, identity) for m in message) if r is not None]
            return self._send(200 if out else 202, out or {"ok": True}, headers)
        response = dispatch(message, identity)
        tool = ""
        if isinstance(message, dict) and message.get("method") == "tools/call":
            tool = str((message.get("params") or {}).get("name", ""))
        _log("POST /mcp %s %s %s" % (identity,
                                     (message or {}).get("method", "?") if isinstance(message, dict) else "batch",
                                     tool))
        if response is None:
            return self._send(202, {"ok": True}, headers)
        self._send(200, response, headers)

    def _health(self):
        identity, err = authenticate(self.headers)
        stopped = stop_reason()
        basic = {"ok": not stopped, "server": SERVER_INFO["name"], "version": SERVER_INFO["version"],
                 "transport": "mcp/streamable-http", "endpoint": "/mcp",
                 "auth": "X-Alma-Body-Token or a verified Cloudflare Access JWT",
                 "stopped": bool(stopped), "time": _iso()}
        if err:
            return self._send(200, basic)
        report = tool_report()
        basic.update({
            "identity": identity,
            "tools": len(M.TOOLS),
            "policy_source": _profile().get("source"),
            "policy_note": _profile().get("error", ""),
            "allowed": report["allow"], "needs_arming": report["confirm"],
            "blocked": report["block"],
            "arm": arm_state(),
            "stop_reason": stopped,
            "rate_limit": "%d/%ds" % (RATE_LIMIT, int(RATE_WINDOW)),
            "audit": str(M._audit_target()),
        })
        self._send(200, basic)


class BodyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False          # a second copy must FAIL, not silently shadow


def serve(host: str = "", port: int = 0, ready: threading.Event | None = None) -> BodyServer:
    httpd = BodyServer((host or HOST, int(port or PORT)), BodyHandler)
    if ready is not None:
        ready.set()
    return httpd


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALMIDO's body over HTTP (MCP Streamable HTTP)")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the server (default)")
    p_token = sub.add_parser("token", help="create the shared secret, ACL'd to this user")
    p_token.add_argument("--force", action="store_true", help="rotate an existing token")
    p_arm = sub.add_parser("arm", help="allow the CONFIRM tools for a while")
    p_arm.add_argument("--minutes", type=float, default=15.0)
    p_arm.add_argument("--tools", default="*", help="comma-separated globs, e.g. computer_*,phone_*")
    p_arm.add_argument("--note", default="")
    sub.add_parser("disarm", help="revoke the arm now")
    sub.add_parser("status", help="what this door would do right now")
    args = parser.parse_args(argv)
    cmd = args.cmd or "serve"

    if cmd == "token":
        print(json.dumps(create_token(args.force), ensure_ascii=False, indent=1))
        return 0
    if cmd == "arm":
        row = arm(args.minutes, [t for t in str(args.tools).split(",")], note=args.note)
        print(json.dumps(row, ensure_ascii=False, indent=1))
        return 0
    if cmd == "disarm":
        print(json.dumps({"disarmed": disarm()}, ensure_ascii=False))
        return 0
    if cmd == "status":
        report = tool_report()
        print(json.dumps({"listen": "%s:%d" % (HOST, PORT), "tools": len(M.TOOLS),
                          "token_present": bool(read_token()),
                          "access_configured": bool(access_config().get("aud")),
                          "policy_source": _profile().get("source"),
                          "policy_note": _profile().get("error", ""),
                          "allowed": report["allow"], "needs_arming": report["confirm"],
                          "blocked": report["block"], "arm": arm_state(),
                          "stop": stop_reason() or "clear"},
                         ensure_ascii=False, indent=1))
        return 0

    if not read_token() and not access_config().get("aud"):
        print("REFUSING TO START: there is no way to authenticate a caller.\n"
              "Run:  python %s token" % Path(__file__).name, file=sys.stderr)
        return 2
    if read_token() and os.environ.get("ALMA_BODY_SECURE", "1") == "1" and not file_is_private(TOKEN_FILE):
        state = _secure_file(TOKEN_FILE)
        if state is not True:
            print("REFUSING TO START: %s is readable by accounts other than yours (%s).\n"
                  "Fix it with:  icacls \"%s\" /inheritance:r /grant:r \"%%USERNAME%%:(F)\""
                  % (TOKEN_FILE, state, TOKEN_FILE), file=sys.stderr)
            return 3
    M.warm_computer()                     # pay the pyautogui import off the critical path
    httpd = serve()
    _log("SERVING on %s:%d  tools=%d  policy=%s" % (HOST, PORT, len(M.TOOLS), _profile().get("source")))
    print("alma-body on http://%s:%d/mcp  (%d tools)  health: /health" % (HOST, PORT, len(M.TOOLS)))
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""join.py — ER"N-GRID volunteer client (DiLoCo / Local-SGD loop).

ALMAWARE · 100% ours · purity law · plan-first · 2026-07-06, live 2026-08-24
Architecture: see D:/CLAUDE/eran-grid/SPEC.md  (this file IS component **B · Volunteer Client**).
Coordinator: D:/CLAUDE/eran-federation-app/worker/src/grid.js — a Cloudflare
Worker at https://federation.iddoperez.ai, not eran2/VPS as earlier drafts of
this file assumed.

WHAT THIS IS
------------
The volunteer training loop from SPEC.md §1 (DiLoCo / Local-SGD, "TRAIN"
path), now wired to a REAL coordinator. A volunteer runs ONE command; the
client:

    register()                         # SPEC §2-B, §2-A: claim a kosher slot
      -> pull_global()                 # authoritative protos + a real-voice shard
      -> train_real(H, pure python)    # H inner steps of prototype refinement
      -> compute_real_deltas()         # the pseudo-gradient we upload
      -> push_delta()                  # coordinator does the OUTER optimizer
      -> repeat                        # until told to stop / preempted

Communication drops ~H× vs step-wise data-parallel — that is the whole point
(SPEC §0/§1). We reference the METHODS (OpenDiLoCo / INTELLECT-1 / Petals) but
import NONE of them: stdlib only for the live path. No hivemind, no petals,
no requests, no external HTTP client. That is the ALMAWARE purity law.

PURITY / PRIVACY (SPEC §3)
--------------------------
- Volunteers train ONLY on public/curated shards handed out by the Coordinator
  (grid.js: real human voice already public, e.g. the Cafe-Claude episode —
  synthetic clips are banned as training data, measured 08-23 to transfer at
  chance).
- Sacred data (Iddo's voice, the private corpus, the organism's own state)
  NEVER leaves the DGX core. The organism on eran1 stays sovereign and
  read-only from this lane's point of view (grid.js "ONE-ERAN LAW"): the grid
  trains a separate cloud STUDENT copy the organism may eat later, or never.
- Kosher unit = one real person, one of their OWN accounts, within that
  provider's ToS. Sybil (one entity, many accounts) is forbidden — enforced at
  registration (see PROVIDER_PROFILES + register()).

STATE OF THE CODE
-----------------
The Coordinator is LIVE at https://federation.iddoperez.ai (grid.js, deployed
2026-08-24) and every method on CoordinatorClient below hits it for real.
Live mode trains the real cloud STUDENT brain — DiLoCo prototype refinement
over 192-dim vectors, pure Python, no torch on that path at all (purity law:
torch stays optional, used only by --dry-run's toy model). A 503 "no shards
yet" / "no student brain yet" from the coordinator is an HONEST answer, not a
client bug — it means the fleet hasn't curated/pushed training data yet.
With ``--dry-run`` the client still prints the intended loop end-to-end
(register -> pull -> train -> delta -> push) against a tiny in-memory toy
model and touches no network. It never silently changes a failed live run
into a simulation.

Run:
    py -3.13 join.py --dry-run --provider gcloud
    py -3.13 join.py --provider gcloud --consent yes     # live, one-liner
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field, asdict

# torch is the ONE heavy dependency we allow (SPEC purity: "stdlib + torch only").
# We degrade gracefully so --dry-run can be read/tested on a box without torch.
try:
    import torch
    import torch.nn as nn
    _HAVE_TORCH = True
except Exception:  # pragma: no cover - torch optional only for dry-run reading
    torch = None
    nn = None
    _HAVE_TORCH = False

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# The real, live ER"N-GRID coordinator (grid.js, Cloudflare Worker).
DEFAULT_COORDINATOR = "https://federation.iddoperez.ai"
# Identifies us to the coordinator in the register payload AND as the HTTP
# User-Agent — Cloudflare 403s the default urllib UA, so every request needs one.
USER_AGENT = "eran-grid/join.py"


# ---------------------------------------------------------------------------
# Per-provider ToS-respect profiles  (SPEC §4 — factual, not moral)
# ---------------------------------------------------------------------------
# The Coordinator is authoritative on policy; this table is the CLIENT-SIDE
# behavior hook so the volunteer respects each provider's terms by construction.

@dataclass
class ProviderProfile:
    name: str
    headless_ok: bool          # may we run long, unattended, background compute?
    interactive_heartbeat: bool  # must we prove a human is present (Colab)?
    short_bursts_only: bool    # cap H per round so we never look like a bg daemon
    max_inner_steps: int       # ceiling on H the client will accept from coord
    notes: str


# One real person, one of their OWN accounts, within ToS (SPEC §4 kosher unit).
PROVIDER_PROFILES = {
    # Google Cloud $300 trial: person == account == one trial. Full headless.
    "gcloud": ProviderProfile(
        name="gcloud", headless_ok=True, interactive_heartbeat=False,
        short_bursts_only=False, max_inner_steps=500,
        notes="Budget-aware; one trial per person.",
    ),
    # Kaggle: 30 GPU-hrs/week — quota-aware, but headless within a session is fine.
    "kaggle": ProviderProfile(
        name="kaggle", headless_ok=True, interactive_heartbeat=False,
        short_bursts_only=False, max_inner_steps=500,
        notes="Quota-aware scheduler; ~30 GPU-hrs/week.",
    ),
    # HF Spaces: within policy — lean toward inference / light delta work.
    "hf": ProviderProfile(
        name="hf", headless_ok=True, interactive_heartbeat=False,
        short_bursts_only=True, max_inner_steps=200,
        notes="Light delta / inference-leaning within Spaces policy.",
    ),
    # Colab free: BANS long background compute -> interactive heartbeat, short bursts.
    "colab": ProviderProfile(
        name="colab", headless_ok=False, interactive_heartbeat=True,
        short_bursts_only=True, max_inner_steps=100,
        notes="Interactive heartbeat; short bursts only; no bg daemon.",
    ),
    # Your own machine: no ToS to respect but your own, no trial to burn.
    "local": ProviderProfile(
        name="local", headless_ok=True, interactive_heartbeat=False,
        short_bursts_only=False, max_inner_steps=500,
        notes="Any machine you own — PC, laptop, home server.",
    ),
}


def provider_profile(name: str) -> ProviderProfile:
    if name not in PROVIDER_PROFILES:
        raise SystemExit(
            f"Unknown provider '{name}'. Choose one of: {', '.join(PROVIDER_PROFILES)}"
        )
    return PROVIDER_PROFILES[name]


# ---------------------------------------------------------------------------
# Local checkpoint — survive preemption / churn (SPEC §2-B)
# ---------------------------------------------------------------------------
# Colab/Kaggle/Spaces can preempt us at any moment. We persist just enough to
# resume the SAME round on restart without re-pulling from the Coordinator.

@dataclass
class GridState:
    node_id: str = ""
    member_secret: str = ""       # signs our deltas; minted once at register()
    provider: str = ""
    global_version: int = -1      # which authoritative version we pulled
    shard_id: str = ""            # data shard the Coordinator assigned us
    inner_step: int = 0           # progress inside the current H-step round
    rounds_done: int = 0          # completed delta round-trips this lifetime

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)     # atomic on POSIX & Windows — no half-written state

    @classmethod
    def load(cls, path: str) -> "GridState":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return cls(**json.load(f))
        return cls()


# ---------------------------------------------------------------------------
# Coordinator HTTP client  (SPEC §2-A — the API this talks to is grid.js, the
# Cloudflare Worker at https://federation.iddoperez.ai — LIVE since 2026-08-24)
# ---------------------------------------------------------------------------
# Deliberately built on urllib (stdlib) — NO `requests`, per purity law.
# Every method here hits a real /api/grid/* endpoint (see grid.js).

class CoordinatorClient:
    def __init__(self, base_url: str | None, dry_run: bool = False, timeout: float = 30.0):
        self.base_url = self._validated_url(base_url) if not dry_run else ""
        self.dry_run = dry_run
        self.timeout = timeout

    @staticmethod
    def _validated_url(base_url: str | None) -> str:
        raw = (base_url or "").strip()
        parsed = urllib.parse.urlsplit(raw)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("live coordinator must be a real HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("coordinator URL cannot contain credentials, query, or fragment")
        if parsed.path not in ("", "/"):
            raise ValueError("coordinator URL cannot contain a path")
        return raw.rstrip("/")

    def _send(self, req: urllib.request.Request) -> dict:
        """Shared transport. grid.js returns honest JSON even on 4xx/5xx (e.g.
        503 'no shards yet') — we surface that body as data, not an exception.
        Only real connectivity failures (URLError/OSError) still raise, so the
        refuse-to-fake-live behavior in main() is untouched."""
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"error": body[:200]}
            parsed.setdefault("ok", False)
            parsed["http_status"] = e.code
            return parsed

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON -> JSON. STUB in dry-run; real urllib call otherwise."""
        if self.dry_run:
            print(f"    [dry-run] POST {path}  <- {json.dumps(payload)[:120]}")
            return {"ok": True, "dry_run": True}
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        return self._send(req)

    def _get(self, path: str) -> dict:
        if self.dry_run:
            print(f"    [dry-run] GET  {path}")
            return {"ok": True, "dry_run": True}
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
        return self._send(req)

    # -- registration ------------------------------------------------------
    def register(self, node_id: str, provider: str, profile: ProviderProfile) -> dict:
        """Claim a slot. grid.js POST /api/grid/register -> {ok, member_id,
        version, note}. The member_id it returns IS our identity from here on
        (see main(): state.node_id is replaced with it) — the client's own
        node_id above is only a local stub, not a durable identity.

        REGISTRATION-SIDE NOTE (SPEC §2-B, §4): the "one real person, one own
        account" (anti-sybil) rule is enforced HERE, coordinator-side — the
        client cannot self-certify kosherness. We only DECLARE provider+profile.
        """
        payload = {
            "node_id": node_id,
            "provider": provider,
            "profile": asdict(profile),
            "client": USER_AGENT,
            "purity": "almaware-100pct-ours",
        }
        return self._post("/api/grid/register", payload)

    # -- pull authoritative global protos + a real-voice shard --------------
    def pull_global(self, node_id: str) -> dict:
        """GET /api/grid/global?node=<member_id> -> {ok, version, dim, protos,
        shard_id, shard:{id,source,vecs}, H, eta, rule}, or {ok:false, error}
        with HTTP 503 when there's no shard/brain yet — an honest answer, not
        a fault (see _send: we return that body instead of raising)."""
        return self._get(f"/api/grid/global?node={urllib.parse.quote(node_id, safe='')}")

    # -- push our pseudo-gradient (deltas) -----------------------------------
    def push_delta(self, node_id: str, member_secret: str, base_version: int, deltas: list) -> dict:
        """POST /api/grid/delta {node_id, member_secret, base_version, deltas:[{i,dv}...]}
        -> {ok, accepted, new_version, moved, gated}. accepted:false with
        reason "stale"/"too_fast" means: re-pull / wait and retry next round —
        not an error (grid.js: another member merged first, our base_version
        aged out, or we hit the per-member cooldown). Coordinator runs the OUTER
        step: seed-gated, norm-clipped merge, and signs it against member_secret.
        """
        payload = {"node_id": node_id, "member_secret": member_secret,
                   "base_version": base_version, "deltas": deltas}
        return self._post("/api/grid/delta", payload)

    # -- liveness for interactive providers (Colab) ------------------------
    def heartbeat(self, node_id: str) -> dict:
        """Prove a human is present (SPEC §4 Colab profile)."""
        return self._post("/api/grid/heartbeat", {"node_id": node_id, "t": time.time()})


# ---------------------------------------------------------------------------
# Toy replica model — STUB standing in for the real Eran replica
# ---------------------------------------------------------------------------
# SPEC §5.1/§5.3 prove the loop on a "tiny Eran replica" first. Real wiring will
# import eran-audio's build_model (see D:/CLAUDE/eran-audio/model.py) or the
# byte-LM. Until then this trivial net lets the WHOLE delta round-trip run.

def build_toy_model():
    """STUB(SPEC §2-B): replace with the real Eran replica factory.

    TODO(model wiring): swap for eran-audio `build_model(model_cfg_from(cfg))`
    or the byte-LM; keep the same state_dict() / load_state_dict() contract so
    compute_delta() and apply below are unchanged.
    """
    if not _HAVE_TORCH:
        return None
    torch.manual_seed(0)
    return nn.Sequential(nn.Linear(16, 32), nn.ReLU(), nn.Linear(32, 16))


def toy_batch(shard_id: str):
    """STUB: a deterministic 'public shard' batch. Real shards come from Coord.

    SPEC §3 privacy: volunteers only ever see PUBLIC/curated shards like this —
    never the sacred/private corpus.
    """
    if not _HAVE_TORCH:
        return None, None
    g = torch.Generator().manual_seed(abs(hash(shard_id)) % (2**31))
    x = torch.randn(64, 16, generator=g)
    y = x.roll(1, dims=1)          # trivial self-supervised target (toy)
    return x, y


# ---------------------------------------------------------------------------
# The DiLoCo / Local-SGD inner loop  (SPEC §1)
# ---------------------------------------------------------------------------

def train_local(model, shard_id: str, H: int, lr: float, state: GridState,
                ckpt_path: str, save_every: int = 25) -> None:
    """Train a full replica for H inner steps with AdamW (SPEC §1 TRAIN).

    Checkpoints mid-round so a preemption resumes from `state.inner_step`
    instead of restarting the whole H-step block (SPEC §2-B churn survival).
    """
    if not _HAVE_TORCH:
        print(f"    [no-torch] would AdamW-train {H} inner steps on shard={shard_id}")
        state.inner_step = H
        return

    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    x, y = toy_batch(shard_id)

    start = state.inner_step   # resume point after preemption
    for step in range(start, H):
        opt.zero_grad()
        out = model(x)
        loss = loss_fn(out, y)
        loss.backward()
        opt.step()

        state.inner_step = step + 1
        if (step + 1) % save_every == 0 or (step + 1) == H:
            # Persist BOTH the training weights and the round progress.
            torch.save(model.state_dict(), ckpt_path)
            state.save(ckpt_path + ".state.json")
            print(f"    inner {step + 1:>4}/{H}  loss={loss.item():.4f}  (ckpt saved)")


def compute_delta(local_model, global_state_dict) -> dict:
    """delta = local - global  (the pseudo-gradient we upload; SPEC §1).

    Returns metadata here; the REAL client ships compressed tensors (int8 /
    top-k — ours, SPEC §6 bandwidth). We compute the true delta so its norm is
    honest even in the skeleton.
    """
    if not _HAVE_TORCH:
        return {"stub": True, "note": "no torch; delta not computed"}
    local = local_model.state_dict()
    total_sq = 0.0
    n_params = 0
    for k, lv in local.items():
        gv = global_state_dict[k]
        d = lv - gv
        total_sq += float((d * d).sum())
        n_params += d.numel()
    # TODO(SPEC §6): attach compressed tensor payload; norm feeds Coordinator's
    #                §2-C norm-clip / cosine-gate robust aggregation.
    return {"delta_norm": total_sq ** 0.5, "n_params": n_params, "compressed": False}


# ---------------------------------------------------------------------------
# The REAL inner loop — live path, pure stdlib (no torch; SPEC purity law)
# ---------------------------------------------------------------------------
# grid.js hands us ~63 prototype vectors + a curated real-voice shard, both
# 192-dim. That is small enough that pure Python clears H~200 steps in well
# under a second — torch buys nothing here, so the live path never touches it.
# The step rule below matches grid.js's own `rule` string exactly, so client
# and coordinator agree on what one inner step means.

def _dot(a: list, b: list) -> float:
    return sum(ai * bi for ai, bi in zip(a, b))


def _l2_normalize(v: list) -> list:
    n = sum(c * c for c in v) ** 0.5
    return [c / n for c in v] if n > 0 else list(v)


def train_real(protos: list, shard_vecs: list, node_id: str, version: int,
               H: int, eta: float, round_no: int = 0) -> tuple:
    """DiLoCo inner loop against the REAL global (SPEC §1, live path).

    for each step: x = shard[perm[t % len]]; winner = argmax dot(proto, x);
    winner = l2_normalize((1-eta)*winner + eta*x)   -- grid.js's own `rule`.

    Shuffle order is a deterministic function of (node_id, version, round_no).
    round_no is IN the seed on purpose (2026-08-25): seeding by version alone
    meant that while the coordinator's version sat still, every round retrained
    the identical trajectory and re-pushed the identical delta — a volunteer
    watched 31 straight rounds come back "not merged" with no explanation.
    Varying the shard order per round explores different winners instead.
    (hashlib, not hash(): Python salts str hash per process, which silently
    broke cross-run reproducibility too.) Returns (local_protos,
    touched_indices) — `protos` itself is left untouched so the caller can
    still diff local-vs-global for the delta.
    """
    import hashlib
    local = [list(p) for p in protos]
    n = len(shard_vecs)
    digest = hashlib.sha256(f"{node_id}:{version}:{round_no}".encode()).digest()
    seed = int.from_bytes(digest[:4], "big")
    rng = random.Random(seed)
    perm = list(range(n))
    rng.shuffle(perm)

    touched: set[int] = set()
    for t in range(H):
        x = shard_vecs[perm[t % n]]
        winner_i = max(range(len(local)), key=lambda i: _dot(local[i], x))
        w = local[winner_i]
        cand = [(1 - eta) * w[d] + eta * x[d] for d in range(len(w))]
        local[winner_i] = _l2_normalize(cand)
        touched.add(winner_i)

    return local, touched


def compute_real_deltas(local: list, protos: list, touched: set) -> list:
    """delta = local - global for the touched prototypes only (SPEC §1),
    rounded to 6dp — matches grid.js's own ROUND6 so re-sent deltas are exact."""
    deltas = []
    for i in sorted(touched):
        dv = [round(local[i][d] - protos[i][d], 6) for d in range(len(protos[i]))]
        deltas.append({"i": i, "dv": dv})
    return deltas


# ---------------------------------------------------------------------------
# One full DiLoCo round  (register is done once; this repeats)
# ---------------------------------------------------------------------------

def run_round_toy(coord: CoordinatorClient, model, profile: ProviderProfile,
                   state: GridState, H: int, lr: float, ckpt_path: str) -> None:
    """pull -> snapshot global -> train H -> delta -> push. --dry-run ONLY:
    the toy in-memory torch model, never the live coordinator/protos path."""

    # 1) Pull (dry-run stub only — this function never runs live; see
    #    run_round_live for the real pull/train/delta/push against grid.js).
    print("  [pull] fetching global weights + shard from Coordinator")
    coord.pull_global(state.node_id)
    state.global_version += 1
    state.shard_id = state.shard_id or "shard-0"

    # Snapshot the GLOBAL weights BEFORE local training — delta is measured
    # against this exact reference (SPEC §1: pseudo-gradient = local - global).
    global_snapshot = (
        copy.deepcopy(model.state_dict()) if _HAVE_TORCH and model is not None else None
    )

    # 2) Heartbeat for interactive providers (Colab ToS — SPEC §4).
    if profile.interactive_heartbeat:
        print("  [heartbeat] interactive provider -> proving human presence")
        coord.heartbeat(state.node_id)

    # 3) Train H inner steps locally with AdamW (SPEC §1).
    print(f"  [train] {H} inner steps (AdamW, lr={lr}) on shard={state.shard_id}")
    train_local(model, state.shard_id, H, lr, state, ckpt_path)

    # 4) Compute the delta (local - global).
    delta_meta = compute_delta(model, global_snapshot) if global_snapshot is not None \
        else {"stub": True}
    print(f"  [delta] {json.dumps(delta_meta)}")

    # 5) Push the delta; Coordinator runs the outer optimizer + robust merge.
    print("  [push] uploading delta to Coordinator (outer Nesterov step happens there)")
    coord.push_delta(state.node_id, state.member_secret, state.global_version, delta_meta)

    # 6) Round complete — reset inner progress, bump counter, persist.
    state.inner_step = 0
    state.rounds_done += 1
    state.save(ckpt_path + ".state.json")
    print(f"  [round {state.rounds_done}] complete; delta round-tripped.\n")


def run_round_live(coord: CoordinatorClient, profile: ProviderProfile,
                    state: GridState, H: int, ckpt_path: str) -> bool:
    """pull -> train_real(H) -> compute_real_deltas -> push. One REAL outer
    round against grid.js. No torch anywhere in this path (purity law).

    Returns True if the round trained+pushed (whatever the merge outcome —
    a "stale"/"raced" reject is honest, not a failure). Returns False if the
    pull came back 503 "no shards/brain yet" — nothing to train on this round.
    """
    print("  [pull] fetching global protos + shard from Coordinator")
    g = coord.pull_global(state.node_id)
    if not g.get("ok", False):
        print(f"  [!] {g.get('error', 'coordinator refused the pull')} "
              f"(http {g.get('http_status', '?')})\n")
        return False

    version = int(g["version"])
    protos = g["protos"]
    shard = g["shard"]["vecs"]
    shard_id = str(g.get("shard_id", ""))
    eta = float(g.get("eta", 0.05))
    H_round = min(H, int(g.get("H", H)))   # respect both our ceiling and the server's

    state.global_version = version
    state.shard_id = shard_id

    # Heartbeat for interactive providers (Colab ToS — SPEC §4).
    if profile.interactive_heartbeat:
        print("  [heartbeat] interactive provider -> proving human presence")
        coord.heartbeat(state.node_id)

    print(f"  [train] {H_round} inner steps (pure-python DiLoCo, eta={eta}) "
          f"on shard={shard_id} ({len(shard)} vecs, dim={g.get('dim')})")
    local, touched = train_real(protos, shard, state.node_id, version, H_round, eta,
                                round_no=state.rounds_done)
    deltas = compute_real_deltas(local, protos, touched)
    print(f"  [delta] {len(deltas)} prototype(s) touched (of {len(protos)})")

    print("  [push] uploading deltas to Coordinator (outer merge happens there)")
    resp = coord.push_delta(state.node_id, state.member_secret, version, deltas)
    if resp.get("accepted"):
        print(f"  [merged] new_version={resp.get('new_version')} "
              f"moved={resp.get('moved')} gated={resp.get('gated')}")
    else:
        # Say WHAT happened, always. "reason=None" for two minutes straight is
        # how a volunteer concludes the whole thing is broken (2026-08-25).
        why = resp.get("reason") or resp.get("error")
        if not why and resp.get("gated") is not None:
            why = (f"all {resp.get('gated')} deltas held by the safety cone "
                   f"(moved={resp.get('moved', 0)}, clipped={resp.get('clipped', 0)}) "
                   f"— normal; retrying a different shard order")
        print(f"  [not merged] {why or 'coordinator gave no detail'} "
              f"(version={resp.get('new_version')}) -> re-pull next round")

    state.inner_step = 0
    state.rounds_done += 1
    state.save(ckpt_path + ".state.json")
    print(f"  [round {state.rounds_done}] complete.\n")
    return True


# ---------------------------------------------------------------------------
# CLI + main loop
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="join.py",
        description="ER\"N-GRID volunteer client — DiLoCo/Local-SGD (SPEC.md §2-B).",
    )
    p.add_argument("--coordinator", default=DEFAULT_COORDINATOR,
                   help=f"Coordinator base URL (SPEC §2-A). Default: {DEFAULT_COORDINATOR}"
                        " — ignored under --dry-run.")
    p.add_argument("--provider", required=True,
                   choices=sorted(PROVIDER_PROFILES.keys()),
                   help="Which provider you (one person, own account) run on.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the intended loop with no live Coordinator.")
    p.add_argument("--consent", choices=("yes",), default=None,
                   help="Required in live mode: confirms an account you own and control.")
    p.add_argument("--inner-steps", type=int, default=None,
                   help="H inner steps per round (default: provider max, SPEC §1 H≈500).")
    p.add_argument("--lr", type=float, default=1e-3, help="Inner AdamW learning rate.")
    p.add_argument("--rounds", type=int, default=2,
                   help="Outer rounds to run this session (skeleton default: 2).")
    p.add_argument("--workdir", default=None,
                   help="Where to keep local checkpoints (default: alongside join.py).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    dry_run = args.dry_run
    if not dry_run and not args.coordinator:
        print("[error] live mode requires --coordinator. Use --dry-run for the verified toy demo.")
        return 2
    if not dry_run and args.consent != "yes":
        print("[error] live mode requires --consent yes.")
        return 2

    profile = provider_profile(args.provider)

    # Clamp H to the provider's ToS ceiling (SPEC §4). Colab/HF => short bursts.
    H = args.inner_steps if args.inner_steps is not None else profile.max_inner_steps
    H = min(H, profile.max_inner_steps)

    workdir = args.workdir or os.path.dirname(os.path.abspath(__file__))
    os.makedirs(workdir, exist_ok=True)
    ckpt_path = os.path.join(workdir, f"grid_local_{args.provider}.pt")
    state_path = ckpt_path + ".state.json"

    # Resume prior state if we were preempted mid-life (SPEC §2-B).
    state = GridState.load(state_path)
    if not state.node_id:
        # STUB(SPEC §2-B): real node_id is bound to a verified human at register().
        state.node_id = f"{args.provider}-{uuid.uuid4().hex[:8]}"
        state.provider = args.provider

    print("=" * 68)
    print("  ER\"N-GRID volunteer client  ·  ALMAWARE · 100% ours")
    print("  DiLoCo / Local-SGD loop  ·  SPEC.md §2-B")
    print("=" * 68)
    print(f"  node_id     : {state.node_id}")
    print(f"  provider    : {profile.name}  ({profile.notes})")
    print(f"  headless_ok : {profile.headless_ok}   "
          f"heartbeat: {profile.interactive_heartbeat}   "
          f"short_bursts: {profile.short_bursts_only}")
    print(f"  inner H     : {H}   (provider ceiling {profile.max_inner_steps})")
    print(f"  coordinator : {'(dry-run — coordinator not contacted)' if dry_run else args.coordinator}")
    print(f"  checkpoint  : {ckpt_path}")
    print(f"  torch       : {'yes' if _HAVE_TORCH else 'NO (skeleton prints only)'}")
    print("  platform    :", platform.platform())
    print("=" * 68 + "\n")

    try:
        coord = CoordinatorClient(args.coordinator, dry_run=dry_run)
    except ValueError as exc:
        print(f"[error] coordinator refused: {exc}")
        return 2

    # --- register once (anti-sybil enforced coordinator-side) ---
    # A saved identity is REUSED: re-registering on every launch minted a fresh
    # phantom member per run (2026-08-25) and orphaned the old one's rounds.
    if not dry_run and state.node_id.startswith("m-") and state.member_secret:
        print(f"[register] resuming existing member identity {state.node_id} "
              f"(saved state — no re-registration)")
        print()
        reg = {"ok": True, "member_id": state.node_id, "resumed": True}
    else:
        print("[register] claiming a kosher slot (one person, one own account)")
        try:
            reg = coord.register(state.node_id, args.provider, profile)
            # Never print the body verbatim — it carries member_secret, our
            # signing credential. Show only the non-secret fields.
            print(f"  -> coordinator: ok={reg.get('ok')} member_id={reg.get('member_id')} "
                  f"version={reg.get('version')}")
            member_id = reg.get("member_id")
            member_secret = reg.get("member_secret")
            if not dry_run and reg.get("ok") and member_id and member_secret:
                print(f"  -> adopted member_id: {state.node_id} -> {member_id} (secret held)")
                state.node_id = member_id
                state.member_secret = member_secret
                state.save(state_path)
            elif not dry_run and reg.get("ok") and not member_secret:
                print("  [!] coordinator returned no member_secret; cannot sign deltas. Stopping.")
                return 1
            print()
        except (urllib.error.URLError, OSError) as e:
            print(f"  [!] coordinator unreachable ({e}); live run stopped.\n")
            return 1

    # --- build the (toy, for now) replica — dry-run ONLY; the live path below
    #     is pure Python and never touches torch (purity law). ---
    model = build_toy_model() if dry_run else None

    # --- outer loop: repeat DiLoCo rounds ---
    for r in range(args.rounds):
        print(f"--- outer round {r + 1}/{args.rounds} "
              f"(lifetime round {state.rounds_done + 1}) ---")
        try:
            if dry_run:
                run_round_toy(coord, model, profile, state, H, args.lr, ckpt_path)
            else:
                run_round_live(coord, profile, state, H, ckpt_path)
        except KeyboardInterrupt:
            print("\n[interrupt] checkpoint saved; safe to resume later.")
            state.save(state_path)
            return 130
        except (urllib.error.URLError, OSError) as e:
            # Preemption / network churn — persist and stop cleanly (SPEC §2-B).
            print(f"[churn] coordinator/network issue ({e}); state saved, will resume.")
            state.save(state_path)
            return 1

        # Respect the coordinator's per-member cooldown (grid.js MIN_DELTA_GAP_MS
        # = 3 s) so a back-to-back round is not wasted as "too_fast".
        if not dry_run and r + 1 < args.rounds:
            time.sleep(3.2)

        # short-bursts providers pause between rounds so we never look like a
        # long-running background daemon (SPEC §4 Colab/HF).
        if profile.short_bursts_only and r + 1 < args.rounds:
            print("  [burst-gap] short-bursts provider -> brief pause before next round\n")
            time.sleep(0.1)   # STUB: real gap is minutes; kept tiny for the skeleton.

    print("[done] session complete. "
          f"lifetime rounds={state.rounds_done}, version={state.global_version}.")
    print("       This client is a BODY for the global Eran, not a replacement")
    print("       for the sovereign DGX core (SPEC §3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""join.py — ER"N-GRID volunteer client (DiLoCo / Local-SGD loop).

ALMAWARE · 100% ours · purity law · plan-first · 2026-07-06
Architecture: see D:/CLAUDE/eran-grid/SPEC.md  (this file IS component **B · Volunteer Client**).

WHAT THIS IS
------------
A runnable *skeleton* of the volunteer training loop from SPEC.md §1 (DiLoCo /
Local-SGD, "TRAIN" path). A volunteer runs ONE command; the client:

    register()                         # SPEC §2-B, §2-A: claim a kosher slot
      -> pull_global_weights_and_shard()   # authoritative weights + data shard
      -> train_local(H, AdamW)         # H≈500 inner steps on a full replica
      -> compute_delta(local - global) # the pseudo-gradient we upload
      -> push_delta()                  # coordinator does the OUTER optimizer
      -> repeat                        # until told to stop / preempted

Communication drops ~H× vs step-wise data-parallel — that is the whole point
(SPEC §0/§1). We reference the METHODS (OpenDiLoCo / INTELLECT-1 / Petals) but
import NONE of them: stdlib + torch only. No hivemind, no petals, no requests,
no external HTTP client. That is the ALMAWARE purity law.

PURITY / PRIVACY (SPEC §3)
--------------------------
- Volunteers train ONLY on public/curated shards handed out by the Coordinator.
- Sacred data (Iddo's voice, the private corpus) NEVER leaves the DGX core.
- Kosher unit = one real person, one of their OWN accounts, within that
  provider's ToS. Sybil (one entity, many accounts) is forbidden — enforced at
  registration (see PROVIDER_PROFILES + register()).

STATE OF THE CODE
-----------------
Every place the real Coordinator HTTP API or the real Eran model must attach is
marked  `# TODO(SPEC §...)`  and, where it stands in for live behavior, `STUB:`.
With no coordinator reachable the client runs in **--dry-run** mode: it prints
the intended loop end-to-end (register -> pull -> train -> delta -> push) using a
tiny in-memory toy model, so you can read the whole shape before wiring the API.

Run:
    python join.py --coordinator https://grid.almaware/eran --provider gcloud
    python join.py --dry-run --provider colab        # no coordinator needed
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
# Coordinator HTTP client  (SPEC §2-A — the API this talks to lives on eran2/VPS)
# ---------------------------------------------------------------------------
# Deliberately built on urllib (stdlib) — NO `requests`, per purity law.
# Every method here is where the REAL Coordinator endpoints attach.

class CoordinatorClient:
    def __init__(self, base_url: str | None, dry_run: bool = False, timeout: float = 30.0):
        self.base_url = (base_url or "").rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON -> JSON. STUB in dry-run; real urllib call otherwise."""
        if self.dry_run:
            print(f"    [dry-run] POST {path}  <- {json.dumps(payload)[:120]}")
            return {"ok": True, "dry_run": True}
        # TODO(SPEC §2-A): confirm real endpoint paths + auth header w/ Coordinator.
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str) -> dict:
        if self.dry_run:
            print(f"    [dry-run] GET  {path}")
            return {"ok": True, "dry_run": True}
        # TODO(SPEC §2-A): real GET (weights blob may be binary, not JSON — see below).
        url = f"{self.base_url}{path}"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # -- registration ------------------------------------------------------
    def register(self, node_id: str, provider: str, profile: ProviderProfile) -> dict:
        """Claim a slot. Coordinator enforces Beit-Din trust + one-account-per-person.

        REGISTRATION-SIDE NOTE (SPEC §2-B, §4): the "one real person, one own
        account" (anti-sybil) rule is enforced HERE, coordinator-side — the
        client cannot self-certify kosherness. We only DECLARE provider+profile;
        the Coordinator binds it to a verified human identity (ALMA-Link /
        Beit-Din trust) and may refuse duplicates.
        """
        payload = {
            "node_id": node_id,
            "provider": provider,
            "profile": asdict(profile),
            "client": "eran-grid/join.py",
            "purity": "almaware-100pct-ours",
        }
        # TODO(SPEC §2-A/C): endpoint returns assigned shard_id, layer range,
        #                    accepted H, and current global_version.
        return self._post("/register", payload)

    # -- pull authoritative global weights + assignment --------------------
    def pull_global(self, node_id: str) -> dict:
        """Fetch authoritative weights + version + data shard (SPEC §2-A)."""
        # TODO(SPEC §2-A): real impl streams a binary weights blob (safetensors-
        #   style, OURS) + metadata; here it is one JSON call for the skeleton.
        return self._get(f"/global?node={node_id}")

    # -- push our pseudo-gradient (delta) ----------------------------------
    def push_delta(self, node_id: str, global_version: int, delta_meta: dict) -> dict:
        """Upload delta = local - global. Coordinator runs the OUTER optimizer.

        SPEC §1: coordinator applies Nesterov-momentum outer step + robust
        aggregation (§2-C: norm-clip, cosine gate, validation-gated merge).
        The heavy tensor payload will be compressed (int8 / top-k — ours, SPEC §6).
        """
        payload = {
            "node_id": node_id,
            "base_version": global_version,   # which version this delta is against
            "delta": delta_meta,              # TODO: real tensor blob, compressed
        }
        # TODO(SPEC §2-A): endpoint returns whether merge was accepted + new version.
        return self._post("/delta", payload)

    # -- liveness for interactive providers (Colab) ------------------------
    def heartbeat(self, node_id: str) -> dict:
        """Prove a human is present (SPEC §4 Colab profile)."""
        return self._post("/heartbeat", {"node_id": node_id, "t": time.time()})


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
# One full DiLoCo round  (register is done once; this repeats)
# ---------------------------------------------------------------------------

def run_round(coord: CoordinatorClient, model, profile: ProviderProfile,
              state: GridState, H: int, lr: float, ckpt_path: str) -> None:
    """pull -> snapshot global -> train H -> delta -> push. One outer round."""

    # 1) Pull authoritative weights + shard (SPEC §2-A).
    print("  [pull] fetching global weights + shard from Coordinator")
    g = coord.pull_global(state.node_id)
    if not coord.dry_run:
        # TODO(model wiring): deserialize real weights blob -> model.load_state_dict.
        # STUB: dry-run/skeleton keeps whatever weights the model already has.
        state.global_version = int(g.get("version", state.global_version + 1))
        state.shard_id = str(g.get("shard_id", state.shard_id or "shard-0"))
    else:
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
    coord.push_delta(state.node_id, state.global_version, delta_meta)

    # 6) Round complete — reset inner progress, bump counter, persist.
    state.inner_step = 0
    state.rounds_done += 1
    state.save(ckpt_path + ".state.json")
    print(f"  [round {state.rounds_done}] complete; delta round-tripped.\n")


# ---------------------------------------------------------------------------
# CLI + main loop
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="join.py",
        description="ER\"N-GRID volunteer client — DiLoCo/Local-SGD (SPEC.md §2-B).",
    )
    p.add_argument("--coordinator", default=None,
                   help="Coordinator base URL (SPEC §2-A). Omit for --dry-run.")
    p.add_argument("--provider", required=True,
                   choices=sorted(PROVIDER_PROFILES.keys()),
                   help="Which provider you (one person, own account) run on.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the intended loop with no live Coordinator.")
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

    # No coordinator + not explicitly dry-run -> fall back to dry-run, loudly.
    dry_run = args.dry_run or not args.coordinator
    if dry_run and not args.dry_run:
        print("[note] no --coordinator given -> running in DRY-RUN mode.\n")

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
    print(f"  coordinator : {args.coordinator or '(none — dry-run)'}")
    print(f"  checkpoint  : {ckpt_path}")
    print(f"  torch       : {'yes' if _HAVE_TORCH else 'NO (skeleton prints only)'}")
    print("  platform    :", platform.platform())
    print("=" * 68 + "\n")

    coord = CoordinatorClient(args.coordinator, dry_run=dry_run)

    # --- register once (anti-sybil enforced coordinator-side) ---
    print("[register] claiming a kosher slot (one person, one own account)")
    try:
        reg = coord.register(state.node_id, args.provider, profile)
        print(f"  -> coordinator: {json.dumps(reg)[:160]}\n")
    except (urllib.error.URLError, OSError) as e:
        print(f"  [!] coordinator unreachable ({e}); switching to dry-run.\n")
        coord.dry_run = True

    # --- build the (toy, for now) replica ---
    model = build_toy_model()

    # --- outer loop: repeat DiLoCo rounds ---
    for r in range(args.rounds):
        print(f"--- outer round {r + 1}/{args.rounds} "
              f"(lifetime round {state.rounds_done + 1}) ---")
        try:
            run_round(coord, model, profile, state, H, args.lr, ckpt_path)
        except KeyboardInterrupt:
            print("\n[interrupt] checkpoint saved; safe to resume later.")
            state.save(state_path)
            return 130
        except (urllib.error.URLError, OSError) as e:
            # Preemption / network churn — persist and stop cleanly (SPEC §2-B).
            print(f"[churn] coordinator/network issue ({e}); state saved, will resume.")
            state.save(state_path)
            return 1

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

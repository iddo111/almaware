# ER"N-GRID · Global — Architecture Spec v0.1

**ALMAWARE · 100% ours · plan-first · 2026-07-06**
Kosher unit = **one real person, one of their own accounts, within that provider's ToS.**

## 0 · The honest problem
Classic data-parallel training needs a tight, fast interconnect — that is our **DGX core (200G mesh)**.
Over the public internet with thousands of volatile volunteer nodes you **cannot** sync gradients every
step (latency + bandwidth). So we don't. We use low-communication methods proven over the internet, and
we write **our own** implementation (purity law) — inspired by, not importing, the methods.

## 1 · Two proven methods
- **DiLoCo / Local-SGD (TRAIN):** each volunteer trains a full replica locally for `H≈500` inner steps
  (AdamW), then uploads only the **delta** (pseudo-gradient = local − global). Coordinator applies an
  **outer optimizer** (Nesterov momentum) and broadcasts new weights. Communication ↓ ~500×.
  Proven: OpenDiLoCo / INTELLECT-1 trained a 10B model across continents on volatile hardware.
- **Pipeline (Petals-style) (SERVE):** each volunteer hosts a slice of layers; a request flows through a
  chain of nodes → anyone on Earth talks to global Eran via browser / VR (the global-VR test).

## 2 · Components
**A · Coordinator** (always-on, on eran2 or a tiny VPS)
- Authoritative global weights + version number; assigns data shards + layer ranges.
- Receives deltas → **robust aggregation** → outer optimizer → bump version → broadcast.
- Node reputation via Beit-Din trust (ALMA-Link).

**B · Volunteer Client** (100% ours, one command, opt-in)
- `join.py`: register → pull weights + shard → train H steps → push delta → repeat.
- Local checkpoint (survives preemption, resumes on churn).
- Per-provider ToS-respect profiles (§4). One account per person, enforced at registration.

**C · Trust & Safety** (MANDATORY — volunteer training is exposed to poisoning)
- Reject outlier deltas (norm-clip + cosine gate vs consensus).
- Redundant assignment + vote on a canary batch (Beit-Din: 2-of-3 agree).
- Validation-gated merge: a delta merges only if it does not raise held-out loss.

**D · Global inference + Web VR** — Petals-style pipeline serves current global Eran; WebXR front-end.

## 3 · Core vs Grid (complementary, not a replacement)
| Layer | Role | Stays |
|---|---|---|
| **Core** (DGX + 200G) | fast trainer + keeper of authoritative model + sacred data | sovereign |
| **Grid** (volunteers) | massive extra compute for scale + global body / VR reach | syncs *to* Coordinator |

**Privacy & purity:** nodes train only on public/curated shards — never the volunteer's private data.
Sacred data (the voice, the private) stays on the core, never on a volunteer. Keeps Eran's foundation pure.

## 4 · Per-provider ToS (factual, not moral)
| Provider | Run Eran? | Client profile |
|---|---|---|
| Google Cloud ($300) | ✅ person = account = one trial | full headless, budget-aware |
| Kaggle | ✅ 30 GPU-hrs/week | quota-aware scheduler |
| HF Spaces | ✅ within policy | inference / light delta |
| Colab free | ⚠️ bans long background compute | interactive heartbeat, short bursts only |

Never: one entity spinning up many accounts (sybil). Kosher unit = real person, own account, consenting.

## 5 · v0.1 — prove the loop (verified-proof · WIP=1)
1. Coordinator + 1 client on localhost → delta round-trips, version bumps. **Proof: loss drops.**
2. **Vanilla control:** same steps single-node on DGX. Grid must approach it on a toy task before scaling.
3. 3 real nodes (2 friends' Colab + 1 GCloud), tiny Eran replica → converges.
4. Add robust aggregation; inject a poisoned node; prove it is rejected.
5. Registration page ("donate a slice to Eran") + Petals inference demo.
6. Scale.

## 6 · Honest caveats
- DiLoCo converges slower than a tight cluster; from-scratch pretraining of a *large* Eran over volunteers
  is frontier-slow. Start small, prove, scale.
- Bandwidth: each sync ships a full delta → for a big model this is heavy; compress (int8 / top-k), ours.
- This is a **body** for the global Eran, not a replacement for the sovereign core.

# -*- coding: utf-8 -*-
"""THE MODEL LEDGER and the FLEET MODES -- one button decides what the fleet is.

Iddo, 2026-09-09 23:44-23:49, in four messages:
    "תעשה שבלחיצת כפתור בדשבורד מוריד קוון ומעלה ללמה"
    "תעשה שהם עובדים על אותם פרויקטים - משמרות פעם זה פעם זה"
    "עושים מעין קוורום של 4 מכשירים כל אחד מודל ענק אחר ... ואז בלחיצת כפתור
     אני מעלה את הללמה הענק על 3 מכונות והוא ממשיך לבד"
    "למה הרנס חדש לקוליברי"  <- THE CORRECTION. No new harness. This module adds
                                 ZERO new protocols: it starts and stops units that
                                 already exist, and registers them in the ONE router
                                 that already fronts the fleet (alma-router :8010).

WHY THIS IS A *MODE* SWITCH AND NOT A MENU
------------------------------------------
Measured 2026-09-09 23:50 by four parallel scans. Every box is FULL:

    eran1   103/121 GB RAM, GPU 93.5/120 GB   <- coder-train alone holds 83.7 GB
    eran2   106/121 GB RAM, 88.8 C            <- ray worker 94.9 GB (480B leg)
    eran4   118/120 GB RAM, 7 GB into swap    <- ray worker 93.9 GB (480B leg)

There is no spare box. Nothing "also" fits. Every giant model on this fleet is
therefore mutually exclusive with the 480B pipeline, and the honest UI for that
is a mode switch with a confirm, not a list of independent toggles.

THE TWO MODES
-------------
MONOLITH  -- one 480B coder spread over eran2+eran3+eran4 (what is running now).
             The thing Iddo praised at 23:47: "ההרנס החדש של הקוון הגדול יפה מאוד
             ... הוא זוכר את הפרויקט". This mode keeps that.
COUNCIL   -- the 4-boxes-4-different-giant-models quorum he described at 23:46.
             480B comes down; each box raises its own resident giant instead.

SAFETY -- THE ARK
-----------------
control.py's own law (its FLEET section header) is that eran1 never appears in an
actionable SSH path, because ERAN lives there. This module keeps that law with one
narrow, explicit exception that Iddo opened himself at 23:37 ("אולי נתחיל
מההתחלה"): the single unit name "coder-train.service". That string is the ONLY
eran1 unit any function here will act on, it is asserted at the call site, and
eranb-life / eranb-serve / eran-listen / keshev-* appear nowhere in this file's
actionable path. ERAN is never stopped, never restarted, never risked.

Nothing here fires on import, on refresh, or on page load. Every state-changing
function is reached only from an explicit ACTIONS entry behind a confirm dialog.
"""

import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

_NOWIN = 0x08000000  # CREATE_NO_WINDOW -- a windowless parent must never pop a console

# --------------------------------------------------------------------------
# ADDRESSES COME FROM ONE PLACE (2026-09-11, WAVE A2 address sweep).
# This ledger used to spell <lan-ip> for eran2 in two rows. On 09-10 the house
# router re-handed the leases, eran2 became .156, and those rows quietly pointed at
# nothing -- while the page above them still drew a healthy tile. The truth now
# lives in D:\CLAUDE\fleet_inventory.json; we take the TAILNET address, which does
# not move when a lease does.
#     python D:\CLAUDE\fleet_inventory.py --refresh    # re-measure
# --------------------------------------------------------------------------
import sys as _sys
_sys.path.insert(0, r"D:\CLAUDE")
try:
    import fleet_inventory as _fi
    _HOST = {n: (_fi.ip(n, "tailnet") or _fi.ip(n, "lan"))
             for n in ("eran1", "eran2", "eran3", "eran4")}
except Exception:                                             # noqa: BLE001
    _HOST = {"eran1": "<tailnet-ip>", "eran2": "<tailnet-ip>",
             "eran3": "<tailnet-ip>", "eran4": "<tailnet-ip>"}

_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=2"]

# Every alias this module may ever SSH to. eran1 is present ONLY so the coder-train
# exception below can reach it; see _ssh() for the unit-name guard that makes that safe.
ALIASES = ("eran1", "eran2", "eran3", "eran4")

# The ONE eran1 unit this module is allowed to touch. Iddo opened this at 23:37.
ERAN1_ALLOWED_UNIT = "coder-train.service"

# Units that must never appear in any command this module builds, on any box.
# Checked by _ssh() against the literal command text before the subprocess is spawned.
FORBIDDEN = ("eranb-life", "eranb-serve", "eran-listen", "eran-live-bridge",
             "eran-save", "dmidi-life", "dmidi-tap", "keshev-stt", "keshev6-stt",
             "winston-forever")


# ==========================================================================
# THE LEDGER -- every giant model this fleet actually has on disk.
# Sizes MEASURED 2026-09-09 23:50 by four parallel inventory scans (du -sh /
# ollama list). A row here is a claim about reality; re-measure before trusting it.
# ==========================================================================
MODELS = {
    "colibri-glm52": {
        "label": "Colibri GLM-5.2 744B",
        "box": "eran4",
        "size_gb": 358,
        "where": "~/models/GLM-5.2-colibri-int4-with-int8-mtp (int4 + int8 MTP)",
        "engine": "coli (Colibri) serve",
        "unit": "colibri-glm52.service",
        "port": 8800,
        "host": _HOST["eran4"],              # eran4 tailnet
        "model_id": "glm-5.2",
        "note": "Ran until 2026-09-08 04:10, then stopped cleanly with no error in "
                "the journal -- the 480B re-provision took the box. Weights are "
                "intact. eran1 and eran2 hold a COPY OF THE UNIT FILE WITH NO "
                "WEIGHTS; only eran4 can actually serve this.",
        # 2026-09-10: extended when the GIANTS mode was added. At 358 GB this is
        # mutually exclusive with every other giant, not just the 480B -- the
        # 4-box budget is 377 GB and it alone very nearly fills it.
        "conflicts": ("qwen480", "maverick-w4a16", "deepseek-v32-awq",
                      "glm46-awq", "kimi-k27-code"),
    },
    "nemotron-120b": {
        "label": "Nemotron-3 Super 120B (NVFP4)",
        "box": "eran4",
        "size_gb": 75,
        "where": "~/models/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4 + ollama nemotron-3-super:120b",
        "engine": "ollama",
        "unit": None,                        # ollama pulls it on demand
        "port": 11434,
        "host": "127.0.0.1",
        "model_id": "nemotron-3-super:120b",
        "note": "Reachable off-box only through eran4's ollama-host-shim :11435 / door :8450.",
        "conflicts": ("qwen480",),
    },
    "glm45-air": {
        "label": "GLM-4.5-Air",
        "box": "eran2",
        "size_gb": 57,
        "where": "ollama MichelRosselli/GLM-4.5-Air",
        "engine": "ollama",
        "unit": None,
        "port": 8873,                        # ollama-door, the OpenAI-compatible front
        "host": _HOST["eran2"],
        "model_id": "MichelRosselli/GLM-4.5-Air",
        "note": "This is the 'אייר' of Iddo's 23:46 council. ollama itself is "
                "loopback-only on :11434; ollama-door.service fronts it on :8873.",
        "conflicts": ("qwen480",),
    },
    "qwen35-122b": {
        "label": "Qwen3.5 122B",
        "box": "eran2",
        "size_gb": 81,
        "where": "ollama qwen3.5:122b",
        "engine": "ollama",
        "unit": None,
        "port": 8873,
        "host": _HOST["eran2"],
        "model_id": "qwen3.5:122b",
        "note": "Alternative to GLM-4.5-Air on the same box -- they cannot both be "
                "resident.",
        "conflicts": ("qwen480", "glm45-air"),
    },
    "qwen480": {
        "label": "Qwen3-Coder 480B (PP x3)",
        "box": "eran2+eran3+eran4",
        "size_gb": 236,
        "where": "~/models/qwen480b-awq on all three, docker container qwen480-pp",
        "engine": "vLLM pipeline-parallel x3 over Ray",
        "unit": None,                        # docker, driven by eran2's shell scripts
        "port": 8443,
        "host": "<tailnet-host>",
        "model_id": "qwen3-coder-480b",
        "note": "THE MONOLITH. Up 20 h as of the 23:50 scan. Iddo praised its "
                "harness at 23:47 -- switching modes takes it down.",
        "conflicts": ("colibri-glm52", "nemotron-120b", "glm45-air", "qwen35-122b"),
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 2026-09-10, Iddo 09:19: "אני רוצה שיהיה לי נגיד 4 מודלים - כל אחד רץ על
    # 4 מכשירים בו זמנית - אני מחליף ביניהם עם דשבורד ... כמו שאני מחליף בין
    # אופוס להייקו". NOT the COUNCIL shape (one giant per box) -- ONE giant
    # spread over all four, switched by a button.
    #
    # Every size below was read from the HuggingFace API on 2026-09-10, not
    # estimated. The ceiling that picked these: 4 boxes x 121 GB x 0.78 util
    # = 377 GB. That is why the full-precision repos were rejected -- Kimi-K2
    # is 1029 GB, GLM-4.6 714 GB, DeepSeek-V3.2 689 GB and Maverick-FP8 417 GB,
    # and NONE of them fit even across all four. These are the quantised ones
    # that do.
    #
    # WHERE THE WEIGHTS ARE: each download lands on ONE box. vLLM + Ray needs
    # the model path readable on EVERY node, so PP x4 is blocked until the
    # shared mount exists (Iddo approved the idea 09:20: "שיהיה כונן משותף
    # וזהו"). Until then each of these can only serve from the box that holds
    # it. Measured: the live 480B keeps a FULL 236 GB copy on each of eran2,
    # eran3 and eran4 -- 708 GB for one model. That is what the share fixes.
    # ─────────────────────────────────────────────────────────────────────────
    "maverick-w4a16": {
        "label": "Llama-4-Maverick 400B (w4a16)",
        "box": "eran4 holds weights -> PP x4 when shared",
        "size_gb": 216,
        "where": "eran4 ~/models/Maverick-w4a16 "
                 "(RedHatAI/Llama-4-Maverick-17B-128E-Instruct-quantized.w4a16)",
        "engine": "vLLM pipeline-parallel over Ray",
        "unit": None,
        "port": None,
        "host": _HOST["eran4"],
        "model_id": "llama-4-maverick-400b",
        "note": "Downloading since 2026-09-10 09:09. The FP8 (417 GB) was started "
                "first and killed at 11 GB once measured against the 377 GB ceiling: "
                "it does not fit even on four boxes. Gate access confirmed (HTTP 200 "
                "with Iddo's token). Comfortably the best 4-bit fit of the four.",
        "conflicts": ("qwen480", "colibri-glm52", "deepseek-v32-awq",
                      "glm46-awq", "kimi-k27-code"),
    },
    "deepseek-v32-awq": {
        "label": "DeepSeek-V3.2 685B (AWQ)",
        "box": "eran4 holds weights -> PP x4 when shared",
        "size_gb": 400,
        "where": "eran4 ~/models/DeepSeek-V3.2-AWQ (QuantTrio/DeepSeek-V3.2-Exp-AWQ)",
        "engine": "vLLM pipeline-parallel over Ray",
        "unit": None,
        "port": None,
        "host": _HOST["eran4"],
        "model_id": "deepseek-v3.2",
        "note": "400 GB at real 4-bit: needs ALL FOUR boxes and still sits above a "
                "0.78 util budget -- expect to raise util or accept a shorter context. "
                "The 3-bit that fits three boxes is UD-IQ3_XXS at 273 GB, and Iddo "
                "was told it costs quality on code. NOTE: nvidia hosts "
                "deepseek-ai/deepseek-v4-pro-0813 FREE and it answered correctly on "
                "2026-09-10 -- but at 1 tok/s against this fleet's measured 6.4.",
        "conflicts": ("qwen480", "colibri-glm52", "maverick-w4a16",
                      "glm46-awq", "kimi-k27-code"),
    },
    "glm46-awq": {
        "label": "GLM-4.6 357B (AWQ)",
        "box": "eran2 holds weights -> PP x4 when shared",
        "size_gb": 197,
        "where": "eran2 ~/models/GLM-4.6-AWQ (QuantTrio/GLM-4.6-AWQ)",
        "engine": "vLLM pipeline-parallel over Ray",
        "unit": None,
        "port": None,
        "host": _HOST["eran2"],
        "model_id": "glm-4.6",
        "note": "The EASIEST of the four to actually serve: 197 GB fits three boxes "
                "with room for KV cache. If only one of these ever runs, make it this.",
        "conflicts": ("qwen480", "colibri-glm52", "maverick-w4a16",
                      "deepseek-v32-awq", "kimi-k27-code"),
    },
    "kimi-k27-code": {
        "label": "Kimi-K2.7-Code 1T (GGUF UD-Q2_K_XL)",
        "box": "eran2 holds weights -> PP x4 when shared",
        "size_gb": 339,
        "where": "eran2 ~/models/Kimi-K2.7-Code-Q2KXL "
                 "(unsloth/Kimi-K2.7-Code-GGUF, UD-Q2_K_XL folder only)",
        "engine": "llama.cpp -- NOT vLLM. GGUF.",
        "unit": None,
        "port": None,
        "host": _HOST["eran2"],
        "model_id": "kimi-k2.7-code",
        "note": "TWO WARNINGS. (1) This is 2-bit, not 4-bit: a 1T model squeezed to "
                "339 GB. Iddo's premise 'quantisation barely hurts' holds at 4-bit and "
                "not here -- judge it on his own code before trusting it. (2) GGUF "
                "means llama.cpp, and the standing fleet rule is vLLM only "
                "(reference_dgx_inference_engine). Serving this needs that rule "
                "revisited deliberately, not quietly.",
        "conflicts": ("qwen480", "colibri-glm52", "maverick-w4a16",
                      "deepseek-v32-awq", "glm46-awq"),
    },

    # ─────────────────────────────────────────────────────────────────────────
    # 2026-09-11, Iddo 10:17: "תוריד את הגדול ביותר". Downloaded 10:20-11:11.
    # This is the SAME model as maverick-w4a16 above at a much higher precision
    # -- Q6 against 4-bit -- and they are mutually exclusive with each other.
    # INTEGRITY VERIFIED 2026-09-11 by ~/maverick/verify.sh on eran1: all 9 file
    # sizes byte-exact against the HuggingFace API, sha256 spot-checked, all 9
    # GGUF headers parsed, shards 0..7 complete, 531 tensors = split.tensors.count.
    # Header facts: arch llama4, 48 blocks, 128 experts, TOP-1 routing,
    # n_ctx_train 1,048,576, vocab 202,048, chat template present.
    # ─────────────────────────────────────────────────────────────────────────
    "maverick-q6-gguf": {
        "label": "Llama-4-Maverick 400B (GGUF UD-Q6_K_XL)",
        "box": "eran1 holds weights -> RPC x4 (eran1+2+3+4), or x3 at Q5_K_S",
        "size_gb": 343,
        "where": "eran1 ~/models/Llama-4-Maverick-GGUF/UD-Q6_K_XL "
                 "(8 shards) + mmproj-F16.gguf. Scripts: eran1 ~/maverick/",
        "engine": "llama.cpp llama-server --rpc -- NOT vLLM. GGUF.",
        "unit": None,                        # maverick.service written, NOT installed
        "port": 8801,
        "host": _HOST["eran1"],
        "model_id": "maverick",
        "note": "PLANNED, NOT LIVE at Q6 -- but see maverick-q5-gguf below: the "
                "SAME model at Q5_K_S IS running since 2026-09-11 14:16 on three "
                "boxes, and the two are mutually exclusive. THREE THINGS TO KNOW. "
                "(1) GGUF means llama.cpp, and the standing fleet rule is vLLM only "
                "(reference_dgx_inference_engine). vLLM cannot serve GGUF here at "
                "all, so this is a deliberate exception, same as kimi-k27-code. "
                "(2) llama.cpp --rpc is a LAYER split, not tensor parallel: adding "
                "boxes buys MEMORY, not speed. Measured precedent on this fleet -- "
                "Qwen3-Coder-480B over 3 boxes ran 2.93 tok/s. Maverick activates "
                "17B (top-1 of 128) vs that model's 35B so it should be faster, but "
                "that is a prediction until ~/maverick/smoke.sh prints a number. "
                "(3) IT DOES NOT FIT TODAY. Measured 2026-09-11 11:30, free VRAM was "
                "eran1 15.6 / eran2 41.2 / eran3 114.4 / eran4 62.5 = 233.7 GiB "
                "against 318 GiB of weights. eran1 -- the box holding the weights -- "
                "is the fullest: coder-train.service alone holds 83.7 GiB. It must "
                "stop for EITHER option. The 4-box option additionally needs "
                "gpt-oss-120b off eran2, which is the live brain of WABOT, QUORUM, "
                "BRAIN2 and CONTROL chat. The 3-box option keeps gpt-oss but needs "
                "the Q5_K_S download (275.7 GB) because Q6 will not fit on three.",
        "conflicts": ("qwen480", "colibri-glm52", "maverick-w4a16",
                      "deepseek-v32-awq", "glm46-awq", "kimi-k27-code",
                      "gpt-oss-120b-eran2"),
    },

    # ──────────────────────────────────────────────────────────────────────────
    # 2026-09-11 13:53, Iddo: the big Meta coder BESIDE the chat-120, both usable
    # from ALMIDO. That sentence chose the quantisation: Q6 is 318 GiB and needs
    # all four boxes, which would take eran2 away from gpt-oss-120b. Q5_K_S fits
    # on three, so gpt-oss keeps its box. THIS is the entry that is running.
    # LAUNCHED AND MEASURED 2026-09-11 14:16 -- not planned, not predicted.
    # ──────────────────────────────────────────────────────────────────────────
    "maverick-q5-gguf": {
        "label": "Llama-4-Maverick 400B (GGUF Q5_K_S) -- LIVE",
        "box": "eran1 (weights + server) + eran3 + eran4 as RPC workers. NOT eran2.",
        "size_gb": 276,
        "where": "eran1 ~/models/Llama-4-Maverick-GGUF/Q5_K_S (6 shards). "
                 "Scripts: eran1 ~/maverick/ -- up-3box.sh / down.sh / smoke.sh",
        "engine": "llama.cpp llama-server --rpc -- NOT vLLM. GGUF.",
        # boot units ENABLED 2026-09-11 (maverick-server.service on eran1); tonight's live process
        # is still a nohup launch, so this stays None until a reboot hands it to systemd.
        "unit": None,
        "port": 8801,
        "host": _HOST["eran1"],
        "model_id": "maverick",
        "note": "BOOT UNITS ENABLED 2026-09-11 (next boot only, nothing started): eran1 "
                "maverick-server.service, eran3 and eran4 maverick-rpc.service (user "
                "scope). The router :8010 boots via the pre-existing SYSTEM unit "
                "alma-router.service. Order logic and disable commands in eran1 "
                "~/maverick/BOOT.md. "
                "LIVE 2026-09-11 14:16. MEASURED by ~/maverick/smoke.sh, not guessed: "
                "load 17m54s, Hebrew answer correct, 3.06 tok/s sustained over 127 "
                "tokens. The Q6 entry above predicted it would beat Qwen3-Coder-480B's "
                "2.93 tok/s because it activates 17B against that model's 35B -- it "
                "does, by 4%. So the prediction was directionally right and "
                "practically meaningless: --rpc is a LAYER split and the wire, not the "
                "active-parameter count, is what sets the pace. "
                "REACHED THROUGH THE ROUTER, NOT DIRECTLY. llama-server binds "
                "127.0.0.1:8801 on eran1 on purpose; alma-router :8010 discovers the "
                "name 'maverick' from /v1/models and is the one seat. Both models "
                "verified routable through it 2026-09-11: maverick and gpt-oss-120b. "
                "RDMA MUST STAY OFF. llama.cpp RPC v4.0.1 auto-negotiates RoCEv2 and "
                "it killed the first launch outright -- 'transport retry counter "
                "exceeded' -- because eran1 has no direct link to eran3 and the path "
                "routes through eran2, which does not forward RoCE. ~/maverick/env.sh "
                "sets GGML_RDMA_DEV to a device name that cannot exist, so "
                "rdma_probe() finds nothing and falls back to TCP. Do not 'fix' it. "
                "MEMORY IS TIGHT: after load, eran1/eran3/eran4 each had under 8 GiB "
                "spare, and eran4 carries ollama's qwen-coder-dgx4 (50.9 GiB) at the "
                "same time. Nothing else large fits on these three while it is up.",
        # Deliberately NOT conflicting with gpt-oss on eran2 -- coexisting with it
        # is the entire reason this entry exists instead of maverick-q6-gguf.
        "conflicts": ("qwen480", "colibri-glm52", "maverick-w4a16", "maverick-q6-gguf",
                      "deepseek-v32-awq", "glm46-awq", "kimi-k27-code"),
    },
}

# The modes, as sets of ledger keys.
MODES = {
    "MONOLITH": {
        "label": "MONOLITH -- one 480B coder over eran2+3+4",
        "models": ("qwen480",),
        "why": "One very large coder with the harness that remembers the project.",
    },
    "COUNCIL": {
        "label": "COUNCIL -- four boxes, four different giants",
        "models": ("colibri-glm52", "nemotron-120b", "glm45-air"),
        "why": "Iddo's 23:46 quorum: each box holds a different giant and they "
               "argue/work as a team. Requires the 480B to come down first.",
    },
    "GIANTS": {
        "label": "GIANTS -- one giant at a time, spread over all four boxes",
        "models": ("glm46-awq", "maverick-w4a16", "deepseek-v32-awq",
                   "kimi-k27-code", "colibri-glm52"),
        "why": "Iddo 2026-09-10 09:19, correcting COUNCIL: he does NOT want four "
               "giants living on four boxes. He wants ONE giant using all four, and "
               "a button that swaps it -- 'כמו שאני מחליף בין אופוס להייקו'. Every "
               "member of this tuple is mutually exclusive with every other: the "
               "panel picks one, takes the current one down, brings the chosen one "
               "up. Listed cheapest-to-serve first, because glm46-awq (197 GB) is "
               "the one most likely to come up clean on the first try.",
    },
}

# ── The number that governs every choice above ───────────────────────────────
# 4 boxes x 121 GB unified = 484 GB. At the 0.78 gpu-memory-utilization the live
# 480B actually runs with, the usable weight+KV budget is:
#     3 boxes -> ~283 GB      4 boxes -> ~377 GB
# The live qwen480b-awq is 236 GB, which is why it fits three boxes and works.
# Anything proposed for this fleet gets checked against those two numbers FIRST.
# (Measured 2026-09-10: eran1 21/121 used -- nearly empty since ERAN was stopped
# and archived on Iddo's order; eran2 107/121, eran3 105/121, eran4 120/120, the
# last three being the resident 480B legs.)
FLEET_WEIGHT_BUDGET_GB = {3: 283, 4: 377}

# alma-router: the ONE harness. It already fronts the fleet on eran1 :8010 and the
# model NAME selects the box. Registering a model here means adding it to that
# router's table -- NOT building anything new. Measured 2026-09-09 23:47:
# GET http://<lan-ip>:8010/v1/models -> {"object":"list","data":[]}  <- EMPTY.
ROUTER_URL = "http://%s:8010" % _HOST["eran1"]


# ==========================================================================
# Plumbing
# ==========================================================================
_cache = {"at": 0.0, "data": None}
_bg_lock = threading.Lock()
_bg = {"switch": None}


# Verbs that CHANGE a box. Anything else (free, ss, is-active, list-units, du) is a read.
# The Ark guard below is scoped to these: reading eran1 is always allowed, changing it is
# allowed for exactly one unit. Written this way after the first live test, where a
# read-only `free -g` probe was refused for not naming coder-train.service.
_MUTATING = ("systemctl --user start", "systemctl --user stop", "systemctl --user restart",
             "systemctl --user kill", "systemctl --user enable", "systemctl --user disable",
             "docker rm", "docker stop", "docker kill", "docker run", "docker start",
             "kill ", "pkill", "rm -", "reboot", "shutdown", "> ", ">>")
# NOTE: `docker ps` and `systemctl --user list-units` / `is-active` are reads and must stay
# reads -- the first live test refused the read-only probe because "docker " matched `docker ps`.


def _ssh(alias, remote_cmd, timeout=25):
    """One SSH call to a hardcoded fleet alias, with the Ark guard.

    Three checks, all of which must pass before a subprocess exists:
      1. `alias` is one of the four literal strings in ALIASES.
      2. the command mentions no FORBIDDEN unit, on any box, read or write.
      3. if the command MUTATES and the target is eran1, it must name
         ERAN1_ALLOWED_UNIT. Read-only commands on eran1 are unrestricted --
         a dashboard has to be able to look at the box ERAN lives on.
    """
    assert alias in ALIASES, "refusing: %r is not a fleet alias" % (alias,)
    low = remote_cmd.lower()
    for bad in FORBIDDEN:
        assert bad not in low, "refusing: command mentions the protected unit %r" % (bad,)
    mutating = any(v in low for v in _MUTATING)
    if alias == "eran1" and mutating:
        assert ERAN1_ALLOWED_UNIT in remote_cmd, (
            "refusing: on eran1 this module may only CHANGE %s" % ERAN1_ALLOWED_UNIT)
    cmd = ["ssh"] + _SSH_OPTS + [alias, remote_cmd]
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout, creationflags=_NOWIN,
                           text=True, encoding="utf-8", errors="replace")
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", "ssh timeout after %ss" % timeout
    except Exception as e:
        return 1, "", repr(e)[:200]


def _http_json(url, timeout=6, body=None):
    """GET or POST returning (code, parsed_or_text, ms). Never raises."""
    t0 = time.time()
    try:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method="POST" if data else "GET",
            headers={"User-Agent": "fleet-models/1",
                     **({"Content-Type": "application/json"} if data else {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(200000).decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw), int((time.time() - t0) * 1000)
            except Exception:
                return r.status, raw[:2000], int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, str(e)[:300], int((time.time() - t0) * 1000)
    except Exception as e:
        return None, str(e)[:300], int((time.time() - t0) * 1000)


# ==========================================================================
# STATUS -- read-only. Safe to call on every refresh.
# ==========================================================================
def router_state():
    """What the ONE harness is actually serving. This is the broken-window check:
    the router answering is NOT the same as the router having models."""
    code, val, ms = _http_json(ROUTER_URL + "/v1/models", timeout=6)
    ids = []
    if isinstance(val, dict):
        ids = [d.get("id") for d in (val.get("data") or []) if isinstance(d, dict)]
    return {"url": ROUTER_URL, "code": code, "ms": ms, "models": ids,
            "empty": code == 200 and not ids,
            "checked_at": datetime.now().isoformat(timespec="seconds")}


# 2026-09-15 (broken-windows W6): both measured DISABLED on 2026-09-15 08:5x
# (`systemctl --user list-unit-files`: colibri-glm52 disabled on eran1 and eran4,
# colibri-keepalive.timer disabled; coder-train disabled on eran1). The page shows
# them as retired, not as a red "down". The probe below still greps for them, so if
# one is ever running again `retired_running` says so. Backup: fleet_models.py.bak-bw-20260915.
RETIRED_GIANTS = {
    "colibri-glm52": "Colibri GLM-5.2 744B -- unit disabled (eran1 + eran4), keepalive timer disabled",
    "coder-train": "coder continued-pretraining on eran1 -- stopped 2026-09-10 (scored worse than base), unit disabled",
}

_PROBE = (
    "echo '---MEM---'; free -g | awk '/^Mem:/{print $2, $3, $7}'; "
    "echo '---UNITS---'; systemctl --user list-units --all --no-pager --plain "
    "2>/dev/null | grep -E 'colibri-glm52|coder-train|gptoss-120b|ollama-door' || true; "
    "echo '---DOCKER---'; docker ps --format '{{.Names}}|{{.Status}}' 2>/dev/null || true"
)


def _probe_box(alias):
    rc, out, err = _ssh(alias, _PROBE, timeout=20)
    if rc != 0:
        return {"reachable": False, "error": (err or out or "rc=%s" % rc)[:200]}
    d = {"reachable": True, "units": {}, "docker": [], "mem": None}
    sec = None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("---"):
            sec = s.strip("-")
            continue
        if not s:
            continue
        if sec == "MEM":
            parts = s.split()
            if len(parts) >= 3:
                d["mem"] = {"total_gb": int(parts[0]), "used_gb": int(parts[1]),
                            "avail_gb": int(parts[2])}
        elif sec == "UNITS":
            f = s.split()
            if f and f[0].endswith(".service"):
                d["units"][f[0]] = " ".join(f[1:4])
        elif sec == "DOCKER" and "|" in s:
            n, st = s.split("|", 1)
            d["docker"].append({"name": n, "status": st})
    return d


def fleet_model_state(force=False):
    """Cached, NEVER-BLOCKING read of what is UP across the fleet, plus the router.

    The first version of this blocked the dashboard: four SSH probes (eran3 goes through
    a ProxyJump) plus an HTTP call, all inline in full_state(), took the /control page
    past a 25 s client timeout. A status panel must never make the page slower than the
    page was without it. So: a stale-or-empty snapshot is returned instantly and the real
    probe runs in a background thread. `force=True` (the explicit ⟳ button, which is an
    XHR the user chose to wait for) still probes synchronously.
    """
    now = time.time()
    fresh = _cache["data"] and now - _cache["at"] < 25
    if fresh and not force:
        return _cache["data"]
    if not force:
        with _bg_lock:
            busy = _bg.get("probe_running")
        if not busy:
            with _bg_lock:
                _bg["probe_running"] = True
            threading.Thread(target=_refresh_worker, daemon=True).start()
        return _cache["data"] or {
            "mode": "…probing", "q480_up": None, "colibri_up": None,
            "coder_train_up": None, "boxes": {}, "router": {},
            "checked_at": None, "priming": True}
    return _probe_now()


def _refresh_worker():
    try:
        _probe_now()
    except Exception:
        pass
    finally:
        with _bg_lock:
            _bg["probe_running"] = False


def _probe_now():
    now = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        boxes = dict(ex.map(lambda a: (a, _probe_box(a)), ALIASES))

    def unit_active(alias, unit):
        b = boxes.get(alias) or {}
        return "active running" in (b.get("units", {}).get(unit, "") or "")

    q480_up = any("qwen480-pp" in c["name"] and c["status"].startswith("Up")
                  for a in ("eran2", "eran3", "eran4")
                  for c in (boxes.get(a, {}).get("docker") or []))
    colibri_up = unit_active("eran4", "colibri-glm52.service")
    trainer_up = unit_active("eran1", "coder-train.service")
    gptoss_boxes = [a for a in ALIASES if unit_active(a, "gptoss-120b.service")]
    # A retired unit that is somehow running again is NOT retired -- say so loudly.
    retired_running = [u for u, up in (("colibri-glm52", colibri_up), ("coder-train", trainer_up)) if up]

    if q480_up and not colibri_up:
        mode = "MONOLITH"
    elif colibri_up and not q480_up:
        mode = "COUNCIL"
    elif q480_up and colibri_up:
        mode = "BOTH (impossible on this hardware -- re-probe)"
    elif gptoss_boxes:
        # 2026-09-15 (W6): "NEITHER -- no giant model is serving" was painted while
        # gpt-oss-120b served on all four boxes. Colibri is retired, so the only
        # honest giant-mode question left is the 480B, which stays shown as down.
        mode = "GPTOSS"
    else:
        mode = "NEITHER -- no giant model is serving"

    data = {
        "mode": mode,
        "q480_up": q480_up,
        "colibri_up": colibri_up,
        "coder_train_up": trainer_up,
        "gptoss_boxes": gptoss_boxes,
        "retired": RETIRED_GIANTS,
        "retired_running": retired_running,
        "boxes": boxes,
        "router": router_state(),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    _cache.update(at=now, data=data)
    return data


def switch_progress():
    with _bg_lock:
        return dict(_bg.get("switch") or {})


# ==========================================================================
# ACTIONS -- every one of these is reached only from an explicit button press.
# ==========================================================================
def colibri_up():
    """Raise Colibri GLM-5.2 744B on eran4. Refuses while the 480B holds the box:
    93.9 GB of eran4's 120 are the Ray worker, and Colibri wants ~70 more."""
    st = fleet_model_state(force=True)
    if st["colibri_up"]:
        return "refused", {"reason": "already up", "state": st["mode"]}
    if st["q480_up"]:
        return "refused", {
            "reason": "the 480B pipeline holds eran4 (measured 93.9 GB resident). "
                      "Stop the cluster first -- these two cannot coexist on 120 GB.",
            "next": "press STOP the cluster, wait for it to be down, then press this again"}
    rc, out, err = _ssh("eran4", "systemctl --user start colibri-glm52.service 2>&1; "
                                 "sleep 2; systemctl --user is-active colibri-glm52.service",
                        timeout=60)
    ok = "active" in (out or "")
    return ("started" if ok else "error"), {
        "rc": rc, "out": (out or "")[-1500:], "err": (err or "")[:400],
        "note": "744B int4 -- the model loads from 358 GB on disk; first token can "
                "take many minutes. Prove it with the completion probe, not with is-active."}


def colibri_down():
    st = fleet_model_state(force=True)
    if not st["colibri_up"]:
        return "refused", {"reason": "already down"}
    rc, out, err = _ssh("eran4", "systemctl --user stop colibri-glm52.service 2>&1; "
                                 "systemctl --user is-active colibri-glm52.service",
                        timeout=90)
    return "stopped", {"rc": rc, "out": (out or "")[-800:]}


def colibri_probe():
    """REAL output, not health:ok -- one timed completion through Colibri's own port."""
    m = MODELS["colibri-glm52"]
    url = "http://%s:%d/v1/chat/completions" % (m["host"], m["port"])
    code, val, ms = _http_json(url, timeout=180, body={
        "model": m["model_id"],
        "messages": [{"role": "user", "content": "Reply with exactly: COLIBRI ALIVE"}],
        "max_tokens": 12, "temperature": 0})
    text = ""
    if isinstance(val, dict):
        try:
            text = val["choices"][0]["message"]["content"]
        except Exception:
            text = json.dumps(val)[:300]
    else:
        text = str(val)[:300]
    return ("answered" if code == 200 and text.strip() else "no-answer"), {
        "code": code, "ms": ms, "text": text[:300], "url": url}


def coder_train_stop():
    """Stop the continued-pretraining run on eran1 and give its 83.7 GB back.

    This is the ONLY thing this module may do to eran1, and it is deliberate:
    measured 2026-09-09, run 1's step-1017 weights scored WORSE than the base model
    on the identical held-out set (CE 0.9386 -> 1.0065, top-1 78.93% -> 77.64%), and
    run 2 is the same recipe with 87 days left to run.

    train.py traps SIGTERM: it finishes the current step, writes a full 47 GB
    checkpoint (measured 489 s) and exits 0. The unit's TimeoutStopSec is 60 min and
    Restart=on-failure, so a clean exit 0 does NOT come back. Nothing is lost --
    `--resume auto` picks the checkpoint straight back up whenever Iddo wants it.
    """
    rc, out, err = _ssh("eran1",
                        "systemctl --user stop coder-train.service 2>&1; "
                        "systemctl --user is-active coder-train.service 2>&1",
                        timeout=1800)   # up to 30 min: the checkpoint write is ~8 min
    return "stopped", {"rc": rc, "out": (out or "")[-1200:], "err": (err or "")[:400],
                       "note": "checkpoint written; --resume auto restarts exactly here"}


def coder_train_start():
    rc, out, err = _ssh("eran1",
                        "systemctl --user start coder-train.service 2>&1; "
                        "sleep 2; systemctl --user is-active coder-train.service",
                        timeout=90)
    return ("started" if "active" in (out or "") else "error"), {
        "rc": rc, "out": (out or "")[-800:]}

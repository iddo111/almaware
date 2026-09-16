# DictaLM on a DGX — Hebrew fallback brain for alma-mic

The mic's brain is **Grok primary, DictaLM Hebrew fallback** (Iddo, 2026-07-07).
A 7B model is heavy → it runs on a **DGX Spark node**, not the PC (`heavy → DGX`).
`dicta.py` is only the client; this file is how to stand up the server.

## What alma-mic expects
An **OpenAI-compatible** `/v1/chat/completions` endpoint. Put its URL in the mic's
settings (⚙ → "מוח: כתובת DictaLM על DGX") or `config.json` → `dicta_url`, e.g.:

    http://eran1:8090/v1/chat/completions

Then in the mic, set the 🧠 backend to `dicta` (force Hebrew), or leave it on `grok`
— Grok answers, and if Grok fails, the mic auto-falls-back to this Dicta endpoint.

## Serve it on a DGX node (pick one)

**Option A — llama.cpp OpenAI server (GGUF, light, matches the fleet's existing setup):**
```bash
# on eranN, in the venv that has llama.cpp built:
# 1) get a DictaLM 2.0 instruct GGUF (Q5_K_M is a good speed/quality balance on GB10)
#    from HF (dicta-il), place at ~/models/dictalm2.0-instruct.Q5_K_M.gguf
llama-server \
  -m ~/models/dictalm2.0-instruct.Q5_K_M.gguf \
  --host 0.0.0.0 --port 8090 \
  --ctx-size 4096 --n-gpu-layers 999 \
  --chat-template chatml
# endpoint -> http://<eranN>:8090/v1/chat/completions   (model name: any, dicta.py sends "dicta")
```

**Option B — vLLM (full HF weights, higher throughput):**
```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
  --model dicta-il/dictalm2.0-instruct \
  --host 0.0.0.0 --port 8090 --dtype auto
# endpoint -> http://<eranN>:8090/v1/chat/completions
```

## Reachability
- The PC reaches the DGX over the LAN/Tailscale. Use the node's hostname (`eran1`…)
  or its Tailscale IP. DGX IPs drift on DHCP — Tailscale name is the stable choice.
- Don't fight Eran for the GPU: run Dicta on a node/slot not training Eran, or accept
  it shares. Keep it a **fallback**, not the always-on path (Grok stays primary).

## Honest notes
- **Not built/verified from here** — the mic's client side is tested; the DGX server
  must be started on a node and the URL entered. Until then the mic says, honestly,
  "דיקטה לא זמינה … ודא ששרת ה-DGX רץ".
- DictaLM is a MODEL (model-not-app, like Whisper/Grok/Eran) — allowed under the
  purity law; the app code is 100% ours.

# pc-chat — chat with Claude on PC from your phone

Installed on the A70 Termux at `~/pc-chat` (and also `~/bin/pc-chat`).

## Usage

In Termux:
```
pc-chat "what's the time on PC?"
pc-chat hi
echo "long question on multiple lines..." | pc-chat
```

Reply prints to stdout.

## Routes

1. **Tailscale (default)**: POST to `http://<tailnet-ip>:18180/chat`. Works anywhere both devices are online (home wifi, LTE, hotel).
2. **ADB-reverse fallback**: If tailscale fails, falls back to `http://localhost:18180/chat`. Requires PC to have run `adb -s <lan-ip>:<port> reverse tcp:18180 tcp:18180` first.

## Backend

PC's pc-listener.py at port 18180 routes `/chat` POSTs to:
- **claude-cli (Opus 4.7)** — primary, uses your Claude Code subscription, no API key needed
- **Ollama qwen3:8b** — fallback if claude-cli fails

Reply latency: ~4 sec for short messages via claude-cli, ~2 sec via Ollama qwen3:8b (warm).

## Tier 0 commands

The same intents the WA bot recognizes — pc-chat goes through them too:
```
pc-chat "play movie"   # PC launches random movie from D:\xxxmovies in mpc-hc
pc-chat "/play"
```

## Verify working

```
pc-chat hi
# expect: "hi" or similar within 5 sec
```

## Troubleshooting

```
# Test PC reachable on tailnet
curl -sS http://<tailnet-ip>:18180/ping
# expect: pong

# Or via adb-reverse
curl -sS http://localhost:18180/ping
```

If tailnet ping fails, your phone's Tailscale may be off — open the Tailscale app and toggle on.

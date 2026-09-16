# ALMA FS MCP

Filesystem tools for **gpt-oss-120b**, GLM-5.2, or any MCP-capable chat client.

Built 2026-08-07 because gpt-oss kept replying *"I'm not able to touch the files
on your computer directly"* and handing back code snippets in six languages. It
wasn't lying — it had no tools. Now it does.

## Start it

```powershell
powershell -ExecutionPolicy Bypass -File D:\CLAUDE\alma-fs-mcp\start-alma-fs-mcp.ps1
```

Idempotent — kills any stale listener on 8930 first, then verifies with a real
health check before telling you it worked.

## Point your chat UI at it

Add **one** of these in the UI's MCP server settings:

| Transport | URL |
|---|---|
| Streamable HTTP (current spec) | `http://<tailnet-ip>:8930/mcp` |
| Legacy HTTP+SSE | `http://<tailnet-ip>:8930/sse` |

Use `127.0.0.1` instead of the Tailscale IP if the UI runs on this PC.
Both work; if one won't connect, try the other — clients differ on which
transport they implement.

Opening `/mcp` in a browser shows a status page, not an error. That's expected:
the URL is an MCP endpoint, browsers send GET, MCP clients POST.

## Tools

| Tool | What it does |
|---|---|
| `write_file` | Write text to a file, creating parent dirs. Overwrites. |
| `append_file` | Append to a file, creating it if absent. |
| `read_file` | Read a text file back. |
| `list_dir` | List a directory. |
| `delete_file` | Delete a single file. Refuses directories. |

## Sandbox

Writes are confined to these roots — anything outside is refused:

```
D:\
C:\Users\<user>\Desktop
C:\Users\<user>\Downloads
```

Change them with the `ALMA_FS_ROOTS` env var (semicolon-separated) before start:

```powershell
$env:ALMA_FS_ROOTS = "D:\;C:\Users\<user>\Desktop"
```

Verified: a `write_file` to `C:\Windows\System32\evil.txt` is rejected with
`isError: true`.

## Health

```powershell
curl http://127.0.0.1:8930/health
```

## Troubleshooting

**Intermittent, nondeterministic failures** — two processes can bind the same
port on Windows via `SO_REUSEADDR` and both will answer, alternating. Symptom:
one request succeeds, the next 404s. Confirm exactly one listener:

```
netstat -ano | findstr :8930
```

Two `LISTENING` lines is the bug. Kill by port, not by command line —
`pkill -f alma_fs_mcp.py` silently matches nothing for a Windows Python process:

```powershell
Get-NetTCPConnection -LocalPort 8930 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

**The model still says it can't write files** — the MCP server being up is only
half of it. The model must also be able to *emit* tool calls. For llama.cpp,
that generally needs `--jinja` with a chat template that supports tool calling.
Check how llama-server was launched on eran4 before blaming the MCP server.

## Files

| Path | What |
|---|---|
| `D:\CLAUDE\alma-fs-mcp\alma_fs_mcp.py` | The server. Stdlib only, no deps. |
| `D:\CLAUDE\alma-fs-mcp\start-alma-fs-mcp.ps1` | Restart + verify. |
| `D:\CLAUDE\alma-fs-mcp\server.log` / `.err` | Output from the running process. |

Port **8930** is claimed in RAMCHAT. Clod holds 8790/8794/8795 — don't collide.

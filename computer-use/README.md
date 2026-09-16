# computer-use — the PC's hands, gated

MCP stdio server. Stdlib only, no pip install, no venv.

## Tools

Free: `screenshot`, `cursor_pos`, `list_windows`, `audit_tail`.
Gated: `request_action` → `confirm_action` / `deny_action`
for `click`, `move`, `type`, `key`, `scroll`.
Confirm ids are single-use and expire after 120 s.
Everything lands in `audit.jsonl`.

## Run

From this directory, fresh shell:

```
python server.py
```

## Prove

```
python probe.py
```

## Wire into Muse / agents

`.mcp.json` entry (already added on the PC):

```json
"computer-use": {
  "command": "C:/Program Files/Python312/python.exe",
  "args": ["D:/CLAUDE/computer-use/server.py"],
  "cwd": "D:/CLAUDE/computer-use"
}
```

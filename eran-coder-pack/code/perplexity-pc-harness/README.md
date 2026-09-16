# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: verify real output; a health check alone is not acceptance.

# Perplexity PC Harness

הפרויקט הקיים מספק bridge מקומי מוגבל ל-Perplexity Agent API ושכבת Computer Use בטוחה עבור Windows. פעולות UI אמיתיות פועלות רק מתוך ה-runtime המהימן של Codex דרך `sky_driver.mjs`; הרצת Python עצמאית נכשלת באופן סגור ואינה עוקפת את שכבת האישורים.

This existing project provides a bounded local bridge for the Perplexity Agent API plus a safe Windows Computer Use policy layer. Real UI input is available only inside the trusted Codex Computer Use runtime through `sky_driver.mjs`; standalone Python fails closed rather than bypassing trusted approvals and interruption handling.

## Current status / מצב נוכחי

- `VERIFIED`: read-only tools, policy validation, screenshot/image flow, fake Agent API end-to-end loop, redacted audit records, and STOP behavior pass offline tests.
- `VERIFIED`: the trusted Sky adapter uses only returned `Window` objects, one-time grants, one action per fresh observation, and immediate post-action refresh.
- `VERIFIED`: at `2026-07-24T20:43+03:00`, the trusted adapter selected the unique native test window, focused its edit control, typed `PPLX_REAL_UI_MARKER_20260724`, clicked Commit, and returned a fresh screenshot whose title and visible result contained the exact marker. The post-commit screenshot SHA-256 was `e7afdc33cdfb02b1beb5bb57cf5b08207c42e57bd2f9b8dd0e1df0f7cea92251`.
- `BLOCKED`: `start.ps1` cannot perform real UI input by itself because the official Computer Use wrapper intentionally works only in trusted `node_repl`.
- `BLOCKED`: live Perplexity-to-PC acceptance needs a user-supplied API key and a model proven to support both vision and custom tools.

Do not describe the two blocked gates as completed.

## Architecture / ארכיטקטורה

- `harness.py`: Perplexity Agent API protocol, local approval, auditing, bounded requests/responses, and custom-tool orchestration.
- `computer_use.py`: backend-independent policy engine, window identity checks, screenshot hashing, action limits, redaction, fake backend, and fail-closed standalone backend.
- `sky_driver.mjs`: real Windows adapter for the official trusted `sky` runtime. It never reconstructs or guesses a window handle.
- `test_window.py`: deterministic, harmless local acceptance target.
- `allowlist.json`: strict schemas. There is no arbitrary shell, executable path, Registry, service, or policy tool.

The Agent API loop sends `function_call_output` items and injects fresh PNG observations as `input_image` data URIs. Every mutating action invalidates the previous observation; another action requires the newly returned observation ID.

## Install / התקנה

Requirements:

- Windows 11.
- Python 3.12 or compatible Python 3 on Windows; the deterministic target uses only `ctypes` and native Win32 controls.
- Node.js only for syntax-checking or loading `sky_driver.mjs` inside trusted `node_repl`.
- A Perplexity API key only for the final live cloud gate.
- The Codex Computer Use plugin/runtime for real Windows input.

No third-party Python package is required for offline tests. Do not put an API key in a file, command line, RAMCHAT, screenshot, or test fixture.

## Run / הפעלה

Non-secret verification:

```powershell
py -3 .\harness.py --self-test
py -3 -m unittest discover -s .\tests -v
node --check .\sky_driver.mjs
```

Agent API session:

```powershell
.\start.ps1
.\start.ps1 -DryRun -Prompt "Inspect the requested target and describe the planned action."
.\start.ps1 -ObserveOnly -Prompt "List targetable windows and observe only the selected safe window."
```

`start.ps1` prompts for the key as a `SecureString` when it is absent, passes it only in child-process memory, restores or removes the environment value in `finally`, and zeroes the temporary BSTR. Diagnostic subprocesses receive a sanitized environment with `PERPLEXITY_API_KEY` removed.

`--dry-run` validates and displays a requested action but performs no input. `--observe-only` removes the action tool from the Agent API tool list. A bounded session summary is printed after a successful run.

## Trusted Windows Computer Use / שימוש מהימן ב-Windows

Before real UI automation, load the installed `computer-use` skill and read `guidance`, `api`, and `confirmations`. Initialize its official wrapper in `node_repl`, then import this project module:

```javascript
var driverModule = await import("file:///D:/CLAUDE/perplexity-pc-harness/sky_driver.mjs");
var safeSession = new driverModule.SafeSkySession(sky, {
  stopPath: "D:\\CLAUDE\\perplexity-pc-harness\\STOP",
});
var safeWindows = await safeSession.listWindows();
```

Selection must yield exactly one returned window. Observe it, inspect the result, grant exactly one matching action locally, perform exactly one action, and use the automatically refreshed observation:

```javascript
var observed = await safeSession.observe("<returned stable id>");
safeSession.grantOnce({
  windowId: observed.window.id,
  observationId: observed.observation_id,
  action: "click",
  x: 100,
  y: 100,
});
var refreshed = await safeSession.act({
  windowId: observed.window.id,
  observationId: observed.observation_id,
  action: "click",
  x: 100,
  y: 100,
});
```

Coordinates and screenshot IDs expire after every action. Typing re-observes focus immediately before `type_text`. If input or refresh fails, the outcome is unknown: re-list and re-observe before any retry.

## Security boundary and threat model / גבול אבטחה ומודל איומים

Assume model output, webpage text, documents, filenames, window titles, and third-party content can be malicious.

The harness:

- requires local `ALLOW ONCE` for Python tools and a consumed one-time grant in the trusted Sky adapter;
- shows target, action, risk class, and a redacted text preview;
- blocks credential/password managers, UAC, Windows Security/Defender, terminals, shells, Registry Editor, Codex, and ChatGPT windows;
- refuses stale observations, changed app identity, materially moved/resized windows in the policy engine, out-of-bounds coordinates, unknown fields/actions, unapproved keys, secret-looking text, oversize screenshots, and repeated no-progress actions;
- caps actions, turns, elapsed time, wait/scroll values, screenshot bytes, request bytes, response bytes, and Agent turns;
- hashes screenshots in audit records without saving screenshot bytes by default;
- records no raw tool arguments, results, typed content, or API keys;
- exposes no inbound network listener and no arbitrary shell.

Never use the harness to bypass secure desktop, UAC, browser warnings, permissions, password fields, payment confirmation, deletion, irreversible actions, CAPTCHA policy, or security software. Clipboard reading is not implemented. File upload/download, drag, set-value, and move-only pointer actions are intentionally not exposed.

## Limitations / מגבלות

- The official Windows Computer Use wrapper rejects untrusted standalone processes. Therefore Python `computer_action` returns a clear capability error until a trusted adapter is connected; the project does not emulate the privileged pipe.
- The Sky API returns app ID, window ID, title, screenshot origin/dimensions, and accessibility state. It does not expose every requested Win32 property directly; `foreground` remains unknown and `dpi_scale` is reported as logical scale `1` in the trusted adapter.
- `perplexity/sonar` is configurable but is not assumed to support the required vision-plus-custom-tool combination. Use a model verified live for both capabilities.
- The live cloud gate is intentionally not simulated by the fake transport.
- Audit JSONL is local evidence, not a tamper-proof remote ledger.

## Recovery and STOP / התאוששות ועצירה

Create `STOP` in this directory or press Ctrl+C. STOP is checked before the next tool/action and again before the post-action observation. Remove only the exact `STOP` file when you intentionally want a new session:

```powershell
Remove-Item -LiteralPath .\STOP
```

If a target disappears, changes identity, moves materially, loses focus, or an action outcome is unknown, do not retry from cached coordinates. List windows again, select exactly one safe returned window, and capture a fresh observation.

If the API returns an error, incomplete shape, invalid JSON, oversize body, unsupported model capability, or no visible final text, the session stops as `BLOCKED`.

## Tests and acceptance / בדיקות וקבלה

Offline tests cover:

- strict schemas and unknown-tool rejection;
- coordinate, key, text, target identity, and approval policy;
- kill switch, turn/action/screenshot limits, and no-progress detection;
- dry-run and observe-only behavior;
- screenshot hashes and audit redaction;
- fake Agent API flow: observe screenshot → approved safe action → fresh screenshot → nonempty final text.

The deterministic real-UI acceptance target is:

```powershell
py -3 .\test_window.py --expected-marker PPLX_REAL_UI_MARKER_20260724
```

Drive only this exact returned window through trusted `sky_driver.mjs`. The acceptance gate requires a real click/type/commit sequence, a changed screenshot hash, and a fresh screenshot visibly showing the marker. Tests must never type into an unrelated window.

Fresh trusted-runtime acceptance passed on 2026-07-24: each action consumed an exact one-time grant, the edit control was re-observed as focused before typing, screenshot hashes changed after the click/type/commit sequence, and the final title/result displayed `PPLX_REAL_UI_MARKER_20260724`.

## RAMCHAT coordination / תיאום RAMCHAT

Use mapping names, not invented numeric addresses:

- `RAMCHAT_COUNCIL_V1`: 16 MiB, magic `RAMCHAT1`, little-endian payload length, schema-1 JSON.
- `RAMCHAT_QUEUE_V1`: 8 MiB, magic `RAMQUEU1`, little-endian payload length, schema-1 JSON.

Read mappings using the documented bounded contract. Never write secrets to RAMCHAT and never treat a process or snapshot file as proof of live IPC.

## Uninstall and cleanup / הסרה וניקוי

Stop active sessions and close the deterministic test window. This project installs no service, driver, scheduled task, Registry value, listener, or global package. To remove local generated evidence, delete only:

```powershell
Remove-Item -LiteralPath .\STOP -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\logs -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\__pycache__ -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\tests\__pycache__ -Recurse -Force -ErrorAction SilentlyContinue
```

Do not remove the project directory unless the user explicitly requests deletion.

Official protocol references:

- [Agent API quickstart](https://docs.perplexity.ai/docs/agent-api/quickstart)
- [Agent API tools and function calling](https://docs.perplexity.ai/docs/agent-api/tools/web-search)
- [Agent API image attachments](https://docs.perplexity.ai/docs/agent-api/image-attachments)

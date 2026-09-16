# Handout — finish the existing Perplexity full-computer-use harness

Date: 2026-07-24 (Asia/Jerusalem)  
Coordinator: Codex  
Orchestrator: Perplexity Agent API  
Existing project: `D:\CLAUDE\perplexity-pc-harness`

## הוראה מרכזית / Primary instruction

המשך את הפרויקט הקיים. אל תיצור harness חלופי ואל תעתיק אותו לפרויקט חדש.

Continue the existing project in place. Do not create a replacement harness or a parallel product directory.

The user authorizes finishing a full Windows computer-use harness for Perplexity. This does **not** authorize disabling Windows security, bypassing UAC or secure-desktop boundaries, suppressing confirmation prompts, scraping saved credentials, or exposing API keys.

## VERIFIED baseline

Fresh local evidence at `2026-07-24T20:19:15+03:00`:

- `py -3 .\harness.py --self-test` exited `0` and printed `PPLX_LOCAL_POLICY_SELFTEST_OK`.
- `py -3 -m unittest discover -s .\tests -v` passed `10/10`.
- The API key is accepted from process memory and is not intentionally written to disk.
- Every current tool call requires `ALLOW ONCE`.
- Current local functions are only `pc_status`, `list_workspace`, `read_workspace_text`, and `run_diagnostic`.
- There is no arbitrary shell and no inbound network listener.
- Therefore the existing implementation is a tested, least-privilege, read-only bridge. It is **not yet full computer use**.
- Live cloud-to-PC acceptance is still **BLOCKED** until a user-supplied Perplexity API key produces a real tool call and a nonempty unique-marker result.

## Official API contract

Use the Perplexity Agent API at `POST https://api.perplexity.ai/v1/agent`.

- Custom tools are declared as functions with strict JSON Schema.
- `function_call.arguments` is a JSON string and must be parsed.
- Local results return as `function_call_output`.
- Screenshots can be returned to a vision-capable Agent API model as `input_image` with a base64 PNG/JPEG data URI.
- Do not assume every model supports both vision and custom tools; make the model configurable and fail with a clear capability error.

Primary documentation:

- https://docs.perplexity.ai/docs/agent-api/quickstart
- https://docs.perplexity.ai/docs/agent-api/tools/web-search
- https://docs.perplexity.ai/docs/agent-api/image-attachments

## Required implementation

Build a bounded observe-decide-act loop for Windows:

1. Observe
   - Enumerate visible top-level windows with stable IDs, title, process name, bounds, and foreground state.
   - Capture either a selected window or the desktop as a bounded, compressed screenshot.
   - Include DPI scale and image dimensions so coordinates are deterministic.
   - Hash screenshots in the audit log; do not store screenshots by default.

2. Act
   - Focus a selected window.
   - Move/click/double-click/right-click at validated coordinates.
   - Type text.
   - Press an allowlisted key or key chord.
   - Scroll vertically or horizontally.
   - Wait for a bounded duration and then re-observe.
   - Every action is scoped to the selected window/session and requires explicit local `ALLOW ONCE`.

3. Loop
   - After every mutating action, capture a fresh observation before another action.
   - Bound total turns, total actions, screenshot bytes, request bytes, elapsed time, retries, and repeated identical actions.
   - Detect no-progress loops using screenshot hashes and action history.
   - `STOP` and Ctrl+C must prevent the next action immediately.

4. Safety
   - No general shell, PowerShell, `cmd`, arbitrary executable, Registry editor, service control, policy change, credential-store access, or security-tool suppression.
   - Do not interact with UAC/secure desktop, password fields, credential dialogs, payment/financial confirmation, account deletion, or irreversible/destructive actions.
   - Clipboard reads are denied by default. Typing user-provided text is allowed only after the approval dialog displays a redacted preview and destination window.
   - Refuse actions when the target window changed, disappeared, moved materially, or no longer matches the approved target.
   - Fail closed on unknown tools, fields, enum values, coordinates, windows, response shapes, and API errors.

5. UX
   - Keep `start.ps1`.
   - Add `--dry-run`, `--observe-only`, and a bounded session summary.
   - Show the target window, requested action, risk class, and redacted arguments before approval.
   - Never print or log the Perplexity API key.

6. Tests
   - Unit-test schema validation, coordinate bounds, window identity, approval, redaction, kill switch, no-progress detection, action/turn limits, screenshot size limits, and absence of arbitrary shell.
   - Add a fake Agent API transport test covering: screenshot observation -> function call -> approved safe action -> fresh screenshot -> nonempty final response.
   - Add a deterministic local test window for acceptance. It must display a unique marker after a real click/type sequence.
   - Tests must not move the real mouse or type into an unrelated window.

## Definition of Done

Do not report “full computer use complete” until all gates pass:

- `VERIFIED`: all offline tests pass with exact counts and exit codes.
- `VERIFIED`: a safe local test window receives a real approved click/type sequence and shows a unique marker.
- `VERIFIED`: fresh post-action screenshot proves the marker is visible.
- `VERIFIED`: audit log proves approvals, target window IDs, screenshot hashes, timings, and outcomes without raw secrets or typed secret content.
- `VERIFIED`: `STOP` prevents the next action.
- `VERIFIED`: no arbitrary shell/tool path exists in function definitions or handlers.
- `VERIFIED` or `BLOCKED`: with a user-provided API key, the live Agent API invokes the local tool loop and returns a nonempty unique marker. If the key/model/capability is unavailable, report this gate as `BLOCKED`; do not simulate it.
- README contains install, run, security boundary, threat model, limitations, recovery, test, and uninstall/cleanup instructions.
- Final handoff reports `VERIFIED / ACTIVE / BLOCKED / NEXT`, changed files, test output, and whether anything was committed or pushed.

## RAMCHAT address — כתובת RAM לתקשורת

The stable Windows shared-memory identifiers are mapping names, not numeric virtual addresses. Numeric `0x...` addresses differ per process because of virtual memory and ASLR.

Council conversation and shared state:

```text
RAMCHAT_COUNCIL_V1
```

- Capacity: `16 MiB`
- Bytes `0..7`: ASCII magic `RAMCHAT1`
- Bytes `8..15`: unsigned little-endian 64-bit payload length
- Bytes `16..`: UTF-8 JSON with `schema: 1`, `transcript`, and `shared_memory`

Shared work queue:

```text
RAMCHAT_QUEUE_V1
```

- Capacity: `8 MiB`
- Bytes `0..7`: ASCII magic `RAMQUEU1`
- Bytes `8..15`: unsigned little-endian 64-bit payload length
- Bytes `16..`: UTF-8 JSON with `schema: 1` and `items`

Fresh direct validation at `2026-07-24T20:18:42+03:00`, after one bounded launcher recovery:

- `RAMCHAT_COUNCIL_V1`: magic `RAMCHAT1`, payload `3757` bytes, schema `1`, required keys present.
- `RAMCHAT_QUEUE_V1`: magic `RAMQUEU1`, payload `29448` bytes, schema `1`, required keys present.
- Status: `ACTIVE / VERIFIED` for that timestamp only.

Canonical local documentation:

- `D:\CLAUDE\RAMCHAT\RAM_SHARED_MEMORY.md`
- `D:\CLAUDE\RAMCHAT\RAM_ADDRESS_REGISTRY.json`
- Read-only validator: `D:\CLAUDE\RAMCHAT\reports\_audit_mapping_validator.py`

Communication rule:

- Read the mappings using the documented header and bounded payload contract.
- Never place API keys, passwords, tokens, or credential material in RAMCHAT.
- Use `RAMCHAT_COUNCIL_V1` for conversation/status and `RAMCHAT_QUEUE_V1` for task handoffs.
- Do not invent a numeric address and do not write directly into producer-owned mappings unless an explicitly approved connector is implemented.
- If a mapping fails validation, report `BLOCKED`; do not treat a process, window, or snapshot file as proof of live IPC.

## Immediate NEXT

1. Preserve the passing read-only behavior.
2. Implement the safe Windows observation/action layer and fake-transport loop.
3. Run the full offline test suite.
4. Run the local deterministic UI acceptance.
5. Request the user-provided Perplexity API key only for the final live gate.
6. Post progress and handoff status through the RAMCHAT mapping names above without secrets.


# Alma Free Cloud Armada

This is a local operator/controller for the already deployed Alma GPT-OSS 120B Cloud Worker. It begins with four **logical roles**—engineering, QA, research, and operations—and can enlist bounded specialist child workers. All workers deliberately share the same free Groq-backed `openai/gpt-oss-120b` gateway. It does not claim separate deployments, separate models, or a production SLA.

## Safety and cost boundary

- No cloud resources are created by this controller.
- No paid fallback, local model, or DGX fallback exists.
- `ALMA_CHAT_ACCESS_TOKEN` is read only from the process environment. It is never written to state or logs.
- Persisted prompts and outputs are scrubbed for common API-key/token patterns.
- One atomic controller lock prevents two schedulers from draining the same queue.
- The armada is capped at 2 concurrent tasks, 5 requests/minute, 4,000 estimated tokens/minute, and 200 requests/day—well below the gateway's separate global guard.
- Quota consumption is conservative: a failed provider call still consumes the local estimate.
- A `429`, identity mismatch, empty stream, or missing token fails closed. There is no silent alternate route.
- Enlistment creates logical worker records only. It cannot create accounts, API keys, cloud deployments, VMs, or extra provider quota.
- At most 8 enlisted workers exist, lineage depth is 2, each parent gets 2 children, and one run may enlist at most 2 children.
- Children default to a 24-hour lifetime and 3-task budget. Hard code-level ceilings reject unsafe configuration expansion.

These settings are operator policy, not a promise that the external free tier will remain available. The provider can still throttle earlier.

## Operator commands

From `D:\CLAUDE\alma-gptoss120b-cloud-worker-20260721`:

```powershell
npm run armada -- init
npm run armada -- add --role engineering --priority 80 --prompt "Design the smallest patch for issue X."
npm run armada -- add --role qa --prompt "Create deterministic acceptance tests for issue X."
npm run armada -- status
npm run armada -- workers
```

## Bounded self-enlistment

An operator may explicitly enlist a specialist:

```powershell
npm run armada -- enlist --parent engineering --name release-auditor --base-role qa --purpose "Audit release evidence and deterministic acceptance gates."
npm run armada -- add --role release-auditor --prompt "Review the current release evidence."
```

Or permit workers to request a child during one bounded queue run:

```powershell
npm run armada -- run --max-tasks 4 --allow-enlistment
```

A worker request is untrusted model output. The controller accepts only one exact `ENLIST_WORKER_JSON` object, validates its slug, built-in base role, purpose, first task, parent, depth, child count, lifetime and task budget, and queues the child task for a **later** run. A child never executes recursively in the run that created it. Omit `--allow-enlistment` to disable model-requested growth entirely.

Supply the existing private gateway access token only to the process that runs work. This example converts a hidden prompt into a short-lived environment value because Node cannot read a PowerShell secure string directly:

```powershell
$armadaSecure = Read-Host 'Alma access token' -AsSecureString
try {
  $env:ALMA_CHAT_ACCESS_TOKEN = [Net.NetworkCredential]::new('', $armadaSecure).Password
  npm run armada -- run --max-tasks 4
  npm run armada -- accept
} finally {
  Remove-Item Env:\ALMA_CHAT_ACCESS_TOKEN -ErrorAction SilentlyContinue
  $armadaSecure = $null
}
```

`accept` first validates `/api/status`, including exact runtime/provider/model and both fallback flags, then performs a real generation that must echo a unique exact marker. It consumes one free-tier request.

## Persistent evidence

- `state/tasks.json`: queue and terminal task states.
- `state/workers.json`: enlisted-worker lineage, expiry, and consumed task budgets.
- `state/results/<task-id>.json`: model output or sanitized failure evidence.
- `state/quota.json`: conservative local UTC day/minute ledger.
- `state/controller.lock`: exists only during an active controller run.

The state directory contains no provider or access credentials. Back it up if task history matters. Do not treat a status-only check as proof of generation; use `accept` for that gate.

## Tests

```powershell
npm run armada:test
npm test
npm run check
```

Armada tests use a mocked gateway and a temporary state directory. They do not consume cloud quota.

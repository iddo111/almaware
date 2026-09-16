// dsh-plugin-almido-gate — AlmIdo policy gate for DeepSeek Harness (dsh) v0.1 on eran3.
// Port of almido_gate.py (Perplexity-Computer-Use-Harness, verified 2026-08-14) onto the
// dsh tools pipeline: tools/pre-execute waterfall + ctx.tools.guard monotonic final deny.
// Zero-dependency plain ESM: node: builtins only (~/dsh-almido has no node_modules).
//
// Verdicts keep the Python gate's exact names: ALLOW / CONFIRM / BLOCK.
//   BLOCK   -> deny.
//   CONFIRM -> ALSO deny (dsh on eran3 has no push channel to Iddo), with a
//              "needs Iddo's confirmation" reason so the model knows why.
//   ALLOW   -> pass through, audited after next().
// Kill switch: a STOP file at config.stopPath denies EVERY tool call (same as the
// ~/.iddo-harness/STOP semantics).
// Fail-safe: unreadable policy => all shell commands denied (never open-by-accident).
// Audit: one JSON line per decision to config.auditPath, iddo-harness almido format:
//   {ts, src: "almido/dsh", kind, detail (<=200 chars), verdict, reason}
// Audit failure is swallowed — logging must never change a decision (same as the Python gate).
// Policy is JSON, not YAML: node stdlib has no YAML parser and this plugin imports nothing.

import { readFileSync, appendFileSync, existsSync } from 'node:fs'

export const name = 'almido-gate'
export const inject = ['tools']

const SHELL_TOOLS = new Set(['bash', 'pwsh'])

// fnmatch semantics (same as almido_gate.py): * = any run, ? = any one char,
// case-insensitive, anchored whole-string match.
function globToRegExp(pattern) {
  const esc = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '[\\s\\S]*')
    .replace(/\?/g, '[\\s\\S]')
  return new RegExp(`^${esc}$`, 'i')
}

export function apply(ctx, config = {}) {
  const policyPath = typeof config?.policyPath === 'string' ? config.policyPath : null
  const auditPath = typeof config?.auditPath === 'string' ? config.auditPath : null
  const stopPath = typeof config?.stopPath === 'string' ? config.stopPath : null
  if (!policyPath || !auditPath || !stopPath) {
    throw new Error('almido-gate config requires policyPath, auditPath and stopPath (strings)')
  }

  let policy = null
  let policyError = null
  try {
    policy = JSON.parse(readFileSync(policyPath, 'utf8'))
  } catch (err) {
    policyError = String(err?.message || err)
  }

  const compile = (list) =>
    Array.isArray(list)
      ? list.filter((p) => typeof p === 'string' && p).map((p) => ({ pattern: p, re: globToRegExp(p) }))
      : []
  const blockRules = compile(policy?.block?.commands)
  const confirmRules = compile(policy?.require_confirm?.commands)
  const blockSubstrings = Array.isArray(policy?.block?.command_substrings)
    ? policy.block.command_substrings.filter((s) => typeof s === 'string' && s)
    : []

  const matchRule = (rules, command) => {
    for (const r of rules) if (r.re.test(command)) return r.pattern
    return null
  }

  function audit(kind, detail, verdict, reason) {
    try {
      appendFileSync(
        auditPath,
        JSON.stringify({
          ts: new Date().toISOString(),
          src: 'almido/dsh',
          kind,
          detail: String(detail).slice(0, 200),
          verdict,
          reason,
        }) + '\n',
      )
    } catch {}
  }

  // Shared decision core — used by both the pre-execute waterfall and the sync guard.
  // Returns {verdict, reason} to deny, or null to let the call proceed.
  function decide(toolName, command) {
    if (existsSync(stopPath)) {
      return { verdict: 'BLOCK', reason: 'STOP file present - AlmIdo kill switch engaged; every tool call is denied until Iddo removes it' }
    }
    if (!SHELL_TOOLS.has(toolName) || typeof command !== 'string') return null
    if (policyError) {
      return { verdict: 'BLOCK', reason: `policy unreadable (${policyError}) - failing safe, all shell commands denied` }
    }
    const b = matchRule(blockRules, command)
    if (b) return { verdict: 'BLOCK', reason: `policy.block.commands: ${b}` }
    const lower = command.toLowerCase()
    for (const s of blockSubstrings) {
      if (lower.includes(s.toLowerCase())) {
        return { verdict: 'BLOCK', reason: `policy.block.command_substrings: ${s}` }
      }
    }
    const c = matchRule(confirmRules, command)
    if (c) {
      return { verdict: 'CONFIRM', reason: `policy.require_confirm.commands: ${c} - needs Iddo's confirmation; do not retry without it` }
    }
    return null
  }

  ctx.on('tools/pre-execute', async (exec, next) => {
    const command = exec?.arguments?.command
    const isShell = SHELL_TOOLS.has(exec?.name)
    const hit = decide(exec?.name, command)
    if (hit) {
      audit(isShell ? 'command' : 'tool', isShell ? command : exec?.name, hit.verdict, hit.reason)
      return { kind: 'deny', reason: `denied by almido-gate [${hit.verdict}]: ${hit.reason}` }
    }
    const d = await next()
    if (isShell && typeof command === 'string') {
      audit('command', command, d?.kind === 'allow' ? 'ALLOW' : String(d?.kind || 'unknown').toUpperCase(),
        d?.kind === 'allow' ? 'auto' : (d?.reason || d?.kind || 'unknown'))
    }
    return d
  })

  // Belt and braces: synchronous monotonic guard AFTER the waterfall — no listener can
  // un-deny it. Catches the case where another pre-execute listener short-circuits to
  // allow before our listener runs.
  ctx.tools.guard((exec) => {
    const hit = decide(exec?.name, exec?.arguments?.command)
    if (!hit) return undefined
    audit(SHELL_TOOLS.has(exec?.name) ? 'command' : 'tool',
      SHELL_TOOLS.has(exec?.name) ? exec?.arguments?.command : exec?.name,
      hit.verdict, `${hit.reason} (guard)`)
    return `almido-gate [${hit.verdict}]: ${hit.reason}`
  })

  if (policyError) {
    audit('policy', policyPath, 'BLOCK', `policy load failed: ${policyError}`)
  } else {
    audit('policy', policyPath, 'ALLOW',
      `almido-gate loaded: ${blockRules.length} block, ${confirmRules.length} confirm, ${blockSubstrings.length} substring rules`)
  }
}

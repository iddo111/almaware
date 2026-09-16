// dsh-plugin-almido-organs — AlmIdo organs for DeepSeek Harness (dsh) v0.1 on eran3.
// Part of AlmIdo, Iddo's ONE harness (the name braids Alma z"l + Iddo).
// Zero-dependency plain ESM on purpose: ~/dsh-almido has no node_modules, so this file
// may only use node: builtins and globals (fetch). Registered as a RAW ToolDefinition
// via ctx.tools.register — raw tools own their input validation.
//
// Tools:
//   shamash_weave(note) — read-only fetch of one knowledge knot from SHAMASH (eran2:8850),
//     LAN first (<lan-ip>), fabric fallback (<fabric-ip>). Both verified reachable
//     from eran3 on 2026-08-31.
//   alma_recall — DELIBERATELY OMITTED 2026-08-31: the PC recall server (:8794) is bound
//     to 127.0.0.1 only (measured via netstat, pid 18744); eran3 cannot reach it via LAN
//     <lan-ip> or Tailscale <tailnet-ip>. Re-add when recall is rebound to LAN.
//   ramchat_read — SKIPPED: no clean HTTP path from eran3 to the council; not inventing one.

export const name = 'almido-organs'
export const inject = ['tools']

const DEFAULTS = {
  shamashBase: 'http://<lan-ip>:8850',
  shamashFallback: 'http://<fabric-ip>:8850',
  maxChars: 20000,
}

export function apply(ctx, config = {}) {
  const cfg = { ...DEFAULTS, ...(config && typeof config === 'object' ? config : {}) }

  ctx.tools.register({
    name: 'shamash_weave',
    description:
      "Fetch one knowledge knot from SHAMASH, the librarian organ on eran2:8850 that keeps Iddo's second brain true (417+ notes, 66k+ strands). Pass the note id, e.g. 'project_shamash' or 'project_eran_throat' (memory file name without .md). Read-only; never mutates anything.",
    parameters: {
      type: 'object',
      properties: {
        note: { type: 'string', description: 'SHAMASH note id (memory file name without .md)' },
      },
      required: ['note'],
      additionalProperties: false,
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: String(value) }],
    },
    timeoutMs: 30000,
    isConcurrencySafe: () => true,
    async execute(args, exec) {
      const note = args?.note
      if (typeof note !== 'string' || !note.trim()) {
        throw new Error('note must be a non-empty string (a SHAMASH note id)')
      }
      const path = `/weave?note=${encodeURIComponent(note.trim())}`
      let lastErr
      for (const base of [cfg.shamashBase, cfg.shamashFallback]) {
        if (!base) continue
        try {
          const res = await fetch(base + path, { signal: exec?.signal })
          const text = await res.text()
          if (!res.ok) throw new Error(`SHAMASH ${base} answered HTTP ${res.status}: ${text.slice(0, 300)}`)
          return text.length > cfg.maxChars
            ? text.slice(0, cfg.maxChars) + `\n...[truncated at ${cfg.maxChars} chars]`
            : text
        } catch (err) {
          if (exec?.signal?.aborted) throw err
          lastErr = err
        }
      }
      throw new Error(
        `SHAMASH unreachable on LAN (${cfg.shamashBase}) and fabric (${cfg.shamashFallback}): ${lastErr?.message || lastErr}`,
      )
    },
  })
}

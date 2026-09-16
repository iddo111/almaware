// smoke.mjs — harness-less smoke test of both AlmIdo dsh plugins, run ON eran3:
//   node ~/dsh-almido/smoke.mjs
// Mocks the cordis ctx, then: (1) checks tool registration, (2) does a LIVE SHAMASH
// weave over the network, (3) drives the gate through representative commands,
// (4) flips the STOP kill switch, (5) prints the audit lines it produced.
import { readFileSync, writeFileSync, rmSync } from 'node:fs'
import { apply as organs } from './almido-organs/index.mjs'
import { apply as gate } from './almido-gate/index.mjs'

const registered = []
const guards = []
const listeners = {}
const ctx = {
  tools: { register: (t) => registered.push(t), guard: (g) => { guards.push(g); return () => {} } },
  on: (ev, fn) => { (listeners[ev] ||= []).push(fn); return () => {} },
  effect: (fn) => fn(),
}

const AUDIT = '/tmp/almido-smoke-audit.log'
const STOP = '/tmp/almido-smoke-STOP'
try { rmSync(AUDIT) } catch {}
try { rmSync(STOP) } catch {}

organs(ctx, {})
gate(ctx, { policyPath: new URL('./policy.json', import.meta.url).pathname, auditPath: AUDIT, stopPath: STOP })

console.log('registered tools:', registered.map((t) => t.name))
console.log('pre-execute listeners:', (listeners['tools/pre-execute'] || []).length, '| guards:', guards.length)

// live SHAMASH fetch
const tool = registered.find((t) => t.name === 'shamash_weave')
const ac = new AbortController()
const text = await tool.execute({ note: process.argv[2] || 'project_shamash' }, { signal: ac.signal })
console.log('shamash_weave LIVE ok — bytes:', text.length, 'head:', JSON.stringify(text.slice(0, 100)))

// gate decisions
const pre = listeners['tools/pre-execute'][0]
const tryCmd = async (cmd) => {
  const d = await pre({ name: 'bash', arguments: { command: cmd }, callId: 'smoke' }, async () => ({ kind: 'allow' }))
  console.log(`gate ${JSON.stringify(cmd)} ->`, JSON.stringify(d))
}
await tryCmd('ls -la /home/eran3')            // expect allow
await tryCmd('rm -rf /')                      // expect deny BLOCK
await tryCmd('rm -rf /home/eran3/junk')       // expect deny BLOCK (rm -rf /* glob)
await tryCmd('git push origin main')          // expect deny CONFIRM
await tryCmd('cat /etc/passwd')               // expect deny BLOCK (substring /etc/)
await tryCmd('ssh eran1 uptime')              // expect deny BLOCK (ERAN fence)
await tryCmd('echo $GITHUB_TOKEN')            // expect deny BLOCK (*token*)
console.log('guard("rm -rf /") ->', JSON.stringify(guards[0]({ name: 'bash', arguments: { command: 'rm -rf /' } })))
console.log('guard("pwd") ->', JSON.stringify(guards[0]({ name: 'bash', arguments: { command: 'pwd' } })))

// kill switch
writeFileSync(STOP, 'smoke')
await tryCmd('pwd')                           // expect deny BLOCK (STOP)
const dTool = await pre({ name: 'shamash_weave', arguments: { note: 'x' }, callId: 'smoke' }, async () => ({ kind: 'allow' }))
console.log('STOP blocks non-shell tool too ->', JSON.stringify(dTool))
rmSync(STOP)
await tryCmd('pwd')                           // expect allow again

console.log('--- audit lines written ---')
console.log(readFileSync(AUDIT, 'utf8'))

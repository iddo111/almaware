const strip = document.querySelector('#node-strip');
const checked = document.querySelector('#checked');
const output = document.querySelector('#job-output');
const directorPrompt = document.querySelector('#director-prompt');
const directorOutput = document.querySelector('#director-output');
const directorStatus = document.querySelector('#director-status');
const directorRun = document.querySelector('#director-run');
let manifestCache = null;

async function loadManifest() {
  if (manifestCache) return manifestCache;
  const response = await fetch('/api/manifest', {cache:'no-store'});
  if (!response.ok) throw new Error(`Manifest HTTP ${response.status}`);
  manifestCache = await response.json();
  return manifestCache;
}

function humanBytes(value) {
  if (!Number.isFinite(value)) return 'unknown';
  const units = ['B','KB','MB','GB','TB']; let n = value; let i = 0;
  while (n >= 1000 && i < units.length - 1) { n /= 1000; i += 1; }
  return `${n.toFixed(i > 2 ? 2 : 1)} ${units[i]}`;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function nodeCard(node) {
  const active = (node.jobs || []).filter(j => j.state === 'running');
  const size = Object.values(node.sizes || {}).reduce((a,b) => a + b, 0);
  const canaries = node.canaries || [];
  const passed = canaries.filter(c => c.technical_pass);
  const state = !node.ok ? 'bad' : active.length || passed.length ? 'ok' : '';
  const label = !node.ok ? 'blocked' : active.length ? 'live PID evidence' : passed.length ? 'technical canary passed' : 'reachable; no tracked live PID';
  const canaryText = canaries.length ? canaries.map(c => `${escapeHtml(c.name)}: ${c.technical_pass ? 'technical pass' : c.exit_code === 'unknown' ? 'incomplete' : `exit ${escapeHtml(c.exit_code)}`}`).join('<br>') : 'none';
  return `<article class="node ${state}">
    <h3>${escapeHtml(node.id)}</h3><div class="role">${escapeHtml(node.role)}</div>
    <div class="lamp">${label}</div>
    <dl><dt>GPU</dt><dd>${escapeHtml(node.gpu || 'unverified')}</dd><dt>Free</dt><dd>${humanBytes(node.free_bytes)}</dd><dt>Models</dt><dd>${humanBytes(size)}</dd><dt>Jobs</dt><dd>${active.map(j => escapeHtml(j.name)).join(', ') || 'none'}</dd><dt>Canaries</dt><dd>${canaryText}</dd><dt>Human review</dt><dd>not recorded</dd></dl>
  </article>`;
}

async function refreshNodes() {
  strip.innerHTML = '<article class="node"><h3>Checking</h3><div class="role">bounded read-only SSH probes</div></article>';
  try {
    const response = await fetch('/api/nodes', {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    strip.innerHTML = data.nodes.map(nodeCard).join('');
    checked.textContent = `Fresh evidence · ${new Date().toLocaleString()}`;
  } catch (error) {
    strip.innerHTML = `<article class="node bad"><h3>Blocked</h3><div class="role">${error.message}</div><div class="lamp">no fresh evidence</div></article>`;
    checked.textContent = 'Live node check failed.';
  }
}

document.querySelector('#refresh').addEventListener('click', refreshNodes);
document.querySelector('#job-form').addEventListener('submit', async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  const aspectMap = {'2.39:1':[1920,800], '1.85:1':[1920,1040], '16:9':[1920,1080], '9:16':[1080,1920]};
  const [width,height] = aspectMap[data.aspect];
  const fps = Number(data.fps); const duration = Number(data.duration_s);
  let route;
  try {
    const manifest = await loadManifest();
    if (data.worker_class === 'finishing') {
      route = {
        id: manifest.finishing.engine,
        revision: manifest.finishing.engine_revision,
        license: manifest.finishing.engine_license,
        status: manifest.finishing.status,
      };
    } else {
      route = manifest.models.find(model => model.lane === data.worker_class);
    }
    if (!route || !route.revision || !route.license) throw new Error('selected route is not pinned');
  } catch (error) {
    output.textContent = `BLOCKED: ${error.message}`;
    document.querySelector('#job-state').textContent = 'BLOCKED';
    return;
  }
  const routeVerified = String(route.status || '').startsWith('verified-');
  const job = {
    project_id: data.project_id, shot_id: data.shot_id, version: Number(data.version),
    intent: data.intent, inputs: [], continuity_refs: data.continuity.split(',').map(s => s.trim()).filter(Boolean),
    model_id: route.id, model_revision: route.revision,
    model_license: route.license, worker_class: data.worker_class,
    workflow_id: 'alma-2d-first-v1', workflow_sha256: 'COMPUTE-AFTER-WORKFLOW-PIN',
    seed: Number(data.seed), prompt: data.intent, negative_prompt: 'identity drift, costume drift, temporal flicker, broken anatomy, illegible text, clipped highlights',
    width, height, fps, frames: Math.round(fps * duration), duration_s: duration,
    color_pipeline: 'linear/EXR -> OCIO/ACES -> HDR10-PQ or HLG + SDR trim',
    audio_spec: {sample_rate_hz: 48000, loudness: 'delivery-specific'}, output_paths: [],
    provenance_path: `provenance/${data.project_id}/${data.shot_id}/v${data.version}`,
    acceptance_tests: ['artifact-opens','continuity-review','no-temporal-flicker','audio-sync','provenance-complete'],
    status: 'PLANNED',
    blockers: [
      ...(routeVerified ? [] : [`selected route is not technically accepted: ${route.status || 'unknown'}`]),
      'workflow revision not pinned',
      'human media review pending'
    ]
  };
  output.textContent = JSON.stringify(job, null, 2);
  document.querySelector('#job-state').textContent = 'PLANNED';
});
document.querySelector('#copy').addEventListener('click', async () => {
  await navigator.clipboard.writeText(output.textContent);
  document.querySelector('#job-state').textContent = 'COPIED';
});

directorRun.addEventListener('click', async () => {
  const prompt = directorPrompt.value.trim();
  if (!prompt) return;
  let jobContext = null;
  try { jobContext = JSON.parse(output.textContent); } catch (_error) { jobContext = null; }
  directorRun.disabled = true;
  directorStatus.textContent = 'Nemotron is planning through the canonical route…';
  directorOutput.textContent = '';
  try {
    const response = await fetch('/api/brain/plan', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({prompt, job_context: jobContext, max_tokens: 1200})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    directorOutput.textContent = data.content;
    directorStatus.textContent = `${data.model} · ${data.brain?.node || 'canonical gateway'} · plan only`;
  } catch (error) {
    directorOutput.textContent = `BLOCKED: ${error.message}`;
    directorStatus.textContent = 'Studio brain unavailable.';
  } finally {
    directorRun.disabled = false;
  }
});

refreshNodes();

/* MIKDASH — a walk through the Temple of Yechezkel 40-43.
   Raw WebGL2 + WebXR. No library, no CDN, nothing fetched from anywhere.
   The model arrives in CUBITS and is converted to METRES here, once, because
   WebXR speaks metres and mixing the two is how you end up 1.8x too tall. */
'use strict';

// ---------------------------------------------------------------- mat4 ----
const M4 = {
  ident: () => new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]),
  mul(a, b, o) {                        // o = a * b  (column-major, GL order)
    o = o || new Float32Array(16);
    for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
      o[c*4+r] = a[r]*b[c*4] + a[4+r]*b[c*4+1] + a[8+r]*b[c*4+2] + a[12+r]*b[c*4+3];
    }
    return o;
  },
  persp(fovy, asp, n, f) {
    const t = 1 / Math.tan(fovy / 2);
    return new Float32Array([t/asp,0,0,0, 0,t,0,0, 0,0,(f+n)/(n-f),-1, 0,0,2*f*n/(n-f),0]);
  },
  lookAt(e, c, u) {
    let z = [e[0]-c[0], e[1]-c[1], e[2]-c[2]];
    let l = Math.hypot(z[0],z[1],z[2]) || 1; z = z.map(v => v/l);
    let x = [u[1]*z[2]-u[2]*z[1], u[2]*z[0]-u[0]*z[2], u[0]*z[1]-u[1]*z[0]];
    l = Math.hypot(x[0],x[1],x[2]) || 1; x = x.map(v => v/l);
    const y = [z[1]*x[2]-z[2]*x[1], z[2]*x[0]-z[0]*x[2], z[0]*x[1]-z[1]*x[0]];
    return new Float32Array([
      x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0,
      -(x[0]*e[0]+x[1]*e[1]+x[2]*e[2]),
      -(y[0]*e[0]+y[1]*e[1]+y[2]*e[2]),
      -(z[0]*e[0]+z[1]*e[1]+z[2]*e[2]), 1]);
  },
  // world->view from an XR view matrix (ref space) plus our own ref->world placement
  fromXR(viewFromRef, px, py, pz, yaw) {
    const s = Math.sin(-yaw), c = Math.cos(-yaw);
    const refFromWorld = new Float32Array([
      c,0,-s,0,  0,1,0,0,  s,0,c,0,
      -(c*px + s*pz), -py, -(-s*px + c*pz), 1]);
    return M4.mul(viewFromRef, refFromWorld);
  }
};

// -- palette: comes from model.json, the same one the TZELEM stills use -----
let PAL = { _default:[.72,.67,.58] };
function colourOf(kind) {
  if (PAL[kind]) return PAL[kind];
  const i = kind.lastIndexOf('_');
  if (i > 0) { const k = '_gate' + kind.slice(i); if (PAL[k]) return PAL[k]; }
  return PAL._default;
}

// ------------------------------------------------------------ stations ----
// (x, z) in CUBITS, plus the level to stand on and a heading.
const STATIONS = [
  ['מחוץ לשער המזרחי · outside the east gate',      262,   0, 0,    Math.PI/2],
  ['בתוך שער החצר החיצונה · in the outer gate',     225,   0, 3.5,  Math.PI/2],
  ['החצר החיצונה · the outer court',                150,   0, 3.5,  Math.PI/2],
  ['שער החצר הפנימית · the inner gate',              75,   0, 7.5,  Math.PI/2],
  ['לפני המזבח · before the altar',                  27,  19, 7.5,  0.965],
  ['האולם · the porch of the House',                -58,   0, 12.5, Math.PI/2],
];

// ------------------------------------------------------------------ GL ----
const cv = document.getElementById('c');
const gl = cv.getContext('webgl2', { antialias:true, alpha:false, xrCompatible:true });
if (!gl) { document.body.innerHTML = '<p style="color:#fff;padding:2em">' +
  'הדפדפן הזה לא תומך ב-WebGL2 / This browser has no WebGL2.</p>'; throw new Error('no webgl2'); }

const VS = `#version 300 es
in vec3 aPos; in vec3 aNrm; in vec3 aCol; in float aInf;
uniform mat4 uProj, uView;
out vec3 vNrm, vCol; out float vInf, vDepth;
void main(){
  vec4 vp = uView * vec4(aPos, 1.0);
  gl_Position = uProj * vp;
  vNrm = aNrm; vCol = aCol; vInf = aInf; vDepth = length(vp.xyz);
}`;

const FS = `#version 300 es
precision highp float;
in vec3 vNrm, vCol; in float vInf, vDepth;
uniform vec3 uLight, uSky; uniform float uShowInf, uFog;
out vec4 frag;
void main(){
  vec3 n = normalize(vNrm);
  float sun = max(dot(n, -uLight), 0.0);
  float up  = n.y * 0.5 + 0.5;
  vec3 amb  = mix(vec3(0.38,0.34,0.30), vec3(0.60,0.67,0.78), up);  // ground bounce -> sky
  vec3 col  = vCol * (amb + sun * vec3(1.15,1.06,0.90));
  if (uShowInf > 0.5 && vInf > 0.5) col = mix(col, vec3(1.00,0.46,0.05), 0.62);
  float f = clamp(vDepth / uFog, 0.0, 1.0);
  col = mix(col, uSky, f * f * 0.9);
  frag = vec4(pow(col, vec3(1.0/2.2)), 1.0);
}`;

function shader(type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
  return s;
}
const prog = gl.createProgram();
gl.attachShader(prog, shader(gl.VERTEX_SHADER, VS));
gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FS));
gl.linkProgram(prog);
if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
gl.useProgram(prog);
const U = {};
for (const n of ['uProj','uView','uLight','uSky','uShowInf','uFog'])
  U[n] = gl.getUniformLocation(prog, n);

const SKY = [0.80, 0.855, 0.93];
gl.enable(gl.DEPTH_TEST);
gl.enable(gl.CULL_FACE);
gl.clearColor(SKY[0], SKY[1], SKY[2], 1);

// --------------------------------------------------------------- state ----
let MODEL = null, BOXES = [], NVERT = 0, CUBIT = 0.56;
let showInf = 0;
const P = { x:0, y:0, z:0, vy:0, yaw:Math.PI/2, pitch:-0.05 };
let EYE = 1.65, RAD = 0.34, STEPUP = 0.46, GRAV = 22.0;

// six faces of a unit box: normal + the four corners as (dx,dy,dz) selectors
const FACES = [
  [[ 1,0,0], [[1,0,0],[1,1,0],[1,1,1],[1,0,1]]],
  [[-1,0,0], [[0,0,1],[0,1,1],[0,1,0],[0,0,0]]],
  [[0, 1,0], [[0,1,0],[0,1,1],[1,1,1],[1,1,0]]],
  [[0,-1,0], [[0,0,1],[0,0,0],[1,0,0],[1,0,1]]],
  [[0,0, 1], [[1,0,1],[1,1,1],[0,1,1],[0,0,1]]],
  [[0,0,-1], [[0,0,0],[0,1,0],[1,1,0],[1,0,0]]],
];

function buildBuffers(boxes) {
  const n = boxes.length * 36;
  const pos = new Float32Array(n*3), nrm = new Float32Array(n*3),
        col = new Float32Array(n*3), inf = new Float32Array(n);
  let v = 0;
  for (const b of boxes) {
    const c = colourOf(b.kind), lo = b.lo, hi = b.hi, fi = b.inferred ? 1 : 0;
    for (const [N, quad] of FACES) {
      for (const t of [0,1,2, 0,2,3]) {
        const q = quad[t];
        pos[v*3  ] = q[0] ? hi[0] : lo[0];
        pos[v*3+1] = q[1] ? hi[1] : lo[1];
        pos[v*3+2] = q[2] ? hi[2] : lo[2];
        nrm[v*3] = N[0]; nrm[v*3+1] = N[1]; nrm[v*3+2] = N[2];
        col[v*3] = c[0]; col[v*3+1] = c[1]; col[v*3+2] = c[2];
        inf[v] = fi; v++;
      }
    }
  }
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  const attach = (data, size, loc) => {
    const bo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, bo);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0);
  };
  attach(pos, 3, gl.getAttribLocation(prog, 'aPos'));
  attach(nrm, 3, gl.getAttribLocation(prog, 'aNrm'));
  attach(col, 3, gl.getAttribLocation(prog, 'aCol'));
  attach(inf, 1, gl.getAttribLocation(prog, 'aInf'));
  gl.bindVertexArray(null);
  NVERT = v;
  return vao;
}
let VAO = null;

// ------------------------------------------------------------- physics ----
function groundAt(x, z, ceil) {
  let g = 0;
  for (const b of BOXES) {
    if (x < b.lo[0] || x > b.hi[0] || z < b.lo[2] || z > b.hi[2]) continue;
    const t = b.hi[1];
    if (t <= ceil && t > g) g = t;
  }
  return g;
}
function blocked(x, foot, z) {
  const head = foot + EYE + 0.12, lim = foot + STEPUP;
  for (const b of BOXES) {
    if (b.hi[1] <= lim || b.lo[1] >= head) continue;
    if (x + RAD <= b.lo[0] || x - RAD >= b.hi[0]) continue;
    if (z + RAD <= b.lo[2] || z - RAD >= b.hi[2]) continue;
    return true;
  }
  return false;
}
function move(dx, dz, dt) {
  if (dx || dz) {
    if (!blocked(P.x + dx, P.y, P.z)) P.x += dx;
    if (!blocked(P.x, P.y, P.z + dz)) P.z += dz;
  }
  const g = groundAt(P.x, P.z, P.y + STEPUP);
  if (P.y - g <= STEPUP && P.vy <= 0) { P.y = g; P.vy = 0; }
  else { P.vy -= GRAV * dt; P.y += P.vy * dt; if (P.y < g) { P.y = g; P.vy = 0; } }
}
function goStation(i) {
  const s = STATIONS[i]; if (!s) return;
  P.x = s[1] * CUBIT; P.z = s[2] * CUBIT;
  P.y = groundAt(P.x, P.z, s[3] * CUBIT + 1.0);
  P.vy = 0; P.yaw = s[4]; P.pitch = -0.03;
  say(s[0], '');
}

// ------------------------------------------------------------ crosshair ----
function pick() {                       // ray from the eye along the view dir
  const cp = Math.cos(P.pitch);
  const d = [-Math.sin(P.yaw)*cp, Math.sin(P.pitch), -Math.cos(P.yaw)*cp];
  const o = [P.x, P.y + EYE, P.z];
  let best = null, bt = 1e9;
  for (const b of BOXES) {
    let t0 = 0, t1 = 1e9, ok = true;
    for (let a = 0; a < 3; a++) {
      if (Math.abs(d[a]) < 1e-9) { if (o[a] < b.lo[a] || o[a] > b.hi[a]) { ok = false; break; } continue; }
      let ta = (b.lo[a]-o[a])/d[a], tb = (b.hi[a]-o[a])/d[a];
      if (ta > tb) { const s = ta; ta = tb; tb = s; }
      if (ta > t0) t0 = ta; if (tb < t1) t1 = tb;
      if (t0 > t1) { ok = false; break; }
    }
    if (ok && t0 > 0.02 && t0 < bt) { bt = t0; best = b; }
  }
  return best ? { box: best, dist: bt } : null;
}
const $ = id => document.getElementById(id);
function say(k, s) { $('wk').textContent = k; $('ws').innerHTML = s; }

let lastPick = null;
function updateHUD() {
  const h = pick();
  if (h && h.box !== lastPick) {
    lastPick = h.box;
    const b = h.box, w = (b.hi[0]-b.lo[0])/CUBIT, ht = (b.hi[1]-b.lo[1])/CUBIT,
          d = (b.hi[2]-b.lo[2])/CUBIT;
    const r = n => (Math.round(n*100)/100);
    say(b.kind.replace(/_/g,' '),
      (b.inferred ? '<span class="inf">&#9888; לא נמסר בכתוב / not given by the text</span><br>' : '') +
      b.src + (b.note ? '<br><i>' + b.note + '</i>' : '') +
      `<br>${r(w)} &times; ${r(d)} &times; ${r(ht)} אמות / cubits`);
  } else if (!h) { lastPick = null; }
  $('wp').textContent =
    `x ${(P.x/CUBIT).toFixed(0)}  z ${(P.z/CUBIT).toFixed(0)}  ` +
    `floor ${(P.y/CUBIT).toFixed(1)} cubits (${P.y.toFixed(1)} m)` +
    (h ? `   |   ${(h.dist/CUBIT).toFixed(0)} cubits away` : '');
}

// -------------------------------------------------------- desktop input ----
const keys = Object.create(null);
addEventListener('keydown', e => {
  keys[e.code] = true;
  if (e.code === 'KeyI') { showInf = showInf ? 0 : 1;
    say(showInf ? 'מראה את מה שאינו בכתוב' : 'מראה רק את הכתוב',
        showInf ? 'Amber = a dimension Yechezkel does not give. Everything else traces to a verse.'
                : 'Press I again to light up the inferred parts.'); }
  const n = 'Digit1 Digit2 Digit3 Digit4 Digit5 Digit6'.split(' ').indexOf(e.code);
  if (n >= 0) goStation(n);
});
addEventListener('keyup', e => { keys[e.code] = false; });
cv.addEventListener('click', () => { if (!xrSession) cv.requestPointerLock(); });
$('veil').addEventListener('click', () => {
  $('veil').classList.add('hide'); $('cross').classList.remove('hide'); cv.requestPointerLock();
});
addEventListener('mousemove', e => {
  if (document.pointerLockElement !== cv) return;
  P.yaw -= e.movementX * 0.0022;
  P.pitch = Math.max(-1.4, Math.min(1.4, P.pitch - e.movementY * 0.0022));
});

function walk(dt) {
  const sp = (keys['ShiftLeft'] || keys['ShiftRight'] ? 9.0 : 3.1) * dt;
  let f = (keys['KeyW']?1:0) - (keys['KeyS']?1:0);
  let r = (keys['KeyD']?1:0) - (keys['KeyA']?1:0);
  if (!f && !r) { move(0, 0, dt); return; }
  const l = Math.hypot(f, r); f /= l; r /= l;
  const s = Math.sin(P.yaw), c = Math.cos(P.yaw);
  move((-s*f + c*r) * sp, (-c*f - s*r) * sp, dt);
}

// ------------------------------------------------------------------ XR ----
let xrSession = null, xrRefSpace = null, snapCool = 0;
async function probeXR() {
  const note = $('xrnote'), btn = $('vr');
  if (!navigator.xr) {
    btn.textContent = 'אין WebXR'; btn.disabled = true;
    note.innerHTML = '<b>navigator.xr לא קיים.</b><br>No WebXR in this browser. ' +
      'The desktop walkthrough below is the whole model &mdash; nothing is missing from it.';
    return false;
  }
  let ok = false;
  try { ok = await navigator.xr.isSessionSupported('immersive-vr'); } catch (e) {}
  if (ok) {
    btn.disabled = false; btn.textContent = 'כניסה ל-VR · Enter VR';
    note.innerHTML = '<b>navigator.xr.isSessionSupported(\'immersive-vr\') = true.</b><br>' +
      'Left stick walks, right stick turns.';
  } else {
    btn.textContent = 'VR לא זמין כאן'; btn.disabled = true;
    note.innerHTML = '<b>navigator.xr קיים, אבל immersive-vr = false.</b><br>' +
      'This browser has the WebXR API but no VR device. Open this same URL in the ' +
      'Quest browser to enter.';
  }
  return ok;
}
async function enterXR() {
  try {
    xrSession = await navigator.xr.requestSession('immersive-vr',
      { optionalFeatures: ['local-floor', 'bounded-floor'] });
  } catch (e) { $('xrnote').innerHTML = 'requestSession נכשל: ' + e.message; return; }
  await gl.makeXRCompatible();
  xrSession.updateRenderState({ baseLayer: new XRWebGLLayer(xrSession, gl),
                                depthNear: 0.05, depthFar: 3000 });
  try { xrRefSpace = await xrSession.requestReferenceSpace('local-floor'); }
  catch (e) { xrRefSpace = await xrSession.requestReferenceSpace('local'); }
  xrSession.addEventListener('end', () => { xrSession = null; requestAnimationFrame(loop); });
  document.querySelectorAll('.panel,#cross').forEach(n => n.classList.add('hide'));
  xrSession.requestAnimationFrame(xrLoop);
}
$('vr').addEventListener('click', enterXR);

function xrInput(dt) {
  let mx = 0, mz = 0, turn = 0;
  for (const src of xrSession.inputSources) {
    const g = src.gamepad; if (!g || g.axes.length < 4) continue;
    const ax = g.axes[2] || 0, ay = g.axes[3] || 0;
    const dead = v => Math.abs(v) < 0.16 ? 0 : v;
    if (src.handedness === 'right') turn += dead(ax);
    else { mx += dead(ax); mz += dead(ay); }
  }
  snapCool -= dt;
  if (Math.abs(turn) > 0.7 && snapCool <= 0) { P.yaw -= Math.sign(turn) * Math.PI/6; snapCool = 0.28; }
  const sp = 3.1 * dt, s = Math.sin(P.yaw), c = Math.cos(P.yaw);
  move((-s*(-mz) + c*mx) * sp, (-c*(-mz) - s*mx) * sp, dt);
}

// ---------------------------------------------------------------- draw ----
const LIGHT = (() => { const v = [-0.68, -0.62, -0.39];    // morning sun, from the east
  const l = Math.hypot(...v); return v.map(x => x/l); })();

function drawWith(proj, view) {
  gl.useProgram(prog);
  gl.uniformMatrix4fv(U.uProj, false, proj);
  gl.uniformMatrix4fv(U.uView, false, view);
  gl.uniform3fv(U.uLight, LIGHT);
  gl.uniform3fv(U.uSky, SKY);
  gl.uniform1f(U.uShowInf, showInf);
  gl.uniform1f(U.uFog, 620.0);
  gl.bindVertexArray(VAO);
  gl.drawArrays(gl.TRIANGLES, 0, NVERT);
}

let last = 0;
function loop(t) {
  if (xrSession) return;
  const dt = Math.min(0.05, (t - last) / 1000 || 0.016); last = t;
  walk(dt);
  const w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  gl.viewport(0, 0, cv.width, cv.height);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  const cp = Math.cos(P.pitch);
  const eye = [P.x, P.y + EYE, P.z];
  const ctr = [eye[0] - Math.sin(P.yaw)*cp, eye[1] + Math.sin(P.pitch), eye[2] - Math.cos(P.yaw)*cp];
  drawWith(M4.persp(1.05, cv.width / cv.height, 0.05, 3000), M4.lookAt(eye, ctr, [0,1,0]));
  updateHUD();
  requestAnimationFrame(loop);
}

function xrLoop(t, frame) {
  const dt = Math.min(0.05, (t - last) / 1000 || 0.016); last = t;
  xrSession.requestAnimationFrame(xrLoop);
  const pose = frame.getViewerPose(xrRefSpace);
  if (!pose) return;
  xrInput(dt);
  const layer = xrSession.renderState.baseLayer;
  gl.bindFramebuffer(gl.FRAMEBUFFER, layer.framebuffer);
  gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  for (const view of pose.views) {
    const vp = layer.getViewport(view);
    gl.viewport(vp.x, vp.y, vp.width, vp.height);
    drawWith(view.projectionMatrix,
             M4.fromXR(view.transform.inverse.matrix, P.x, P.y, P.z, P.yaw));
  }
}

// ---------------------------------------------------------------- boot ----
(async function boot() {
  const r = await fetch('model.json');
  MODEL = await r.json();
  CUBIT = MODEL.cubit_m; EYE = MODEL.eye_m;
  if (MODEL.palette) PAL = MODEL.palette;
  BOXES = MODEL.boxes.map(b => ({
    lo: b.lo.map(v => v * CUBIT), hi: b.hi.map(v => v * CUBIT),
    kind: b.kind, src: b.src, note: b.note, inferred: b.inferred
  }));
  VAO = buildBuffers(BOXES);
  goStation(0);
  await probeXR();
  say('מחוץ לשער המזרחי · outside the east gate',
      'לחץ על המסך ולך מערבה אל השער. Click, then walk west into the gate.');
  console.log(`MIKDASH: ${BOXES.length} boxes, ${NVERT} vertices, cubit ${CUBIT} m`);
  requestAnimationFrame(loop);
})();

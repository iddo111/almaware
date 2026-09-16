// לזכרה של עלמה ז״ל
"use strict";

// UI Elements
const cv = document.getElementById('scene');
const ctx = cv.getContext('2d');
const w1Slider = document.getElementById('w1');
const w2Slider = document.getElementById('w2');
const w3Slider = document.getElementById('w3');
const thetaSlider = document.getElementById('theta');
const rateSlider = document.getElementById('rate');

const w1Out = document.getElementById('w1-value');
const w2Out = document.getElementById('w2-value');
const w3Out = document.getElementById('w3-value');
const thetaOut = document.getElementById('theta-value');
const rateOut = document.getElementById('rate-value');

const btnStep = document.getElementById('step');
const btnEpoch = document.getElementById('epoch');
const btnAuto = document.getElementById('auto');
const btnReset = document.getElementById('reset');

const txtAccuracy = document.getElementById('accuracy');
const txtErrors = document.getElementById('errors');
const txtUpdates = document.getElementById('updates');
const txtIterations = document.getElementById('iterations');

const txtSelectedCoords = document.getElementById('selected-coords');
const txtSelectedResult = document.getElementById('selected-result');
const logTape = document.getElementById('training-log');

const sumEquation = document.getElementById('sum-equation');
const sumValue = document.getElementById('sum-value');
const thresholdTest = document.getElementById('threshold-test');

const term1Read = document.getElementById('term1');
const term2Read = document.getElementById('term2');
const term3Read = document.getElementById('term3');
const machineSum = document.getElementById('machine-sum');
const machineTest = document.getElementById('machine-test');
const machineOutput = document.getElementById('machine-output');
const planeReadout = document.getElementById('plane-readout');
const liveDescription = document.getElementById('live-description');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const COLORS = {
  night: '#050a07',
  grid: 'rgba(222, 214, 189, 0.11)',
  green: '#a7ff3f',
  greenGlow: 'rgba(167, 255, 63, 0.42)',
  amber: '#ffbd3e',
  amberGlow: 'rgba(255, 189, 62, 0.42)',
  cyan: '#7edbd0',
  error: '#ff6659',
  paper: '#ded6bd'
};

// 3D Canvas parameters
let W, H, DPR;
function resize() {
  DPR = Math.min(window.devicePixelRatio || 1, 2);
  const rect = cv.getBoundingClientRect();
  W = cv.width = Math.round(rect.width * DPR);
  H = cv.height = Math.round(rect.height * DPR);
}
window.addEventListener('resize', () => { resize(); draw(); });
resize();

// --- Perceptron State ---
let w1 = parseFloat(w1Slider.value);
let w2 = parseFloat(w2Slider.value);
let w3 = parseFloat(w3Slider.value);
let theta = parseFloat(thetaSlider.value);
let eta = parseFloat(rateSlider.value);

let iterations = 0;
let updatesCount = 0;
let autoTraining = false;
let autoTrainTimer = null;
let selectedPoint = null;

// Orbit view variables
let yaw = 0.55;
let pitch = 0.45;
let zoom = 1.0;
let dragging = false;
let px = 0, py = 0;

// Deterministic Separable Dataset (Seedable style)
let dataset = [];
const W_TRUE = [0.8, -0.6, 0.4];
const THETA_TRUE = 0.15;

function generateDataset() {
  dataset = [];
  let seed = 42;
  function random() {
    let x = Math.sin(seed++) * 10000;
    return x - Math.floor(x);
  }
  
  // Create 10 positive and 10 negative points
  let posCount = 0;
  let negCount = 0;
  
  while (posCount < 10 || negCount < 10) {
    let x1 = (random() * 2.0) - 1.0;
    let x2 = (random() * 2.0) - 1.0;
    let x3 = (random() * 2.0) - 1.0;
    
    // Check separator distance
    let dist = W_TRUE[0]*x1 + W_TRUE[1]*x2 + W_TRUE[2]*x3 - THETA_TRUE;
    if (Math.abs(dist) < 0.15) continue; // Keep margin for visual clarity
    
    let label = dist >= 0 ? 1 : -1;
    
    if (label === 1 && posCount < 10) {
      dataset.push({ x: [x1, x2, x3], target: 1 });
      posCount++;
    } else if (label === -1 && negCount < 10) {
      dataset.push({ x: [x1, x2, x3], target: -1 });
      negCount++;
    }
  }
}
generateDataset();
selectedPoint = dataset[0];

// --- Perceptron Logic ---
function predict(x) {
  let sum = w1*x[0] + w2*x[1] + w3*x[2];
  return sum >= theta ? 1 : -1;
}

function calculateAccuracy() {
  let correct = 0;
  dataset.forEach(pt => {
    if (predict(pt.x) === pt.target) correct++;
  });
  return correct / dataset.length;
}

function appendLog(message, type = '') {
  const li = document.createElement('li');
  if (type) li.className = type;
  li.textContent = `[צעד ${iterations}] ${message}`;
  logTape.appendChild(li);
  logTape.scrollTop = logTape.scrollHeight;
  while (logTape.children.length > 30) {
    logTape.removeChild(logTape.firstChild);
  }
}

function updateSliders() {
  w1Slider.value = w1.toFixed(2);
  w2Slider.value = w2.toFixed(2);
  w3Slider.value = w3.toFixed(2);
  thetaSlider.value = theta.toFixed(2);
  
  w1Out.value = w1.toFixed(2);
  w2Out.value = w2.toFixed(2);
  w3Out.value = w3.toFixed(2);
  thetaOut.value = theta.toFixed(2);
}

function trainStep() {
  iterations++;
  let foundError = false;
  
  for (let i = 0; i < dataset.length; i++) {
    let pt = dataset[i];
    let y = predict(pt.x);
    if (y !== pt.target) {
      foundError = true;
      let errorVal = pt.target - y; // 2 or -2
      
      let dw1 = eta * errorVal * pt.x[0];
      let dw2 = eta * errorVal * pt.x[1];
      let dw3 = eta * errorVal * pt.x[2];
      let dtheta = -eta * errorVal; // bias update
      
      w1 += dw1;
      w2 += dw2;
      w3 += dw3;
      theta += dtheta;
      
      updatesCount++;
      
      appendLog(`טעות בנקודה (${pt.x[0].toFixed(2)}, ${pt.x[1].toFixed(2)}, ${pt.x[2].toFixed(2)}): צפוי ${pt.target}, קיבל ${y}. עדכון משקלים!`, 'update');
      break;
    }
  }
  
  if (!foundError) {
    appendLog("הפרספטרון מסווג את כל הנקודות בציון 100% דיוק באופן מושלם!", 'correct');
    if (autoTraining) toggleAutoTrain();
  }
  
  updateSliders();
  updateMetrics();
  draw();
  announceState();
}

function trainEpoch() {
  iterations++;
  let updatesInEpoch = 0;
  
  for (let i = 0; i < dataset.length; i++) {
    let pt = dataset[i];
    let y = predict(pt.x);
    if (y !== pt.target) {
      let errorVal = pt.target - y;
      w1 += eta * errorVal * pt.x[0];
      w2 += eta * errorVal * pt.x[1];
      w3 += eta * errorVal * pt.x[2];
      theta += -eta * errorVal;
      
      updatesCount++;
      updatesInEpoch++;
    }
  }
  
  if (updatesInEpoch === 0) {
    appendLog("סיבוב מלא עבר ללא שום טעויות - דיוק מושלם!", 'correct');
    if (autoTraining) toggleAutoTrain();
  } else {
    appendLog(`סיבוב מלא הסתיים עם ${updatesInEpoch} עדכוני משקלים.`, 'update');
  }
  
  updateSliders();
  updateMetrics();
  draw();
  announceState();
}

function toggleAutoTrain() {
  autoTraining = !autoTraining;
  if (autoTraining) {
    btnAuto.textContent = 'עצור אימון רציף';
    btnAuto.setAttribute('aria-pressed', 'true');
    autoTrainTimer = setInterval(() => {
      let accuracy = calculateAccuracy();
      if (accuracy >= 1.0) {
        toggleAutoTrain();
      } else {
        trainStep();
      }
    }, reducedMotion.matches ? 720 : 360);
  } else {
    btnAuto.textContent = 'הפעל אימון רציף';
    btnAuto.setAttribute('aria-pressed', 'false');
    clearInterval(autoTrainTimer);
  }
}

function resetAll() {
  w1 = 0.25;
  w2 = -0.35;
  w3 = 0.15;
  theta = 0.55;
  iterations = 0;
  updatesCount = 0;
  if (autoTraining) toggleAutoTrain();
  logTape.innerHTML = '<li>המעבדה אותחלה מחדש.</li>';
  updateSliders();
  updateMetrics();
  draw();
  announceState();
}

function announceState() {
  if (!liveDescription) return;
  const errors = dataset.reduce((total, point) => total + (predict(point.x) === point.target ? 0 : 1), 0);
  liveDescription.textContent = `צעד ${iterations}. ${errors} טעויות מתוך ${dataset.length}. דיוק ${(calculateAccuracy() * 100).toFixed(0)} אחוז.`;
}

function updateMetrics() {
  let accuracy = calculateAccuracy();
  let errors = 0;
  dataset.forEach(pt => {
    if (predict(pt.x) !== pt.target) errors++;
  });
  
  txtAccuracy.textContent = `${(accuracy * 100).toFixed(0)}%`;
  txtErrors.textContent = errors;
  txtUpdates.textContent = updatesCount;
  txtIterations.textContent = iterations;
  
  // Highlight values based on accuracy
  if (accuracy === 1.0) {
    txtAccuracy.style.color = 'var(--green)';
    txtErrors.style.color = 'var(--ink-muted)';
  } else {
    txtAccuracy.style.color = 'var(--accent)';
    txtErrors.style.color = 'var(--red)';
  }
  
  // Update selected point UI
  if (selectedPoint) {
    let val = w1*selectedPoint.x[0] + w2*selectedPoint.x[1] + w3*selectedPoint.x[2];
    txtSelectedCoords.textContent = `x₁ ${selectedPoint.x[0].toFixed(2)} · x₂ ${selectedPoint.x[1].toFixed(2)} · x₃ ${selectedPoint.x[2].toFixed(2)}`;
    let active = val >= theta ? 1 : -1;
    let isCorrect = active === selectedPoint.target;
    txtSelectedResult.innerHTML = `סכום: <span style="font-family:var(--font-mono)">${val.toFixed(3)}</span> · פלט: ${active} (${isCorrect ? '<span style="color:var(--green)">תואם</span>' : '<span style="color:var(--red)">טעות</span>'})`;
    
    // Update schematic
    const terms = [selectedPoint.x[0] * w1, selectedPoint.x[1] * w2, selectedPoint.x[2] * w3];
    term1Read.textContent = terms[0].toFixed(3);
    term2Read.textContent = terms[1].toFixed(3);
    term3Read.textContent = terms[2].toFixed(3);
    machineSum.textContent = val.toFixed(3);
    machineTest.textContent = val >= theta ? 'כן (≥ θ)' : 'לא (< θ)';
    machineOutput.textContent = active;
    machineOutput.style.color = active === 1 ? 'var(--green)' : 'var(--red)';
    
    sumValue.textContent = val.toFixed(3);
    thresholdTest.textContent = `מול θ = ${theta.toFixed(3)}`;
    if (sumEquation) sumEquation.textContent = `${terms[0].toFixed(3)} + ${terms[1].toFixed(3)} + ${terms[2].toFixed(3)} = ${val.toFixed(3)}`;
  }
  
  planeReadout.textContent = `PLANE: [w=${w1.toFixed(2)},${w2.toFixed(2)},${w3.toFixed(2)} / θ=${theta.toFixed(2)}]`;
}

// --- 3D Projection Engine ---
const S3D = 130; // 3D scale

function rot(p) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  let x = p[0] * cy - p[2] * sy;
  let z = p[0] * sy + p[2] * cy;
  let y = p[1];
  
  const cx = Math.cos(pitch), sx = Math.sin(pitch);
  let y2 = y * cx - z * sx;
  let z2 = y * sx + z * cx;
  
  return { x, y: y2, z: z2 };
}

function project(p) {
  const r = rot(p);
  const fov = 400;
  const f = (fov / (fov + r.z)) * zoom;
  return {
    x: W / 2 + r.x * f * DPR,
    y: H / 2 - r.y * f * DPR, // invert Y for screen coords
    f,
    z: r.z
  };
}

function drawLine3D(a, b, color, width = 1) {
  const A = project(a);
  const B = project(b);
  ctx.strokeStyle = color;
  ctx.lineWidth = width * DPR * Math.max(0.4, A.f);
  ctx.beginPath();
  ctx.moveTo(A.x, A.y);
  ctx.lineTo(B.x, B.y);
  ctx.stroke();
}

function drawPoint3D(p, label, isSelected = false, isCorrect = true) {
  const proj = project(p);
  const size = (isSelected ? 10 : 7) * DPR * proj.f;
  const color = label === 1 ? COLORS.green : COLORS.amber;
  
  // Draw glow
  const glow = ctx.createRadialGradient(proj.x, proj.y, 0, proj.x, proj.y, size * 2.2);
  glow.addColorStop(0, label === 1 ? COLORS.greenGlow : COLORS.amberGlow);
  glow.addColorStop(1, 'rgba(0, 0, 0, 0)');
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(proj.x, proj.y, size * 2.2, 0, 7);
  ctx.fill();
  
  // Base point
  ctx.fillStyle = color;
  ctx.beginPath();
  if (label === 1) {
    ctx.arc(proj.x, proj.y, size, 0, Math.PI * 2);
  } else {
    ctx.moveTo(proj.x, proj.y - size * 1.2);
    ctx.lineTo(proj.x + size * 1.2, proj.y);
    ctx.lineTo(proj.x, proj.y + size * 1.2);
    ctx.lineTo(proj.x - size * 1.2, proj.y);
    ctx.closePath();
  }
  ctx.fill();
  if (!isCorrect) {
    ctx.strokeStyle = COLORS.error;
    ctx.lineWidth = 2.5 * DPR;
    ctx.stroke();
  }
  
  if (isSelected) {
    ctx.strokeStyle = COLORS.paper;
    ctx.lineWidth = 2 * DPR;
    ctx.beginPath();
    ctx.arc(proj.x, proj.y, size + 3 * DPR, 0, 7);
    ctx.stroke();
  }
}

// Generate a quad polygon on the decision plane w.x = theta
function getDecisionPlanePolygon() {
  const normSq = w1*w1 + w2*w2 + w3*w3;
  if (normSq < 0.001) return [];
  
  // Normal vector
  const n = [w1, w2, w3];
  const len = Math.sqrt(normSq);
  const n_norm = [n[0]/len, n[1]/len, n[2]/len];
  
  // Find two orthogonal vectors u and v on the plane
  let h = Math.abs(n_norm[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
  // Cross product u = h x n
  const u = [
    h[1]*n_norm[2] - h[2]*n_norm[1],
    h[2]*n_norm[0] - h[0]*n_norm[2],
    h[0]*n_norm[1] - h[1]*n_norm[0]
  ];
  const uLen = Math.sqrt(u[0]*u[0] + u[1]*u[1] + u[2]*u[2]);
  const u_norm = [u[0]/uLen, u[1]/uLen, u[2]/uLen];
  
  // Cross product v = n x u
  const v_norm = [
    n_norm[1]*u_norm[2] - n_norm[2]*u_norm[1],
    n_norm[2]*u_norm[0] - n_norm[0]*u_norm[2],
    n_norm[0]*u_norm[1] - n_norm[1]*u_norm[0]
  ];
  
  // Point on plane closest to origin
  const p0_dist = theta / len;
  const p0 = [n_norm[0]*p0_dist, n_norm[1]*p0_dist, n_norm[2]*p0_dist];
  
  // Construct square corners around p0 on the plane
  const L = 1.3;
  const corners = [];
  const coords = [
    [L, L],
    [-L, L],
    [-L, -L],
    [L, -L]
  ];
  
  coords.forEach(pt => {
    corners.push([
      p0[0] + pt[0]*u_norm[0] + pt[1]*v_norm[0],
      p0[1] + pt[0]*u_norm[1] + pt[1]*v_norm[1],
      p0[2] + pt[0]*u_norm[2] + pt[1]*v_norm[2]
    ]);
  });
  
  return corners;
}

function drawDecisionPlane() {
  const corners = getDecisionPlanePolygon();
  if (corners.length < 4) return;
  
  const proj = corners.map(pt => project([pt[0]*S3D, pt[1]*S3D, pt[2]*S3D]));
  
  // Fill the plane
  ctx.fillStyle = 'rgba(167, 255, 63, 0.13)';
  ctx.beginPath();
  ctx.moveTo(proj[0].x, proj[0].y);
  for (let i = 1; i < proj.length; i++) {
    ctx.lineTo(proj[i].x, proj[i].y);
  }
  ctx.closePath();
  ctx.fill();
  
  // Outline the plane
  ctx.strokeStyle = 'rgba(167, 255, 63, 0.88)';
  ctx.lineWidth = 1.5 * DPR;
  ctx.beginPath();
  ctx.moveTo(proj[0].x, proj[0].y);
  for (let i = 1; i < proj.length; i++) {
    ctx.lineTo(proj[i].x, proj[i].y);
  }
  ctx.closePath();
  ctx.stroke();
  
  // Draw normal vector pointing from the center of the plane
  const n_len = Math.sqrt(w1*w1 + w2*w2 + w3*w3);
  if (n_len > 0.01) {
    const center = [
      (corners[0][0] + corners[2][0]) / 2,
      (corners[0][1] + corners[2][1]) / 2,
      (corners[0][2] + corners[2][2]) / 2
    ];
    const normalEnd = [
      center[0] + (w1/n_len) * 0.3,
      center[1] + (w2/n_len) * 0.3,
      center[2] + (w3/n_len) * 0.3
    ];
    drawLine3D(
      [center[0]*S3D, center[1]*S3D, center[2]*S3D],
      [normalEnd[0]*S3D, normalEnd[1]*S3D, normalEnd[2]*S3D],
      COLORS.amber,
      2
    );
  }
}

function draw() {
  ctx.fillStyle = COLORS.night;
  ctx.fillRect(0, 0, W, H);
  
  // Draw Grid/Bounding Cube
  const b = S3D;
  const gridColor = COLORS.grid;
  
  // Bottom square
  drawLine3D([-b, -b, -b], [b, -b, -b], gridColor);
  drawLine3D([b, -b, -b], [b, -b, b], gridColor);
  drawLine3D([b, -b, b], [-b, -b, b], gridColor);
  drawLine3D([-b, -b, b], [-b, -b, -b], gridColor);
  
  // Top square
  drawLine3D([-b, b, -b], [b, b, -b], gridColor);
  drawLine3D([b, b, -b], [b, b, b], gridColor);
  drawLine3D([b, b, b], [-b, b, b], gridColor);
  drawLine3D([-b, b, b], [-b, b, -b], gridColor);
  
  // Vertical pillars
  drawLine3D([-b, -b, -b], [-b, b, -b], gridColor);
  drawLine3D([b, -b, -b], [b, b, -b], gridColor);
  drawLine3D([b, -b, b], [b, b, b], gridColor);
  drawLine3D([-b, -b, b], [-b, b, b], gridColor);
  
  // Coordinate Axes
  drawLine3D([0, 0, 0], [b*1.2, 0, 0], COLORS.amber, 1.5);
  drawLine3D([0, 0, 0], [0, b*1.2, 0], COLORS.cyan, 1.5);
  drawLine3D([0, 0, 0], [0, 0, b*1.2], COLORS.green, 1.5);
  const axisLabels = [
    { point: [b*1.28, 0, 0], text: 'x₁', color: COLORS.amber },
    { point: [0, b*1.28, 0], text: 'x₂', color: COLORS.cyan },
    { point: [0, 0, b*1.28], text: 'x₃', color: COLORS.green }
  ];
  ctx.font = `${12 * DPR}px Consolas, monospace`;
  ctx.textAlign = 'center';
  axisLabels.forEach(({ point, text, color }) => {
    const labelPoint = project(point);
    ctx.fillStyle = color;
    ctx.fillText(text, labelPoint.x, labelPoint.y);
  });
  
  // Draw Decision Plane
  drawDecisionPlane();
  
  // Sort points by depth so back points draw first
  const points = dataset.map((pt, idx) => {
    const pt3d = [pt.x[0]*S3D, pt.x[1]*S3D, pt.x[2]*S3D];
    const proj = project(pt3d);
    return { pt, idx, proj, pt3d };
  });
  points.sort((a, b) => b.proj.z - a.proj.z);
  
  // Draw Points
  points.forEach(item => {
    const isSelected = selectedPoint === item.pt;
    drawPoint3D(item.pt3d, item.pt.target, isSelected, predict(item.pt.x) === item.pt.target);
  });
}

// --- Event Handlers & Controls ---
function setupEventListeners() {
  w1Slider.addEventListener('input', (e) => { w1 = parseFloat(e.target.value); w1Out.value = w1.toFixed(2); updateMetrics(); draw(); });
  w2Slider.addEventListener('input', (e) => { w2 = parseFloat(e.target.value); w2Out.value = w2.toFixed(2); updateMetrics(); draw(); });
  w3Slider.addEventListener('input', (e) => { w3 = parseFloat(e.target.value); w3Out.value = w3.toFixed(2); updateMetrics(); draw(); });
  thetaSlider.addEventListener('input', (e) => { theta = parseFloat(e.target.value); thetaOut.value = theta.toFixed(2); updateMetrics(); draw(); });
  rateSlider.addEventListener('input', (e) => { eta = parseFloat(e.target.value); rateOut.value = eta.toFixed(2); updateMetrics(); });
  
  btnStep.addEventListener('click', () => { trainStep(); });
  btnEpoch.addEventListener('click', () => { trainEpoch(); });
  btnAuto.addEventListener('click', () => { toggleAutoTrain(); });
  btnReset.addEventListener('click', () => { resetAll(); });
  
  // Canvas Orbit Rotation Controls
  cv.addEventListener('mousedown', (e) => {
    dragging = true;
    px = e.clientX;
    py = e.clientY;
  });
  
  window.addEventListener('mouseup', () => {
    dragging = false;
  });
  
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    yaw += (e.clientX - px) * 0.007;
    pitch += (e.clientY - py) * 0.007;
    pitch = Math.max(-1.4, Math.min(1.4, pitch)); // lock poles
    px = e.clientX;
    py = e.clientY;
    draw();
  });
  
  // Mouse Wheel Zoom
  cv.addEventListener('wheel', (e) => {
    e.preventDefault();
    zoom += e.deltaY * -0.001;
    zoom = Math.max(0.4, Math.min(2.5, zoom));
    draw();
  }, { passive: false });
  
  // Click selection of points
  cv.addEventListener('click', (e) => {
    if (dragging) return;
    const rect = cv.getBoundingClientRect();
    const clickX = (e.clientX - rect.left) * DPR;
    const clickY = (e.clientY - rect.top) * DPR;
    
    let closestPt = null;
    let minDist = 30 * DPR; // tolerance threshold in pixels
    
    dataset.forEach(pt => {
      const pt3d = [pt.x[0]*S3D, pt.x[1]*S3D, pt.x[2]*S3D];
      const proj = project(pt3d);
      const dx = clickX - proj.x;
      const dy = clickY - proj.y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      if (dist < minDist) {
        minDist = dist;
        closestPt = pt;
      }
    });
    
    if (closestPt) {
      selectedPoint = closestPt;
      updateMetrics();
      draw();
    }
  });
  
  // Touch support for mobile
  cv.addEventListener('touchstart', (e) => {
    dragging = true;
    px = e.touches[0].clientX;
    py = e.touches[0].clientY;
  }, { passive: true });
  
  cv.addEventListener('touchmove', (e) => {
    if (!dragging) return;
    e.preventDefault();
    yaw += (e.touches[0].clientX - px) * 0.008;
    pitch += (e.touches[0].clientY - py) * 0.008;
    pitch = Math.max(-1.4, Math.min(1.4, pitch));
    px = e.touches[0].clientX;
    py = e.touches[0].clientY;
    draw();
  }, { passive: false });
  
  cv.addEventListener('touchend', () => {
    dragging = false;
  });

  cv.addEventListener('keydown', (e) => {
    let handled = true;
    if (e.key === 'ArrowLeft') yaw -= 0.12;
    else if (e.key === 'ArrowRight') yaw += 0.12;
    else if (e.key === 'ArrowUp') pitch = Math.max(-1.4, pitch - 0.1);
    else if (e.key === 'ArrowDown') pitch = Math.min(1.4, pitch + 0.1);
    else if (e.key === '+' || e.key === '=') zoom = Math.min(2.5, zoom + 0.1);
    else if (e.key === '-' || e.key === '_') zoom = Math.max(0.4, zoom - 0.1);
    else if (e.key === ' ' || e.key === 'Enter') trainStep();
    else handled = false;
    if (handled) {
      e.preventDefault();
      draw();
    }
  });
}

// --- Init ---
setupEventListeners();
if ('ResizeObserver' in window) {
  new ResizeObserver(() => { resize(); draw(); }).observe(cv.parentElement);
}
updateSliders();
updateMetrics();
draw();
appendLog("מעבדת ALMA Perceptron 3D מוכנה. לחצו על 'צעד אימון אחד' או 'הפעל אימון רציף' כדי ללמוד.", 'correct');

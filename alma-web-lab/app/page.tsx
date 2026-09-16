"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Mode = "science" | "fantasy";
type Params = { dynamicity: number; noise: number; samples: number; seed: number };
type Point = { actual: number; vanilla: number; rich: number };
type Result = {
  vanilla: { train: number; test: number; ci: number; params: number };
  rich: { train: number; test: number; ci: number; params: number };
  improvement: number;
  verdict: "rich" | "vanilla" | "tie";
  points: Point[];
};

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function gaussian(rand: () => number) {
  const u = Math.max(rand(), 1e-12);
  const v = Math.max(rand(), 1e-12);
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function solve(matrix: number[][], vector: number[]) {
  const n = vector.length;
  const a = matrix.map((row, i) => [...row, vector[i]]);
  for (let col = 0; col < n; col++) {
    let pivot = col;
    for (let row = col + 1; row < n; row++) {
      if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row;
    }
    [a[col], a[pivot]] = [a[pivot], a[col]];
    const divisor = Math.abs(a[col][col]) < 1e-12 ? 1e-12 : a[col][col];
    for (let j = col; j <= n; j++) a[col][j] /= divisor;
    for (let row = 0; row < n; row++) {
      if (row === col) continue;
      const factor = a[row][col];
      for (let j = col; j <= n; j++) a[row][j] -= factor * a[col][j];
    }
  }
  return a.map((row) => row[n]);
}

function fit(xs: number[][], ys: number[], ridge = 1e-5) {
  const p = xs[0].length;
  const xtx = Array.from({ length: p }, () => Array(p).fill(0));
  const xty = Array(p).fill(0);
  for (let i = 0; i < xs.length; i++) {
    for (let j = 0; j < p; j++) {
      xty[j] += xs[i][j] * ys[i];
      for (let k = 0; k < p; k++) xtx[j][k] += xs[i][j] * xs[i][k];
    }
  }
  for (let i = 0; i < p; i++) xtx[i][i] += ridge;
  return solve(xtx, xty);
}

function dot(a: number[], b: number[]) {
  return a.reduce((sum, value, i) => sum + value * b[i], 0);
}

function mean(values: number[]) {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function mse(actual: number[], predicted: number[]) {
  return mean(actual.map((value, i) => (value - predicted[i]) ** 2));
}

function features(x: number, recency: number, distance: number, attention: number) {
  const proximity = 1 - distance;
  return {
    vanilla: [x],
    rich: [x, x * recency, x * proximity, x * attention, x * recency * attention],
  };
}

function oneRun(params: Params, run: number) {
  const rand = mulberry32(params.seed + run * 7919);
  const rows = Array.from({ length: params.samples }, () => {
    const x = rand() * 2 - 1;
    const recency = rand();
    const distance = rand();
    const attention = rand();
    const contextual =
      0.3 * recency + 0.24 * (1 - distance) + 0.28 * attention +
      0.22 * recency * attention - 0.26;
    const trueWeight = 0.58 + params.dynamicity * contextual;
    const y = x * trueWeight + gaussian(rand) * params.noise;
    return { x, recency, distance, attention, y };
  });
  const cut = Math.floor(rows.length * 0.7);
  const train = rows.slice(0, cut);
  const test = rows.slice(cut);
  const xvTrain = train.map((r) => features(r.x, r.recency, r.distance, r.attention).vanilla);
  const xrTrain = train.map((r) => features(r.x, r.recency, r.distance, r.attention).rich);
  const yTrain = train.map((r) => r.y);
  const wv = fit(xvTrain, yTrain);
  const wr = fit(xrTrain, yTrain, 0.001);
  const predictV = (r: (typeof rows)[number]) => dot(features(r.x, r.recency, r.distance, r.attention).vanilla, wv);
  const predictR = (r: (typeof rows)[number]) => dot(features(r.x, r.recency, r.distance, r.attention).rich, wr);
  return {
    vanillaTrain: mse(yTrain, train.map(predictV)),
    richTrain: mse(yTrain, train.map(predictR)),
    vanillaTest: mse(test.map((r) => r.y), test.map(predictV)),
    richTest: mse(test.map((r) => r.y), test.map(predictR)),
    points: test.slice(0, 34).map((r) => ({ actual: r.y, vanilla: predictV(r), rich: predictR(r) })),
  };
}

function summarize(params: Params): Result {
  const runs = Array.from({ length: 16 }, (_, i) => oneRun(params, i));
  const vanillaTests = runs.map((r) => r.vanillaTest);
  const richTests = runs.map((r) => r.richTest);
  const ci = (values: number[]) => {
    const m = mean(values);
    const variance = mean(values.map((v) => (v - m) ** 2));
    return 1.96 * Math.sqrt(variance / values.length);
  };
  const vanilla = mean(vanillaTests);
  const rich = mean(richTests);
  const improvement = vanilla > 0 ? ((vanilla - rich) / vanilla) * 100 : 0;
  const threshold = Math.max(0.0002, Math.min(vanilla, rich) * 0.02);
  return {
    vanilla: { train: mean(runs.map((r) => r.vanillaTrain)), test: vanilla, ci: ci(vanillaTests), params: 1 },
    rich: { train: mean(runs.map((r) => r.richTrain)), test: rich, ci: ci(richTests), params: 5 },
    improvement,
    verdict: rich + threshold < vanilla ? "rich" : vanilla + threshold < rich ? "vanilla" : "tie",
    points: runs[0].points,
  };
}

function stableHash(params: Params) {
  const text = `${params.dynamicity}|${params.noise}|${params.samples}|${params.seed}`;
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return `AL-${(h >>> 0).toString(16).toUpperCase().padStart(8, "0")}`;
}

function LoomCanvas({ mode, pulse, dynamicity }: { mode: Mode; pulse: number; dynamicity: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frame = 0;
    let raf = 0;
    const labels = mode === "science"
      ? ["אות", "זמן", "מרחב", "גוף", "קשר", "תוצאה"]
      : ["ניצוץ", "עבר", "מקום", "דופק", "זיקה", "גורל"];
    const nodes = [
      [0.1, 0.5], [0.27, 0.18], [0.29, 0.8], [0.52, 0.82], [0.56, 0.42], [0.86, 0.42],
    ];
    const edges = [[0, 4], [1, 4], [2, 4], [3, 4], [4, 5], [1, 3], [2, 3]];
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const draw = () => {
      resize();
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      context.clearRect(0, 0, w, h);
      const time = reduced ? 0.5 : ((frame++ + pulse * 19) % 240) / 240;
      for (let i = 0; i < edges.length; i++) {
        const [a, b] = edges[i];
        const [x1, y1] = nodes[a];
        const [x2, y2] = nodes[b];
        context.beginPath();
        context.moveTo(x1 * w, y1 * h);
        context.quadraticCurveTo(((x1 + x2) / 2) * w, ((y1 + y2) / 2) * h - 18, x2 * w, y2 * h);
        context.strokeStyle = i < 5 ? "rgba(110,231,204,.42)" : "rgba(135,150,255,.24)";
        context.lineWidth = 1 + (i < 5 ? dynamicity * 2.4 : 0.6);
        context.stroke();
        if (i < 5) {
          const t = (time + i * 0.18) % 1;
          const px = (x1 + (x2 - x1) * t) * w;
          const py = (y1 + (y2 - y1) * t - Math.sin(Math.PI * t) * 0.055) * h;
          context.beginPath();
          context.arc(px, py, 3.2, 0, Math.PI * 2);
          context.fillStyle = mode === "science" ? "#ffc857" : "#c9a7ff";
          context.shadowColor = context.fillStyle;
          context.shadowBlur = 12;
          context.fill();
          context.shadowBlur = 0;
        }
      }
      nodes.forEach(([x, y], i) => {
        context.beginPath();
        context.arc(x * w, y * h, i === 4 ? 23 : 16, 0, Math.PI * 2);
        context.fillStyle = i === 4 ? "#dffcf4" : "#0d2923";
        context.fill();
        context.strokeStyle = i === 4 ? "#6ee7cc" : "rgba(223,252,244,.55)";
        context.lineWidth = 1.3;
        context.stroke();
        context.fillStyle = i === 4 ? "#071310" : "#effcf8";
        context.font = `600 ${i === 4 ? 13 : 11}px system-ui`;
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText(labels[i], x * w, y * h);
      });
      if (!reduced) raf = requestAnimationFrame(draw);
    };
    draw();
    window.addEventListener("resize", draw);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", draw);
    };
  }, [mode, pulse, dynamicity]);

  return <canvas ref={ref} className="loom-canvas" aria-label="מפת הקשרים של הניסוי" />;
}

function Metric({ label, value, ci, accent }: { label: string; value: number; ci: number; accent: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong style={{ color: accent }}>{value.toFixed(4)}</strong>
      <small>± {ci.toFixed(4)} · 95% CI</small>
    </div>
  );
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("science");
  const [params, setParams] = useState<Params>({ dynamicity: 0.72, noise: 0.08, samples: 240, seed: 36 });
  const [committed, setCommitted] = useState(params);
  const [pulse, setPulse] = useState(0);
  const [saved, setSaved] = useState(0);
  const result = useMemo(() => summarize(committed), [committed]);
  const hash = stableHash(committed);
  const isFalsified = committed.dynamicity > 0.55 && result.improvement < 10;
  const modeCopy = mode === "science" ? {
    eyebrow: "ALMA EMPIRICAL LOOM / ניסוי 001",
    title: "האם קשר הוא יותר ממשקל?",
    run: "הרץ 16 חזרות",
    relation: "קשר מרחב־זמן",
    vanilla: "משקל ונילה",
  } : {
    eyebrow: "ALMA WONDERLOOM / מארג 001",
    title: "האם זיקה היא יותר ממספר?",
    run: "שחרר 16 ניצוצות",
    relation: "זיקת זמן־מקום",
    vanilla: "חוט יחיד",
  };

  const run = () => {
    setCommitted({ ...params });
    setPulse((p) => p + 1);
  };

  const save = () => {
    const record = { id: hash, timestamp: new Date().toISOString(), params: committed, result };
    const records = JSON.parse(localStorage.getItem("alma-lab-runs") || "[]") as object[];
    localStorage.setItem("alma-lab-runs", JSON.stringify([record, ...records].slice(0, 50)));
    setSaved(records.length + 1);
  };

  const exportRun = () => {
    const blob = new Blob([JSON.stringify({ id: hash, params: committed, result }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${hash}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className={`lab ${mode}`} dir="rtl">
      <header className="topbar">
        <div className="mark" aria-label="ALMA Lab"><i /> עלמה <span>LAB</span></div>
        <div className="mode-switch" role="group" aria-label="מצב תצוגה">
          <button className={mode === "science" ? "active" : ""} onClick={() => setMode("science")}>מדעי</button>
          <button className={mode === "fantasy" ? "active" : ""} onClick={() => setMode("fantasy")}>פנטזיה</button>
        </div>
        <div className="run-id" dir="ltr">{hash}</div>
      </header>

      <section className="thesis">
        <p className="eyebrow">{modeCopy.eyebrow}</p>
        <h1>{modeCopy.title}</h1>
        <p className="lede">
          אותו מידע, אותו seed ואותו holdout. מודל אחד מקבל מספר יחיד; השני מקבל זמן, מרחק,
          קשב ואינטראקציות. התוצאה יכולה לתמוך ברעיון — או להפיל אותו.
        </p>
        <div className="truth-strip">
          <b>גבול הכנות:</b> זה benchmark סינתטי לבדיקת מנגנון. הוא אינו הוכחה שהמוח עובד כך.
        </div>
      </section>

      <section className="workbench">
        <aside className="controls panel">
          <div className="panel-head"><span>פרוטוקול</span><b>01</b></div>
          <label>
            <span>דינמיות של היחס <output>{params.dynamicity.toFixed(2)}</output></span>
            <input type="range" min="0" max="1" step="0.01" value={params.dynamicity}
              onChange={(e) => setParams({ ...params, dynamicity: Number(e.target.value) })} />
            <small>0 = העולם באמת סקלרי · 1 = היחס תלוי מאוד בהקשר</small>
          </label>
          <label>
            <span>רעש מדידה <output>{params.noise.toFixed(2)}</output></span>
            <input type="range" min="0" max="0.35" step="0.01" value={params.noise}
              onChange={(e) => setParams({ ...params, noise: Number(e.target.value) })} />
          </label>
          <label>
            <span>דגימות <output>{params.samples}</output></span>
            <input type="range" min="60" max="600" step="20" value={params.samples}
              onChange={(e) => setParams({ ...params, samples: Number(e.target.value) })} />
          </label>
          <label>
            <span>Seed</span>
            <input className="seed" type="number" value={params.seed}
              onChange={(e) => setParams({ ...params, seed: Number(e.target.value) || 1 })} />
          </label>
          <button className="run-button" onClick={run}>{modeCopy.run}<span>↗</span></button>
          <p className="protocol-note">70% אימון · 30% בדיקה · 16 seeds עוקבים · Ridge קבוע</p>
        </aside>

        <section className="loom panel">
          <div className="panel-head"><span>המארג הסיבתי</span><b>LIVE</b></div>
          <LoomCanvas mode={mode} pulse={pulse} dynamicity={committed.dynamicity} />
          <div className="loom-legend">
            <span><i className="dot teal" /> קלט שנצפה</span>
            <span><i className="dot gold" /> השלכה זמנית</span>
            <span><i className="dot violet" /> קשר עקיף</span>
          </div>
          <p className="invariant">החלפת מדעי ↔ פנטזיה משנה שפה וחומר בלבד. הנתונים והתוצאה נשארים זהים.</p>
        </section>

        <aside className="results panel">
          <div className="panel-head"><span>תוצאת holdout</span><b>{result.verdict === "tie" ? "DRAW" : "DECIDED"}</b></div>
          <div className={`verdict ${result.verdict}`}>
            <small>המוביל כרגע</small>
            <strong>{result.verdict === "rich" ? modeCopy.relation : result.verdict === "vanilla" ? modeCopy.vanilla : "אין הכרעה"}</strong>
            <span>{Math.abs(result.improvement).toFixed(1)}% {result.improvement >= 0 ? "פחות שגיאה" : "יותר שגיאה למודל העשיר"}</span>
          </div>
          <div className="metrics">
            <Metric label={`${modeCopy.vanilla} · 1 פרמטר`} value={result.vanilla.test} ci={result.vanilla.ci} accent="#ffc857" />
            <Metric label={`${modeCopy.relation} · 5 פרמטרים`} value={result.rich.test} ci={result.rich.ci} accent="#6ee7cc" />
          </div>
          <div className={`falsification ${isFalsified ? "failed" : ""}`}>
            <b>{isFalsified ? "ההשערה לא עמדה בקריטריון" : "קריטריון ההפרכה נשמר"}</b>
            <p>בדינמיות מעל 0.55 נדרוש לפחות 10% שיפור ב־holdout. אחרת לא נטען שהמורכבות מוצדקת.</p>
          </div>
          <div className="result-actions">
            <button onClick={save}>שמור מקומית{saved ? ` · ${saved}` : ""}</button>
            <button onClick={exportRun}>ייצא JSON</button>
          </div>
        </aside>
      </section>

      <section className="comparison panel">
        <div className="panel-head"><span>ביקורת ונילה</span><b>FAIR TEST</b></div>
        <div className="compare-grid">
          <article>
            <p>H₀ · השערת האפס</p>
            <h2>מספר אחד מספיק.</h2>
            <span>אם העולם יציב, מודל פשוט אמור להשתוות או לנצח בגלל פחות דרגות חופש.</span>
          </article>
          <article className="rich-card">
            <p>H₁ · השערת עלמה</p>
            <h2>יחס משתנה עם זמן, מקום וגוף.</h2>
            <span>המורכבות מקבלת זכות קיום רק אם היא משפרת הכללה על מידע שלא ראתה.</span>
          </article>
          <div className="error-bars" aria-label="השוואת שגיאות">
            <div><span>ונילה</span><i style={{ width: `${Math.min(100, result.vanilla.test * 900)}%` }} /></div>
            <div><span>עשיר</span><i className="rich-bar" style={{ width: `${Math.min(100, result.rich.test * 900)}%` }} /></div>
            <small>אורך הפס = MSE נמוך עדיף · סקלה זהה</small>
          </div>
        </div>
      </section>

      <section className="lab-book">
        <div>
          <p className="eyebrow">מחברת המעבדה</p>
          <h2>מה נבדוק אחרי שהניסוי הזה שורד?</h2>
        </div>
        <ol>
          <li><b>002</b><span>זיכרון מהיר/איטי מול משקל יחיד</span><em>מתוכנן</em></li>
          <li><b>003</b><span>JEPA לטנטי מול חיזוי אוטורגרסיבי</span><em>מתוכנן</em></li>
          <li><b>004</b><span>שעון וגוף מול position encoding בלבד</span><em>מתוכנן</em></li>
        </ol>
      </section>

      <footer>
        <span>ALMA LAB · evidence before mythology</span>
        <span>כל תוצאה ניתנת לשחזור לפי מזהה הריצה</span>
      </footer>
    </main>
  );
}

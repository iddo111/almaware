const state = {
  ants: [],
  judges: [],
  norms: [],
  selected: null,
  listening: false,
  busy: false,
  sound: true,
  recognition: null,
};

const els = {
  antNodes: document.querySelector("#antNodes"),
  chatTitle: document.querySelector("#chatTitle"),
  antTemperament: document.querySelector("#antTemperament"),
  portrait: document.querySelector("#portrait"),
  transcript: document.querySelector("#transcript"),
  emptyState: document.querySelector("#emptyState"),
  messageInput: document.querySelector("#messageInput"),
  sendButton: document.querySelector("#sendButton"),
  micButton: document.querySelector("#micButton"),
  voiceStatus: document.querySelector("#voiceStatus"),
  soundToggle: document.querySelector("#soundToggle"),
  statusDot: document.querySelector("#statusDot"),
  systemStatus: document.querySelector("#systemStatus"),
  modelName: document.querySelector("#modelName"),
  judgeRail: document.querySelector("#judgeRail"),
  normsDialog: document.querySelector("#normsDialog"),
  normsList: document.querySelector("#normsList"),
  showNorms: document.querySelector("#showNorms"),
  closeNorms: document.querySelector("#closeNorms"),
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.kind = payload.kind || "request_failed";
    throw error;
  }
  return payload;
}

function renderAnts() {
  els.antNodes.replaceChildren();
  for (const ant of state.ants) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ant-node";
    button.style.left = `${ant.x}%`;
    button.style.top = `${ant.y}%`;
    button.style.setProperty("--ant-color", ant.color);
    button.dataset.antId = ant.id;
    button.setAttribute("aria-label", `${ant.name}, ${ant.role}`);
    button.innerHTML = `
      <span class="mini-ant" aria-hidden="true"><span class="body"></span></span>
      <span class="name">${ant.name}</span>
      <span class="role">${ant.role}</span>
    `;
    button.addEventListener("click", () => selectAnt(ant.id));
    els.antNodes.append(button);
  }
}

function renderJudges(results = null) {
  const source = results || state.judges;
  els.judgeRail.replaceChildren();
  for (const judge of source) {
    const item = document.createElement("div");
    item.className = "judge";
    const score = Number.isFinite(judge.score)
      ? `<span class="score">${judge.score}</span>`
      : "";
    item.innerHTML = `<b>${judge.name}</b>${score}<span>${judge.verdict || judge.mission || "ממתין לתשובה"}</span>`;
    els.judgeRail.append(item);
  }
}

async function selectAnt(antId) {
  const ant = state.ants.find((candidate) => candidate.id === antId);
  if (!ant) return;
  state.selected = ant;
  document.querySelectorAll(".ant-node").forEach((node) => {
    node.classList.toggle("selected", node.dataset.antId === antId);
  });
  els.chatTitle.textContent = `${ant.name} · ${ant.role}`;
  els.antTemperament.textContent = ant.temperament;
  els.portrait.style.background = ant.color;
  els.messageInput.placeholder = `כתוב ל${ant.name}…`;
  await loadHistory();
}

function addMessage(speaker, text, options = {}) {
  els.emptyState?.remove();
  const message = document.createElement("div");
  message.className = `message ${speaker}${options.error ? " error" : ""}`;
  const label = speaker === "human" ? "אתה" : state.selected?.name || "נמלה";
  const speakerLabel = document.createElement("span");
  speakerLabel.className = "speaker";
  speakerLabel.textContent = options.error ? "הקן" : label;
  const body = document.createElement("span");
  body.textContent = text;
  message.append(speakerLabel, body);
  els.transcript.append(message);
  els.transcript.scrollTop = els.transcript.scrollHeight;
  return message;
}

async function loadHistory() {
  els.transcript.replaceChildren();
  try {
    const payload = await request(`/api/history?ant_id=${encodeURIComponent(state.selected.id)}`);
    if (!payload.messages.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.id = "emptyState";
      empty.innerHTML = `
        <span class="trail-mark" aria-hidden="true">· · · ⟡</span>
        <h3>${state.selected.name} מקשיב${state.selected.name.endsWith("ה") ? "ה" : ""}</h3>
        <p>לחץ על כפתור הדיבור ואמור משהו בעברית. אפשר גם להקליד.</p>
      `;
      els.transcript.append(empty);
    } else {
      for (const item of payload.messages) {
        addMessage(item.speaker, item.text);
      }
    }
  } catch (error) {
    addMessage("ant", `לא ניתן לטעון זיכרון: ${error.message}`, { error: true });
  }
}

function setBusy(value) {
  state.busy = value;
  els.sendButton.disabled = value;
  els.micButton.disabled = value;
}

async function sendMessage(text = els.messageInput.value) {
  const clean = String(text || "").trim();
  if (!clean || !state.selected || state.busy) return;
  els.messageInput.value = "";
  addMessage("human", clean);
  const typing = document.createElement("div");
  typing.className = "typing";
  typing.textContent = `${state.selected.name} קורא את שביל הריח…`;
  els.transcript.append(typing);
  els.transcript.scrollTop = els.transcript.scrollHeight;
  setBusy(true);
  try {
    const payload = await request("/api/chat", {
      method: "POST",
      body: JSON.stringify({ ant_id: state.selected.id, message: clean }),
    });
    typing.remove();
    addMessage("ant", payload.reply);
    renderJudges(payload.judges);
    if (state.sound) speak(payload.reply);
  } catch (error) {
    typing.remove();
    addMessage("ant", error.message, { error: true });
    if (error.kind === "model_unavailable") {
      els.statusDot.className = "status-dot blocked";
      els.systemStatus.textContent = "המוח המקומי אינו זמין";
    }
  } finally {
    setBusy(false);
    els.messageInput.focus();
  }
}

function speak(text) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "he-IL";
  utterance.rate = 0.96;
  utterance.pitch = 1.08;
  const voices = window.speechSynthesis.getVoices();
  const hebrew = voices.find((voice) => voice.lang?.toLowerCase().startsWith("he"));
  if (hebrew) utterance.voice = hebrew;
  window.speechSynthesis.speak(utterance);
}

function configureSpeechRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    els.micButton.disabled = true;
    els.voiceStatus.textContent = "הדפדפן הזה לא מספק זיהוי דיבור; ההקלדה פעילה";
    return;
  }
  const recognition = new Recognition();
  recognition.lang = "he-IL";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    state.listening = true;
    els.micButton.classList.add("listening");
    els.micButton.querySelector(".mic-label").textContent = "מקשיב…";
    els.voiceStatus.textContent = `דבר עכשיו אל ${state.selected?.name || "הנמלה"}`;
  };
  recognition.onresult = (event) => {
    let finalText = "";
    let interimText = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const text = event.results[i][0].transcript;
      if (event.results[i].isFinal) finalText += text;
      else interimText += text;
    }
    els.messageInput.value = finalText || interimText;
    if (finalText.trim()) sendMessage(finalText);
  };
  recognition.onerror = (event) => {
    const messages = {
      "not-allowed": "נדרשת הרשאת מיקרופון לדף המקומי",
      "no-speech": "לא זוהה דיבור; לחץ ונסה שוב",
      network: "שירות זיהוי הדיבור של הדפדפן לא זמין",
    };
    els.voiceStatus.textContent = messages[event.error] || `שגיאת מיקרופון: ${event.error}`;
  };
  recognition.onend = () => {
    state.listening = false;
    els.micButton.classList.remove("listening");
    els.micButton.querySelector(".mic-label").textContent = "דבר עם הנמלה";
    if (!els.voiceStatus.textContent.includes("שגיאת")) {
      els.voiceStatus.textContent = "לחיצה אחת מתחילה האזנה בעברית";
    }
  };
  state.recognition = recognition;
}

async function checkHealth() {
  try {
    const payload = await request("/api/health");
    const ready = payload.model.reachable && payload.model.model_loaded;
    els.statusDot.className = `status-dot ${ready ? "ready" : "blocked"}`;
    els.systemStatus.textContent = ready ? "גשר הדמו מוכן · המוח מאפס טרם חובר" : "גשר הדמו טרם נטען";
    els.modelName.textContent = payload.model.model || "";
  } catch (error) {
    els.statusDot.className = "status-dot blocked";
    els.systemStatus.textContent = "שירות הקן אינו זמין";
  }
}

async function boot() {
  try {
    const colony = await request("/api/colony");
    state.ants = colony.ants;
    state.judges = colony.judges;
    state.norms = colony.norms;
    renderAnts();
    renderJudges();
    els.normsList.replaceChildren(
      ...state.norms.map((norm) => {
        const item = document.createElement("li");
        item.textContent = norm;
        return item;
      }),
    );
    await selectAnt(state.ants[0].id);
  } catch (error) {
    addMessage("ant", `הקן לא עלה: ${error.message}`, { error: true });
  }
  configureSpeechRecognition();
  await checkHealth();
}

els.sendButton.addEventListener("click", () => sendMessage());
els.messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
els.micButton.addEventListener("click", () => {
  if (!state.recognition || state.busy) return;
  if (state.listening) state.recognition.stop();
  else state.recognition.start();
});
els.soundToggle.addEventListener("click", () => {
  state.sound = !state.sound;
  els.soundToggle.textContent = state.sound ? "קול פעיל" : "קול כבוי";
  els.soundToggle.setAttribute("aria-pressed", String(state.sound));
  if (!state.sound && "speechSynthesis" in window) window.speechSynthesis.cancel();
});
els.showNorms.addEventListener("click", () => els.normsDialog.showModal());
els.closeNorms.addEventListener("click", () => els.normsDialog.close());

boot();

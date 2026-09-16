const state = {
  messages: [],
  busy: false,
  accessToken: sessionStorage.getItem("almaAccessToken") || ""
};

const ui = {
  rail: document.querySelector(".cloud-rail"),
  intro: document.querySelector("#intro"),
  messages: document.querySelector("#messages"),
  composer: document.querySelector("#composer"),
  prompt: document.querySelector("#prompt"),
  sendButton: document.querySelector("#sendButton"),
  keyButton: document.querySelector("#keyButton"),
  keyDialog: document.querySelector("#keyDialog"),
  keyForm: document.querySelector("#keyForm"),
  dialogClose: document.querySelector("#dialogClose"),
  accessToken: document.querySelector("#accessToken"),
  statusDot: document.querySelector("#statusDot"),
  truthLabel: document.querySelector("#truthLabel"),
  truthValue: document.querySelector("#truthValue"),
  truthDetail: document.querySelector("#truthDetail")
};

function setTruth(kind, value, detail) {
  ui.statusDot.className = `status-dot ${kind}`;
  ui.truthValue.className = kind;
  ui.truthValue.textContent = value;
  ui.truthDetail.textContent = detail;
}

function addMessage(role, content = "") {
  ui.intro.classList.add("compact");
  const element = document.createElement("div");
  element.className = `message ${role}`;
  const label = document.createElement("span");
  label.className = "role";
  label.textContent = role === "user" ? "YOU" : role === "error" ? "CLOUD ERROR" : "ALMA · 120B";
  const text = document.createElement("span");
  text.className = "content";
  text.textContent = content;
  element.append(label, text);
  ui.messages.append(element);
  ui.messages.scrollTop = ui.messages.scrollHeight;
  return text;
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    const status = await response.json();
    if (!status.ok) {
      setTruth("bad", "לא מוגדר", "חסרים secrets בענן");
      return;
    }
    if (status.generationVerified) {
      setTruth("good", "120B נשמע", `אומת ${new Date(status.lastGenerationAt).toLocaleTimeString("he-IL")}`);
    } else {
      setTruth("", "המסלול מוכן", "ממתין לתשובה הראשונה");
    }
  } catch {
    setTruth("bad", "הענן לא זמין", "לא התקבלה תשובת status");
  }
}

function parseSseEvent(line) {
  if (!line.startsWith("data:") || line.includes("[DONE]")) return "";
  try {
    const event = JSON.parse(line.slice(5).trim());
    return String(event?.choices?.[0]?.delta?.content || "");
  } catch {
    return "";
  }
}

async function streamChat() {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Alma-Access": state.accessToken },
    body: JSON.stringify({ messages: state.messages, temperature: 0.35 })
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    if (response.status === 401) ui.keyDialog.showModal();
    throw new Error(detail.error || `Cloud returned HTTP ${response.status}`);
  }
  if (response.headers.get("X-Alma-Local-Fallback") !== "false") {
    throw new Error("Cloud truth header is missing; response rejected");
  }

  const output = addMessage("assistant");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const delta = parseSseEvent(line);
      if (!delta) continue;
      full += delta;
      output.textContent = full;
      ui.messages.scrollTop = ui.messages.scrollHeight;
    }
  }
  if (!full.trim()) throw new Error("GroqCloud returned an empty generation");
  state.messages.push({ role: "assistant", content: full });
}

async function send(event) {
  event.preventDefault();
  if (state.busy) return;
  const prompt = ui.prompt.value.trim();
  if (!prompt) return;
  if (!state.accessToken) {
    ui.keyDialog.showModal();
    return;
  }

  state.busy = true;
  ui.sendButton.disabled = true;
  ui.rail.classList.add("streaming");
  state.messages.push({ role: "user", content: prompt });
  addMessage("user", prompt);
  ui.prompt.value = "";
  setTruth("", "שומע בענן", "GroqCloud מייצר עכשיו");
  try {
    await streamChat();
    setTruth("good", "120B ענה", "התקבלה תשובה לא ריקה");
    setTimeout(refreshStatus, 700);
  } catch (error) {
    addMessage("error", error.message);
    setTruth("bad", "הבקשה נכשלה", error.message);
  } finally {
    state.busy = false;
    ui.sendButton.disabled = false;
    ui.rail.classList.remove("streaming");
    ui.prompt.focus();
  }
}

ui.composer.addEventListener("submit", send);
ui.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    ui.composer.requestSubmit();
  }
});
ui.keyButton.addEventListener("click", () => {
  ui.accessToken.value = state.accessToken;
  ui.keyDialog.showModal();
});
ui.dialogClose.addEventListener("click", () => ui.keyDialog.close());
ui.keyForm.addEventListener("submit", (event) => {
  if (event.submitter?.value !== "save") return;
  event.preventDefault();
  state.accessToken = ui.accessToken.value.trim();
  if (!state.accessToken) return;
  sessionStorage.setItem("almaAccessToken", state.accessToken);
  ui.keyDialog.close();
  ui.prompt.focus();
});

refreshStatus();
if (!state.accessToken) setTimeout(() => ui.keyDialog.showModal(), 450);

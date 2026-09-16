const $ = (selector) => document.querySelector(selector);

const musicState = {
  peer: null,
  sessionId: null,
  statsTimer: null,
  lastBytes: 0,
  lastStatsAt: 0
};

const setMusicHealth = (text, state = "idle") => {
  $("#musicHealth").textContent = text;
  $("#musicDot").className = `status-dot ${state === "ok" ? "ok" : state === "bad" ? "bad" : ""}`;
};

const musicLog = (message) => {
  const log = $("#musicLog");
  const stamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  log.textContent += `\n[${stamp}] ${message}`;
  log.scrollTop = log.scrollHeight;
};

const pairingToken = () => $("#pairingToken").value.trim();

const musicFetch = (path, init = {}) => {
  const token = pairingToken();
  if (token.length < 8) throw new Error("הזן קוד צימוד מהמחשב · Enter the PC pairing token");
  return fetch(path, {
    ...init,
    headers: {
      ...(init.headers || {}),
      "X-A70-Pairing-Token": token
    }
  });
};

const readJsonResponse = async (response) => {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
};

async function checkMusicRelay() {
  setMusicHealth("בודק ממסר מקומי… · Checking local relay…");
  try {
    const payload = await readJsonResponse(await musicFetch("/api/music/health", { cache: "no-store" }));
    const device = payload.device || payload.backend || "WASAPI";
    setMusicHealth(`${payload.codec || "Opus"} · ${device}`, payload.ready ? "ok" : "bad");
    musicLog(payload.ready ? "PC relay authenticated and ready." : "PC relay answered but capture is not ready.");
    return payload;
  } catch (error) {
    setMusicHealth(error.message, "bad");
    musicLog(`Check failed: ${error.message}`);
    throw error;
  }
}

const waitForIceGathering = (peer, timeoutMs = 6000) => new Promise((resolve, reject) => {
  if (peer.iceGatheringState === "complete") return resolve();
  const timeout = setTimeout(() => {
    peer.removeEventListener("icegatheringstatechange", changed);
    reject(new Error("Local ICE gathering timed out"));
  }, timeoutMs);
  function changed() {
    if (peer.iceGatheringState !== "complete") return;
    clearTimeout(timeout);
    peer.removeEventListener("icegatheringstatechange", changed);
    resolve();
  }
  peer.addEventListener("icegatheringstatechange", changed);
});

const preferOpus = (transceiver) => {
  if (!transceiver.setCodecPreferences || !window.RTCRtpReceiver?.getCapabilities) return;
  const codecs = RTCRtpReceiver.getCapabilities("audio")?.codecs || [];
  const opus = codecs.filter((codec) => codec.mimeType.toLowerCase() === "audio/opus");
  const remaining = codecs.filter((codec) => codec.mimeType.toLowerCase() !== "audio/opus");
  if (opus.length) transceiver.setCodecPreferences([...opus, ...remaining]);
};

const directHostOffer = (sdp) => {
  let kept = 0;
  const lines = sdp.replaceAll("\r\n", "\n").split("\n").filter((line) => {
    if (!line.startsWith("a=candidate:")) return true;
    const parts = line.slice("a=candidate:".length).trim().split(/\s+/);
    const typeAt = parts.indexOf("typ");
    const type = typeAt >= 0 ? parts[typeAt + 1]?.toLowerCase() : "";
    const address = (parts[4] || "").toLowerCase();
    const tailscaleV4 = /^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\./.test(address);
    const tailscaleV6 = address.startsWith("fd7a:115c:a1e0:");
    const allowed = type === "host" && !tailscaleV4 && !tailscaleV6;
    if (allowed) kept += 1;
    return allowed;
  });
  if (!kept) throw new Error("No direct local ICE candidate was gathered");
  return lines.join("\r\n");
};

const clearMusicStats = () => {
  for (const id of ["musicCodec", "musicRate", "musicLoss", "musicJitter", "musicRoute"]) $("#" + id).textContent = "—";
  musicState.lastBytes = 0;
  musicState.lastStatsAt = 0;
};

async function updateMusicStats() {
  if (!musicState.peer) return;
  const reports = await musicState.peer.getStats();
  const inbound = [...reports.values()].find((item) => item.type === "inbound-rtp" && (item.kind === "audio" || item.mediaType === "audio"));
  if (inbound) {
    const codec = reports.get(inbound.codecId);
    $("#musicCodec").textContent = codec?.mimeType?.replace("audio/", "") || "Opus";
    $("#musicLoss").textContent = String(inbound.packetsLost ?? 0);
    $("#musicJitter").textContent = Number.isFinite(inbound.jitter) ? `${Math.round(inbound.jitter * 1000)} ms` : "—";
    const now = performance.now();
    if (musicState.lastStatsAt && inbound.bytesReceived >= musicState.lastBytes) {
      const kbps = ((inbound.bytesReceived - musicState.lastBytes) * 8) / (now - musicState.lastStatsAt);
      $("#musicRate").textContent = `${kbps.toFixed(1)} kb/s`;
    }
    musicState.lastBytes = inbound.bytesReceived;
    musicState.lastStatsAt = now;
  }

  const transport = [...reports.values()].find((item) => item.type === "transport" && item.selectedCandidatePairId);
  const pair = transport ? reports.get(transport.selectedCandidatePairId) : [...reports.values()].find((item) => item.type === "candidate-pair" && item.nominated && item.state === "succeeded");
  if (pair) {
    const local = reports.get(pair.localCandidateId);
    const remote = reports.get(pair.remoteCandidateId);
    const localRoute = local?.networkType || local?.candidateType || "local";
    const remoteRoute = remote?.candidateType || "host";
    $("#musicRoute").textContent = `${localRoute} → ${remoteRoute}`;
  }
}

async function stopMusicRelay(notifyServer = true) {
  clearInterval(musicState.statsTimer);
  musicState.statsTimer = null;
  const sessionId = musicState.sessionId;
  musicState.sessionId = null;
  if (notifyServer && sessionId) {
    try {
      await musicFetch("/api/music/session/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId })
      });
    } catch (error) {
      musicLog(`Close acknowledgement unavailable: ${error.message}`);
    }
  }
  if (musicState.peer) musicState.peer.close();
  musicState.peer = null;
  const audio = $("#musicAudio");
  audio.pause();
  audio.srcObject = null;
  $("#musicConnect").disabled = false;
  $("#musicStop").disabled = true;
  clearMusicStats();
}

async function connectMusicRelay() {
  if (!window.RTCPeerConnection) {
    setMusicHealth("WebRTC is unavailable in this browser", "bad");
    return;
  }
  await stopMusicRelay(true);
  $("#musicConnect").disabled = true;
  setMusicHealth("מתחבר ב‑WebRTC… · Connecting…");

  try {
    await checkMusicRelay();
    const peer = new RTCPeerConnection({ iceServers: [] });
    musicState.peer = peer;
    const transceiver = peer.addTransceiver("audio", { direction: "recvonly" });
    preferOpus(transceiver);

    peer.ontrack = (event) => {
      const audio = $("#musicAudio");
      audio.srcObject = event.streams[0] || new MediaStream([event.track]);
      audio.play().then(() => musicLog("Remote Opus track is playing.")).catch(() => musicLog("Tap Play once; Android blocked autoplay."));
    };
    peer.onconnectionstatechange = () => {
      const state = peer.connectionState;
      musicLog(`WebRTC connection: ${state}`);
      if (state === "connected") setMusicHealth("מחובר · Connected (Opus)", "ok");
      if (["failed", "disconnected", "closed"].includes(state)) setMusicHealth(`WebRTC: ${state}`, state === "disconnected" ? "idle" : "bad");
    };

    await peer.setLocalDescription(await peer.createOffer());
    await waitForIceGathering(peer);
    const answer = await readJsonResponse(await musicFetch("/api/music/offer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sdp: directHostOffer(peer.localDescription.sdp), type: peer.localDescription.type })
    }));
    musicState.sessionId = answer.sessionId;
    await peer.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
    $("#musicCodec").textContent = answer.codec || "Opus";
    $("#musicStop").disabled = false;
    musicState.statsTimer = setInterval(() => updateMusicStats().catch(() => {}), 1000);
    musicLog(`Authenticated SDP answer received; session ${answer.sessionId.slice(0, 6)}…`);
  } catch (error) {
    await stopMusicRelay(false);
    setMusicHealth(error.message, "bad");
    musicLog(`Connect failed: ${error.message}`);
  }
}

$("#musicCheck").onclick = () => checkMusicRelay().catch(() => {});
$("#musicConnect").onclick = connectMusicRelay;
$("#musicStop").onclick = async () => {
  await stopMusicRelay(true);
  setMusicHealth("נעצר · Stopped");
  musicLog("Session stopped by the phone.");
};
$("#pairingToken").addEventListener("input", () => setMusicHealth("קוד השתנה; בדוק שוב · Token changed; check again"));
window.addEventListener("pagehide", () => {
  if (musicState.peer) musicState.peer.close();
});

const routes = {
  grokEnglish: { label: "Grok‑1 English Agent via distributed llama.cpp / Ollama-compatible gateway", health: "/api/grok/health", generate: "/api/grok/generate", mode: "english" },
  grokRaw: { label: "Grok‑1 Exact Raw research mode", health: "/api/grok/health", generate: "/api/grok/generate", mode: "raw" },
  shiri: { label: "Shiri relay — configure an HTTPS deployment first" },
  manual: { label: "Manual draft — no network call" }
};

const setHealth = (text, ok = false) => {
  $("#health").textContent = text;
  $("#dot").className = `status-dot ${ok ? "ok" : ""}`;
};

async function check() {
  const route = routes[$("#model").value];
  if (!route.health) return setHealth(route.label);
  try {
    const response = await fetch(route.health, { signal: AbortSignal.timeout(6000) });
    const payload = await response.json();
    setHealth(`${route.label}: ${payload.ready ? "ready" : "not ready"}`, !!payload.ready);
  } catch {
    setHealth(`${route.label}: private bridge unavailable.`);
  }
}

$("#check").onclick = check;
$("#model").onchange = check;
$("#generate").onclick = async () => {
  const route = routes[$("#model").value];
  const prompt = $("#prompt").value.trim();
  if (!prompt) {
    $("#answer").textContent = "Write or dictate a message first.";
    return;
  }
  if (!route.generate) {
    $("#answer").textContent = `Draft only:\n${prompt}\n\nNo remote action was sent.`;
    return;
  }
  $("#answer").textContent = "Asking the selected service…";
  try {
    const response = await fetch(route.generate, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: "grok-1-q6", prompt, mode: route.mode, stream: true, options: { num_predict: 64, temperature: .3 } })
    });
    if (!response.ok || !response.body) {
      const failure = await response.json().catch(() => ({}));
      $("#answer").textContent = failure.error || `Grok returned ${response.status}`;
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";
    $("#answer").textContent = "";
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const part = JSON.parse(line);
        if (part.error) throw new Error(part.error);
        if (part.response) answer += part.response;
        if (route.mode === "english") {
          const cyrillic = answer.search(/[\u0400-\u04ff]/);
          const repeatedPrompt = answer.search(/\n(?:Question|English-only response):/i);
          const cuts = [cyrillic, repeatedPrompt].filter((index) => index >= 0);
          if (cuts.length) {
            answer = answer.slice(0, Math.min(...cuts)).trimEnd();
            await reader.cancel();
            $("#answer").textContent = answer || "English guard stopped a non-English continuation. Try again.";
            buffer = "";
            break;
          }
        }
        $("#answer").textContent = answer || "Waiting for the first token…";
      }
      if (done) break;
    }
    $("#answer").textContent = answer || "No response";
  } catch (error) {
    $("#answer").textContent = error.message || "Cannot reach Grok through the private bridge.";
  }
};

$("#listen").onclick = () => {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    $("#answer").textContent = "Browser voice recognition is unavailable. Type instead or use the separate Shiri relay.";
    return;
  }
  const recognition = new Recognition();
  recognition.lang = $("#language").value;
  recognition.onresult = (event) => {
    $("#prompt").value += ($("#prompt").value ? " " : "") + event.results[0][0].transcript;
  };
  recognition.onerror = () => { $("#answer").textContent = "Voice input failed. Check microphone permission."; };
  recognition.start();
};

$("#speak").onclick = () => {
  const utterance = new SpeechSynthesisUtterance($("#answer").textContent);
  utterance.lang = $("#language").value;
  speechSynthesis.speak(utterance);
};

$("#copyTask").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("#prompt").value || $("#answer").textContent);
    $("#answer").textContent = "Copied a draft only. Review it in Remote before sending.";
  } catch {
    $("#answer").textContent = "Clipboard access is unavailable in this browser context.";
  }
};

check();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

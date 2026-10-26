const player = document.getElementById("player");
let requestController;
let audioUrl;
let playGeneration = 0;

function reportStatus(status, detail = {}) {
  chrome.runtime.sendMessage({
    target: "sidepanel",
    type: "PLAYER_STATUS",
    status,
    ...detail
  }).catch(() => {});
}

function clearAudio() {
  player.pause();
  player.removeAttribute("src");
  player.load();
  if (audioUrl) {
    URL.revokeObjectURL(audioUrl);
    audioUrl = undefined;
  }
}

function stopPlayback() {
  playGeneration++;
  requestController?.abort();
  requestController = undefined;
  clearAudio();
}

function splitText(text, maxLength = 400) {
  const cleaned = text
    .replace(/```[\s\S]*?```/g, " bloque de código omitido ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[#*_~>]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const sentences = cleaned.match(/[^.!?;]+[.!?;]?/g) || [];
  const chunks = [];
  let current = "";
  for (const sentence of sentences) {
    const part = sentence.trim();
    if (!part) continue;
    if (current && current.length + part.length + 1 > maxLength) {
      chunks.push(current);
      current = "";
    }
    current = current ? `${current} ${part}` : part;
  }
  if (current) chunks.push(current);
  return chunks;
}

async function synthesizeChunk(text, backendUrl, accessToken, voice, rate, signal) {
  const form = new FormData();
  form.append("text", text);
  form.append("voice", voice);
  form.append("rate", `${rate >= 0 ? "+" : ""}${rate}%`);

  const response = await fetch(`${backendUrl.replace(/\/+$/, "")}/tts`, {
    method: "POST",
    body: form,
    signal,
    headers: accessToken ? { Authorization: "Bearer " + accessToken } : {}
  });
  if (!response.ok) throw new Error(`El servidor TTS respondió ${response.status}`);
  return response.blob();
}

async function playText({ text, backendUrl, accessToken, voice, rate }) {
  stopPlayback();
  const generation = playGeneration;
  requestController = new AbortController();
  const signal = requestController.signal;
  const chunks = splitText(text);

  try {
    if (!chunks.length) throw new Error("No hay texto para leer.");
    reportStatus("started", { total: chunks.length });
    for (const [index, chunk] of chunks.entries()) {
      if (generation !== playGeneration || signal.aborted) return;
      reportStatus("chunk", { index, total: chunks.length, text: chunk });
      const blob = await synthesizeChunk(chunk, backendUrl, accessToken, voice, rate, signal);
      if (generation !== playGeneration || signal.aborted) return;

      audioUrl = URL.createObjectURL(blob);
      player.src = audioUrl;
      await new Promise((resolve, reject) => {
        const onAbort = () => {
          cleanup();
          resolve();
        };
        const onEnded = () => {
          cleanup();
          resolve();
        };
        const onError = () => {
          cleanup();
          reject(new Error("No se pudo reproducir el audio."));
        };
        const cleanup = () => {
          player.removeEventListener("ended", onEnded);
          player.removeEventListener("error", onError);
          signal.removeEventListener("abort", onAbort);
        };
        player.addEventListener("ended", onEnded, { once: true });
        player.addEventListener("error", onError, { once: true });
        signal.addEventListener("abort", onAbort, { once: true });
        player.play().catch((error) => {
          cleanup();
          reject(error);
        });
      });
      URL.revokeObjectURL(audioUrl);
      audioUrl = undefined;
    }
    if (generation === playGeneration && !signal.aborted) reportStatus("completed");
  } catch (error) {
    if (error.name !== "AbortError") {
      console.error("Error en la lectura TTS:", error);
      reportStatus("error", { message: error.message });
    }
  } finally {
    if (generation === playGeneration) {
      requestController = undefined;
      clearAudio();
    }
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== "offscreen") return;

  if (message.type === "PLAY") {
    void playText(message);
  } else if (message.type === "STOP") {
    stopPlayback();
  } else if (message.type === "TOGGLE_PAUSE") {
    if (player.paused) {
      void player.play().catch((error) => console.error("No se pudo reanudar:", error));
    } else {
      player.pause();
    }
  }
});

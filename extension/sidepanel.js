const textInput = document.getElementById("text");
const backendInput = document.getElementById("backend");
const accessTokenInput = document.getElementById("access-token");
const voiceInput = document.getElementById("voice");
const rateInput = document.getElementById("rate");
const status = document.getElementById("status");

function setStatus(text) {
  status.textContent = text;
}

function backendOriginPattern(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Ingresá una URL válida para el servidor.");
  }
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("Usá una URL HTTP o HTTPS sin credenciales.");
  }
  return `${url.origin}/*`;
}

function updateRateLabel() {
  const value = Number(rateInput.value);
  document.getElementById("rate-output").textContent = `${value >= 0 ? "+" : ""}${value}%`;
}

async function loadSettings() {
  const settings = await chrome.storage.local.get({
    backendUrl: "http://127.0.0.1:8000",
    accessToken: "",
    voice: "es-US-AlonsoNeural",
    rate: 20,
    currentText: ""
  });
  backendInput.value = settings.backendUrl;
  accessTokenInput.value = settings.accessToken;
  voiceInput.value = settings.voice;
  rateInput.value = settings.rate;
  textInput.value = settings.currentText;
  updateRateLabel();
  document.getElementById("version").textContent =
    `Extensión v${chrome.runtime.getManifest().version}`;
}

rateInput.addEventListener("input", updateRateLabel);
textInput.addEventListener("input", () => {
  void chrome.storage.local.set({ currentText: textInput.value });
});

async function getSelectedText(tabId) {
  if (!tabId) throw new Error("No se encontró la pestaña activa.");
  const [{ result = "" } = {}] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => window.getSelection()?.toString() || ""
  });
  if (!result.trim()) throw new Error("Seleccioná texto en la página y volvé a intentar.");
  return result;
}

async function startReading(text, tabId) {
  await chrome.storage.local.set({ currentText: text });
  textInput.value = text;
  const reply = await chrome.runtime.sendMessage({
    target: "background",
    type: "PLAY_FROM_PANEL",
    text,
    tabId,
    voice: voiceInput.value,
    rate: Number(rateInput.value),
    accessToken: accessTokenInput.value.trim()
  });
  if (!reply?.ok) throw new Error(reply?.error || "No se pudo iniciar la lectura.");
}

async function storeVoiceSettings() {
  await chrome.storage.local.set({
    voice: voiceInput.value,
    rate: Number(rateInput.value)
  });
}

voiceInput.addEventListener("change", () => {
  void storeVoiceSettings();
});
rateInput.addEventListener("change", () => {
  void storeVoiceSettings();
});

document.getElementById("read-selection").addEventListener("click", async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const text = await getSelectedText(tab?.id);
    await startReading(text, tab.id);
    setStatus("Leyendo la selección de la página.");
  } catch (error) {
    setStatus(error.message);
  }
});

document.getElementById("clipboard-read").addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (!text.trim()) throw new Error("El portapapeles está vacío. Copiá primero la respuesta.");
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await startReading(text, tab?.id);
    setStatus("Leyendo el texto copiado.");
  } catch (error) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") {
      setStatus("Chrome no permitió leer el portapapeles. Pegá con Ctrl+V en el campo y tocá «Leer texto».");
      return;
    }
    setStatus(error.message);
  }
});

document.getElementById("ocr-visible").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.windowId || !tab.id) throw new Error("No se encontró la pestaña activa.");

    if (tab.url) {
      const pageOrigin = new URL(tab.url).origin;
      if (pageOrigin.startsWith("http")) {
        const originPattern = `${pageOrigin}/*`;
        const alreadyAllowed = await chrome.permissions.contains({ origins: [originPattern] });
        if (!alreadyAllowed) {
          const granted = await chrome.permissions.request({ origins: [originPattern] });
          if (!granted) throw new Error("Chrome necesita permiso para capturar esta página. Permitilo y volvé a tocar OCR.");
        }
      }
    }

    setStatus("Capturando la página visible para OCR...");
    const screenshotUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
    const screenshot = await fetch(screenshotUrl).then((response) => response.blob());
    const settings = await chrome.storage.local.get({
      backendUrl: "http://127.0.0.1:8000",
      accessToken: ""
    });
    const form = new FormData();
    form.append("file", screenshot, "pagina-visible.png");

    setStatus("Reconociendo texto de la página...");
    const response = await fetch(`${settings.backendUrl.replace(/\/+$/, "")}/extract`, {
      method: "POST",
      body: form,
      headers: settings.accessToken ? { Authorization: "Bearer " + settings.accessToken } : {}
    });
    const result = await response.json();
    if (!response.ok) throw new Error(`OCR: ${result.detail || "el servidor rechazó la captura."}`);
    if (!result.text.trim()) throw new Error("No se encontró texto legible en la captura.");

    await startReading(result.text, tab.id);
    setStatus("Texto reconocido y lectura iniciada. El texto quedó disponible para editar.");
  } catch (error) {
    console.error("OCR de página visible falló:", error);
    setStatus(`No se pudo leer la página: ${error.message}`);
  } finally {
    button.disabled = false;
  }
});

document.getElementById("document").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const settings = await chrome.storage.local.get({
      backendUrl: "http://127.0.0.1:8000",
      accessToken: ""
    });
    const form = new FormData();
    form.append("file", file);
    setStatus(`Extrayendo texto de ${file.name}...`);
    const response = await fetch(`${settings.backendUrl.replace(/\/+$/, "")}/extract`, {
      method: "POST",
      body: form,
      headers: settings.accessToken ? { Authorization: "Bearer " + settings.accessToken } : {}
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "No se pudo extraer el texto.");
    textInput.value = result.text;
    await chrome.storage.local.set({ currentText: result.text });
    setStatus(`Texto extraído de ${file.name}. Podés corregirlo o editarlo antes de leer.`);
  } catch (error) {
    setStatus(error.message);
  } finally {
    event.target.value = "";
  }
});

document.getElementById("clear").addEventListener("click", async () => {
  textInput.value = "";
  await chrome.storage.local.set({ currentText: "" });
  setStatus("Texto borrado.");
});

document.getElementById("save").addEventListener("click", async () => {
  try {
    const backendUrl = backendInput.value.trim().replace(/\/+$/, "");
    const originPattern = backendOriginPattern(backendUrl);
    const hasPermission = await chrome.permissions.contains({ origins: [originPattern] });
    if (!hasPermission) {
      const granted = await chrome.permissions.request({ origins: [originPattern] });
      if (!granted) throw new Error("Chrome no concedió permiso para conectar con ese servidor.");
    }
    await chrome.storage.local.set({
      backendUrl,
      accessToken: accessTokenInput.value.trim(),
      voice: voiceInput.value,
      rate: Number(rateInput.value),
      currentText: textInput.value
    });
    setStatus("Ajustes guardados.");
  } catch (error) {
    setStatus(error.message);
  }
});

document.getElementById("read").addEventListener("click", async () => {
  try {
    const text = textInput.value.trim();
    if (!text) throw new Error("Seleccioná texto en la página o escribilo acá.");
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    await startReading(text, tab?.id);
    setStatus("Leyendo el texto del panel.");
  } catch (error) {
    setStatus(error.message);
  }
});

for (const [id, command] of [["pause", "TOGGLE_PAUSE"], ["stop", "STOP"]]) {
  document.getElementById(id).addEventListener("click", async () => {
    const reply = await chrome.runtime.sendMessage({
      target: "background",
      type: "PLAYER_COMMAND",
      command
    });
    setStatus(reply?.ok ? (id === "stop" ? "Lectura detenida." : "Pausada / reanudada.") : reply?.error);
  });
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.currentText && document.activeElement !== textInput) {
    textInput.value = changes.currentText.newValue || "";
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== "sidepanel" || message.type !== "PLAYER_STATUS") return;
  if (message.status === "started") {
    setStatus(`Preparando lectura: ${message.total} fragmentos.`);
  } else if (message.status === "chunk") {
    setStatus(`Leyendo fragmento ${message.index + 1} de ${message.total}.`);
    const start = textInput.value.indexOf(message.text);
    if (start >= 0) {
      textInput.focus({ preventScroll: true });
      textInput.setSelectionRange(start, start + message.text.length);
      textInput.scrollTop = textInput.scrollHeight * (start / Math.max(textInput.value.length, 1));
    }
  } else if (message.status === "completed") {
    setStatus("Lectura completada.");
    textInput.setSelectionRange(0, 0);
  } else if (message.status === "error") {
    setStatus(`Error al sintetizar/reproducir: ${message.message}`);
  }
});

void loadSettings();

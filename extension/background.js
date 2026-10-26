const OFFSCREEN_PATH = "offscreen.html";
let creatingOffscreen;

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(console.error);
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "read-selection",
      title: "Leer selección con Alonso",
      contexts: ["selection"]
    });
  });
});

async function ensureOffscreenDocument() {
  const offscreenUrl = chrome.runtime.getURL(OFFSCREEN_PATH);
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ["OFFSCREEN_DOCUMENT"],
    documentUrls: [offscreenUrl]
  });
  if (contexts.length) return;

  if (!creatingOffscreen) {
    creatingOffscreen = chrome.offscreen.createDocument({
      url: OFFSCREEN_PATH,
      reasons: ["AUDIO_PLAYBACK"],
      justification: "Reproducir en segundo plano el audio TTS solicitado por el usuario."
    });
  }
  try {
    await creatingOffscreen;
  } finally {
    creatingOffscreen = undefined;
  }
}

async function sendToPlayer(message) {
  await ensureOffscreenDocument();
  return chrome.runtime.sendMessage({ ...message, target: "offscreen" });
}

async function readSelection(tabId) {
  if (!tabId) return;
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => window.getSelection()?.toString() || ""
    });
    const text = results[0]?.result?.trim();
    if (!text) return;

    await chrome.storage.session.set({ sourceTabId: tabId });
    await chrome.storage.local.set({ currentText: text });
    const {
      backendUrl = "http://127.0.0.1:8000",
      accessToken = "",
      voice = "es-US-AlonsoNeural",
      rate = 20
    } = await chrome.storage.local.get(["backendUrl", "accessToken", "voice", "rate"]);
    await sendToPlayer({ type: "PLAY", text, backendUrl, accessToken, voice, rate });
  } catch (error) {
    console.error("No se pudo leer la selección:", error);
  }
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "read-selection" && info.selectionText && tab?.id) {
    chrome.storage.local.get(["backendUrl", "accessToken", "voice", "rate"]).then(async (settings) => {
      await chrome.storage.session.set({ sourceTabId: tab.id });
      await chrome.storage.local.set({ currentText: info.selectionText });
      await sendToPlayer({
        type: "PLAY",
        text: info.selectionText,
        backendUrl: settings.backendUrl || "http://127.0.0.1:8000",
        accessToken: settings.accessToken || "",
        voice: settings.voice || "es-US-AlonsoNeural",
        rate: settings.rate ?? 20
      });
    }).catch(console.error);
  }
});

chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command === "read-selection") {
    await readSelection(tab?.id);
  } else if (command === "pause-reading") {
    await sendToPlayer({ type: "TOGGLE_PAUSE" });
  } else if (command === "stop-reading") {
    await sendToPlayer({ type: "STOP" });
  }
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const { sourceTabId } = await chrome.storage.session.get("sourceTabId");
  if (sourceTabId === tabId) {
    await sendToPlayer({ type: "STOP" });
    await chrome.storage.session.remove("sourceTabId");
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.target !== "background") return;

  if (message.type === "PLAY_FROM_PANEL") {
    chrome.storage.local.get(["backendUrl", "accessToken", "voice", "rate"]).then(async (settings) => {
      if (message.tabId) {
        await chrome.storage.session.set({ sourceTabId: message.tabId });
      }
      await chrome.storage.local.set({ currentText: message.text });
      await sendToPlayer({
        type: "PLAY",
        text: message.text,
        backendUrl: settings.backendUrl || "http://127.0.0.1:8000",
        accessToken: message.accessToken ?? settings.accessToken ?? "",
        voice: message.voice || settings.voice || "es-US-AlonsoNeural",
        rate: message.rate ?? settings.rate ?? 20
      });
      sendResponse({ ok: true });
    }).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }

  if (message.type === "PLAYER_COMMAND") {
    sendToPlayer({ type: message.command }).then(
      () => sendResponse({ ok: true }),
      (error) => sendResponse({ ok: false, error: error.message })
    );
    return true;
  }
});

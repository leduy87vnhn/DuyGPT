const state = {
  messages: [],
  busy: false,
  recording: false,
  mediaRecorder: null,
  audioChunks: [],
  audioMimeType: "",
  conversationId: null,
  auth: { authenticated: false, username: null, user_type: null },
  requireLogin: false,
  disableRegistration: false,
  imageProvider: "disabled",
  featureFlags: {},
  personas: [],
  selectedPersonaId: null,
};

const els = {
  status: document.querySelector("#status"),
  gpu: document.querySelector("#gpu"),
  provider: document.querySelector("#provider"),
  model: document.querySelector("#model"),
  temperature: document.querySelector("#temperature"),
  temperatureValue: document.querySelector("#temperatureValue"),
  newChat: document.querySelector("#newChat"),
  messages: document.querySelector("#messages"),
  composer: document.querySelector("#composer"),
  prompt: document.querySelector("#prompt"),
  record: document.querySelector("#record"),
  image: document.querySelector("#image"),
  voiceStatus: document.querySelector("#voiceStatus"),
  send: document.querySelector("#send"),

  authLoggedOut: document.querySelector("#authLoggedOut"),
  authLoggedIn: document.querySelector("#authLoggedIn"),
  tabLogin: document.querySelector("#tabLogin"),
  tabRegister: document.querySelector("#tabRegister"),
  loginForm: document.querySelector("#loginForm"),
  registerForm: document.querySelector("#registerForm"),
  loginUsername: document.querySelector("#loginUsername"),
  loginPassword: document.querySelector("#loginPassword"),
  loginError: document.querySelector("#loginError"),
  registerUsername: document.querySelector("#registerUsername"),
  registerPassword: document.querySelector("#registerPassword"),
  registerError: document.querySelector("#registerError"),
  userBadgeName: document.querySelector("#userBadgeName"),
  userBadgeType: document.querySelector("#userBadgeType"),
  logoutBtn: document.querySelector("#logoutBtn"),

  settingsPanel: document.querySelector("#settingsPanel"),
  settingsToggle: document.querySelector("#settingsToggle"),

  historyPanel: document.querySelector("#historyPanel"),
  historyToggle: document.querySelector("#historyToggle"),
  historyList: document.querySelector("#historyList"),

  personaPanel: document.querySelector("#personaPanel"),
  personaToggle: document.querySelector("#personaToggle"),
  activePersonaForm: document.querySelector("#activePersonaForm"),
  activeWebPersona: document.querySelector("#activeWebPersona"),
  activeVoicePersona: document.querySelector("#activeVoicePersona"),
  personaSelect: document.querySelector("#personaSelect"),
  newPersonaBtn: document.querySelector("#newPersonaBtn"),
  deletePersonaBtn: document.querySelector("#deletePersonaBtn"),
  personaForm: document.querySelector("#personaForm"),
  personaNameInput: document.querySelector("#personaNameInput"),
  personaDescriptionInput: document.querySelector("#personaDescriptionInput"),
  webPersonaInput: document.querySelector("#webPersonaInput"),
  voicePersonaInput: document.querySelector("#voicePersonaInput"),
  personaMemoryForm: document.querySelector("#personaMemoryForm"),
  personaMemoryInput: document.querySelector("#personaMemoryInput"),
  personaMemoryFile: document.querySelector("#personaMemoryFile"),
  personaMemoryList: document.querySelector("#personaMemoryList"),
  personaError: document.querySelector("#personaError"),
  personaStatus: document.querySelector("#personaStatus"),

  adminPanel: document.querySelector("#adminPanel"),
  adminToggle: document.querySelector("#adminToggle"),
  uploadForm: document.querySelector("#uploadForm"),
  uploadFile: document.querySelector("#uploadFile"),
  uploadError: document.querySelector("#uploadError"),
  documentList: document.querySelector("#documentList"),
};

function render() {
  if (state.messages.length === 0) {
    els.messages.innerHTML = '<div class="empty">Start a local GPU chat session.</div>';
    return;
  }

  const thread = document.createElement("div");
  thread.className = "thread";
  for (const message of state.messages) {
    const row = document.createElement("article");
    row.className = `message ${message.role}`;
    const role = document.createElement("div");
    role.className = "role";
    role.textContent = message.role;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (message.content) {
      const text = document.createElement("div");
      text.textContent = message.content;
      bubble.append(text);
    }
    if (message.imageUrl) {
      const link = document.createElement("a");
      link.href = message.imageUrl;
      link.target = "_blank";
      link.rel = "noreferrer";
      const image = document.createElement("img");
      image.className = "generated-image";
      image.src = message.imageUrl;
      image.alt = message.prompt || "Generated image";
      link.append(image);
      bubble.append(link);
    }
    row.append(role, bubble);
    thread.append(row);
  }
  els.messages.replaceChildren(thread);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function setupCollapsible(panel, toggle, storageKey, defaultCollapsed = false) {
  const stored = localStorage.getItem(storageKey);
  const collapsed = stored === null ? defaultCollapsed : stored === "1";
  panel.classList.toggle("collapsed", collapsed);
  toggle.setAttribute("aria-expanded", String(!collapsed));
  toggle.addEventListener("click", () => {
    const isCollapsed = panel.classList.toggle("collapsed");
    toggle.setAttribute("aria-expanded", String(!isCollapsed));
    localStorage.setItem(storageKey, isCollapsed ? "1" : "0");
  });
}

setupCollapsible(els.settingsPanel, els.settingsToggle, "duygpt_settings_collapsed");
setupCollapsible(els.historyPanel, els.historyToggle, "duygpt_history_collapsed", true);
setupCollapsible(els.personaPanel, els.personaToggle, "duygpt_persona_collapsed");
setupCollapsible(els.adminPanel, els.adminToggle, "duygpt_admin_collapsed");

function setBusy(value) {
  state.busy = value;
  els.send.disabled = value;
  els.prompt.disabled = value;
  els.record.disabled = value;
  els.image.disabled = value || state.imageProvider === "disabled";
}

function autoSize() {
  els.prompt.style.height = "auto";
  els.prompt.style.height = `${Math.min(els.prompt.scrollHeight, 320)}px`;
}

function setVoiceStatus(message, isError = false) {
  els.voiceStatus.textContent = message;
  els.voiceStatus.classList.toggle("error", isError);
}

function appendPromptText(text) {
  const cleaned = text.trim();
  if (!cleaned) return;
  const current = els.prompt.value.trim();
  els.prompt.value = current ? `${current}\n${cleaned}` : cleaned;
  autoSize();
  els.prompt.focus();
}

function readBlobAsBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function updateImageButtonState() {
  const configuredOff = state.imageProvider === "disabled";
  const hiddenByAdmin = state.auth.user_type !== "admin_user" && state.featureFlags.image_generation === false;
  els.image.classList.toggle("hidden", hiddenByAdmin);
  els.image.disabled = configuredOff;
  els.image.title = configuredOff
    ? "Image generation is not configured"
    : `Generate image with ${state.imageProvider}`;
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    state.requireLogin = Boolean(data.require_login);
    state.disableRegistration = Boolean(data.disable_registration);
    state.imageProvider = data.image_provider || "disabled";
    updateImageButtonState();
    els.status.textContent = `${data.provider} / ${data.model}`;
    els.provider.value = data.provider;
    els.model.value = data.model;
    if (data.gpu?.ok && data.gpu.gpus?.length) {
      els.gpu.textContent = data.gpu.gpus.map((gpu) => `${gpu.name} (${gpu.memory})`).join(", ");
    } else {
      els.gpu.textContent = "";
    }
  } catch (error) {
    els.status.textContent = "Server unavailable";
    els.gpu.textContent = error.message;
  }
}

async function loadFeatureFlags() {
  try {
    const data = await fetch("/api/feature-flags").then((r) => r.json());
    state.featureFlags = data.flags || {};
  } catch {
    state.featureFlags = {};
  }
  updateImageButtonState();
}

// --- Auth ---

function renderAuth() {
  const authed = state.auth.authenticated;
  els.authLoggedOut.classList.toggle("hidden", authed);
  els.authLoggedIn.classList.toggle("hidden", !authed);
  els.tabRegister.classList.toggle("hidden", state.disableRegistration);
  if (state.disableRegistration && els.tabRegister.classList.contains("active")) {
    setActiveTab("login");
  }
  els.historyPanel.classList.toggle("hidden", !authed);
  els.personaPanel.classList.toggle("hidden", state.auth.user_type !== "admin_user");
  els.adminPanel.classList.toggle("hidden", state.auth.user_type !== "admin_user");
  if (authed) {
    els.userBadgeName.textContent = state.auth.username;
    els.userBadgeType.textContent = state.auth.user_type;
  }
  updateImageButtonState();
}

async function loadAuth() {
  try {
    const response = await fetch("/api/auth/me");
    const data = await response.json();
    state.auth = data;
  } catch {
    state.auth = { authenticated: false, username: null, user_type: null };
  }
  renderAuth();
  if (state.auth.authenticated) {
    loadConversations();
    if (state.auth.user_type === "admin_user") {
      loadPersona();
      loadDocuments();
    }
  }
}

function setActiveTab(tab) {
  const isLogin = tab === "login";
  els.tabLogin.classList.toggle("active", isLogin);
  els.tabRegister.classList.toggle("active", !isLogin);
  els.loginForm.classList.toggle("hidden", !isLogin);
  els.registerForm.classList.toggle("hidden", isLogin);
}

function resetChatState() {
  state.messages = [];
  state.conversationId = null;
  render();
}

els.tabLogin.addEventListener("click", () => setActiveTab("login"));
els.tabRegister.addEventListener("click", () => setActiveTab("register"));

els.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.loginError.textContent = "";
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: els.loginUsername.value.trim(),
        password: els.loginPassword.value,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Login failed");
    els.loginForm.reset();
    resetChatState();
    await loadAuth();
  } catch (error) {
    els.loginError.textContent = error.message;
  }
});

els.registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.registerError.textContent = "";
  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: els.registerUsername.value.trim(),
        password: els.registerPassword.value,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Registration failed");
    els.registerForm.reset();
    resetChatState();
    await loadAuth();
  } catch (error) {
    els.registerError.textContent = error.message;
  }
});

els.logoutBtn.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  resetChatState();
  await loadAuth();
});

// --- Conversation history ---

async function loadConversations() {
  try {
    const response = await fetch("/api/conversations");
    const data = await response.json();
    renderHistory(data.conversations || []);
  } catch {
    els.historyList.textContent = "Failed to load history";
  }
}

function renderHistory(conversations) {
  if (conversations.length === 0) {
    els.historyList.innerHTML = '<p class="muted-note">No conversations yet.</p>';
    return;
  }
  els.historyList.replaceChildren(
    ...conversations.map((conversation) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "history-item";
      item.textContent = conversation.title || "New chat";
      if (conversation.id === state.conversationId) item.classList.add("active");
      item.addEventListener("click", () => loadConversation(conversation.id));
      return item;
    })
  );
}

async function loadConversation(id) {
  try {
    const response = await fetch(`/api/conversations/${id}/messages`);
    if (!response.ok) throw new Error("Failed to load conversation");
    const data = await response.json();
    state.conversationId = id;
    state.messages = (data.messages || []).map(({ role, content }) => ({ role, content }));
    render();
    loadConversations();
  } catch (error) {
    els.gpu.textContent = error.message;
  }
}

// --- Chat ---

async function sendMessage(content) {
  if (content.trim().toLowerCase().startsWith("/image ")) {
    await sendImagePrompt(content.trim().slice(7).trim());
    return;
  }
  if (state.requireLogin && !state.auth.authenticated) {
    state.messages.push({
      role: "error",
      content: "Vui lòng đăng nhập hoặc đăng ký tài khoản trước khi chat.",
    });
    render();
    setActiveTab("login");
    els.loginUsername.focus();
    return;
  }
  const userMessage = { role: "user", content };
  const assistantMessage = { role: "assistant", content: "" };
  state.messages.push(userMessage, assistantMessage);
  render();
  setBusy(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: els.provider.value,
        model: els.model.value.trim(),
        temperature: Number(els.temperature.value),
        conversation_id: state.conversationId,
        messages: state.messages
          .filter((message) => message.role !== "error")
          .map(({ role, content }) => ({ role, content })),
      }),
    });

    if (!response.ok || !response.body) {
      if (response.status === 401) {
        throw new Error("Vui lòng đăng nhập lại rồi gửi tin nhắn.");
      }
      throw new Error(`Chat request failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      for (const event of events) {
        const line = event.split("\n").find((item) => item.startsWith("data: "));
        if (!line) continue;
        const data = JSON.parse(line.slice(6));
        if (data.error) throw new Error(data.error);
        if (data.conversation_id) {
          state.conversationId = data.conversation_id;
        }
        if (data.delta) {
          assistantMessage.content += data.delta;
          render();
        }
      }
    }

    if (state.auth.authenticated) {
      loadConversations();
    }
  } catch (error) {
    assistantMessage.role = "error";
    assistantMessage.content = error.message;
    render();
  } finally {
    setBusy(false);
    els.prompt.focus();
  }
}

async function sendImagePrompt(prompt) {
  if (!prompt) return;
  if (state.imageProvider === "disabled") {
    state.messages.push({
      role: "error",
      content:
        "Chưa cấu hình dịch vụ tạo ảnh. Hãy bật IMAGE_PROVIDER=openai, sdwebui hoặc comfyui trong .env, rồi restart DuyGPT.",
    });
    render();
    return;
  }
  if (state.requireLogin && !state.auth.authenticated) {
    state.messages.push({
      role: "error",
      content: "Vui lòng đăng nhập hoặc đăng ký tài khoản trước khi tạo ảnh.",
    });
    render();
    setActiveTab("login");
    els.loginUsername.focus();
    return;
  }
  const userMessage = { role: "user", content: `/image ${prompt}` };
  const assistantMessage = { role: "assistant", content: "Đang tạo ảnh..." };
  state.messages.push(userMessage, assistantMessage);
  render();
  setBusy(true);

  try {
    const response = await fetch("/api/image/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) {
        throw new Error("Vui lòng đăng nhập lại rồi tạo ảnh.");
      }
      throw new Error(data.error || `Image request failed: ${response.status}`);
    }
    assistantMessage.content = `Ảnh đã tạo từ ${data.provider}: ${prompt}`;
    assistantMessage.imageUrl = data.url;
    assistantMessage.prompt = prompt;
    render();
  } catch (error) {
    assistantMessage.role = "error";
    assistantMessage.content = error.message;
    render();
  } finally {
    setBusy(false);
    els.prompt.focus();
  }
}

// --- Voice input ---

function supportedAudioType() {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function audioExtension(mimeType) {
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("webm")) return "webm";
  return "wav";
}

function setRecording(value) {
  state.recording = value;
  els.record.classList.toggle("recording", value);
  els.record.setAttribute("aria-label", value ? "Stop recording" : "Start recording");
  els.record.title = value ? "Stop recording" : "Start recording";
}

async function startRecording() {
  setVoiceStatus("");
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    setVoiceStatus("Trình duyệt này chưa hỗ trợ ghi âm trực tiếp.", true);
    return;
  }

  if (!window.isSecureContext) {
    setVoiceStatus(
      "Trình duyệt đang chặn micro trên HTTP. Dùng localhost hoặc mở trang bằng HTTPS.",
      true
    );
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.audioMimeType = supportedAudioType();
    state.audioChunks = [];
    state.mediaRecorder = new MediaRecorder(
      stream,
      state.audioMimeType ? { mimeType: state.audioMimeType } : undefined
    );

    state.mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) state.audioChunks.push(event.data);
    });

    state.mediaRecorder.addEventListener("stop", () => {
      stream.getTracks().forEach((track) => track.stop());
      transcribeRecording();
    });

    state.mediaRecorder.start();
    setRecording(true);
    setVoiceStatus("Đang ghi âm...");
  } catch (error) {
    setRecording(false);
    setVoiceStatus(error.message || "Không mở được micro.", true);
  }
}

function stopRecording() {
  if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
    state.mediaRecorder.stop();
  }
  setRecording(false);
  setVoiceStatus("Đang nhận dạng giọng nói...");
}

async function transcribeRecording() {
  if (!state.audioChunks.length) {
    setVoiceStatus("Không có âm thanh để nhận dạng.", true);
    return;
  }

  const blob = new Blob(state.audioChunks, {
    type: state.audioMimeType || state.audioChunks[0].type || "audio/webm",
  });
  const filename = `recording.${audioExtension(blob.type)}`;

  setBusy(true);
  try {
    const audioBase64 = await readBlobAsBase64(blob);
    const response = await fetch("/api/voice/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ audio_base64: audioBase64, filename }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Speech recognition failed");
    appendPromptText(data.text || "");
    setVoiceStatus(data.text ? "" : "Không nhận ra nội dung nói.", !data.text);
  } catch (error) {
    setVoiceStatus(error.message, true);
  } finally {
    state.audioChunks = [];
    state.mediaRecorder = null;
    setBusy(false);
  }
}

// --- Persona (admin only) ---

function selectedPersona() {
  return state.personas.find((item) => item.id === state.selectedPersonaId) || state.personas[0] || null;
}

function fillPersonaSelect(select, personas) {
  select.replaceChildren(
    ...personas.map((item) => {
      const option = document.createElement("option");
      option.value = String(item.id);
      option.textContent = item.name;
      return option;
    })
  );
}

function renderPersonaEditor() {
  fillPersonaSelect(els.personaSelect, state.personas);
  fillPersonaSelect(els.activeWebPersona, state.personas);
  fillPersonaSelect(els.activeVoicePersona, state.personas);
  if (state.selectedPersonaId) els.personaSelect.value = String(state.selectedPersonaId);
  const item = selectedPersona();
  if (!item) {
    els.personaNameInput.value = "";
    els.personaDescriptionInput.value = "";
    els.webPersonaInput.value = "";
    els.voicePersonaInput.value = "";
    els.deletePersonaBtn.disabled = true;
    els.personaMemoryList.innerHTML = '<p class="muted-note">No persona selected.</p>';
    return;
  }
  state.selectedPersonaId = item.id;
  els.personaSelect.value = String(item.id);
  els.personaNameInput.value = item.name || "";
  els.personaDescriptionInput.value = item.description || "";
  els.webPersonaInput.value = item.web_system_prompt || "";
  els.voicePersonaInput.value = item.voice_system_prompt || "";
  els.deletePersonaBtn.disabled = state.personas.length <= 1;
}

async function loadPersona() {
  try {
    const response = await fetch("/api/admin/personas");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to load persona");
    state.personas = data.personas || [];
    state.selectedPersonaId =
      state.selectedPersonaId ||
      data.active_web_persona_id ||
      data.active_voice_persona_id ||
      state.personas[0]?.id ||
      null;
    renderPersonaEditor();
    if (data.active_web_persona_id) els.activeWebPersona.value = String(data.active_web_persona_id);
    if (data.active_voice_persona_id) els.activeVoicePersona.value = String(data.active_voice_persona_id);
    if (state.selectedPersonaId) loadPersonaMemories(state.selectedPersonaId);
  } catch (error) {
    els.personaError.textContent = error.message;
  }
}

async function loadPersonaMemories(personaId) {
  try {
    const response = await fetch(`/api/admin/personas/${personaId}/memories`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to load memories");
    renderPersonaMemories(data.memories || []);
  } catch (error) {
    els.personaMemoryList.textContent = error.message;
  }
}

function renderPersonaMemories(memories) {
  if (memories.length === 0) {
    els.personaMemoryList.innerHTML = '<p class="muted-note">No memories yet.</p>';
    return;
  }
  els.personaMemoryList.replaceChildren(
    ...memories.map((memory) => {
      const row = document.createElement("div");
      row.className = "memory-item";
      const text = document.createElement("span");
      const label = memory.filename ? `${memory.source_type}: ${memory.filename}` : memory.source_type;
      text.textContent = `${label} - ${memory.content}`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "secondary";
      remove.textContent = "Delete";
      remove.addEventListener("click", async () => {
        await fetch(`/api/admin/persona-memories/${memory.id}`, { method: "DELETE" });
        loadPersonaMemories(state.selectedPersonaId);
      });
      row.append(text, remove);
      return row;
    })
  );
}

els.activePersonaForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.personaError.textContent = "";
  els.personaStatus.textContent = "";
  try {
    const response = await fetch("/api/admin/personas/active", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        web_persona_id: Number(els.activeWebPersona.value),
        voice_persona_id: Number(els.activeVoicePersona.value),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to apply active personas");
    els.personaStatus.textContent = "Active personas applied.";
    loadPersona();
  } catch (error) {
    els.personaError.textContent = error.message;
  }
});

els.personaSelect.addEventListener("change", () => {
  state.selectedPersonaId = Number(els.personaSelect.value);
  renderPersonaEditor();
  loadPersonaMemories(state.selectedPersonaId);
});

els.newPersonaBtn.addEventListener("click", async () => {
  els.personaError.textContent = "";
  els.personaStatus.textContent = "";
  try {
    const response = await fetch("/api/admin/personas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Nhân vật mới" }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to create persona");
    state.selectedPersonaId = data.id;
    els.personaStatus.textContent = "Created.";
    loadPersona();
  } catch (error) {
    els.personaError.textContent = error.message;
  }
});

els.deletePersonaBtn.addEventListener("click", async () => {
  const item = selectedPersona();
  if (!item || state.personas.length <= 1) return;
  if (!window.confirm(`Delete persona "${item.name}"?`)) return;
  els.personaError.textContent = "";
  els.personaStatus.textContent = "";
  try {
    const response = await fetch(`/api/admin/personas/${item.id}`, { method: "DELETE" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to delete persona");
    state.selectedPersonaId = null;
    els.personaStatus.textContent = "Deleted.";
    loadPersona();
  } catch (error) {
    els.personaError.textContent = error.message;
  }
});

els.personaForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.personaError.textContent = "";
  els.personaStatus.textContent = "";
  const item = selectedPersona();
  if (!item) return;
  const name = els.personaNameInput.value.trim();
  const webSystemPrompt = els.webPersonaInput.value.trim();
  const voiceSystemPrompt = els.voicePersonaInput.value.trim();
  if (!name) {
    els.personaError.textContent = "name must not be empty";
    return;
  }
  if (!webSystemPrompt) {
    els.personaError.textContent = "web_system_prompt must not be empty";
    return;
  }
  if (!voiceSystemPrompt) {
    els.personaError.textContent = "voice_system_prompt must not be empty";
    return;
  }
  try {
    const response = await fetch(`/api/admin/personas/${item.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        description: els.personaDescriptionInput.value.trim(),
        web_system_prompt: webSystemPrompt,
        voice_system_prompt: voiceSystemPrompt,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to save persona");
    els.personaStatus.textContent = "Saved.";
    loadPersona();
  } catch (error) {
    els.personaError.textContent = error.message;
  }
});

els.personaMemoryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.personaError.textContent = "";
  els.personaStatus.textContent = "";
  const item = selectedPersona();
  if (!item) return;
  const file = els.personaMemoryFile.files[0];
  const note = els.personaMemoryInput.value.trim();
  if (!file && !note) {
    els.personaError.textContent = "memory note or file is required";
    return;
  }
  const payload = { content: note, source_type: file ? "file" : "note" };
  if (file) {
    payload.filename = file.name;
    payload.content_base64 = await readFileAsBase64(file);
  }
  try {
    const response = await fetch(`/api/admin/personas/${item.id}/memories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to add memory");
    els.personaMemoryInput.value = "";
    els.personaMemoryFile.value = "";
    els.personaStatus.textContent = "Memory added.";
    loadPersona();
    loadPersonaMemories(item.id);
  } catch (error) {
    els.personaError.textContent = error.message;
  }
});

// --- Admin documents (RAG) ---

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

async function loadDocuments() {
  try {
    const response = await fetch("/api/admin/documents");
    const data = await response.json();
    renderDocuments(data.documents || []);
  } catch {
    els.documentList.textContent = "Failed to load documents";
  }
}

function renderDocuments(documents) {
  if (documents.length === 0) {
    els.documentList.innerHTML = '<p class="muted-note">No documents yet.</p>';
    return;
  }
  els.documentList.replaceChildren(
    ...documents.map((doc) => {
      const row = document.createElement("div");
      row.className = "document-item";
      const label = document.createElement("span");
      label.textContent = `${doc.filename} (${doc.chunks} chunks)`;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "secondary";
      remove.textContent = "Delete";
      remove.addEventListener("click", async () => {
        await fetch(`/api/admin/documents/${doc.id}`, { method: "DELETE" });
        loadDocuments();
      });
      row.append(label, remove);
      return row;
    })
  );
}

els.uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.uploadError.textContent = "";
  const file = els.uploadFile.files[0];
  if (!file) return;
  try {
    const contentBase64 = await readFileAsBase64(file);
    const response = await fetch("/api/admin/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, content_base64: contentBase64 }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Upload failed");
    els.uploadForm.reset();
    loadDocuments();
  } catch (error) {
    els.uploadError.textContent = error.message;
  }
});

els.temperature.addEventListener("input", () => {
  els.temperatureValue.textContent = els.temperature.value;
});

els.prompt.addEventListener("input", autoSize);

els.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    els.composer.requestSubmit();
  }
});

els.newChat.addEventListener("click", () => {
  resetChatState();
  els.prompt.focus();
});

els.record.addEventListener("click", () => {
  if (state.busy && !state.recording) return;
  if (state.recording) {
    stopRecording();
  } else {
    startRecording();
  }
});

els.image.addEventListener("click", () => {
  const prompt = els.prompt.value.trim().replace(/^\/image\s+/i, "");
  if (!prompt || state.busy) return;
  els.prompt.value = "";
  autoSize();
  sendImagePrompt(prompt);
});

els.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = els.prompt.value.trim();
  if (!content || state.busy) return;
  els.prompt.value = "";
  autoSize();
  sendMessage(content);
});

render();
loadHealth();
loadAuth();
loadFeatureFlags();

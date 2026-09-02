const TABS = ["chat", "vieccanlam", "lichhop"];

function currentTab() {
  const t = new URLSearchParams(location.search).get("tab");
  return TABS.includes(t) ? t : "chat";
}

const state = {
  tasks: [],
  meetings: [],
  messages: [],
  conversationId: null,
  busy: false,
};

const $ = (q) => document.querySelector(q);

const els = {
  status: $("#status"),
  featureDisabledNotice: $("#featureDisabledNotice"),
  crmMain: $("#crmMain"),

  historyPanel: $("#historyPanel"),
  historyToggle: $("#historyToggle"),
  newChat: $("#newChat"),
  historyList: $("#historyList"),
  messages: $("#messages"),
  composer: $("#composer"),
  prompt: $("#prompt"),
  send: $("#send"),

  taskForm: $("#taskForm"),
  taskTitleInput: $("#taskTitleInput"),
  taskDueInput: $("#taskDueInput"),
  taskList: $("#taskList"),

  meetingForm: $("#meetingForm"),
  meetingTitleInput: $("#meetingTitleInput"),
  meetingLocationInput: $("#meetingLocationInput"),
  meetingStartInput: $("#meetingStartInput"),
  meetingEndInput: $("#meetingEndInput"),
  meetingList: $("#meetingList"),

  record: $("#record"),
  voiceStatus: $("#voiceStatus"),

  fabAdd: $("#fabAdd"),
  addChoicePopup: $("#addChoicePopup"),
  modalTask: $("#modalTask"),
  modalMeeting: $("#modalMeeting"),
};

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

setupCollapsible(els.historyPanel, els.historyToggle, "work_history_collapsed", true);

function formatDate(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return value;
  }
}

function renderTab() {
  const tab = currentTab();
  for (const t of TABS) {
    document.querySelector(`#tab-${t}`).classList.toggle("hidden", t !== tab);
  }
}

// --- Add button (Thêm) ---

function openModal(modal) {
  modal.classList.remove("hidden");
}

function closeModal(modal) {
  modal.classList.add("hidden");
}

els.fabAdd.addEventListener("click", (event) => {
  event.stopPropagation();
  els.addChoicePopup.classList.toggle("hidden");
});

els.addChoicePopup.querySelectorAll("[data-choice]").forEach((button) => {
  button.addEventListener("click", () => {
    els.addChoicePopup.classList.add("hidden");
    openModal(button.dataset.choice === "task" ? els.modalTask : els.modalMeeting);
  });
});

document.addEventListener("click", (event) => {
  if (!els.addChoicePopup.contains(event.target) && event.target !== els.fabAdd) {
    els.addChoicePopup.classList.add("hidden");
  }
});

for (const modal of [els.modalTask, els.modalMeeting]) {
  modal.addEventListener("click", (event) => {
    if (event.target === modal || event.target.closest("[data-close]")) closeModal(modal);
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  els.addChoicePopup.classList.add("hidden");
  closeModal(els.modalTask);
  closeModal(els.modalMeeting);
});

// --- Tasks (Việc Cần Làm) ---

async function loadTasks() {
  const response = await fetch("/api/work/tasks");
  if (response.status === 401) {
    location.href = "/login";
    return;
  }
  const data = await response.json();
  state.tasks = data.tasks || [];
  renderTasks();
}

function renderTasks() {
  if (!state.tasks.length) {
    els.taskList.innerHTML = '<p class="muted-note">Chưa có việc cần làm.</p>';
    return;
  }
  els.taskList.replaceChildren(
    ...state.tasks.map((task) => {
      const item = document.createElement("div");
      item.className = "crm-item";
      if (task.done) item.classList.add("inactive");

      const header = document.createElement("div");
      header.className = "crm-item-header";

      const left = document.createElement("label");
      left.className = "checkbox-line";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = task.done;
      checkbox.addEventListener("change", async () => {
        await fetch(`/api/work/tasks/${task.id}/done`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ done: checkbox.checked }),
        });
        loadTasks();
      });
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = task.title;
      left.append(checkbox, title);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", async () => {
        await fetch(`/api/work/tasks/${task.id}`, { method: "DELETE" });
        loadTasks();
      });
      header.append(left, del);

      const meta = document.createElement("div");
      meta.className = "crm-item-meta";
      meta.textContent = task.due_at ? `Hạn: ${formatDate(task.due_at)}` : "Không có hạn cụ thể";

      item.append(header, meta);
      return item;
    })
  );
}

els.taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = els.taskTitleInput.value.trim();
  if (!title) return;
  const dueRaw = els.taskDueInput.value;
  await fetch("/api/work/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, due_at: dueRaw ? new Date(dueRaw).toISOString() : null }),
  });
  els.taskForm.reset();
  closeModal(els.modalTask);
  loadTasks();
});

// --- Meetings (Lịch Họp) ---

async function loadMeetings() {
  const response = await fetch("/api/schedule");
  if (response.status === 401) {
    location.href = "/login";
    return;
  }
  const data = await response.json();
  state.meetings = data.entries || [];
  renderMeetings();
}

function renderMeetings() {
  if (!state.meetings.length) {
    els.meetingList.innerHTML = '<p class="muted-note">Chưa có lịch họp.</p>';
    return;
  }
  els.meetingList.replaceChildren(
    ...state.meetings.map((meeting) => {
      const item = document.createElement("div");
      item.className = "crm-item";
      if (meeting.done) item.classList.add("inactive");

      const header = document.createElement("div");
      header.className = "crm-item-header";

      const left = document.createElement("label");
      left.className = "checkbox-line";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = meeting.done;
      checkbox.addEventListener("change", async () => {
        await fetch(`/api/schedule/${meeting.id}/done`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ done: checkbox.checked }),
        });
        loadMeetings();
      });
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = meeting.title;
      left.append(checkbox, title);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", async () => {
        await fetch(`/api/schedule/${meeting.id}`, { method: "DELETE" });
        loadMeetings();
      });
      header.append(left, del);

      const meta = document.createElement("div");
      meta.className = "crm-item-meta";
      meta.textContent = `${formatDate(meeting.start_at)} → ${formatDate(meeting.end_at)}${
        meeting.location ? " · " + meeting.location : ""
      }`;

      item.append(header, meta);
      return item;
    })
  );
}

els.meetingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = els.meetingTitleInput.value.trim();
  if (!title) return;
  const body = {
    title,
    location: els.meetingLocationInput.value.trim(),
    start_at: new Date(els.meetingStartInput.value).toISOString(),
    end_at: new Date(els.meetingEndInput.value).toISOString(),
  };
  const response = await fetch("/api/schedule", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (response.ok) {
    els.meetingForm.reset();
    closeModal(els.modalMeeting);
    loadMeetings();
  }
});

// --- Chat ---

function setBusy(value) {
  state.busy = value;
  els.send.disabled = value;
  els.prompt.disabled = value;
  els.record.disabled = value;
}

function autoSize() {
  els.prompt.style.height = "auto";
  els.prompt.style.height = `${Math.min(els.prompt.scrollHeight, 320)}px`;
}

attachVoiceInput({ button: els.record, textarea: els.prompt, status: els.voiceStatus, onBusyChange: setBusy });

function renderMessages() {
  if (!state.messages.length) {
    els.messages.innerHTML = '<div class="empty">Nhờ trợ lý thêm việc cần làm hoặc lịch họp -- trợ lý sẽ tự nhận biết loại nào.</div>';
    return;
  }
  const thread = document.createElement("div");
  thread.className = "thread";
  for (const message of state.messages) {
    const row = document.createElement("article");
    row.className = `message ${message.role}`;
    const role = document.createElement("div");
    role.className = "role";
    role.textContent = message.role === "user" ? "Bạn" : message.role === "assistant" ? "Trợ lý" : message.role;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = message.content;
    row.append(role, bubble);
    thread.append(row);
  }
  els.messages.replaceChildren(thread);
  els.messages.scrollTop = els.messages.scrollHeight;
}

async function sendMessage(content) {
  state.messages.push({ role: "user", content });
  renderMessages();
  setBusy(true);
  try {
    const response = await fetch("/api/work/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: content, conversation_id: state.conversationId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Lỗi không xác định");
    state.conversationId = data.conversation_id;
    state.messages.push({ role: "assistant", content: data.reply || "" });
    renderMessages();
    if ((data.tool_calls || []).length) {
      loadTasks();
      loadMeetings();
    }
  } catch (error) {
    state.messages.push({ role: "error", content: error.message });
    renderMessages();
  } finally {
    setBusy(false);
  }
  loadHistory();
}

els.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = els.prompt.value.trim();
  if (!content || state.busy) return;
  els.prompt.value = "";
  autoSize();
  sendMessage(content);
});

els.prompt.addEventListener("input", autoSize);
els.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    els.composer.requestSubmit();
  }
});

els.newChat.addEventListener("click", () => {
  state.conversationId = null;
  state.messages = [];
  renderMessages();
});

async function loadHistory() {
  const data = await fetch("/api/conversations?kind=work").then((r) => r.json());
  els.historyList.replaceChildren(
    ...(data.conversations || []).map((c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "history-item";
      b.textContent = c.title;
      b.addEventListener("click", async () => {
        const x = await fetch(`/api/conversations/${c.id}/messages`).then((r) => r.json());
        state.conversationId = c.id;
        state.messages = x.messages || [];
        renderMessages();
      });
      return b;
    })
  );
}

// --- Init ---

async function init() {
  renderTab();
  const auth = await fetch("/api/auth/me").then((r) => r.json());
  if (!auth.authenticated) {
    location.href = "/login";
    return;
  }

  if (auth.user_type !== "admin_user") {
    try {
      const flagsData = await fetch("/api/feature-flags").then((r) => r.json());
      if (flagsData.flags?.work === false) {
        els.featureDisabledNotice.classList.remove("hidden");
        els.crmMain.classList.add("hidden");
        els.fabAdd.classList.add("hidden");
        els.status.textContent = "Tính năng đang tắt";
        return;
      }
    } catch {
      // ignore, fall through to normal init
    }
  }

  els.status.textContent = `${auth.username} · Sẵn sàng`;
  renderMessages();
  await Promise.all([loadTasks(), loadMeetings(), loadHistory()]);
}

init();

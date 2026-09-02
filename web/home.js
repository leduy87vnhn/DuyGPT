const TABS = ["chat", "lichgiadinh", "nhacviec", "muasam", "ghichu"];

function currentTab() {
  const t = new URLSearchParams(location.search).get("tab");
  return TABS.includes(t) ? t : "chat";
}

const state = {
  authenticated: false,
  messages: [],
  conversationId: null,
  busy: false,
};

const $ = (q) => document.querySelector(q);

const els = {
  status: $("#status"),
  loggedOutNotice: $("#loggedOutNotice"),
  featureDisabledNotice: $("#featureDisabledNotice"),
  crmMain: $("#crmMain"),

  historyPanel: $("#historyPanel"),
  historyToggle: $("#historyToggle"),
  newChat: $("#newChat"),
  historyList: $("#historyList"),
  messages: $("#messages"),
  composer: $("#composer"),
  prompt: $("#prompt"),
  record: $("#record"),
  voiceStatus: $("#voiceStatus"),
  send: $("#send"),

  calendarForm: $("#calendarForm"),
  calendarTitle: $("#calendarTitle"),
  calendarLocation: $("#calendarLocation"),
  calendarStart: $("#calendarStart"),
  calendarEnd: $("#calendarEnd"),
  calendarList: $("#calendarList"),

  reminderForm: $("#reminderForm"),
  reminderInput: $("#reminderInput"),
  reminderList: $("#reminderList"),

  shoppingForm: $("#shoppingForm"),
  shoppingInput: $("#shoppingInput"),
  shoppingQuantityInput: $("#shoppingQuantityInput"),
  shoppingList: $("#shoppingList"),

  noteForm: $("#noteForm"),
  noteInput: $("#noteInput"),
  noteList: $("#noteList"),

  fabAdd: $("#fabAdd"),
  addChoicePopup: $("#addChoicePopup"),
  modalCalendar: $("#modalCalendar"),
  modalReminder: $("#modalReminder"),
  modalShopping: $("#modalShopping"),
  modalNote: $("#modalNote"),
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

setupCollapsible(els.historyPanel, els.historyToggle, "home_history_collapsed", true);

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

const MODAL_BY_CHOICE = {
  calendar: els.modalCalendar,
  reminder: els.modalReminder,
  shopping: els.modalShopping,
  note: els.modalNote,
};
const ALL_MODALS = [els.modalCalendar, els.modalReminder, els.modalShopping, els.modalNote];

els.fabAdd.addEventListener("click", (event) => {
  event.stopPropagation();
  els.addChoicePopup.classList.toggle("hidden");
});

els.addChoicePopup.querySelectorAll("[data-choice]").forEach((button) => {
  button.addEventListener("click", () => {
    els.addChoicePopup.classList.add("hidden");
    openModal(MODAL_BY_CHOICE[button.dataset.choice]);
  });
});

document.addEventListener("click", (event) => {
  if (!els.addChoicePopup.contains(event.target) && event.target !== els.fabAdd) {
    els.addChoicePopup.classList.add("hidden");
  }
});

for (const modal of ALL_MODALS) {
  modal.addEventListener("click", (event) => {
    if (event.target === modal || event.target.closest("[data-close]")) closeModal(modal);
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  els.addChoicePopup.classList.add("hidden");
  ALL_MODALS.forEach(closeModal);
});

function renderMessages() {
  if (state.messages.length === 0) {
    els.messages.innerHTML = '<div class="empty">Hỏi trợ lý gia đình về việc cần nhắc, mua sắm hoặc ghi chú.</div>';
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

function formatDueAt(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return value;
  }
}

// --- Lịch gia đình ---

function renderCalendar(events) {
  if (!events.length) {
    els.calendarList.innerHTML = '<p class="muted-note">Chưa có lịch gia đình.</p>';
    return;
  }
  els.calendarList.replaceChildren(
    ...events.map((event) => {
      const item = document.createElement("div");
      item.className = "crm-item";

      const header = document.createElement("div");
      header.className = "crm-item-header";
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = event.title;
      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", async () => {
        await fetch(`/api/home/calendar/${event.id}`, { method: "DELETE" });
        loadSummary();
      });
      header.append(title, del);

      const meta = document.createElement("div");
      meta.className = "crm-item-meta";
      meta.textContent = `${formatDueAt(event.start_at)}${event.location ? " · " + event.location : ""}`;

      item.append(header, meta);
      return item;
    })
  );
}

els.calendarForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const response = await fetch("/api/home/calendar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: els.calendarTitle.value,
      location: els.calendarLocation.value,
      start_at: new Date(els.calendarStart.value).toISOString(),
      end_at: new Date(els.calendarEnd.value).toISOString(),
    }),
  });
  if (response.ok) {
    els.calendarForm.reset();
    closeModal(els.modalCalendar);
    loadSummary();
  }
});

// --- Nhắc việc ---

function renderReminders(reminders) {
  if (!reminders.length) {
    els.reminderList.innerHTML = '<p class="muted-note">Chưa có việc cần nhắc.</p>';
    return;
  }
  els.reminderList.replaceChildren(
    ...reminders.map((reminder) => {
      const item = document.createElement("div");
      item.className = "crm-item";
      if (reminder.done) item.classList.add("inactive");

      const header = document.createElement("div");
      header.className = "crm-item-header";

      const left = document.createElement("label");
      left.className = "checkbox-line";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = reminder.done;
      checkbox.addEventListener("change", () => completeReminder(reminder.id));
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = reminder.content;
      left.append(checkbox, title);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", () => deleteReminder(reminder.id));
      header.append(left, del);

      item.append(header);
      const due = formatDueAt(reminder.due_at);
      if (due) {
        const meta = document.createElement("div");
        meta.className = "crm-item-meta";
        meta.textContent = `Nhắc lúc: ${due}`;
        item.append(meta);
      }
      return item;
    })
  );
}

async function completeReminder(id) {
  await fetch(`/api/home/reminders/${id}`, { method: "PUT" });
  loadSummary();
}

async function deleteReminder(id) {
  await fetch(`/api/home/reminders/${id}`, { method: "DELETE" });
  loadSummary();
}

els.reminderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = els.reminderInput.value.trim();
  if (!content) return;
  await fetch("/api/home/reminders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  els.reminderForm.reset();
  closeModal(els.modalReminder);
  loadSummary();
});

// --- Mua sắm ---

function renderShopping(items) {
  if (!items.length) {
    els.shoppingList.innerHTML = '<p class="muted-note">Danh sách mua sắm trống.</p>';
    return;
  }
  els.shoppingList.replaceChildren(
    ...items.map((shoppingItem) => {
      const item = document.createElement("div");
      item.className = "crm-item";
      if (shoppingItem.done) item.classList.add("inactive");

      const header = document.createElement("div");
      header.className = "crm-item-header";

      const left = document.createElement("label");
      left.className = "checkbox-line";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = shoppingItem.done;
      checkbox.addEventListener("change", () => checkOffShoppingItem(shoppingItem.id));
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = shoppingItem.content;
      left.append(checkbox, title);

      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", () => deleteShoppingItem(shoppingItem.id));
      header.append(left, del);

      item.append(header);
      if (shoppingItem.quantity) {
        const meta = document.createElement("div");
        meta.className = "crm-item-meta";
        meta.textContent = `Số lượng: ${shoppingItem.quantity}`;
        item.append(meta);
      }
      return item;
    })
  );
}

async function checkOffShoppingItem(id) {
  await fetch(`/api/home/shopping/${id}`, { method: "PUT" });
  loadSummary();
}

async function deleteShoppingItem(id) {
  await fetch(`/api/home/shopping/${id}`, { method: "DELETE" });
  loadSummary();
}

els.shoppingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = els.shoppingInput.value.trim();
  if (!content) return;
  await fetch("/api/home/shopping", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, quantity: els.shoppingQuantityInput.value.trim() }),
  });
  els.shoppingForm.reset();
  closeModal(els.modalShopping);
  loadSummary();
});

// --- Ghi chú ---

function renderNotes(notes) {
  if (!notes.length) {
    els.noteList.innerHTML = '<p class="muted-note">Chưa có ghi chú.</p>';
    return;
  }
  els.noteList.replaceChildren(
    ...notes.map((note) => {
      const item = document.createElement("div");
      item.className = "crm-item";

      const header = document.createElement("div");
      header.className = "crm-item-header";
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = note.content;
      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", () => deleteNote(note.id));
      header.append(title, del);

      item.append(header);
      return item;
    })
  );
}

async function deleteNote(id) {
  await fetch(`/api/home/notes/${id}`, { method: "DELETE" });
  loadSummary();
}

els.noteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = els.noteInput.value.trim();
  if (!content) return;
  await fetch("/api/home/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  els.noteForm.reset();
  closeModal(els.modalNote);
  loadSummary();
});

async function loadSummary() {
  try {
    const response = await fetch("/api/home/summary");
    if (!response.ok) return;
    const data = await response.json();
    renderCalendar(data.calendar_events || []);
    renderReminders(data.reminders || []);
    renderShopping(data.shopping_items || []);
    renderNotes(data.recent_notes || []);
  } catch {
    // ignore, keep last known state
  }
}

// --- Conversation history ---

async function loadConversations() {
  try {
    const response = await fetch("/api/conversations?kind=home");
    const data = await response.json();
    renderHistory(data.conversations || []);
  } catch {
    els.historyList.textContent = "Không tải được lịch sử";
  }
}

function renderHistory(conversations) {
  if (conversations.length === 0) {
    els.historyList.innerHTML = '<p class="muted-note">Chưa có cuộc trò chuyện nào.</p>';
    return;
  }
  els.historyList.replaceChildren(
    ...conversations.map((conversation) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "history-item";
      item.textContent = conversation.title || "Trợ lý gia đình";
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
    renderMessages();
    loadConversations();
  } catch (error) {
    els.status.textContent = error.message;
  }
}

els.newChat.addEventListener("click", () => {
  state.conversationId = null;
  state.messages = [];
  renderMessages();
  loadConversations();
});

// --- Chat ---

async function sendMessage(content) {
  state.messages.push({ role: "user", content });
  renderMessages();
  setBusy(true);
  try {
    const response = await fetch("/api/home/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: content, conversation_id: state.conversationId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Lỗi không xác định");
    state.conversationId = data.conversation_id;
    state.messages.push({ role: "assistant", content: data.reply || "" });
    renderMessages();
    loadConversations();
    loadSummary();
  } catch (error) {
    state.messages.push({ role: "error", content: error.message });
    renderMessages();
  } finally {
    setBusy(false);
  }
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

// --- Init ---

async function init() {
  renderTab();
  let userType = null;
  try {
    const response = await fetch("/api/auth/me");
    const data = await response.json();
    state.authenticated = Boolean(data.authenticated);
    userType = data.user_type;
  } catch {
    state.authenticated = false;
  }

  els.loggedOutNotice.classList.toggle("hidden", state.authenticated);
  els.crmMain.classList.toggle("hidden", !state.authenticated);
  els.fabAdd.classList.toggle("hidden", !state.authenticated);

  if (!state.authenticated) {
    els.status.textContent = "Chưa đăng nhập";
    renderMessages();
    return;
  }

  if (userType !== "admin_user") {
    try {
      const flagsData = await fetch("/api/feature-flags").then((r) => r.json());
      if (flagsData.flags?.home === false) {
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

  els.status.textContent = "Sẵn sàng";
  renderMessages();
  await Promise.all([loadSummary(), loadConversations()]);
}

init();

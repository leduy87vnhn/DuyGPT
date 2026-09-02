const TABS = ["tuvan", "hientrang", "tailieu", "dexuat", "khachhang", "sanpham"];
const SELECTION_TABS = ["tuvan", "hientrang", "tailieu", "dexuat"];

function currentTab() {
  const t = new URLSearchParams(location.search).get("tab");
  return TABS.includes(t) ? t : "tuvan";
}

const state = {
  hasCrmAccess: false,
  customers: [],
  products: [],
  selectedCustomerId: null,
  selectedProductId: null,
  showAllVersions: false,
  editingProposalId: null,
  messages: [],
  conversationId: null,
  busy: false,
};

const els = {
  status: document.querySelector("#status"),
  notAdminNotice: document.querySelector("#notAdminNotice"),
  featureDisabledNotice: document.querySelector("#featureDisabledNotice"),
  crmMain: document.querySelector("#crmMain"),

  contextPanel: document.querySelector("#contextPanel"),
  customerSelect: document.querySelector("#customerSelect"),
  productSelect: document.querySelector("#productSelect"),

  noSelectionNotice: document.querySelector("#noSelectionNotice"),

  customerForm: document.querySelector("#customerForm"),
  customerNameInput: document.querySelector("#customerNameInput"),
  customerList: document.querySelector("#customerList"),

  productForm: document.querySelector("#productForm"),
  productNameInput: document.querySelector("#productNameInput"),
  productList: document.querySelector("#productList"),

  requirementForm: document.querySelector("#requirementForm"),
  currentStateInput: document.querySelector("#currentStateInput"),
  requirementInput: document.querySelector("#requirementInput"),
  requirementList: document.querySelector("#requirementList"),

  documentForm: document.querySelector("#documentForm"),
  documentTitleInput: document.querySelector("#documentTitleInput"),
  documentTypeInput: document.querySelector("#documentTypeInput"),
  documentFileInput: document.querySelector("#documentFileInput"),
  documentError: document.querySelector("#documentError"),
  documentShowAllVersions: document.querySelector("#documentShowAllVersions"),
  documentList: document.querySelector("#documentList"),

  proposalForm: document.querySelector("#proposalForm"),
  proposalTitleInput: document.querySelector("#proposalTitleInput"),
  proposalContentInput: document.querySelector("#proposalContentInput"),
  proposalList: document.querySelector("#proposalList"),

  messages: document.querySelector("#messages"),
  composer: document.querySelector("#composer"),
  prompt: document.querySelector("#prompt"),
  record: document.querySelector("#record"),
  voiceStatus: document.querySelector("#voiceStatus"),
  send: document.querySelector("#send"),
};

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function formatDate(value) {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return value;
  }
}

// Selection is stored in localStorage (not the URL) so it survives switching
// between tabs -- each tab is a normal page navigation (see module-settings.js).
const STORAGE_CUSTOMER_KEY = "crm_selected_customer_id";
const STORAGE_PRODUCT_KEY = "crm_selected_product_id";

function getStoredId(key) {
  const raw = localStorage.getItem(key);
  return raw ? Number(raw) : null;
}

function setStoredId(key, id) {
  if (id) localStorage.setItem(key, String(id));
  else localStorage.removeItem(key);
}

// --- Tab switching ---

function renderTab() {
  const tab = currentTab();
  const ready = Boolean(state.selectedCustomerId && state.selectedProductId);
  const blocked = SELECTION_TABS.includes(tab) && !ready;
  els.noSelectionNotice.classList.toggle("hidden", !blocked);
  for (const t of TABS) {
    document.querySelector(`#tab-${t}`).classList.toggle("hidden", t !== tab || blocked);
  }
}

// --- Customers ---

async function loadCustomers(preselectId) {
  const response = await fetch("/api/crm/customers");
  const data = await response.json();
  state.customers = data.customers || [];
  const keepId = preselectId ?? state.selectedCustomerId;
  els.customerSelect.replaceChildren(
    new Option("-- chọn khách hàng --", ""),
    ...state.customers.map((c) => new Option(c.name, String(c.id)))
  );
  const stillExists = state.customers.some((c) => c.id === keepId);
  els.customerSelect.value = stillExists ? String(keepId) : "";
  state.selectedCustomerId = stillExists ? keepId : null;
  setStoredId(STORAGE_CUSTOMER_KEY, state.selectedCustomerId);
  renderCustomerList();
  renderTab();
}

function renderCustomerList() {
  if (!state.customers.length) {
    els.customerList.innerHTML = '<p class="muted-note">Chưa có khách hàng nào.</p>';
    return;
  }
  els.customerList.replaceChildren(
    ...state.customers.map((customer) => {
      const item = document.createElement("div");
      item.className = "crm-item";

      const header = document.createElement("div");
      header.className = "crm-item-header";
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = customer.name;
      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", async () => {
        if (!confirm(`Xóa khách hàng "${customer.name}" và toàn bộ dữ liệu liên quan?`)) return;
        await fetch(`/api/crm/customers/${customer.id}`, { method: "DELETE" });
        if (state.selectedCustomerId === customer.id) state.selectedCustomerId = null;
        await loadCustomers();
      });
      header.append(title, del);

      const notes = document.createElement("textarea");
      notes.rows = 2;
      notes.placeholder = "Ghi chú khách hàng...";
      notes.value = customer.notes || "";
      const save = document.createElement("button");
      save.type = "button";
      save.className = "secondary small";
      save.textContent = "Lưu ghi chú";
      save.addEventListener("click", async () => {
        await fetch(`/api/crm/customers/${customer.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: customer.name, notes: notes.value }),
        });
        await loadCustomers();
      });

      item.append(header, notes, save);
      return item;
    })
  );
}

els.customerSelect.addEventListener("change", () => {
  state.selectedCustomerId = els.customerSelect.value ? Number(els.customerSelect.value) : null;
  setStoredId(STORAGE_CUSTOMER_KEY, state.selectedCustomerId);
  onSelectionChange();
});

els.customerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = els.customerNameInput.value.trim();
  if (!name) return;
  const response = await fetch("/api/crm/customers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await response.json();
  els.customerForm.reset();
  if (response.ok) await loadCustomers(data.id);
});

// --- Products ---

async function loadProducts(preselectId) {
  const response = await fetch("/api/crm/products");
  const data = await response.json();
  state.products = data.products || [];
  const keepId = preselectId ?? state.selectedProductId;
  els.productSelect.replaceChildren(
    new Option("-- chọn sản phẩm --", ""),
    ...state.products.map((p) => new Option(p.name, String(p.id)))
  );
  const stillExists = state.products.some((p) => p.id === keepId);
  els.productSelect.value = stillExists ? String(keepId) : "";
  state.selectedProductId = stillExists ? keepId : null;
  setStoredId(STORAGE_PRODUCT_KEY, state.selectedProductId);
  renderProductList();
  renderTab();
}

function renderProductList() {
  if (!state.products.length) {
    els.productList.innerHTML = '<p class="muted-note">Chưa có sản phẩm nào.</p>';
    return;
  }
  els.productList.replaceChildren(
    ...state.products.map((product) => {
      const item = document.createElement("div");
      item.className = "crm-item";

      const header = document.createElement("div");
      header.className = "crm-item-header";
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = product.name;
      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", async () => {
        if (!confirm(`Xóa sản phẩm "${product.name}" và toàn bộ dữ liệu liên quan?`)) return;
        await fetch(`/api/crm/products/${product.id}`, { method: "DELETE" });
        if (state.selectedProductId === product.id) state.selectedProductId = null;
        await loadProducts();
      });
      header.append(title, del);

      item.append(header);
      return item;
    })
  );
}

els.productSelect.addEventListener("change", () => {
  state.selectedProductId = els.productSelect.value ? Number(els.productSelect.value) : null;
  setStoredId(STORAGE_PRODUCT_KEY, state.selectedProductId);
  onSelectionChange();
});

els.productForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = els.productNameInput.value.trim();
  if (!name) return;
  const response = await fetch("/api/crm/products", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await response.json();
  els.productForm.reset();
  if (response.ok) await loadProducts(data.id);
});

// --- Selection ---

function onSelectionChange() {
  renderTab();
  if (!state.selectedCustomerId || !state.selectedProductId) return;
  state.messages = [];
  state.conversationId = null;
  renderMessages();
  loadRequirements();
  loadDocuments();
  loadProposals();
}

// --- Requirements ---

async function loadRequirements() {
  const response = await fetch(
    `/api/crm/requirements?customer_id=${state.selectedCustomerId}&product_id=${state.selectedProductId}`
  );
  const data = await response.json();
  renderRequirements(data.requirements || []);
}

function renderRequirements(requirements) {
  if (!requirements.length) {
    els.requirementList.innerHTML = '<p class="muted-note">Chưa có mục ghi nhận nào.</p>';
    return;
  }
  els.requirementList.replaceChildren(
    ...requirements.map((r) => {
      const item = document.createElement("div");
      item.className = "crm-item";

      const header = document.createElement("div");
      header.className = "crm-item-header";
      const meta = document.createElement("span");
      meta.className = "crm-item-meta";
      meta.textContent = formatDate(r.created_at);
      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", async () => {
        await fetch(`/api/crm/requirements/${r.id}`, { method: "DELETE" });
        loadRequirements();
      });
      header.append(meta, del);

      const body = document.createElement("div");
      body.className = "crm-item-body";
      if (r.current_state) {
        const stateEl = document.createElement("div");
        stateEl.textContent = `Hiện trạng: ${r.current_state}`;
        body.append(stateEl);
      }
      if (r.requirement) {
        const reqEl = document.createElement("div");
        reqEl.textContent = `Yêu cầu: ${r.requirement}`;
        body.append(reqEl);
      }

      item.append(header, body);
      return item;
    })
  );
}

els.requirementForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const currentState = els.currentStateInput.value.trim();
  const requirement = els.requirementInput.value.trim();
  if (!currentState && !requirement) return;
  await fetch("/api/crm/requirements", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      customer_id: state.selectedCustomerId,
      product_id: state.selectedProductId,
      current_state: currentState,
      requirement,
    }),
  });
  els.requirementForm.reset();
  loadRequirements();
});

// --- Documents ---

els.documentShowAllVersions.addEventListener("change", () => {
  state.showAllVersions = els.documentShowAllVersions.checked;
  loadDocuments();
});

async function loadDocuments() {
  const allParam = state.showAllVersions ? "&all=1" : "";
  const response = await fetch(
    `/api/crm/documents?customer_id=${state.selectedCustomerId}&product_id=${state.selectedProductId}${allParam}`
  );
  const data = await response.json();
  renderDocuments(data.documents || []);
}

const DOC_TYPE_LABELS = { memo: "Memo", proposal_file: "File đề án", other: "Khác" };

function renderDocuments(documents) {
  if (!documents.length) {
    els.documentList.innerHTML = '<p class="muted-note">Chưa có tài liệu nào.</p>';
    return;
  }
  els.documentList.replaceChildren(
    ...documents.map((doc) => {
      const item = document.createElement("div");
      item.className = "crm-item";

      const header = document.createElement("div");
      header.className = "crm-item-header";
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = doc.title;
      const actions = document.createElement("div");
      actions.className = "crm-item-actions";
      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", async () => {
        await fetch(`/api/crm/documents/${doc.id}`, { method: "DELETE" });
        loadDocuments();
      });
      actions.append(del);
      header.append(title, actions);

      const meta = document.createElement("div");
      meta.className = "crm-item-meta";
      meta.textContent = `${DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type} · phiên bản ${doc.version}${
        doc.is_current ? "" : " (cũ)"
      } · ${doc.filename} · ${formatDate(doc.created_at)}`;

      item.append(header, meta);
      return item;
    })
  );
}

els.documentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.documentError.textContent = "";
  const file = els.documentFileInput.files[0];
  if (!file) return;
  try {
    const contentBase64 = await readFileAsBase64(file);
    const response = await fetch("/api/crm/documents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_id: state.selectedCustomerId,
        product_id: state.selectedProductId,
        doc_type: els.documentTypeInput.value,
        title: els.documentTitleInput.value.trim() || file.name,
        filename: file.name,
        content_base64: contentBase64,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Upload thất bại");
    els.documentForm.reset();
    loadDocuments();
  } catch (error) {
    els.documentError.textContent = error.message;
  }
});

// --- Proposals ---

const PROPOSAL_STATUS_LABELS = { draft: "Nháp", finalized: "Đã chốt", superseded: "Đã thay thế" };

async function loadProposals() {
  const response = await fetch(
    `/api/crm/proposals?customer_id=${state.selectedCustomerId}&product_id=${state.selectedProductId}`
  );
  const data = await response.json();
  renderProposals(data.proposals || []);
}

function renderProposals(proposals) {
  if (!proposals.length) {
    els.proposalList.innerHTML = '<p class="muted-note">Chưa có đề xuất nào.</p>';
    return;
  }
  els.proposalList.replaceChildren(
    ...proposals.map((proposal) => {
      const item = document.createElement("div");
      item.className = "crm-item";

      if (state.editingProposalId === proposal.id) {
        const titleInput = document.createElement("input");
        titleInput.value = proposal.title;
        const contentInput = document.createElement("textarea");
        contentInput.rows = 6;
        contentInput.value = proposal.content;
        const actions = document.createElement("div");
        actions.className = "crm-item-actions";
        const save = document.createElement("button");
        save.type = "button";
        save.textContent = "Lưu";
        save.addEventListener("click", async () => {
          await fetch(`/api/crm/proposals/${proposal.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: titleInput.value.trim(), content: contentInput.value.trim() }),
          });
          state.editingProposalId = null;
          loadProposals();
        });
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "secondary";
        cancel.textContent = "Hủy";
        cancel.addEventListener("click", () => {
          state.editingProposalId = null;
          loadProposals();
        });
        actions.append(save, cancel);
        item.append(titleInput, contentInput, actions);
        return item;
      }

      if (!proposal.is_active) item.classList.add("inactive");

      const header = document.createElement("div");
      header.className = "crm-item-header";
      const title = document.createElement("span");
      title.className = "crm-item-title";
      title.textContent = proposal.title || "(không có tiêu đề)";
      const badge = document.createElement("span");
      badge.className = `status-badge ${proposal.status}`;
      badge.textContent = PROPOSAL_STATUS_LABELS[proposal.status] || proposal.status;
      const left = document.createElement("div");
      left.append(title, document.createTextNode(" "), badge);
      if (!proposal.is_active) {
        const inactiveBadge = document.createElement("span");
        inactiveBadge.className = "status-badge superseded";
        inactiveBadge.textContent = "Inactive";
        left.append(document.createTextNode(" "), inactiveBadge);
      }

      const actions = document.createElement("div");
      actions.className = "crm-item-actions";
      if (proposal.status === "draft") {
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "secondary small";
        edit.textContent = "Sửa";
        edit.addEventListener("click", () => {
          state.editingProposalId = proposal.id;
          loadProposals();
        });
        const finalize = document.createElement("button");
        finalize.type = "button";
        finalize.className = "small";
        finalize.textContent = "Chốt";
        finalize.addEventListener("click", async () => {
          if (!confirm(`Chốt đề xuất "${proposal.title || proposal.id}" để triển khai? Đề xuất đã chốt trước đó (nếu có) sẽ chuyển thành "đã thay thế".`)) return;
          await fetch(`/api/crm/proposals/${proposal.id}/finalize`, { method: "PUT" });
          loadProposals();
        });
        actions.append(edit, finalize);
      }
      const toggleActive = document.createElement("button");
      toggleActive.type = "button";
      toggleActive.className = "secondary small";
      toggleActive.textContent = proposal.is_active ? "Inactive hóa" : "Kích hoạt lại";
      toggleActive.addEventListener("click", async () => {
        await fetch(`/api/crm/proposals/${proposal.id}/active`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active: !proposal.is_active }),
        });
        loadProposals();
      });
      actions.append(toggleActive);
      const del = document.createElement("button");
      del.type = "button";
      del.className = "secondary small";
      del.textContent = "Xóa";
      del.addEventListener("click", async () => {
        if (!confirm("Xóa đề xuất này?")) return;
        await fetch(`/api/crm/proposals/${proposal.id}`, { method: "DELETE" });
        loadProposals();
      });
      actions.append(del);

      header.append(left, actions);

      const body = document.createElement("div");
      body.className = "crm-item-body";
      body.textContent = proposal.content;

      const meta = document.createElement("div");
      meta.className = "crm-item-meta";
      meta.textContent = proposal.finalized_at
        ? `Chốt lúc ${formatDate(proposal.finalized_at)}`
        : `Tạo lúc ${formatDate(proposal.created_at)} · Cập nhật ${formatDate(proposal.updated_at)}`;

      const attachmentList = document.createElement("div");
      attachmentList.className = "attachment-list";
      attachmentList.append(
        ...proposal.attachments.map((att) => {
          const row = document.createElement("div");
          row.className = "attachment-item";
          const name = document.createElement("span");
          name.textContent = att.filename;
          const removeBtn = document.createElement("button");
          removeBtn.type = "button";
          removeBtn.className = "secondary small";
          removeBtn.textContent = "Gỡ";
          removeBtn.addEventListener("click", async () => {
            await fetch(`/api/crm/proposals/${proposal.id}/attachments/${att.id}`, { method: "DELETE" });
            loadProposals();
          });
          row.append(name, removeBtn);
          return row;
        })
      );

      const uploadRow = document.createElement("div");
      uploadRow.className = "attachment-upload";
      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = ".docx,.pptx,.xlsx,.pdf";
      const uploadBtn = document.createElement("button");
      uploadBtn.type = "button";
      uploadBtn.className = "secondary small";
      uploadBtn.textContent = "Đính kèm file (docx/pptx/xlsx/pdf)";
      const uploadError = document.createElement("span");
      uploadError.className = "auth-error";
      uploadBtn.addEventListener("click", async () => {
        const file = fileInput.files[0];
        if (!file) return;
        uploadError.textContent = "";
        try {
          const contentBase64 = await readFileAsBase64(file);
          const response = await fetch(`/api/crm/proposals/${proposal.id}/attachments`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: file.name, content_base64: contentBase64 }),
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.error || "Upload thất bại");
          loadProposals();
        } catch (error) {
          uploadError.textContent = error.message;
        }
      });
      uploadRow.append(fileInput, uploadBtn, uploadError);

      item.append(header, body, meta, attachmentList, uploadRow);
      return item;
    })
  );
}

els.proposalForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = els.proposalContentInput.value.trim();
  if (!content) return;
  await fetch("/api/crm/proposals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      customer_id: state.selectedCustomerId,
      product_id: state.selectedProductId,
      title: els.proposalTitleInput.value.trim(),
      content,
    }),
  });
  els.proposalForm.reset();
  loadProposals();
});

// --- Consult chat ---

function setBusy(value) {
  state.busy = value;
  els.send.disabled = value;
  els.prompt.disabled = value;
  els.record.disabled = value;
}

attachVoiceInput({ button: els.record, textarea: els.prompt, status: els.voiceStatus, onBusyChange: setBusy });

function autoSize() {
  els.prompt.style.height = "auto";
  els.prompt.style.height = `${Math.min(els.prompt.scrollHeight, 320)}px`;
}

function renderMessages() {
  if (state.messages.length === 0) {
    els.messages.innerHTML = '<div class="empty">Hỏi trợ lý về hiện trạng, yêu cầu, tài liệu, hoặc xin đề xuất giải pháp.</div>';
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
    const response = await fetch("/api/crm/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_id: state.selectedCustomerId,
        product_id: state.selectedProductId,
        message: content,
        conversation_id: state.conversationId,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Lỗi không xác định");
    state.conversationId = data.conversation_id;
    state.messages.push({ role: "assistant", content: data.reply || "" });
    renderMessages();
    if ((data.tool_calls || []).length) {
      loadRequirements();
      loadDocuments();
      loadProposals();
    }
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
  if (!state.selectedCustomerId || !state.selectedProductId) return;
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
  let auth = { authenticated: false, user_type: null };
  try {
    const response = await fetch("/api/auth/me");
    auth = await response.json();
  } catch {
    // ignore, treated as not authenticated
  }
  state.hasCrmAccess = auth.authenticated && Boolean(auth.crm_access);
  let disabledByAdmin = false;

  if (state.hasCrmAccess && auth.user_type !== "admin_user") {
    try {
      const flagsData = await fetch("/api/feature-flags").then((r) => r.json());
      if (flagsData.flags?.crm === false) {
        state.hasCrmAccess = false;
        disabledByAdmin = true;
      }
    } catch {
      // ignore, fall through with existing access
    }
  }

  els.notAdminNotice.classList.toggle("hidden", state.hasCrmAccess || disabledByAdmin);
  els.featureDisabledNotice.classList.toggle("hidden", !disabledByAdmin);
  els.contextPanel.classList.toggle("hidden", !state.hasCrmAccess);
  els.crmMain.classList.toggle("hidden", !state.hasCrmAccess);

  if (!state.hasCrmAccess) {
    els.status.textContent = "Không có quyền truy cập";
    return;
  }

  els.status.textContent = "Sẵn sàng";
  await loadProducts(getStoredId(STORAGE_PRODUCT_KEY));
  await loadCustomers(getStoredId(STORAGE_CUSTOMER_KEY));
}

init();

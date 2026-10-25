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

function canEditCustomer(customerId = state.selectedCustomerId) {
  return state.customers.some(customer => customer.id === customerId && customer.is_owner === true);
}

function updateCustomerPermissions() {
  const editable = canEditCustomer();
  for (const form of [els.requirementForm, els.documentForm, els.proposalForm]) {
    form.classList.toggle('hidden', !editable);
  }
}

async function showCustomerSharing(customer) {
  const dialog = document.createElement('dialog');
  dialog.className = 'crm-share-dialog';
  const heading = document.createElement('h3'); heading.textContent = `Share — ${customer.name}`;
  const note = document.createElement('p');
  note.textContent = 'Chọn người được xem tài liệu, requirement và chat về khách hàng này. Bỏ tick để thu hồi quyền. Chỉ người tạo được sửa dữ liệu.';
  const list = document.createElement('div'); list.className = 'crm-share-users';
  const error = document.createElement('p'); error.className = 'auth-error'; error.setAttribute('role', 'status');
  const actions = document.createElement('div'); actions.className = 'crm-item-actions';
  const save = document.createElement('button'); save.type = 'button'; save.textContent = 'Lưu chia sẻ'; save.disabled = true;
  const close = document.createElement('button'); close.type = 'button'; close.className = 'secondary'; close.textContent = 'Đóng';
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => dialog.remove());
  actions.append(save, close); dialog.append(heading, note, list, error, actions);
  document.body.append(dialog); dialog.showModal();
  try {
    const data = await crmRequest(`/api/crm/customers/${customer.id}/shares`);
    for (const user of data.users) {
      const label = document.createElement('label'); label.className = 'checkbox-line';
      const input = document.createElement('input'); input.type = 'checkbox'; input.value = String(user.id); input.checked = user.shared;
      label.append(input, document.createTextNode(user.username)); list.append(label);
    }
    if (!data.users.length) list.textContent = 'Chưa có người dùng khác được cấp quyền CRM.';
    save.disabled = false;
    save.addEventListener('click', async () => {
      save.disabled = true; error.textContent = '';
      try {
        await crmRequest(`/api/crm/customers/${customer.id}/shares`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_ids: [...list.querySelectorAll('input:checked')].map(input => Number(input.value)) }),
        });
        dialog.close();
      } catch (failure) { error.textContent = failure.message; }
      finally { save.disabled = false; }
    });
  } catch (failure) { error.textContent = failure.message; }
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
      header.append(title);
      if (customer.is_owner) {
        const share = document.createElement('button'); share.type = 'button'; share.className = 'secondary small';
        share.textContent = 'Share'; share.addEventListener('click', () => showCustomerSharing(customer));
        header.append(share, del);
      } else {
        const badge = document.createElement('span'); badge.className = 'crm-item-meta'; badge.textContent = 'Được chia sẻ · Chỉ xem';
        header.append(badge);
      }

      const notes = document.createElement("textarea");
      notes.rows = 2;
      notes.placeholder = "Ghi chú khách hàng...";
      notes.value = customer.notes || "";
      notes.readOnly = !customer.is_owner;
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

      item.append(header, notes);
      if (customer.is_owner) item.append(save);
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
        try { await crmRequest(`/api/crm/products/${product.id}`, { method: "DELETE" }); }
        catch (error) { alert(error.message); return; }
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
  updateCustomerPermissions();
  renderTab();
  document.querySelector("#documentViewer")?.remove();
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
  const docsResponse = await fetch(`/api/crm/documents?customer_id=${state.selectedCustomerId}&product_id=${state.selectedProductId}`);
  const docs = await docsResponse.json();
  const pending = (docs.documents || []).filter(d => d.analysis_status !== 'ready');
  document.querySelector('#requirementAnalysisNotice').textContent = pending.length
    ? `${pending.length} tài liệu mới nhất chưa phân tích xong. Mở Tài liệu để phân tích / thử lại; danh sách dưới đây chưa đầy đủ.` : '';
}

async function refreshRequirementViews(documentId) {
  await loadRequirements();
  const viewer = document.querySelector('#documentViewer');
  if (viewer && Number(viewer.dataset.documentId) === documentId) {
    await openDocument(documentId, 'requirements');
  }
}

function deleteAllRequirementsButton(doc) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'secondary small';
  button.title = 'Xóa tất cả requirement của phiên bản này';
  button.setAttribute('aria-label', `Xóa tất cả requirement: ${doc.title}, phiên bản ${doc.version}`);
  button.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg>';
  button.append(document.createTextNode(' Xóa tất cả requirement'));
  button.addEventListener('click', async () => {
    if (!confirm(`Xóa toàn bộ requirement của "${doc.title}" — phiên bản ${doc.version}? File gốc vẫn được giữ lại.`)) return;
    button.disabled = true;
    try {
      await crmRequest(`/api/crm/documents/${doc.id}/requirements`, { method: 'DELETE' });
      await refreshRequirementViews(doc.id);
      if (!document.querySelector('#documentViewer')) await openDocument(doc.id, 'requirements');
    } catch (error) { alert(error.message); }
    finally { button.disabled = false; }
  });
  return button;
}

function reanalyzeRequirementsButton(doc) {
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'secondary small';
  button.title = 'Xóa và phân tích lại toàn bộ requirement của phiên bản này';
  button.setAttribute('aria-label', `Phân tích lại yêu cầu: ${doc.title}, phiên bản ${doc.version}`);
  button.textContent = 'Phân tích lại yêu cầu';
  button.addEventListener('click', async () => {
    if (!confirm(`Xóa danh sách requirement hiện tại và phân tích lại file "${doc.title}" — phiên bản ${doc.version}?`)) return;
    await generateDocumentRequirements(doc.id, button, document.querySelector('#requirementAnalysisNotice'), true);
  });
  return button;
}

function renderRequirements(requirements, target = els.requirementList) {
  if (!requirements.length) {
    target.innerHTML = '<p class="muted-note">Chưa có mục ghi nhận nào.</p>';
    return;
  }
  target.replaceChildren(
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
      del.addEventListener('click', async () => {
        if (!confirm('Xóa requirement này khỏi danh sách?')) return;
        del.disabled = true;
        try {
          await crmRequest(r.document_id ? `/api/crm/document-requirements/${r.id}` : `/api/crm/requirements/${r.id}`, { method: 'DELETE' });
          await refreshRequirementViews(r.document_id);
        } catch (error) { alert(error.message); }
        finally { del.disabled = false; }
      });
      header.append(meta);
      if (r.document_id) {
        meta.textContent = `${r.document_title} · phiên bản ${r.version}`;
        const label = document.createElement('label'); label.className = 'requirement-status';
        label.append(document.createTextNode('Trạng thái '));
        const select = document.createElement('select');
        select.setAttribute('aria-label', `Trạng thái: ${r.requirement}`);
        for (const [value, text] of [['todo', 'To Do'], ['progress', 'Progress'], ['done', 'Done'], ['rejected', 'Rejected']]) {
          select.append(new Option(text, value));
        }
        r.status = r.status || (r.completed ? 'done' : 'todo');
        select.value = r.status;
        select.disabled = !canEditCustomer();
        select.addEventListener('change', async () => {
          select.disabled = true;
          try {
            const result = await crmRequest(`/api/crm/document-requirements/${r.id}`, {
              method: 'PUT', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ status: select.value }),
            });
            r.status = result.status; r.completed = result.completed;
          } catch (error) { select.value = r.status; alert(error.message); }
          finally { select.disabled = !canEditCustomer(); }
        });
        label.append(select); header.append(label);
      }
      if (canEditCustomer()) header.append(del);

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

      if (r.document_id) {
        const targets = document.createElement('section'); targets.className = 'requirement-targets';
        const heading = document.createElement('strong'); heading.textContent = 'Ngữ cảnh áp dụng';
        targets.append(heading);
        let known = false;
        for (const [label, value] of [['Module', r.target_module], ['Màn hình', r.target_screen], ['File', r.target_file]]) {
          if (!value) continue;
          const line = document.createElement('div'); line.textContent = `${label}: ${value}`;
          targets.append(line); known = true;
        }
        if (!known) {
          const unknown = document.createElement('p'); unknown.className = 'muted-note';
          unknown.textContent = 'Chưa xác định file / màn hình / module.'; targets.append(unknown);
        }
        if (r.target_evidence) {
          const evidence = document.createElement('details');
          const summary = document.createElement('summary'); summary.textContent = 'Căn cứ xác định ngữ cảnh';
          const text = document.createElement('pre'); text.className = 'document-raw'; text.textContent = r.target_evidence;
          evidence.append(summary, text); targets.append(evidence);
        }
        body.append(targets);
      }
      if (r.source_quote || r.source_context) {
        const context = document.createElement('section'); context.className = 'requirement-context';
        const heading = document.createElement('strong');
        heading.textContent = r.context_start_line ? `Trích dẫn tài liệu · dòng ${r.context_start_line}–${r.context_end_line}` : 'Trích dẫn tài liệu';
        const text = document.createElement('pre'); text.className = 'document-raw';
        text.textContent = r.source_context || r.source_quote;
        context.append(heading, text);
        if (r.document_id) {
          const full = document.createElement('details');
          const summary = document.createElement('summary'); summary.textContent = 'Xem toàn bộ nội dung file';
          const raw = document.createElement('pre'); raw.className = 'document-raw';
          let loaded = false;
          full.addEventListener('toggle', async () => {
            if (!full.open || loaded) return;
            raw.textContent = 'Đang tải…';
            try {
              const doc = await crmRequest(`/api/crm/documents/${r.document_id}`);
              raw.textContent = doc.raw_text; loaded = true;
            } catch (error) { raw.textContent = error.message; }
          });
          full.append(summary, raw); context.append(full);
        }
        body.append(context);
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
        document.querySelector("#documentViewer")?.remove();
        loadDocuments();
        loadRequirements();
      });
      for (const [label, mode] of [['Xem nội dung raw', 'raw'], ['Danh sách requirement', 'requirements']]) {
        const open = document.createElement('button');
        open.type = 'button'; open.className = 'secondary small'; open.textContent = label;
        open.addEventListener('click', () => openDocument(doc.id, mode));
        actions.append(open);
      }
      if (canEditCustomer()) {
        if (doc.analysis_status === 'ready') {
          actions.append(deleteAllRequirementsButton(doc), reanalyzeRequirementsButton(doc));
        }
        actions.append(del);
      }
      header.append(title, actions);

      const meta = document.createElement("div");
      meta.className = "crm-item-meta";
      meta.textContent = `${DOC_TYPE_LABELS[doc.doc_type] || doc.doc_type} · phiên bản ${doc.version}${
        doc.is_current ? "" : " (cũ)"
      } · ${doc.filename} · ${formatDate(doc.created_at)}`;

      const analysis = document.createElement('p');
      analysis.className = 'muted-note';
      analysis.textContent = doc.analysis_status === 'ready' ? 'Đã phân tích yêu cầu' :
        doc.analysis_status === 'failed' ? `Phân tích thất bại: ${doc.analysis_error}` : 'Chưa phân tích yêu cầu';
      analysis.setAttribute('role', 'status');
      if (canEditCustomer() && doc.analysis_status !== 'ready') {
        const generate = document.createElement('button');
        generate.type = 'button'; generate.className = 'small';
        generate.textContent = 'Tạo danh sách Requirement';
        generate.addEventListener('click', () => generateDocumentRequirements(doc.id, generate, analysis));
        actions.prepend(generate);
      }
      item.append(header, meta, analysis);
      return item;
    })
  );
}

els.documentForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  els.documentError.textContent = "";
  const file = els.documentFileInput.files[0];
  if (!file) return;
  const submit = els.documentForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  els.documentError.textContent = 'Đang upload và phân tích yêu cầu bằng AI…';
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
    els.documentError.textContent = data.analysis_status === 'failed'
      ? `Đã lưu file. Phân tích chưa thành công: ${data.analysis_error}. Mở danh sách requirement để thử lại.`
      : 'Đã lưu file và phân tích yêu cầu.';
    loadDocuments();
    loadRequirements();
  } catch (error) {
    els.documentError.textContent = error.message;
  } finally { submit.disabled = false; }
});

async function crmRequest(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Không thực hiện được yêu cầu');
  return data;
}

async function generateDocumentRequirements(id, button, status, force = false) {
  const customerId = state.selectedCustomerId;
  const productId = state.selectedProductId;
  const label = button.textContent;
  button.disabled = true;
  button.textContent = 'Đang tạo…';
  status.textContent = 'AI đang phân tích file và tạo danh sách Requirement… Thời gian chờ AI tối đa 30 phút mỗi lượt. Vui lòng giữ trang mở.';
  try {
    const result = await crmRequest(`/api/crm/documents/${id}/analyze${force ? '?force=1' : ''}`, { method: 'POST' });
    if (customerId !== state.selectedCustomerId || productId !== state.selectedProductId) return;
    if (result.analysis_status === 'running') {
      status.textContent = 'File này đang được phân tích. Hãy mở lại danh sách sau khi hoàn tất.';
    } else if (result.analysis_status === 'failed') {
      status.textContent = `Chưa tạo được danh sách: ${result.analysis_error || 'Vui lòng thử lại.'}`;
    } else if (result.analysis_status === 'ready') {
      await openDocument(id, 'requirements');
      await Promise.all([loadDocuments(), loadRequirements()]);
    } else {
      throw new Error('Chưa nhận được kết quả phân tích. Vui lòng thử lại.');
    }
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

async function openDocument(id, mode = 'raw') {
  document.querySelector('#documentViewer')?.remove();
  const viewer = document.createElement('section');
  viewer.id = 'documentViewer'; viewer.className = 'panel';
  viewer.dataset.documentId = String(id);
  viewer.textContent = 'Đang tải…';
  els.documentList.before(viewer);
  try {
    const doc = await crmRequest(`/api/crm/documents/${id}`);
    if (!viewer.isConnected) return;
    viewer.replaceChildren();
    const heading = document.createElement('h3');
    heading.textContent = `${doc.title} — phiên bản ${doc.version}`;
    const actions = document.createElement('div'); actions.className = 'crm-item-actions';
    for (const [label, nextMode] of [['Nội dung raw', 'raw'], ['Requirement', 'requirements']]) {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'secondary small'; button.textContent = label;
      button.addEventListener('click', () => openDocument(id, nextMode)); actions.append(button);
    }
    if (doc.has_original) {
      const download = document.createElement('a');
      download.href = `/api/crm/documents/${id}/download`; download.textContent = 'Tải file gốc';
      actions.append(download);
    }
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'secondary small'; close.textContent = 'Đóng';
    close.addEventListener('click', () => viewer.remove()); actions.append(close);
    if (mode === 'requirements' && canEditCustomer() && doc.requirements.length) actions.append(deleteAllRequirementsButton(doc));
    viewer.append(heading, actions);
    if (mode === 'raw') {
      const note = document.createElement('p');
      note.textContent = doc.has_original ? 'Văn bản trích xuất từ file gốc:' :
        'Phiên bản cũ chưa lưu file gốc. Dưới đây là các đoạn văn bản đã lưu, có thể có đoạn trùng nhau.';
      const raw = document.createElement('pre'); raw.className = 'document-raw'; raw.textContent = doc.raw_text;
      viewer.append(note, raw);
    } else {
      if (doc.analysis_status !== 'ready') {
        const note = document.createElement('p');
        note.textContent = doc.analysis_error || 'Phiên bản này chưa có danh sách yêu cầu được phân tích.';
        const retry = document.createElement('button');
        retry.type = 'button'; retry.textContent = 'Tạo danh sách Requirement';
        retry.addEventListener('click', () => generateDocumentRequirements(id, retry, note));
        viewer.append(note);
        if (canEditCustomer()) viewer.append(retry);
        else note.append(document.createTextNode(' Chủ sở hữu có thể chạy phân tích lại.'));
      }
      const list = document.createElement('div'); list.className = 'crm-list';
      renderRequirements(doc.requirements, list); viewer.append(list);
    }
    viewer.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) { viewer.textContent = error.message; }
}

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

      if (!canEditCustomer()) {
        actions.replaceChildren();
        attachmentList.querySelectorAll('button').forEach(button => button.remove());
      }
      item.append(header, body, meta, attachmentList);
      if (canEditCustomer()) item.append(uploadRow);
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
  onSelectionChange();
}

init();

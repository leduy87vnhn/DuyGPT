const $ = (q) => document.querySelector(q);
let me = null;

function renderUsers(users) {
  const list = $("#userList");
  if (!users.length) {
    list.innerHTML = '<p class="muted-note">Chưa có tài khoản nào.</p>';
    return;
  }
  list.innerHTML = "";
  users.forEach((u) => {
    const row = document.createElement("div");
    row.className = "crm-item";

    const header = document.createElement("div");
    header.className = "crm-item-header";
    const left = document.createElement("div");
    const name = document.createElement("span");
    name.className = "crm-item-title";
    name.textContent = u.username + (u.username === me.username ? " (bạn)" : "");
    const badge = document.createElement("span");
    badge.className = "status-badge " + (u.user_type === "admin_user" ? "finalized" : "draft");
    badge.textContent = u.user_type === "admin_user" ? "Admin" : "Thường";
    left.append(name, document.createTextNode(" "), badge);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "secondary small";
    del.textContent = "Xóa";
    del.disabled = u.user_type === "admin_user";
    del.addEventListener("click", async () => {
      if (!confirm(`Xóa tài khoản "${u.username}"?`)) return;
      await fetch(`/api/admin/users/${u.id}`, { method: "DELETE" });
      load();
    });
    header.append(left, del);

    const crmLabel = document.createElement("label");
    crmLabel.className = "checkbox-line";
    const crmCheckbox = document.createElement("input");
    crmCheckbox.type = "checkbox";
    crmCheckbox.checked = u.crm_access;
    crmCheckbox.disabled = u.user_type === "admin_user";
    crmCheckbox.addEventListener("change", async () => {
      await fetch(`/api/admin/users/${u.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ crm_access: crmCheckbox.checked }),
      });
      load();
    });
    const crmText = document.createTextNode(
      u.user_type === "admin_user" ? " Luôn có quyền CRM (admin)" : " Quyền truy cập CRM"
    );
    crmLabel.append(crmCheckbox, crmText);

    row.append(header, crmLabel);
    list.append(row);
  });
}

async function load() {
  let meResp = { authenticated: false };
  try {
    meResp = await fetch("/api/auth/me").then((r) => r.json());
  } catch {
    // ignore, treated as not authenticated
  }
  if (!meResp.authenticated) {
    location.href = "/login";
    return;
  }
  me = meResp;
  const isAdmin = meResp.user_type === "admin_user";
  $("#notAdminNotice").classList.toggle("hidden", isAdmin);
  $("#content").classList.toggle("hidden", !isAdmin);
  $("#status").textContent = isAdmin ? "Sẵn sàng" : "Không có quyền truy cập";
  if (!isAdmin) return;
  const data = await fetch("/api/admin/users").then((r) => r.json());
  renderUsers(data.users || []);
}

$("#createForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#createError").textContent = "";
  const body = {
    username: $("#newUsername").value.trim(),
    password: $("#newPassword").value,
    crm_access: $("#newCrmAccess").checked,
  };
  const response = await fetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    $("#createError").textContent = data.error || "Không tạo được tài khoản";
    return;
  }
  event.target.reset();
  load();
});

load();

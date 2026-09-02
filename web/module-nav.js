(() => {
  const items = [
    ["/login", "Đăng nhập", null], ["/settings", "Cài đặt chung", null], ["/", "ChatGPT", null],
    ["/home", "Trợ lý gia đình", "home"], ["/work", "Trợ lý công việc", "work"], ["/crm", "Quản lý khách hàng", "crm"],
    ["/users", "Quản lý người dùng", null],
  ];
  const path = location.pathname.replace(/\/$/, "") || "/";

  function renderNav(isAdmin, flags) {
    const nav = document.createElement("nav");
    nav.className = "module-nav";
    nav.setAttribute("aria-label", "Chuyển module");
    for (const [href, label, featureKey] of items) {
      if (featureKey && !isAdmin && flags[featureKey] === false) continue;
      const a = document.createElement("a");
      a.href = href; a.textContent = label;
      if (path === href) a.className = "active";
      nav.append(a);
    }
    document.body.prepend(nav);
    const moduleSettings = document.createElement("script");
    moduleSettings.src = "/module-settings.js";
    document.head.append(moduleSettings);
  }

  Promise.all([
    fetch("/api/auth/me").then((r) => r.json()).catch(() => ({ authenticated: false })),
    fetch("/api/feature-flags").then((r) => r.json()).catch(() => ({ flags: {} })),
  ]).then(([auth, featureFlags]) => {
    renderNav(auth.authenticated && auth.user_type === "admin_user", featureFlags.flags || {});
  });
})();

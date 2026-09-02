const form = document.querySelector('#loginForm'), registerForm = document.querySelector('#registerForm');
const logout = document.querySelector('#logout'), state = document.querySelector('#accountState'), error = document.querySelector('#error');
const tabLogin = document.querySelector('#tabLogin'), tabRegister = document.querySelector('#tabRegister');

function setTab(tab) {
  const isLogin = tab === 'login';
  tabLogin.classList.toggle('active', isLogin);
  tabRegister.classList.toggle('active', !isLogin);
  form.classList.toggle('hidden', !isLogin);
  registerForm.classList.toggle('hidden', isLogin);
  error.textContent = '';
}
tabLogin.addEventListener('click', () => setTab('login'));
tabRegister.addEventListener('click', () => setTab('register'));

async function refresh() {
  const d = await fetch('/api/auth/me').then(r => r.json());
  document.querySelector('#authTabs').classList.toggle('hidden', d.authenticated);
  form.classList.toggle('hidden', d.authenticated || !tabLogin.classList.contains('active'));
  registerForm.classList.toggle('hidden', d.authenticated || tabLogin.classList.contains('active'));
  logout.classList.toggle('hidden', !d.authenticated);
  state.textContent = d.authenticated ? `Đang đăng nhập: ${d.username} (${d.user_type})` : 'Chưa đăng nhập';
  if (!d.authenticated) {
    const health = await fetch('/api/health').then(r => r.json());
    tabRegister.classList.toggle('hidden', Boolean(health.disable_registration));
    if (health.disable_registration && !tabLogin.classList.contains('active')) setTab('login');
  }
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  error.textContent = '';
  const r = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: document.querySelector('#username').value, password: document.querySelector('#password').value }),
  });
  const d = await r.json();
  if (!r.ok) { error.textContent = d.error || 'Không đăng nhập được'; return; }
  location.href = '/';
});

registerForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  error.textContent = '';
  const r = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: document.querySelector('#regUsername').value, password: document.querySelector('#regPassword').value }),
  });
  const d = await r.json();
  if (!r.ok) { error.textContent = d.error || 'Không tạo được tài khoản'; return; }
  location.href = '/';
});

logout.addEventListener('click', async () => { await fetch('/api/auth/logout', { method: 'POST' }); refresh(); });
refresh();

/**
 * User Menu — MyNutri AI
 *
 * Inicializa o menu de usuário na navbar:
 *   - Preenche avatar, nome e email a partir do localStorage ou da API
 *   - Alterna entre guestNav e authNav (quando existem)
 *   - Controla abertura/fechamento do dropdown
 *   - Wires o botão de logout
 *
 * Uso:
 *   initUserMenu({ requireAuth, logoutRedirect, onUserLoaded })
 *
 * Opções:
 *   requireAuth    {boolean}  Se true, redireciona para /auth/ quando não logado. Default: false.
 *   logoutRedirect {string}   URL para redirecionar após logout. Default: '/'.
 *   onUserLoaded   {Function} Callback(user) chamado após dados do usuário serem aplicados na UI.
 */
async function initUserMenu(opts) {
  opts = Object.assign({ requireAuth: false, logoutRedirect: '/', onUserLoaded: null }, opts);

  // ── Auth guard ─────────────────────────────────────────────────────────────
  const cached = JSON.parse(localStorage.getItem('mynutri_user') || 'null');

  if (!cached && opts.requireAuth) {
    window.location.href = '/auth/';
    return;
  }

  // ── Aplica dados na UI ──────────────────────────────────────────────────────
  function applyUserUI(user) {
    if (!user?.nome) return;

    const guestNav = document.getElementById('guestNav');
    const authNav  = document.getElementById('authNav');
    if (guestNav) guestNav.style.display = 'none';
    if (authNav)  authNav.style.display  = authNav.classList.contains('user-menu-wrap') ? 'flex' : 'block';

    const navAvatar    = document.getElementById('navAvatar');
    const navName      = document.getElementById('navName');
    const dropdownName  = document.getElementById('dropdownName');
    const dropdownEmail = document.getElementById('dropdownEmail');

    if (navAvatar)    navAvatar.textContent    = initials(user.nome);
    if (navName)      navName.textContent      = user.nome.split(' ')[0];
    if (dropdownName)  dropdownName.textContent  = user.nome;
    if (dropdownEmail) dropdownEmail.textContent = user.email || '';

    if (opts.onUserLoaded) opts.onUserLoaded(user);
  }

  // ── Carrega usuário (cache → API) ───────────────────────────────────────────
  if (cached?.nome) {
    applyUserUI(cached);
  } else {
    try {
      const fetchFn = typeof apiFetch === 'function' ? apiFetch : fetch;
      const res = await fetchFn(`${API_BASE}/user/profile`, { credentials: 'include', redirectOn401: false });

      if (res.status === 401) {
        localStorage.removeItem('mynutri_user');
        if (opts.requireAuth) window.location.href = '/auth/';
        return;
      }

      if (!res.ok) return;

      const profile = await res.json();
      const user = { id: profile.id, email: profile.email, nome: profile.nome };
      localStorage.setItem('mynutri_user', JSON.stringify(user));
      applyUserUI(user);
    } catch {
      // Servidor offline — não altera a UI
    }
  }

  // ── Dropdown toggle ─────────────────────────────────────────────────────────
  const menuBtn  = document.getElementById('userMenuBtn');
  const dropdown = document.getElementById('userDropdown');

  if (menuBtn && dropdown) {
    menuBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      const open = dropdown.classList.toggle('open');
      menuBtn.classList.toggle('open', open);
    });

    document.addEventListener('click', function () {
      dropdown.classList.remove('open');
      menuBtn.classList.remove('open');
    });
  }

  // ── Logout ──────────────────────────────────────────────────────────────────
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', async function () {
      await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
      localStorage.removeItem('mynutri_user');
      window.location.href = opts.logoutRedirect;
    });
  }
}

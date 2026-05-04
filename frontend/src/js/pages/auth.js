(function () {
  const setLoading = setLoadingBtn;

  // --- Google OAuth error param ---
  const googleErrorParam = new URLSearchParams(window.location.search).get('google_error');
  if (googleErrorParam) {
    const googleErrorMessages = {
      csrf: 'Falha de segurança no login com Google. Tente novamente.',
      invalid_token: 'Token Google inválido ou expirado. Tente novamente.',
      no_email: 'Não foi possível obter o e-mail da conta Google.',
      service_unavailable: 'Serviço Google indisponível. Tente mais tarde.',
      no_credential: 'Credencial Google não recebida. Tente novamente.',
    };
    const msg = googleErrorMessages[googleErrorParam] || 'Erro ao autenticar com Google.';
    requestAnimationFrame(function () { showError(msg); });
  }

  // --- Tab switching ---
  const tabs  = document.querySelectorAll('.auth-tab');
  const forms = document.querySelectorAll('.auth-form');

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      tabs.forEach(function (t) { t.classList.remove('active'); });
      forms.forEach(function (f) { f.classList.remove('active'); });
      tab.classList.add('active');
      document.getElementById(tab.getAttribute('data-target')).classList.add('active');
      clearError();
    });
  });

  // --- Intent param ---
  const urlParams = new URLSearchParams(window.location.search);
  const intent = urlParams.get('intent');

  if (intent === 'save_diet') {
    document.getElementById('intent-message').classList.add('visible');
    tabs[1].click();
    document.querySelector('.auth-title').textContent = 'Quase lá!';
    document.querySelector('.auth-subtitle').textContent = 'Faltam poucos segundos para ver sua dieta.';
  }

  // --- Helpers ---
  function showError(msg) {
    let el = document.getElementById('auth-error');
    if (!el) {
      el = document.createElement('p');
      el.id = 'auth-error';
      el.style.cssText = 'color:#dc2626;font-size:.875rem;margin-top:12px;text-align:center;';
      document.querySelector('.auth-card').appendChild(el);
    }
    el.textContent = msg;
  }

  function clearError() {
    const el = document.getElementById('auth-error');
    if (el) el.textContent = '';
  }

  function saveSession(data) {
    // Tokens são guardados em cookies HttpOnly pelo servidor.
    // Só salvamos metadados do usuário no localStorage — não contém credenciais.
    if (data.user) localStorage.setItem('mynutri_user', JSON.stringify(data.user));
  }

  function afterAuth() {
    if (intent === 'save_diet' && sessionStorage.getItem('anamneseData')) {
      window.location.href = '/dieta/?generate=1';
      return;
    }
    const ref = document.referrer;
    const refPath = ref ? new URL(ref).pathname : '';
    const skip = ['/', '/auth/'];
    if (ref && !skip.includes(refPath) && new URL(ref).origin === window.location.origin) {
      window.location.href = ref;
    } else {
      window.location.href = '/dieta/';
    }
  }

  // --- Login ---
  document.getElementById('login-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    clearError();
    const btn   = e.target.querySelector('button[type="submit"]');
    const email = e.target.querySelector('input[type="email"]').value.trim();
    const senha = e.target.querySelector('input[type="password"]').value;

    setLoading(btn, true);
    btn.textContent = 'Entrando...';

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password: senha }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.detail || 'E-mail ou senha inválidos.');
        setLoading(btn, false);
        return;
      }

      saveSession(data);
      afterAuth();
    } catch {
      showError('Erro de conexão. Verifique se o servidor está rodando.');
      setLoading(btn, false);
    }
  });

  // --- Cadastro ---
  document.getElementById('register-form').addEventListener('submit', async function (e) {
    e.preventDefault();
    clearError();
    const btn    = e.target.querySelector('button[type="submit"]');
    const inputs = e.target.querySelectorAll('input');
    const nome   = inputs[0].value.trim();
    const email  = inputs[1].value.trim();
    const senha  = inputs[2].value;

    if (senha.length < 8) {
      showError('A senha deve ter pelo menos 8 caracteres.');
      return;
    }

    setLoading(btn, true);
    btn.textContent = 'Criando conta...';

    try {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ nome, email, senha }),
      });
      const data = await res.json();

      if (!res.ok) {
        const msg = data.email?.[0] || data.senha?.[0] || data.nome?.[0] || 'Erro ao criar conta.';
        showError(msg);
        setLoading(btn, false);
        return;
      }

      saveSession(data);
      afterAuth();
    } catch {
      showError('Erro de conexão. Verifique se o servidor está rodando.');
      setLoading(btn, false);
    }
  });

  // --- Google Sign-In ---
  const GOOGLE_CLIENT_ID = '806980657199-js2h4t4o9cq8577c7geulvgosdt777t2.apps.googleusercontent.com';

  async function handleGoogleCredential(response) {
    clearError();
    if (!response?.credential) {
      showError('Credencial Google inválida. Tente novamente.');
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ id_token: response.credential }),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || `Erro ao autenticar com Google (${res.status}).`);
        return;
      }

      saveSession(data);
      afterAuth();
    } catch (err) {
      showError('Erro de conexão ao autenticar com Google. Verifique se o servidor está rodando.');
    }
  }

  function initGoogleSignIn() {
    if (!window.google) return;
    const loginUri = `${window.location.origin}/api/v1/auth/google/callback`;
    google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      auto_select: false,
      ux_mode: 'redirect',
      login_uri: loginUri,
    });
    const container = document.getElementById('google-btn-hidden');
    const width = Math.min(container.parentElement.offsetWidth || 400, 400);
    google.accounts.id.renderButton(container, { theme: 'outline', size: 'large', width });
  }

  // handleGoogleCredential precisa ser global para o callback da SDK do Google
  window.handleGoogleCredential = handleGoogleCredential;

  if (window.google) {
    initGoogleSignIn();
  } else {
    document.querySelector('script[src*="accounts.google.com"]')
      .addEventListener('load', initGoogleSignIn);
  }
})();

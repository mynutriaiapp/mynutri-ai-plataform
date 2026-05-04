(function () {
  const setLoading = setLoadingById;
  let userData = JSON.parse(localStorage.getItem('mynutri_user') || 'null');

  // --- User menu + sidebar avatar ---
  initUserMenu({
    requireAuth: true,
    logoutRedirect: '/',
    onUserLoaded: function (user) {
      const sidebarAvatar = document.getElementById('sidebarAvatar');
      const sidebarName   = document.getElementById('sidebarName');
      const sidebarEmail  = document.getElementById('sidebarEmail');
      if (sidebarAvatar) sidebarAvatar.textContent = initials(user.nome);
      if (sidebarName)   sidebarName.textContent   = user.nome;
      if (sidebarEmail)  sidebarEmail.textContent  = user.email || '';
    },
  });

  // --- Helpers ---
  function setNavUser(nome, email) {
    document.getElementById('navAvatar').textContent     = initials(nome);
    document.getElementById('navName').textContent       = nome.split(' ')[0];
    document.getElementById('dropdownName').textContent  = nome;
    document.getElementById('dropdownEmail').textContent = email;
    const sidebarAvatar = document.getElementById('sidebarAvatar');
    const sidebarName   = document.getElementById('sidebarName');
    const sidebarEmail  = document.getElementById('sidebarEmail');
    if (sidebarAvatar) sidebarAvatar.textContent = initials(nome);
    if (sidebarName)   sidebarName.textContent   = nome;
    if (sidebarEmail)  sidebarEmail.textContent  = email;
  }

  function showAlert(id, msg) {
    const el = document.getElementById(id);
    el.textContent = msg || el.textContent;
    el.classList.add('show');
    setTimeout(function () { el.classList.remove('show'); }, 4000);
  }

  function hideAlert(id) { document.getElementById(id).classList.remove('show'); }

  // --- Sidebar nav ---
  let originalDados = {};
  document.querySelectorAll('.sidebar-nav-item').forEach(function (item) {
    item.addEventListener('click', function () {
      document.querySelectorAll('.sidebar-nav-item').forEach(function (i) { i.classList.remove('active'); });
      document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('active'); });
      item.classList.add('active');
      document.getElementById('panel-' + item.dataset.panel).classList.add('active');

      if (item.dataset.panel === 'nutricional') loadNutricional();
    });
  });

  // --- Load profile from API ---
  async function loadProfile() {
    try {
      const res = await apiFetch(`${API_BASE}/user/profile`);

      if (res.status === 401) { window.location.href = '/auth/'; return; }
      if (!res.ok) throw new Error('Erro ao carregar perfil');

      const data = await res.json();

      const parts     = (data.nome || '').split(' ');
      const firstName = parts[0] || '';
      const lastName  = parts.slice(1).join(' ') || '';

      document.getElementById('inputFirstName').value = firstName;
      document.getElementById('inputLastName').value  = lastName;
      document.getElementById('inputEmail').value     = data.email || '';
      document.getElementById('inputPhone').value     = data.phone || '';
      document.getElementById('inputDob').value       = data.date_of_birth || '';

      originalDados = { firstName, lastName, phone: data.phone || '', dob: data.date_of_birth || '' };

      const nomeCompleto = data.nome || data.email;
      setNavUser(nomeCompleto, data.email);

      if (userData) {
        userData.nome = nomeCompleto;
        localStorage.setItem('mynutri_user', JSON.stringify(userData));
      }
    } catch (err) {
      console.error(err);
    }
  }

  // --- Save personal data ---
  document.getElementById('formDados').addEventListener('submit', async function (e) {
    e.preventDefault();
    hideAlert('alertDadosOk');
    hideAlert('alertDadosErr');

    const first_name    = document.getElementById('inputFirstName').value.trim();
    const last_name     = document.getElementById('inputLastName').value.trim();
    const phone         = document.getElementById('inputPhone').value.trim();
    const date_of_birth = document.getElementById('inputDob').value || null;

    if (!first_name) {
      showAlert('alertDadosErr', 'O nome é obrigatório.');
      return;
    }

    setLoading('btnSaveDados', 'spinnerDados', true);

    try {
      const res = await apiFetch(`${API_BASE}/user/profile`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ first_name, last_name, phone, date_of_birth }),
      });

      const json = await res.json();
      if (!res.ok) {
        const msg = Object.values(json).flat().join(' ');
        showAlert('alertDadosErr', msg || 'Erro ao salvar.');
        return;
      }

      const nomeCompleto = json.nome || `${first_name} ${last_name}`.trim();
      setNavUser(nomeCompleto, json.email);
      if (userData) {
        userData.nome = nomeCompleto;
        localStorage.setItem('mynutri_user', JSON.stringify(userData));
      }
      originalDados = { firstName: first_name, lastName: last_name, phone, dob: date_of_birth || '' };
      showAlert('alertDadosOk');
    } catch {
      showAlert('alertDadosErr', 'Erro de conexão. Verifique se o servidor está rodando.');
    } finally {
      setLoading('btnSaveDados', 'spinnerDados', false);
    }
  });

  // --- Cancel personal data ---
  document.getElementById('btnCancelDados').addEventListener('click', function () {
    document.getElementById('inputFirstName').value = originalDados.firstName;
    document.getElementById('inputLastName').value  = originalDados.lastName;
    document.getElementById('inputPhone').value     = originalDados.phone;
    document.getElementById('inputDob').value       = originalDados.dob;
    hideAlert('alertDadosOk');
    hideAlert('alertDadosErr');
  });

  // --- Load nutritional profile ---
  async function loadNutricional() {
    const container = document.getElementById('nutricionalContent');
    container.innerHTML = `<div style="display:flex;align-items:center;gap:10px;color:var(--gray-400);font-size:.9rem;"><div class="spinner" style="width:24px;height:24px;border-width:3px;"></div>Carregando…</div>`;

    try {
      const res = await apiFetch(`${API_BASE}/anamnese`);

      if (res.status === 404 || res.status === 204) {
        container.innerHTML = `
          <div class="empty-state">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C8 2 5 6 5 10c0 5 7 12 7 12s7-7 7-12c0-4-3-8-7-8z"/><circle cx="12" cy="10" r="2"/></svg>
            <p>Você ainda não preencheu o questionário nutricional.</p>
            <a href="/questionario/" class="btn-save" style="text-decoration:none;display:inline-flex;">Preencher Questionário</a>
          </div>`;
        return;
      }

      if (!res.ok) throw new Error();

      const d = await res.json();

      const goalMap     = { lose: 'Emagrecimento', maintain: 'Manutenção', gain: 'Hipertrofia' };
      const activityMap = { sedentary: 'Sedentário', light: 'Levemente ativo', moderate: 'Moderadamente ativo', intense: 'Muito ativo', athlete: 'Atleta' };
      const genderMap   = { M: 'Masculino', F: 'Feminino', O: 'Outro' };

      container.innerHTML = `
        <div class="info-grid">
          <div class="info-item">
            <div class="info-item-label">Sexo</div>
            <div class="info-item-value">${genderMap[d.sexo] || d.sexo || '—'}</div>
          </div>
          <div class="info-item">
            <div class="info-item-label">Idade</div>
            <div class="info-item-value">${d.idade ? d.idade + ' anos' : '—'}</div>
          </div>
          <div class="info-item">
            <div class="info-item-label">Peso</div>
            <div class="info-item-value">${d.peso ? d.peso + ' kg' : '—'}</div>
          </div>
          <div class="info-item">
            <div class="info-item-label">Altura</div>
            <div class="info-item-value">${d.altura ? d.altura + ' cm' : '—'}</div>
          </div>
          <div class="info-item">
            <div class="info-item-label">Objetivo</div>
            <div class="info-item-value"><span class="badge badge-green">${goalMap[d.objetivo] || d.objetivo || '—'}</span></div>
          </div>
          <div class="info-item">
            <div class="info-item-label">Nível de Atividade</div>
            <div class="info-item-value"><span class="badge badge-blue">${activityMap[d.nivel_atividade] || d.nivel_atividade || '—'}</span></div>
          </div>
          <div class="info-item">
            <div class="info-item-label">Refeições/dia</div>
            <div class="info-item-value">${d.meals_per_day || '—'}</div>
          </div>
          ${d.restricoes ? `<div class="info-item"><div class="info-item-label">Restrições</div><div class="info-item-value" style="font-size:.875rem;">${d.restricoes}</div></div>` : ''}
          ${d.allergies  ? `<div class="info-item"><div class="info-item-label">Alergias</div><div class="info-item-value" style="font-size:.875rem;">${d.allergies}</div></div>` : ''}
          ${d.food_preferences ? `<div class="info-item"><div class="info-item-label">Preferências</div><div class="info-item-value" style="font-size:.875rem;">${d.food_preferences}</div></div>` : ''}
        </div>
        <p style="margin-top:16px;font-size:.8125rem;color:var(--gray-400);">Para alterar esses dados, <a href="/questionario/" style="color:var(--green-600);">refaça o questionário</a>.</p>`;
    } catch {
      container.innerHTML = `<p style="color:var(--gray-400);font-size:.9rem;">Não foi possível carregar o perfil nutricional.</p>`;
    }
  }

  // --- Password strength ---
  document.getElementById('inputNovaSenha').addEventListener('input', function () {
    const val   = this.value;
    const fill  = document.getElementById('strengthFill');
    const label = document.getElementById('strengthLabel');
    let strength = 0;
    if (val.length >= 8)           strength++;
    if (/[A-Z]/.test(val))         strength++;
    if (/[0-9]/.test(val))         strength++;
    if (/[^A-Za-z0-9]/.test(val))  strength++;

    const configs = [
      { w: '0%',   bg: 'transparent', text: '' },
      { w: '25%',  bg: '#ef4444',     text: 'Fraca' },
      { w: '50%',  bg: '#f97316',     text: 'Razoável' },
      { w: '75%',  bg: '#eab308',     text: 'Boa' },
      { w: '100%', bg: '#22c55e',     text: 'Forte' },
    ];
    fill.style.width      = configs[strength].w;
    fill.style.background = configs[strength].bg;
    label.textContent     = configs[strength].text;
  });

  // --- Save password ---
  document.getElementById('formSenha').addEventListener('submit', async function (e) {
    e.preventDefault();
    hideAlert('alertSenhaOk');
    hideAlert('alertSenhaErr');

    const atual     = document.getElementById('inputSenhaAtual').value;
    const nova      = document.getElementById('inputNovaSenha').value;
    const confirmar = document.getElementById('inputConfirmarSenha').value;

    if (!atual || !nova || !confirmar) {
      showAlert('alertSenhaErr', 'Preencha todos os campos.');
      return;
    }
    if (nova.length < 8) {
      showAlert('alertSenhaErr', 'A nova senha deve ter pelo menos 8 caracteres.');
      return;
    }
    if (nova !== confirmar) {
      showAlert('alertSenhaErr', 'As senhas não coincidem.');
      return;
    }

    setLoading('btnSaveSenha', 'spinnerSenha', true);

    try {
      const res = await apiFetch(`${API_BASE}/user/change-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: atual, new_password: nova }),
      });

      if (res.status === 404) {
        showAlert('alertSenhaErr', 'Endpoint de alteração de senha ainda não disponível.');
        return;
      }

      const json = await res.json();
      if (!res.ok) {
        const msg = Object.values(json).flat().join(' ');
        showAlert('alertSenhaErr', msg || 'Erro ao alterar senha.');
        return;
      }

      showAlert('alertSenhaOk');
      document.getElementById('formSenha').reset();
      document.getElementById('strengthFill').style.width = '0';
      document.getElementById('strengthLabel').textContent = '';
    } catch {
      showAlert('alertSenhaErr', 'Erro de conexão.');
    } finally {
      setLoading('btnSaveSenha', 'spinnerSenha', false);
    }
  });

  // --- Init ---
  loadProfile();
})();

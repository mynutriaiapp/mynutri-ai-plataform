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

  // --- Dashboard nutricional ---
  let dashLoaded = false;

  async function loadNutricional() {
    if (dashLoaded) return;

    const elLoading = document.getElementById('dashLoading');
    const elEmpty   = document.getElementById('dashEmpty');
    const elContent = document.getElementById('dashContent');

    elLoading.style.display = 'flex';
    elEmpty.style.display   = 'none';
    elContent.style.display = 'none';

    try {
      const [resAnam, resDiets] = await Promise.all([
        apiFetch(`${API_BASE}/anamnese/last`),
        apiFetch(`${API_BASE}/diet/list`),
      ]);

      elLoading.style.display = 'none';

      if (resAnam.status === 404 || resAnam.status === 204 || !resAnam.ok) {
        elEmpty.style.display = 'block';
        return;
      }

      const d     = await resAnam.json();
      const diets = resDiets.ok ? (await resDiets.json()) : { results: [], count: 0 };

      dashLoaded = true;
      elContent.style.display = 'block';

      _renderGoalBanner(d);
      _renderMetrics(d);
      _renderProgress(d, diets);
      _renderMacros(d);
      _renderHistory(diets);
      _renderAnamnese(d);

    } catch (err) {
      elLoading.innerHTML = `<p style="color:var(--gray-400);font-size:.9rem;">Não foi possível carregar o dashboard.</p>`;
    }
  }

  // ── Maps ──
  const GOAL_MAP     = { lose: 'Emagrecimento', maintain: 'Manutenção', gain: 'Hipertrofia' };
  const ACTIVITY_MAP = { sedentary: 'Sedentário', light: 'Levemente ativo', moderate: 'Moderadamente ativo', intense: 'Muito ativo', athlete: 'Atleta' };
  const GENDER_MAP   = { M: 'Masculino', F: 'Feminino', O: 'Outro' };

  // Fator de atividade para TDEE
  const ACTIVITY_FACTOR = { sedentary: 1.2, light: 1.375, moderate: 1.55, intense: 1.725, athlete: 1.9 };

  // ── Cálculos ──
  function calcIMC(peso, altura) {
    if (!peso || !altura) return null;
    return peso / Math.pow(altura / 100, 2);
  }

  function imcClass(imc) {
    if (imc < 18.5) return { label: 'Abaixo do peso', cls: 'imc-low' };
    if (imc < 25)   return { label: 'Peso normal',     cls: 'imc-normal' };
    if (imc < 30)   return { label: 'Sobrepeso',       cls: 'imc-over' };
    return            { label: 'Obesidade',             cls: 'imc-obese' };
  }

  function calcTMB(peso, altura, idade, sexo) {
    if (!peso || !altura || !idade) return null;
    // Mifflin-St Jeor
    const base = 10 * peso + 6.25 * altura - 5 * idade;
    return sexo === 'F' ? base - 161 : base + 5;
  }

  function calcTDEE(tmb, nivel) {
    if (!tmb || !nivel) return null;
    return Math.round(tmb * (ACTIVITY_FACTOR[nivel] || 1.2));
  }

  function goalCalories(tdee, objetivo) {
    if (!tdee) return null;
    if (objetivo === 'lose')    return Math.round(tdee * 0.80);
    if (objetivo === 'gain')    return Math.round(tdee * 1.15);
    return tdee;
  }

  // Macros em gramas estimados pelo objetivo
  function calcMacros(kcal, objetivo) {
    let pPct, cPct, gPct;
    if (objetivo === 'lose')     { pPct = 0.35; cPct = 0.35; gPct = 0.30; }
    else if (objetivo === 'gain') { pPct = 0.30; cPct = 0.50; gPct = 0.20; }
    else                          { pPct = 0.25; cPct = 0.50; gPct = 0.25; }
    return {
      proteina: Math.round((kcal * pPct) / 4),
      carbo:    Math.round((kcal * cPct) / 4),
      gordura:  Math.round((kcal * gPct) / 9),
      pPct, cPct, gPct,
    };
  }

  // ── Animação de contagem numérica ──
  function animateCount(el, target, duration, isFloat, locale) {
    const start     = performance.now();
    const isNumber  = typeof target === 'number' && !isNaN(target);
    if (!isNumber) return;

    function tick(now) {
      const elapsed  = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased    = 1 - Math.pow(1 - progress, 3);
      const current  = target * eased;
      el.textContent = isFloat
        ? current.toFixed(1)
        : Math.round(current).toLocaleString(locale || 'pt-BR');
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // ── Renderers ──
  function _renderGoalBanner(d) {
    const icons = {
      lose:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
      gain:     '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 5 5 12"/></svg>',
      maintain: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    };
    const subtitles = {
      lose:     'Déficit calórico controlado para perda de gordura com saúde.',
      gain:     'Superávit calórico com foco em ganho de massa muscular.',
      maintain: 'Equilíbrio calórico para manter o peso e a composição atual.',
    };
    document.getElementById('dashGoalBanner').innerHTML = `
      <div class="goal-banner">
        <div class="goal-banner-icon">${icons[d.objetivo] || icons.maintain}</div>
        <div>
          <div class="goal-banner-title">Seu objetivo</div>
          <div class="goal-banner-text">${GOAL_MAP[d.objetivo] || d.objetivo}</div>
          <div class="goal-banner-sub">${subtitles[d.objetivo] || ''}</div>
        </div>
      </div>`;
  }

  function _renderMetrics(d) {
    const peso   = parseFloat(d.peso);
    const altura = parseFloat(d.altura);
    const idade  = parseInt(d.idade);

    const imc  = calcIMC(peso, altura);
    const tmb  = calcTMB(peso, altura, idade, d.sexo);
    const tdee = calcTDEE(tmb, d.nivel_atividade);
    const meta = goalCalories(tdee, d.objetivo);
    const imcInfo = imc ? imcClass(imc) : null;

    const arrowSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>';

    const metrics = [
      {
        icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C8 2 5 6 5 10c0 5 7 12 7 12s7-7 7-12c0-4-3-8-7-8z"/><circle cx="12" cy="10" r="2"/></svg>',
        color: 'green', label: 'IMC',
        numVal: imc, isFloat: true, unit: 'kg/m²',
        extra: imcInfo ? `<span class="imc-badge ${imcInfo.cls}">${imcInfo.label}</span>` : '',
      },
      {
        icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 0 0 0-7.78z"/></svg>',
        color: 'orange', label: 'TMB',
        numVal: tmb ? Math.round(tmb) : null, isFloat: false, unit: 'kcal/dia',
        extra: '<div style="font-size:.68rem;color:var(--gray-400);margin-top:2px;">Taxa Metabólica Basal</div>',
      },
      {
        icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
        color: 'blue', label: 'Gasto Total (TDEE)',
        numVal: tdee, isFloat: false, unit: 'kcal/dia',
        extra: '<div style="font-size:.68rem;color:var(--gray-400);margin-top:2px;">Com atividade física</div>',
      },
      {
        icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/><line x1="6" y1="1" x2="6" y2="4"/><line x1="10" y1="1" x2="10" y2="4"/><line x1="14" y1="1" x2="14" y2="4"/></svg>',
        color: 'purple', label: 'Meta Calórica',
        numVal: meta, isFloat: false, unit: 'kcal/dia',
        extra: '<div style="font-size:.68rem;color:var(--gray-400);margin-top:2px;">Ajustada ao objetivo</div>',
      },
      {
        icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
        color: 'teal', label: 'Refeições/dia',
        numVal: d.meals_per_day ? parseInt(d.meals_per_day) : null, isFloat: false, unit: 'refeições',
        extra: '',
      },
    ];

    const container = document.getElementById('dashMetrics');
    container.innerHTML = metrics.map(function (m, i) {
      const displayVal = m.numVal != null ? (m.isFloat ? m.numVal.toFixed(1) : m.numVal.toLocaleString('pt-BR')) : '—';
      return `
        <div class="dash-metric-card ${m.color}" style="animation-delay:${i * 0.07}s">
          <div class="dash-metric-icon ${m.color}">${m.icon}</div>
          <div class="dash-metric-label">${m.label}</div>
          <div class="dash-metric-value" data-target="${m.numVal != null ? m.numVal : ''}" data-float="${m.isFloat}">${displayVal}</div>
          <div class="dash-metric-unit">${m.unit}</div>
          ${m.extra}
        </div>`;
    }).join('');

    // Animar contagens após um pequeno delay para o card já estar visível
    setTimeout(function () {
      container.querySelectorAll('.dash-metric-value[data-target]').forEach(function (el) {
        const raw   = el.dataset.target;
        const float = el.dataset.float === 'true';
        const val   = parseFloat(raw);
        if (!isNaN(val) && raw !== '') animateCount(el, val, 900, float, 'pt-BR');
      });
    }, 200);
  }

  function _renderProgress(d, diets) {
    const checkSvg = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    const dotSvg   = '<svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="8"/></svg>';

    const steps = [
      { label: 'Questionário preenchido', done: true },
      { label: 'Dados completos',         done: !!(d.peso && d.altura && d.idade && d.nivel_atividade) },
      { label: 'Dieta gerada',            done: diets.count > 0 },
    ];
    const done = steps.filter(function (s) { return s.done; }).length;
    const pct  = Math.round((done / steps.length) * 100);

    // Delay para acionar a transição CSS
    requestAnimationFrame(function () {
      setTimeout(function () {
        document.getElementById('dashProgressFill').style.width = pct + '%';
      }, 100);
    });

    document.getElementById('dashProgressPct').textContent = pct + '%';

    const chips = steps.map(function (s) {
      return `<span class="progress-step ${s.done ? 'done' : 'pending'}">${s.done ? checkSvg : dotSvg} ${s.label}</span>`;
    }).join('');
    document.getElementById('dashProgressSteps').innerHTML = chips;
  }

  function _renderMacros(d) {
    const peso   = parseFloat(d.peso);
    const altura = parseFloat(d.altura);
    const idade  = parseInt(d.idade);
    const tmb    = calcTMB(peso, altura, idade, d.sexo);
    const tdee   = calcTDEE(tmb, d.nivel_atividade);
    const meta   = goalCalories(tdee, d.objetivo);

    if (!meta) { document.getElementById('dashMacroCard').style.display = 'none'; return; }

    const macros = calcMacros(meta, d.objetivo);
    const R    = 52;
    const circ = 2 * Math.PI * R;

    const segments = [
      { label: 'Proteínas',    g: macros.proteina, pct: macros.pPct, color: '#22c55e' },
      { label: 'Carboidratos', g: macros.carbo,    pct: macros.cPct, color: '#3b82f6' },
      { label: 'Gorduras',     g: macros.gordura,  pct: macros.gPct, color: '#a855f7' },
    ];

    // Gerar arcos SVG com gap de 2px entre segmentos
    const GAP = 3;
    let offsetAngle = 0;
    const arcs = segments.map(function (s) {
      const segLen  = s.pct * circ - GAP;
      const dashArr = segLen.toFixed(2) + ' ' + (circ - segLen).toFixed(2);
      const arc = `<circle cx="65" cy="65" r="${R}" fill="none" stroke="${s.color}" stroke-width="14"
        stroke-dasharray="${dashArr}" stroke-dashoffset="${(-offsetAngle).toFixed(2)}"
        stroke-linecap="round" style="transition:stroke-dasharray .8s var(--ease-out);"/>`;
      offsetAngle += s.pct * circ;
      return arc;
    }).join('');

    const legend = segments.map(function (s) {
      return `
        <div class="macro-legend-item">
          <div class="macro-legend-dot" style="background:${s.color}"></div>
          <div class="macro-legend-name">${s.label}</div>
          <div class="macro-legend-val">${s.g}g <span class="macro-legend-pct">(${Math.round(s.pct * 100)}%)</span></div>
        </div>`;
    }).join('');

    document.getElementById('dashMacroWrap').innerHTML = `
      <div class="macro-donut">
        <svg width="130" height="130" viewBox="0 0 130 130">
          <circle cx="65" cy="65" r="${R}" fill="none" stroke="var(--gray-100)" stroke-width="14"/>
          ${arcs}
        </svg>
        <div class="macro-donut-label">
          <div class="macro-donut-kcal" id="donutKcal">0</div>
          <div class="macro-donut-sub">kcal/dia</div>
        </div>
      </div>
      <div class="macro-legend">${legend}</div>`;

    setTimeout(function () {
      const el = document.getElementById('donutKcal');
      if (el) animateCount(el, meta, 900, false, 'pt-BR');
    }, 150);
  }

  function _renderHistory(diets) {
    const list = document.getElementById('dashHistoryList');
    if (!diets.results || diets.results.length === 0) {
      document.getElementById('dashHistoryCard').style.display = 'none';
      return;
    }

    const arrowSvg = '<svg class="diet-history-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>';

    const items = diets.results.slice(0, 5).map(function (plan) {
      const date = new Date(plan.created_at).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
      const goal = plan.goal_description || '—';
      const kcal = plan.calorias_totais ? plan.calorias_totais.toLocaleString('pt-BR') + ' kcal' : '—';
      return `
        <a href="/dieta/" class="diet-history-item">
          <div class="diet-history-dot"></div>
          <div class="diet-history-date">${date}</div>
          <div class="diet-history-kcal">${kcal}</div>
          <div class="diet-history-goal">${goal}</div>
          ${arrowSvg}
        </a>`;
    }).join('');

    const total  = diets.count;
    const footer = total > 5
      ? `<div style="text-align:center;margin-top:14px;">
           <a href="/historico/" style="font-size:.82rem;color:var(--green-600);font-weight:700;text-decoration:none;">
             Ver todas as ${total} dietas →
           </a>
         </div>`
      : '';

    list.innerHTML = `<div class="diet-history-list">${items}</div>${footer}`;
  }

  function _renderAnamnese(d) {
    const fields = [
      { label: 'Sexo',               value: GENDER_MAP[d.sexo] || d.sexo },
      { label: 'Idade',              value: d.idade ? d.idade + ' anos' : null },
      { label: 'Peso',               value: d.peso ? d.peso + ' kg' : null },
      { label: 'Altura',             value: d.altura ? d.altura + ' cm' : null },
      { label: 'Nível de Atividade', value: ACTIVITY_MAP[d.nivel_atividade] || d.nivel_atividade },
      { label: 'Refeições/dia',      value: d.meals_per_day },
      { label: 'Restrições',         value: d.restricoes },
      { label: 'Alergias',           value: d.allergies },
      { label: 'Preferências',       value: d.food_preferences },
    ];

    document.getElementById('dashAnamGrid').innerHTML = fields
      .filter(function (f) { return f.value; })
      .map(function (f, i) {
        return `
          <div class="anam-item" style="animation-delay:${i * 0.05}s">
            <div class="anam-label">${f.label}</div>
            <div class="anam-value">${f.value}</div>
          </div>`;
      }).join('');
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

  // --- Delete account ---
  (function () {
    let modalOverlay = null;

    function buildModal() {
      if (document.getElementById('deleteModalOverlay')) return;
      const overlay = document.createElement('div');
      overlay.className = 'delete-modal-overlay';
      overlay.id = 'deleteModalOverlay';
      overlay.innerHTML = `
        <div class="delete-modal" role="dialog" aria-modal="true" aria-labelledby="deleteModalTitle">
          <div class="delete-modal-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
          </div>
          <div class="delete-modal-title" id="deleteModalTitle">Tem certeza absoluta?</div>
          <div class="delete-modal-body">
            Você está prestes a excluir permanentemente sua conta e <strong>todos os seus dados</strong>, incluindo dietas, histórico e informações pessoais.<br><br>
            <strong>Esta ação não pode ser desfeita.</strong>
          </div>
          <div class="delete-modal-actions">
            <button class="btn-cancel-modal" id="btnCancelDeleteModal">Cancelar</button>
            <button class="btn-confirm-delete" id="btnConfirmDelete">Sim, excluir minha conta</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      modalOverlay = overlay;

      document.getElementById('btnCancelDeleteModal').addEventListener('click', closeModal);
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
      });
      document.addEventListener('keydown', function onKey(e) {
        if (e.key === 'Escape') { closeModal(); document.removeEventListener('keydown', onKey); }
      });
    }

    function openModal() {
      buildModal();
      requestAnimationFrame(function () {
        document.getElementById('deleteModalOverlay').classList.add('show');
      });
    }

    function closeModal() {
      const overlay = document.getElementById('deleteModalOverlay');
      if (overlay) {
        overlay.classList.remove('show');
      }
    }

    document.getElementById('formExcluir').addEventListener('submit', function (e) {
      e.preventDefault();
      hideAlert('alertExcluirErr');

      const senha = document.getElementById('inputSenhaExcluir').value.trim();
      if (!senha) {
        showAlert('alertExcluirErr', 'Digite sua senha para confirmar.');
        return;
      }

      openModal();

      // Bind confirm button fresh each open to avoid duplicate listeners
      const btnConfirm = document.getElementById('btnConfirmDelete');
      const btnConfirmClone = btnConfirm.cloneNode(true);
      btnConfirm.parentNode.replaceChild(btnConfirmClone, btnConfirm);

      btnConfirmClone.addEventListener('click', async function () {
        closeModal();
        setLoading('btnExcluirConta', 'spinnerExcluir', true);

        try {
          const res = await apiFetch(`${API_BASE}/user/delete-account`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: senha }),
          });

          const json = await res.json();

          if (!res.ok) {
            const msg = json.error || Object.values(json).flat().join(' ');
            showAlert('alertExcluirErr', msg || 'Erro ao excluir conta.');
            return;
          }

          // Limpar dados locais e redirecionar
          localStorage.clear();
          sessionStorage.clear();
          window.location.href = '/?conta_excluida=1';
        } catch {
          showAlert('alertExcluirErr', 'Erro de conexão. Tente novamente.');
        } finally {
          setLoading('btnExcluirConta', 'spinnerExcluir', false);
        }
      });
    });
  }());

  // --- Init ---
  loadProfile();
})();

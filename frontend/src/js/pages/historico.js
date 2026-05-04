function show(id)     { document.getElementById(id).style.display = ''; }
function hide(id)     { document.getElementById(id).style.display = 'none'; }
function showFlex(id) { document.getElementById(id).style.display = 'flex'; }

async function loadHistory() {
  hide('stateEmpty');
  hide('stateError');
  hide('stateList');
  showFlex('stateLoading');

  try {
    const res = await apiFetch(`${API_BASE}/diet/list`);

    if (res.status === 401) {
      localStorage.removeItem('mynutri_user');
      hide('stateLoading');
      document.getElementById('stateEmpty').querySelector('.state-title').textContent = 'Faça login para ver seu histórico';
      document.getElementById('stateEmpty').querySelector('.state-subtitle').textContent = 'Entre na sua conta para acessar seus planos alimentares gerados.';
      document.getElementById('stateEmpty').querySelector('a').href = '/auth/';
      document.getElementById('stateEmpty').querySelector('a').textContent = 'Entrar na conta';
      showFlex('stateEmpty');
      return;
    }

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const plans = await res.json();
    hide('stateLoading');

    if (!plans.length) {
      showFlex('stateEmpty');
      return;
    }

    const count = plans.length;
    document.getElementById('countText').textContent = `${count} ${count === 1 ? 'dieta gerada' : 'dietas geradas'}`;

    const list = document.getElementById('historyList');
    list.innerHTML = '';

    plans.forEach((plan) => {
      const macros = plan.macros || {};
      const card = document.createElement('a');
      card.href = `/dieta/?id=${plan.id}`;
      card.className = 'diet-card';
      card.setAttribute('aria-label', `Ver dieta de ${formatDate(plan.created_at)}`);

      card.innerHTML = `
        <div class="diet-card-left">
          <div class="diet-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 3h18v4H3zM3 10h18v4H3zM3 17h18v4H3z"/>
            </svg>
          </div>
          <div class="diet-info">
            <div class="diet-date">${formatDate(plan.created_at)}</div>
            <div class="diet-goal">${goalLabel(plan.goal_description)}</div>
          </div>
        </div>

        <div class="diet-card-meta">
          ${plan.calorias_totais ? `<span class="meta-pill calories">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            ${plan.calorias_totais} kcal
          </span>` : ''}
          ${macros.protein_g ? `<span class="meta-pill protein">${macros.protein_g}g prot</span>` : ''}
          ${macros.carbs_g   ? `<span class="meta-pill carbs">${macros.carbs_g}g carb</span>`   : ''}
          ${macros.fat_g     ? `<span class="meta-pill fat">${macros.fat_g}g gord</span>`       : ''}
        </div>

        <svg class="diet-card-arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      `;

      list.appendChild(card);
    });

    show('stateList');

  } catch (err) {
    hide('stateLoading');
    document.getElementById('errorMsg').textContent = `Erro ao carregar: ${err.message}`;
    showFlex('stateError');
  }
}

initUserMenu({ requireAuth: false, logoutRedirect: '/' });
loadHistory();

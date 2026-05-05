(function () {
// Auth guard: loadUser() e fetchExistingDiet() redirecionam para /auth/ se a API retornar 401.
// Não fazemos redirect síncrono aqui para suportar o fluxo de redirect do Google OAuth,
// onde os cookies são setados pelo backend mas o localStorage ainda está vazio.

// ── Emojis por refeição ──
const MEAL_EMOJIS = ['🌅', '🥗', '🍽️', '🥤', '🌙', '🍎', '🥑', '🫐'];

// ── Paletas de cor por refeição (espelha data-meal-color dos cards) ──
const MODAL_PALETTES = [
  { mc:'#ea580c', mcl:'#fff7ed', mcb:'#fed7aa', mcg:'linear-gradient(135deg,#fff7ed,#ffedd5)' },
  { mc:'#0d9488', mcl:'#f0fdfa', mcb:'#5eead4', mcg:'linear-gradient(135deg,#f0fdfa,#ccfbf1)' },
  { mc:'#16a34a', mcl:'#f0fdf4', mcb:'#86efac', mcg:'linear-gradient(135deg,#f0fdf4,#dcfce7)' },
  { mc:'#7c3aed', mcl:'#fdf4ff', mcb:'#c4b5fd', mcg:'linear-gradient(135deg,#fdf4ff,#f3e8ff)' },
  { mc:'#1d4ed8', mcl:'#eff6ff', mcb:'#93c5fd', mcg:'linear-gradient(135deg,#eff6ff,#dbeafe)' },
  { mc:'#be185d', mcl:'#fdf2f8', mcb:'#f9a8d4', mcg:'linear-gradient(135deg,#fdf2f8,#fce7f3)' },
  { mc:'#0369a1', mcl:'#f0f9ff', mcb:'#7dd3fc', mcg:'linear-gradient(135deg,#f0f9ff,#e0f2fe)' },
  { mc:'#6d28d9', mcl:'#f5f3ff', mcb:'#a78bfa', mcg:'linear-gradient(135deg,#f5f3ff,#ede9fe)' },
];

// ── Estado global ──
let dietData = null;

// ── Estado de regeneração ──
let _currentModalMealIndex = null;
let _currentModalMealId    = null;
let _regenHasUndo          = false;
let _pendingNewMealData    = null;   // resposta da API guardada até confirmação
let _pendingMealIndex      = null;   // índice da refeição com preview pendente
let _selectedChip          = null;   // chip element atualmente selecionado
let _loadingMsgTimer       = null;   // intervalo das mensagens de loading

initUserMenu({ requireAuth: false, logoutRedirect: '/' });

// ════════════════════════════════
//  SUBSTITUIÇÕES — EDIÇÃO
// ════════════════════════════════

// rawFoods da refeição aberta — necessário para re-filtrar subs no cancelar/salvar
let _currentModalRawFoods = [];

function _subIndexInDiet(food) {
  return (dietData.substitutions || []).findIndex(s => s.food === food);
}

function _computeSubsToShow() {
  const allSubs  = dietData.substitutions || [];
  const foodNames = _currentModalRawFoods.map(f => (f.name || '').toLowerCase());
  const relevant  = allSubs.filter(s =>
    foodNames.some(fn => fn.includes((s.food || '').toLowerCase().split(' ')[0]))
  );
  return relevant.length > 0 ? relevant : allSubs;
}

function renderSubstitutions(container) {
  const subsToShow = _computeSubsToShow();
  if (!subsToShow.length) {
    container.innerHTML = '<p class="sub-empty">Nenhuma substituição registrada para esta refeição.</p>';
    return;
  }

  container.innerHTML = subsToShow.map((s, i) => {
    const idx  = _subIndexInDiet(s.food);
    const alts = (s.alternatives || [])
      .map(a => `<span class="sub-tag">${escapeHtml(a)}</span>`).join('');
    const foodMatch = (s.food || '').match(/^(.*?)\s*\((\d+(?:g|ml|un)?)\)$/i);
    const foodLabel = foodMatch ? escapeHtml(foodMatch[1].trim()) : escapeHtml(s.food);
    const foodQty   = foodMatch ? `<span class="sub-from-qty">${escapeHtml(foodMatch[2])}</span>` : '';
    return `
      <div class="sub-row" data-sub-index="${idx}" style="animation-delay:${i * 0.07}s">
        <div class="sub-from-row">
          <div class="sub-from-wrap">
            <span class="sub-from">${foodLabel}</span>
            ${foodQty}
          </div>
          <button class="sub-edit-btn" data-sub-index="${idx}" title="Editar" aria-label="Editar substituição de ${escapeHtml(s.food)}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
        </div>
        <div class="sub-arrow-row">
          <div class="sub-arrow-line">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
            <span class="sub-by-label">por qualquer um de</span>
          </div>
        </div>
        <div class="sub-tags">${alts}</div>
      </div>`;
  }).join('');

  container.querySelectorAll('.sub-edit-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      _openSubEdit(parseInt(btn.dataset.subIndex), container);
    });
  });
}

function _openSubEdit(idx, container) {
  const s   = (dietData.substitutions || [])[idx];
  if (!s) return;
  const row = container.querySelector(`.sub-row[data-sub-index="${idx}"]`);
  if (!row) return;

  row.outerHTML = `
    <div class="sub-row sub-row--editing" data-sub-index="${idx}">
      <div class="sub-edit-fields">
        <div class="sub-edit-field">
          <span class="sub-edit-label">Alimento</span>
          <input class="sub-edit-input" id="sub-food-${idx}" type="text"
                 value="${escapeHtml(s.food)}" maxlength="100" placeholder="Nome do alimento" />
        </div>
        <div class="sub-edit-field">
          <span class="sub-edit-label">Substituições</span>
          <input class="sub-edit-input" id="sub-alts-${idx}" type="text"
                 value="${escapeHtml((s.alternatives || []).join(', '))}" maxlength="500"
                 placeholder="Ex: Batata, Macarrão, Mandioca" />
          <span class="sub-edit-hint">Separe as opções por vírgula.</span>
        </div>
      </div>
      <div class="sub-edit-actions">
        <button class="sub-btn-save"   id="sub-save-${idx}">Salvar</button>
        <button class="sub-btn-cancel" id="sub-cancel-${idx}">Cancelar</button>
      </div>
    </div>`;

  const foodInput = document.getElementById(`sub-food-${idx}`);
  const altsInput = document.getElementById(`sub-alts-${idx}`);
  const saveBtn   = document.getElementById(`sub-save-${idx}`);
  const cancelBtn = document.getElementById(`sub-cancel-${idx}`);

  foodInput.focus();

  saveBtn.addEventListener('click', () => _saveSubEdit(idx, foodInput, altsInput, saveBtn, container));
  cancelBtn.addEventListener('click', () => renderSubstitutions(container));

  [foodInput, altsInput].forEach(input => {
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter')  { e.preventDefault(); saveBtn.click(); }
      if (e.key === 'Escape') cancelBtn.click();
    });
  });
}

async function _saveSubEdit(idx, foodInput, altsInput, saveBtn, container) {
  const food = foodInput.value.trim();
  const alts = altsInput.value.split(',').map(a => a.trim()).filter(Boolean);

  if (!food) {
    foodInput.classList.add('invalid');
    foodInput.focus();
    setTimeout(() => foodInput.classList.remove('invalid'), 2000);
    return;
  }
  if (!alts.length) {
    altsInput.classList.add('invalid');
    altsInput.focus();
    setTimeout(() => altsInput.classList.remove('invalid'), 2000);
    return;
  }

  saveBtn.disabled     = true;
  saveBtn.textContent  = 'Salvando…';

  const updatedSubs = [...(dietData.substitutions || [])];
  updatedSubs[idx]  = { food, alternatives: alts };

  try {
    const res = await apiFetch(`${API_BASE}/diet/${dietData.id}/substitutions`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ substitutions: updatedSubs }),
    });

    if (!res.ok) throw new Error('server');

    const data = await res.json();
    dietData.substitutions = data.substitutions;
    renderSubstitutions(container);
    showToast('Substituição atualizada com sucesso!', 'success');
  } catch {
    saveBtn.disabled    = false;
    saveBtn.textContent = 'Salvar';
    showToast('Não foi possível salvar. Tente novamente.', 'error');
  }
}

// ════════════════════════════════
//  MODAL
// ════════════════════════════════
const overlay   = document.getElementById('modal');
const modalBox  = document.getElementById('modalBox');
const closeBtn  = document.getElementById('modalClose');

// ── Chat helpers ──
function _addChatMessage(text, role = 'bot', isTyping = false) {
  const container = document.getElementById('chat-messages');
  const msg = document.createElement('div');
  msg.className = `chat-msg chat-msg--${role}${isTyping ? ' chat-msg--typing' : ''}`;
  msg.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
  return msg;
}

function _clearChatMessages() {
  const container = document.getElementById('chat-messages');
  if (container) container.innerHTML = '';
}

// ── Chat Dock helpers (declarados cedo para uso em _initChat) ──
function openChatDock() {
  const toggle = document.getElementById('chat-dock-toggle');
  const panel  = document.getElementById('chat-dock-panel');
  if (!toggle || !panel) return;
  toggle.setAttribute('aria-expanded', 'true');
  panel.classList.add('open');
  requestAnimationFrame(() => panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' }));
}

function closeChatDock() {
  const toggle = document.getElementById('chat-dock-toggle');
  const panel  = document.getElementById('chat-dock-panel');
  if (!toggle || !panel) return;
  toggle.setAttribute('aria-expanded', 'false');
  panel.classList.remove('open');
}

function _setDockHint(text) {
  const el = document.getElementById('chat-dock-hint');
  if (el) el.textContent = text;
}

function _initChat() {
  _clearChatMessages();
  _addChatMessage('Olá! Não gostou desta refeição? Me diga o motivo e gero uma nova opção pra você.', 'bot');
  _setDockHint('Não gostou? Posso trocar esta refeição');
  closeChatDock();
}

function _resetRegenSection(keepUndo) {
  document.getElementById('regen-idle-state').style.display    = 'block';
  document.getElementById('regen-loading-state').style.display = 'none';
  document.getElementById('regen-diff-state').style.display    = 'none';
  clearInterval(_loadingMsgTimer);
  if (!keepUndo) {
    document.getElementById('regen-reason').value               = '';
    document.getElementById('btn-undo-meal').style.display      = 'none';
    document.getElementById('regen-remaining-text').textContent = '';
    document.querySelectorAll('.chat-chip').forEach(c => c.classList.remove('selected'));
    _regenHasUndo       = false;
    _pendingNewMealData = null;
    _pendingMealIndex   = null;
    _selectedChip       = null;
    _initChat();
  }
}

function _startLoadingMessages() {
  const msgs = [
    'Analisando seus macros...',
    'Buscando alternativas nutritivas...',
    'Equilibrando proteínas e carboidratos...',
    'Quase pronto...',
  ];
  let i = 0;
  const el = document.getElementById('regen-loading-text');
  if (el) el.textContent = msgs[0];
  _loadingMsgTimer = setInterval(() => {
    i = (i + 1) % msgs.length;
    if (el) el.textContent = msgs[i];
  }, 1600);
}

function _addUserMessageToChat(reason) {
  const text = reason || 'Gerar nova sugestão';
  _addChatMessage(text, 'user');
}

function _showRegenDiff(beforeFoods, beforeKcal, afterFoods, afterKcal, remaining) {
  document.getElementById('regen-idle-state').style.display = 'none';
  document.getElementById('regen-diff-state').style.display = 'block';

  function buildList(foods, kcal) {
    const MAX   = 5;
    const slice = foods.slice(0, MAX);
    const more  = foods.length - MAX;
    return slice.map(f =>
      `<div class="regen-diff-food">
        <span class="regen-diff-dot"></span>
        ${escapeHtml(f.name || '')}${f.quantity_g ? `<span class="regen-diff-qty">${f.quantity_g}g</span>` : ''}
      </div>`
    ).join('') +
    (more > 0 ? `<div class="regen-diff-food regen-diff-more">+${more} mais</div>` : '') +
    `<div class="regen-diff-kcal">🔥 ${kcal} kcal</div>`;
  }

  document.getElementById('regen-diff-before').innerHTML = buildList(beforeFoods, beforeKcal);
  document.getElementById('regen-diff-after').innerHTML  = buildList(afterFoods,  afterKcal);

  const remEl = document.getElementById('regen-diff-remaining');
  remEl.textContent = remaining > 0
    ? `${remaining} regeneração${remaining === 1 ? '' : 'ões'} restante${remaining === 1 ? '' : 's'} hoje`
    : 'Limite de regenerações atingido para hoje';
}

function openModal(mealIndex) {
  // Troca de refeição → descarta preview pendente da outra refeição
  if (_currentModalMealIndex !== mealIndex) {
    if (_pendingNewMealData && _pendingMealIndex !== null) {
      const mealIdToUndo = dietData.refeicoes[_pendingMealIndex]?.id;
      if (mealIdToUndo) {
        apiFetch(`${API_BASE}/diet/${dietData.id}/meal/${mealIdToUndo}/undo`,
          { method: 'POST' }).catch(() => {});
      }
      _pendingNewMealData = null;
      _pendingMealIndex   = null;
    }
    _regenHasUndo = false;
  }
  _currentModalMealIndex = mealIndex;
  _currentModalMealId    = dietData.refeicoes[mealIndex]?.id ?? null;

  const refeicao  = dietData.refeicoes[mealIndex];
  const rawMeal   = (dietData.meals_raw || [])[mealIndex] || {};
  const allSubs   = dietData.substitutions || [];
  const emoji     = MEAL_EMOJIS[mealIndex % MEAL_EMOJIS.length];

  // ── Aplicar paleta de cor no modal ──
  const pal = MODAL_PALETTES[mealIndex % MODAL_PALETTES.length];
  const modalBox = document.getElementById('modalBox');
  modalBox.style.setProperty('--modal-mc',  pal.mc);
  modalBox.style.setProperty('--modal-mcl', pal.mcl);
  modalBox.style.setProperty('--modal-mcb', pal.mcb);
  modalBox.style.setProperty('--modal-mcg', pal.mcg);

  // ── Header ──
  document.getElementById('modal-emoji').textContent     = emoji;
  document.getElementById('modal-order').textContent     = `Refeição ${mealIndex + 1}`;
  document.getElementById('modal-title').textContent     = refeicao.nome_refeicao;
  document.getElementById('modal-kcal-text').textContent = `${refeicao.calorias_estimadas} kcal`;

  const timeSuggestion = rawMeal.time_suggestion || '';
  const timeEl = document.getElementById('modal-time');
  if (timeSuggestion) {
    document.getElementById('modal-time-text').textContent = timeSuggestion;
    timeEl.style.display = 'inline-flex';
  } else {
    timeEl.style.display = 'none';
  }

  // ── Food items ──
  const foodsContainer = document.getElementById('foods-tbody');
  const rawFoods = rawMeal.foods || [];

  if (rawFoods.length > 0) {
    foodsContainer.innerHTML = rawFoods.map((f, idx) => {
      const hasMacros = f.protein_g != null || f.carbs_g != null || f.fat_g != null;
      const macrosHTML = hasMacros ? `
        <div class="food-item-macros">
          <div class="food-mpill p">
            <span class="food-mpill-val">${Math.round(f.protein_g || 0)}<small>g</small></span>
            <span class="food-mpill-lbl">Prot</span>
          </div>
          <div class="food-mpill c">
            <span class="food-mpill-val">${Math.round(f.carbs_g || 0)}<small>g</small></span>
            <span class="food-mpill-lbl">Carb</span>
          </div>
          <div class="food-mpill f">
            <span class="food-mpill-val">${Math.round(f.fat_g || 0)}<small>g</small></span>
            <span class="food-mpill-lbl">Gord</span>
          </div>
        </div>` : '';
      return `
        <div class="food-item" style="animation-delay:${idx * 0.06}s" data-has-macros="${hasMacros}">
          <div class="food-item-main">
            <div class="food-item-info">
              <span class="food-item-name">${escapeHtml(f.name || '—')}</span>
              ${f.quantity ? `<span class="food-item-qty">${escapeHtml(f.quantity)}</span>` : ''}
            </div>
            <div class="food-item-right">
              ${f.calories != null ? `<span class="food-item-kcal">${f.calories}<span> kcal</span></span>` : ''}
              ${hasMacros ? `<svg class="food-item-chevron" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>` : ''}
            </div>
          </div>
          ${macrosHTML}
        </div>`;
    }).join('');

    foodsContainer.querySelectorAll('.food-item[data-has-macros="true"]').forEach(el => {
      el.addEventListener('click', () => el.classList.toggle('fi-expanded'));
    });

  } else {
    const lines = (refeicao.descricao_refeicao || '').split('\n').filter(l => l.trim().startsWith('•'));
    if (lines.length > 0) {
      foodsContainer.innerHTML = lines.map((line, idx) => {
        const clean = line.replace(/^•\s*/, '').trim();
        const [name, qty = ''] = clean.split(/\s+—\s+/);
        return `<div class="food-item" style="animation-delay:${idx * 0.06}s">
          <div class="food-item-main">
            <div class="food-item-info">
              <span class="food-item-name">${escapeHtml(name)}</span>
              ${qty ? `<span class="food-item-qty">${escapeHtml(qty)}</span>` : ''}
            </div>
          </div>
        </div>`;
      }).join('');
    } else {
      foodsContainer.innerHTML = `<p class="food-item-empty">Informação não disponível</p>`;
    }
  }

  // ── Macros no header ──
  let protein = 0, carbs = 0, fat = 0, hasMacros = false;
  rawFoods.forEach(f => {
    if (f.protein_g != null || f.carbs_g != null || f.fat_g != null) {
      hasMacros = true;
      protein += f.protein_g || 0;
      carbs   += f.carbs_g   || 0;
      fat     += f.fat_g     || 0;
    }
  });

  if (!hasMacros && dietData.macros && dietData.calorias_totais) {
    const share = (refeicao.calorias_estimadas || 0) / dietData.calorias_totais;
    protein = Math.round((dietData.macros.protein_g || 0) * share);
    carbs   = Math.round((dietData.macros.carbs_g   || 0) * share);
    fat     = Math.round((dietData.macros.fat_g     || 0) * share);
    hasMacros = true;
  }

  const headerMacros = document.getElementById('modal-header-macros');
  if (hasMacros) {
    document.getElementById('mhm-protein').textContent = Math.round(protein);
    document.getElementById('mhm-carbs').textContent   = Math.round(carbs);
    document.getElementById('mhm-fat').textContent     = Math.round(fat);
    headerMacros.style.display = 'flex';
  } else {
    headerMacros.style.display = 'none';
  }

  // ── Substituições ──
  _currentModalRawFoods = rawFoods;
  renderSubstitutions(document.getElementById('modal-subs'));

  // ── Dicas da refeição (meal_notes individual > fallback notas globais) ──
  const mealNotes   = rawMeal.meal_notes || '';
  const globalNotes = dietData.notes || '';
  const notesText   = mealNotes || globalNotes;
  const notesSection = document.getElementById('modal-notes-section');
  if (notesText) {
    notesSection.style.display = 'block';
    document.getElementById('modal-notes-text').textContent = notesText;
  } else {
    notesSection.style.display = 'none';
  }

  // ── Regeneração — reset (preserva undo se já estava aberto) ──
  _resetRegenSection(_regenHasUndo);

  // Se há preview pendente desta refeição, reexibe o diff (ex: usuário fechou e reabriu o modal)
  if (_pendingNewMealData && _pendingMealIndex === mealIndex) {
    _showRegenDiff(
      _pendingNewMealData.beforeFoods, _pendingNewMealData.beforeKcal,
      _pendingNewMealData.afterFoods,  _pendingNewMealData.afterKcal,
      _pendingNewMealData.remaining,
    );
  }

  // ── Scroll to top and open ──
  document.getElementById('modal-body').scrollTop = 0;
  overlay.classList.add('open');

  // Scroll lock seguro: overflow:hidden no <html> não quebra position:fixed.
  // (position:fixed no body criaria um novo containing block quebrando o overlay)
  document.documentElement.classList.add('modal-open');

  closeBtn.focus();
}

function closeModal() {
  overlay.classList.remove('open');
  document.documentElement.classList.remove('modal-open');
}

closeBtn.addEventListener('click', closeModal);
overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(); });
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (overlay.classList.contains('open')) closeModal();
});

// ════════════════════════════════
//  REGENERAÇÃO DE REFEIÇÃO
// ════════════════════════════════

async function regenerateMeal() {
  if (!_currentModalMealId || !dietData?.id) return;

  const reason = (document.getElementById('regen-reason').value || '').trim();
  const idx    = _currentModalMealIndex;

  // Snapshot "antes" — a UI não muda até o usuário confirmar
  const beforeRaw   = (dietData.meals_raw || [])[idx] || {};
  const beforeFoods = (beforeRaw.foods || []).slice(0, 6);
  const beforeKcal  = dietData.refeicoes[idx]?.calorias_estimadas ?? '—';

  // Adiciona mensagem do usuário e abre o dock
  openChatDock();
  _addUserMessageToChat(reason || 'Gerar nova sugestão');
  _setDockHint('Gerando nova sugestão...');

  document.getElementById('regen-idle-state').style.display    = 'none';
  document.getElementById('regen-loading-state').style.display = 'block';
  _startLoadingMessages();

  try {
    const res = await apiFetch(
      `${API_BASE}/diet/${dietData.id}/meal/${_currentModalMealId}/regenerate`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      },
    );

    const data = await res.json();
    clearInterval(_loadingMsgTimer);

    if (res.status === 401) {
      localStorage.removeItem('mynutri_user');
      window.location.href = '/auth/';
      return;
    }

    if (!res.ok) {
      document.getElementById('regen-loading-state').style.display = 'none';
      document.getElementById('regen-idle-state').style.display    = 'block';
      _addChatMessage(data.error || 'Não consegui gerar uma nova sugestão. Tente novamente.', 'bot');
      showToast(data.error || 'Erro ao regenerar. Tente novamente.', 'error');
      return;
    }

    // Guarda tudo para aplicar só após confirmação — UI fica intacta por enquanto
    const afterRaw   = data.meals_raw_entry || {};
    const afterFoods = (afterRaw.foods || []).slice(0, 6);
    const afterKcal  = data.meal.calories;
    const remaining  = data.regenerations_remaining ?? 0;

    _pendingNewMealData = { apiData: data, beforeFoods, beforeKcal, afterFoods, afterKcal, remaining };
    _pendingMealIndex   = idx;
    _regenHasUndo       = true;

    // Mensagem de resposta do bot antes de mostrar o diff
    _addChatMessage(`Pronto! Criei uma nova opção com ${afterKcal} kcal. Veja abaixo e confirme se quiser manter.`, 'bot');
    _setDockHint('Nova sugestão pronta — confirme ou desfaça');

    // Mostra diff sem alterar nada na UI
    _showRegenDiff(beforeFoods, beforeKcal, afterFoods, afterKcal, remaining);

  } catch {
    clearInterval(_loadingMsgTimer);
    document.getElementById('regen-loading-state').style.display = 'none';
    document.getElementById('regen-idle-state').style.display    = 'block';
    _addChatMessage('Erro de conexão. Verifique sua internet e tente novamente.', 'bot');
    showToast('Erro de conexão. Tente novamente.', 'error');
  }
}

function _applyPendingMeal() {
  if (!_pendingNewMealData) return;
  const { apiData } = _pendingNewMealData;
  const idx         = _pendingMealIndex;

  // Aplica os dados da nova refeição ao estado global
  dietData.refeicoes[idx] = {
    id:                 apiData.meal.id,
    nome_refeicao:      apiData.meal.meal_name,
    descricao_refeicao: apiData.meal.description,
    calorias_estimadas: apiData.meal.calories,
    order:              apiData.meal.order,
  };
  if (dietData.meals_raw) dietData.meals_raw[idx] = apiData.meals_raw_entry;
  dietData.calorias_totais = apiData.total_calories;
  dietData.macros          = apiData.macros;

  const remText = document.getElementById('regen-diff-remaining').textContent;

  _pendingNewMealData = null;
  _pendingMealIndex   = null;

  // Atualiza a UI agora que o usuário confirmou
  renderMealCards(dietData.refeicoes);
  renderMacrosBar(dietData.macros);
  document.getElementById('stat-calories').textContent =
    (apiData.total_calories || '—').toLocaleString('pt-BR');

  // Flash no card confirmado
  requestAnimationFrame(() => {
    const card = document.querySelectorAll('.meal-card')[idx];
    if (card) {
      card.classList.remove('regen-flash');
      void card.offsetWidth;
      card.classList.add('regen-flash');
      setTimeout(() => card.classList.remove('regen-flash'), 1100);
    }
  });

  // Reabre o modal com o novo conteúdo
  openModal(idx);

  // Mostra undo e texto de limite
  document.getElementById('btn-undo-meal').style.display      = 'inline-flex';
  document.getElementById('regen-remaining-text').textContent = remText;
}

async function _discardPendingMeal() {
  if (!_pendingNewMealData || !dietData?.id) return;

  const mealId = dietData.refeicoes[_pendingMealIndex]?.id || _currentModalMealId;

  _pendingNewMealData = null;
  _pendingMealIndex   = null;
  _regenHasUndo       = false;

  // UI já mostra a refeição antiga — só reverte o DB
  _resetRegenSection(false);

  try {
    const res = await fetch(
      `${API_BASE}/diet/${dietData.id}/meal/${mealId}/undo`,
      { method: 'POST', credentials: 'include' },
    );
    if (!res.ok) {
      const data = await res.json();
      showToast(data.error || 'Erro ao descartar. Tente novamente.', 'error');
    }
  } catch {
    showToast('Erro de conexão ao descartar.', 'error');
  }
}

async function undoRegeneration() {
  if (!_currentModalMealId || !dietData?.id) return;

  _pendingNewMealData = null;
  _pendingMealIndex   = null;

  try {
    const res = await fetch(
      `${API_BASE}/diet/${dietData.id}/meal/${_currentModalMealId}/undo`,
      { method: 'POST', credentials: 'include' },
    );

    const data = await res.json();

    if (!res.ok) {
      showToast(data.error || 'Erro ao desfazer. Tente novamente.', 'error');
      return;
    }

    const idx = _currentModalMealIndex;

    dietData.refeicoes[idx] = {
      id:                 data.meal.id,
      nome_refeicao:      data.meal.meal_name,
      descricao_refeicao: data.meal.description,
      calorias_estimadas: data.meal.calories,
      order:              data.meal.order,
    };
    if (dietData.meals_raw) dietData.meals_raw[idx] = data.meals_raw_entry;
    dietData.calorias_totais = data.total_calories;
    dietData.macros          = data.macros;

    renderMealCards(dietData.refeicoes);
    renderMacrosBar(dietData.macros);
    document.getElementById('stat-calories').textContent =
      (data.total_calories || '—').toLocaleString('pt-BR');

    _regenHasUndo = false;
    openModal(idx);

    showToast('Alteração desfeita com sucesso!', 'success');

  } catch {
    showToast('Erro de conexão ao desfazer.', 'error');
  }
}

document.getElementById('btn-regen-meal').addEventListener('click', regenerateMeal);
document.getElementById('btn-undo-meal').addEventListener('click', undoRegeneration);

// ── Chips de motivo ──
document.getElementById('regen-chips').addEventListener('click', e => {
  const chip = e.target.closest('.chat-chip');
  if (!chip) return;

  if (_selectedChip === chip) {
    chip.classList.remove('selected');
    _selectedChip = null;
    document.getElementById('regen-reason').value = '';
  } else {
    if (_selectedChip) _selectedChip.classList.remove('selected');
    chip.classList.add('selected');
    _selectedChip = chip;
    document.getElementById('regen-reason').value = chip.dataset.reason;
    document.getElementById('regen-reason').focus();
  }
});

// ── Auto-resize do textarea ──
document.getElementById('regen-reason').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 96) + 'px';
  // Deseleciona chip se o usuário digitou algo diferente
  if (_selectedChip && this.value !== _selectedChip.dataset.reason) {
    _selectedChip.classList.remove('selected');
    _selectedChip = null;
  }
});

// ── Enter para enviar (Shift+Enter nova linha) ──
document.getElementById('regen-reason').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    document.getElementById('btn-regen-meal').click();
  }
});

// ── Botões do painel diff ──
document.getElementById('btn-diff-keep').addEventListener('click', _applyPendingMeal);
document.getElementById('btn-diff-undo').addEventListener('click', _discardPendingMeal);

// Previne touchmove no fundo do overlay (scroll lock para iOS Safari)
// passive: false é necessário para poder chamar preventDefault()
overlay.addEventListener('touchmove', e => {
  // Permite scroll DENTRO do modal-body, bloqueia fundo
  if (!e.target.closest('#modal-body')) {
    e.preventDefault();
  }
}, { passive: false });

// ════════════════════════════════
//  MODAL DE TRANSPARÊNCIA (IA)
// ════════════════════════════════
const overlayExplain   = document.getElementById('modal-explain');
const closeBtnExplain  = document.getElementById('modalExplainClose');

const EXPLAIN_SECTIONS = [
  {
    key:   'calorie_calculation',
    icon:  '🔥',
    cls:   'calories',
    title: 'Cálculo de Calorias',
    fallback: (d) => {
      const kcal = d.calorias_totais;
      const goal = (d.goal_description || '').toLowerCase();
      const adj  = goal.includes('emagrecimento') ? 'déficit de ~400 kcal'
                 : goal.includes('hipertrofia')   ? 'superávit de ~350 kcal'
                 : 'sem ajuste (manutenção)';
      return `Seu plano foi calculado com base no seu peso, altura, idade e nível de atividade, usando a equação de Mifflin-St Jeor. Com o ajuste para ${adj}, chegamos a ${kcal?.toLocaleString('pt-BR') || '—'} kcal diárias.`;
    },
  },
  {
    key:   'macro_distribution',
    icon:  '📊',
    cls:   'macros',
    title: 'Distribuição de Macros',
    fallback: (d) => {
      const m = d.macros;
      if (!m) return 'Os macronutrientes foram distribuídos de forma equilibrada para atender ao seu objetivo nutricional.';
      return `Seu plano contém ${m.protein_g}g de proteína, ${m.carbs_g}g de carboidratos e ${m.fat_g}g de gordura. Essa distribuição foi ajustada de acordo com seu objetivo para garantir equilíbrio energético e nutricional.`;
    },
  },
  {
    key:   'food_choices',
    icon:  '🥗',
    cls:   'foods',
    title: 'Escolha dos Alimentos',
    fallback: (_) => 'Os alimentos foram selecionados priorizando seus alimentos preferidos, combinados com outros ingredientes para garantir variedade nutricional e praticidade no dia a dia brasileiro.',
  },
  {
    key:   'meal_structure',
    icon:  '🕐',
    cls:   'structure',
    title: 'Estrutura das Refeições',
    fallback: (d) => {
      const n = d.refeicoes?.length || '—';
      return `Seu plano foi dividido em ${n} refeições distribuídas ao longo do dia para manter o metabolismo ativo, controlar o apetite e facilitar a adesão à dieta no cotidiano.`;
    },
  },
  {
    key:   'goal_alignment',
    icon:  '🎯',
    cls:   'goal',
    title: 'Alinhamento com seu Objetivo',
    fallback: (d) => {
      const goal = d.goal_description || 'seu objetivo';
      return `Este plano foi montado especificamente para: ${goal}. Com consistência e adesão, você verá resultados reais em poucas semanas.`;
    },
  },
];

// Converte texto longo em parágrafos separados.
// Quebra em ". " seguido de letra maiúscula, preservando frações decimais (1,55 × 1,5 etc.)
function textToParas(text) {
  if (!text) return '<p class="explain-text" style="color:var(--gray-400);font-style:italic;">Informação não disponível.</p>';
  // Divide nos pontos que terminam frases (". " + maiúscula), preservando "Ex:", decimais etc.
  const sentences = text.split(/(?<=\w\.) (?=[A-ZÁÉÍÓÚÂÊÎÔÛÃẼĨÕŨÀÈÌÒÙÇ])/u);
  // Agrupa em parágrafos de 2 frases cada para leitura mais fácil
  const paras = [];
  for (let i = 0; i < sentences.length; i += 2) {
    const chunk = [sentences[i], sentences[i + 1]].filter(Boolean).join(' ');
    paras.push(`<p class="explain-text">${chunk}</p>`);
  }
  return paras.join('');
}

function openExplainModal() {
  const expl = dietData?.explanation;
  const body = document.getElementById('modal-explain-body');

  body.innerHTML = EXPLAIN_SECTIONS.map(sec => {
    const text = (expl && expl[sec.key]) ? expl[sec.key] : sec.fallback(dietData);
    return `
      <div class="explain-section">
        <div class="explain-section-header">
          <div class="explain-icon ${sec.cls}">${sec.icon}</div>
          <h3 class="explain-section-title">${sec.title}</h3>
        </div>
        ${textToParas(text)}
      </div>
    `;
  }).join('');

  body.scrollTop = 0;
  overlayExplain.classList.add('open');
  document.documentElement.classList.add('modal-open');
  closeBtnExplain.focus();
}

function closeExplainModal() {
  overlayExplain.classList.remove('open');
  document.documentElement.classList.remove('modal-open');
}

document.getElementById('btn-explain').addEventListener('click', openExplainModal);
closeBtnExplain.addEventListener('click', closeExplainModal);
overlayExplain.addEventListener('click', e => { if (e.target === overlayExplain) closeExplainModal(); });
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && overlayExplain.classList.contains('open')) closeExplainModal();
});

overlayExplain.addEventListener('touchmove', e => {
  if (!e.target.closest('#modal-explain-body')) e.preventDefault();
}, { passive: false });

// ════════════════════════════════
//  RENDER PAGE
// ════════════════════════════════

// Esconde o botão de cancelar geração
function hideCancelButton() {
  const btn = document.getElementById('btn-cancel-generation');
  if (btn) btn.style.display = 'none';
}

// Exibe o botão de cancelar geração (mostrado durante generate=1)
function showCancelButton() {
  const btn = document.getElementById('btn-cancel-generation');
  if (btn) btn.style.display = '';
}

/**
 * @param {string} msg
 * @param {string|null} ctaHref  - href do link secundário (ex: '/questionario/')
 * @param {string|null} ctaLabel - label do link secundário
 * @param {boolean} showRetry    - exibe botão "Tentar novamente" (para erros de geração)
 */
function showError(msg, ctaHref, ctaLabel, showRetry = false) {
  stopLoadingTips();
  hideCancelButton();
  document.getElementById('state-loading').style.display = 'none';
  document.getElementById('state-error').style.display   = 'flex';
  document.getElementById('error-msg').textContent = msg;

  const retryBtn = document.getElementById('btn-retry-generation');
  if (retryBtn) retryBtn.style.display = showRetry ? '' : 'none';

  const cta = document.getElementById('error-cta');
  if (cta && ctaHref) {
    cta.href          = ctaHref;
    cta.textContent   = ctaLabel || 'Continuar';
    cta.style.display = '';
  } else if (cta) {
    cta.style.display = 'none';
  }
}

function renderMacrosBar(macros) {
  if (!macros) return;
  const bar = document.getElementById('macros-bar');
  bar.classList.add('visible');

  const pg = macros.protein_g || 0;
  const cg = macros.carbs_g   || 0;
  const fg = macros.fat_g     || 0;

  const pkcal = pg * 4;
  const ckcal = cg * 4;
  const fkcal = fg * 9;
  const total = pkcal + ckcal + fkcal || 1;

  const ppct = Math.round(pkcal / total * 100);
  const cpct = Math.round(ckcal / total * 100);
  const fpct = 100 - ppct - cpct;

  const items = [
    { cls: 'p', emoji: '🥩', name: 'Proteína',     g: pg, kcal: pkcal, pct: ppct },
    { cls: 'c', emoji: '🌾', name: 'Carboidratos', g: cg, kcal: ckcal, pct: cpct },
    { cls: 'f', emoji: '🥑', name: 'Gordura',      g: fg, kcal: fkcal, pct: fpct },
  ];

  bar.innerHTML = `
    <div class="mb-top">
      <span class="mb-label">Macros do dia</span>
      <span class="mb-total" id="mb-total-kcal">0 kcal</span>
    </div>
    <div class="mb-split-bar" id="mb-split-bar">
      <div class="mb-seg p" data-idx="0" style="flex:${ppct}"></div>
      <div class="mb-seg c" data-idx="1" style="flex:${cpct}"></div>
      <div class="mb-seg f" data-idx="2" style="flex:${fpct}"></div>
    </div>
    <div class="mb-legend">
      ${items.map(m => `
        <span class="mb-legend-item">
          <span class="mb-legend-dot ${m.cls}"></span>${m.name} ${m.pct}%
        </span>
      `).join('')}
    </div>
    <div class="mb-cards">
      ${items.map((m, i) => `
        <div class="mb-card ${m.cls}" data-idx="${i}">
          <p class="mb-card-name">${m.emoji} ${m.name}</p>
          <p class="mb-card-value"><span class="mb-count-g" data-target="${m.g}">0</span><span class="mb-card-unit">g</span></p>
          <div class="mb-card-footer">
            <span class="mb-card-kcal"><span class="mb-count-kcal" data-target="${m.kcal}">0</span> kcal</span>
            <span class="mb-card-pct">${m.pct}%</span>
          </div>
          <div class="mb-card-bar"></div>
        </div>
      `).join('')}
    </div>
  `;

  // ── Animated counters ──────────────────────────────────────
  function easeOut(t) { return 1 - Math.pow(1 - t, 3); }
  function animateCounter(el, target, duration) {
    const start = performance.now();
    function tick(now) {
      const t = Math.min((now - start) / duration, 1);
      el.textContent = Math.round(easeOut(t) * target).toLocaleString('pt-BR');
      if (t < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  const DURATION = 900;
  document.querySelectorAll('.mb-count-g').forEach(el =>
    animateCounter(el, +el.dataset.target, DURATION));
  document.querySelectorAll('.mb-count-kcal').forEach(el =>
    animateCounter(el, +el.dataset.target, DURATION));

  // Animate total kcal display
  animateCounter(document.getElementById('mb-total-kcal'), total, DURATION);
  // Append " kcal" suffix after animation ends
  setTimeout(() => {
    const el = document.getElementById('mb-total-kcal');
    if (el) el.textContent = total.toLocaleString('pt-BR') + ' kcal';
  }, DURATION + 50);

  // ── Tooltip + focus/dim interactions ──────────────────────
  const tooltip = document.getElementById('mb-tooltip');
  const splitBar = document.getElementById('mb-split-bar');
  const segs = splitBar.querySelectorAll('.mb-seg');
  const cards = bar.querySelectorAll('.mb-card');

  function focusMacro(idx) {
    bar.classList.add('has-focus');
    splitBar.classList.add('has-focus');
    segs.forEach((s, i) => s.classList.toggle('mb-focus', i === idx));
    cards.forEach((c, i) => c.classList.toggle('mb-focus', i === idx));
  }
  function clearFocus() {
    bar.classList.remove('has-focus');
    splitBar.classList.remove('has-focus');
    segs.forEach(s => s.classList.remove('mb-focus'));
    cards.forEach(c => c.classList.remove('mb-focus'));
    tooltip.classList.remove('show');
  }

  function showTooltip(idx, x, y) {
    const m = items[idx];
    tooltip.textContent = `${m.name} — ${m.g}g · ${m.kcal} kcal (${m.pct}%)`;
    tooltip.classList.add('show');
    tooltip.style.left = (x + 14) + 'px';
    tooltip.style.top  = (y - 36) + 'px';
  }

  segs.forEach((seg, i) => {
    seg.addEventListener('mouseenter', () => focusMacro(i));
    seg.addEventListener('mouseleave', clearFocus);
    seg.addEventListener('mousemove', e => showTooltip(i, e.clientX, e.clientY));
  });

  cards.forEach((card, i) => {
    card.addEventListener('mouseenter', () => focusMacro(i));
    card.addEventListener('mouseleave', clearFocus);
  });
}

function renderMealCards(refeicoes) {
  const grid = document.getElementById('meals-grid');
  grid.innerHTML = '';

  const badge = document.getElementById('meals-count-badge');
  if (badge) badge.textContent = refeicoes.length;

  refeicoes.forEach((r, i) => {
    const rawMeal  = (dietData.meals_raw || [])[i] || {};
    const time     = rawMeal.time_suggestion || null;
    const rawFoods = rawMeal.foods || [];
    const colorIdx = i % 8;

    // Build food chips
    const MAX_CHIPS = 4;
    let chipsHTML = '';
    if (rawFoods.length > 0) {
      const chipItems = rawFoods.slice(0, MAX_CHIPS);
      const moreCount = rawFoods.length - MAX_CHIPS;
      chipsHTML = chipItems.map(f => `<span class="meal-chip">${escapeHtml(f.name)}</span>`).join('');
      if (moreCount > 0) chipsHTML += `<span class="meal-chip-more">+${moreCount}</span>`;
    } else {
      const fallbackItems = (r.descricao_refeicao || '').replace(/•\s*/g, '').split(/[,\n]/).map(s => s.trim()).filter(Boolean).slice(0, 4);
      chipsHTML = fallbackItems.map(s => `<span class="meal-chip">${escapeHtml(s)}</span>`).join('');
    }

    const card = document.createElement('div');
    card.className = 'meal-card';
    card.dataset.mealColor = colorIdx;
    card.style.animationDelay = `${i * 0.08}s`;
    card.tabIndex = 0;
    card.role = 'button';
    card.setAttribute('aria-label', `Ver detalhes de ${r.nome_refeicao}`);
    card.innerHTML = `
      <div class="meal-card-header">
        <div class="meal-card-header-top">
          <div class="meal-emoji-wrap">${MEAL_EMOJIS[i % MEAL_EMOJIS.length]}</div>
          <span class="meal-kcal-badge">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7z"/></svg>
            ${r.calorias_estimadas} kcal
          </span>
        </div>
        <div class="meal-card-header-bottom">
          <p class="meal-order-label">
            <span class="meal-order-dot"></span>
            Refeição ${i + 1}
          </p>
          <p class="meal-name">${escapeHtml(r.nome_refeicao)}</p>
          ${time ? `<span class="meal-time-tag">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            ${escapeHtml(time)}
          </span>` : ''}
        </div>
      </div>
      <div class="meal-card-body">
        <div class="meal-chips">${chipsHTML}</div>
      </div>
      <div class="meal-card-sep"></div>
      <div class="meal-card-footer">
        <div class="meal-detail-link">
          <span>Ver detalhes</span>
          <span class="meal-detail-arrow">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
          </span>
        </div>
      </div>
    `;
    card.addEventListener('click',   () => openModal(i));
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openModal(i); } });
    grid.appendChild(card);
  });

}

function renderDiet(diet) {
  dietData = diet;
  document.getElementById('state-loading').style.display = 'none';
  document.getElementById('diet-content').style.display  = 'block';

  document.getElementById('stat-calories').textContent =
    (diet.calorias_totais || '—').toLocaleString('pt-BR');
  document.getElementById('stat-meals').textContent =
    diet.refeicoes?.length || '—';
  document.getElementById('goal-desc').textContent =
    diet.goal_description || 'Plano personalizado';

  if (diet.created_at) {
    const d = new Date(diet.created_at);
    document.getElementById('diet-date').textContent =
      `Dieta gerada em ${d.toLocaleDateString('pt-BR', { day:'2-digit', month:'long', year:'numeric' })}`;
  }

  renderMacrosBar(diet.macros);
  renderMealCards(diet.refeicoes || []);

  if (diet.notes) {
    document.getElementById('notes-box').classList.add('visible');
    document.getElementById('notes-box-text').textContent = diet.notes;
  }

  // Sempre mostra o botão — o modal tem fallback para dietas antigas sem explanation
  document.getElementById('btn-explain').style.display = 'inline-flex';
}

// ════════════════════════════════
//  LOAD — geração assíncrona com polling
// ════════════════════════════════

// Mensagens rotativas exibidas enquanto a IA processa
const LOADING_TIPS = [
  'Calculando seu metabolismo basal...',
  'Ajustando macronutrientes ao seu objetivo...',
  'Selecionando alimentos compatíveis com suas restrições...',
  'Distribuindo refeições ao longo do dia...',
  'Verificando equilíbrio calórico...',
  'Montando o plano personalizado...',
  'Quase pronto! Finalizando sua dieta...',
];
let _tipIndex = 0;
let _tipInterval = null;

function startLoadingTips() {
  const msgEl = document.getElementById('loading-msg');
  _tipIndex = 0;
  msgEl.textContent = LOADING_TIPS[0];
  _tipInterval = setInterval(() => {
    _tipIndex = (_tipIndex + 1) % LOADING_TIPS.length;
    msgEl.textContent = LOADING_TIPS[_tipIndex];
  }, 4000);
}

function stopLoadingTips() {
  if (_tipInterval) { clearInterval(_tipInterval); _tipInterval = null; }
}

/**
 * Faz polling no endpoint de status a cada POLL_INTERVAL ms.
 * Retorna uma Promise que resolve com o DietPlan ao concluir,
 * ou rejeita com a mensagem de erro se falhar.
 */
function pollJobStatus(jobId) {
  const POLL_INTERVAL = 3000;  // 3 segundos
  const MAX_POLLS     = 60;    // timeout: 3min (60 × 3s)
  return new Promise((resolve, reject) => {
    let polls = 0;

    const interval = setInterval(async () => {
      polls++;

      try {
        const res = await apiFetch(`${API_BASE}/diet/status/${jobId}`);

        if (res.status === 401) {
          clearInterval(interval);
          stopLoadingTips();
          localStorage.removeItem('mynutri_user');
          window.location.href = '/auth/';
          return;
        }

        if (!res.ok) {
          clearInterval(interval);
          stopLoadingTips();
          reject(new Error('Erro ao verificar status da geração.'));
          return;
        }

        const data = await res.json();

        if (data.status === 'done' && data.diet_plan_id) {
          clearInterval(interval);
          stopLoadingTips();
          const planRes = await apiFetch(`${API_BASE}/diet/${data.diet_plan_id}`);
          if (!planRes.ok) { reject(new Error('Erro ao carregar dieta gerada.')); return; }
          resolve(await planRes.json());

        } else if (data.status === 'failed') {
          clearInterval(interval);
          stopLoadingTips();
          reject(new Error(data.error || 'Falha ao gerar dieta. Tente novamente.'));

        } else if (polls >= MAX_POLLS) {
          clearInterval(interval);
          stopLoadingTips();
          reject(new Error('A geração demorou demais. Recarregue a página para verificar se sua dieta foi criada.'));
        }
        // pending/processing → continua polling

      } catch (err) {
        clearInterval(interval);
        stopLoadingTips();
        reject(err);
      }
    }, POLL_INTERVAL);
  });
}

async function generateDiet() {
  const jsonHeaders = { 'Content-Type': 'application/json' };

  // Volta para o estado de loading
  document.getElementById('state-error').style.display   = 'none';
  document.getElementById('state-loading').style.display = 'flex';
  document.getElementById('loading-msg').textContent     = 'Iniciando geração...';
  document.getElementById('loading-subtitle').textContent =
    'A IA está preparando seu plano personalizado. Não feche esta página.';

  showCancelButton();
  startLoadingTips();

  let jobId;
  try {
    const dr = await apiFetch(`${API_BASE}/diet/generate`, { method: 'POST', headers: jsonHeaders, body: '{}' });
    if (!dr.ok) {
      const e = await dr.json().catch(() => ({}));
      showError(e.error || 'Erro ao iniciar geração. Tente novamente.', '/questionario/', 'Refazer questionário', true);
      return;
    }
    const jobData = await dr.json();
    jobId = jobData.job_id;

    // Modo síncrono (dev sem Redis): job já está done, busca direto
    if (jobData.status === 'done' && jobData.diet_plan_id) {
      hideCancelButton();
      stopLoadingTips();
      const planRes = await apiFetch(`${API_BASE}/diet/${jobData.diet_plan_id}`);
      renderDiet(await planRes.json());
      history.replaceState(null, '', 'dieta.html');
      return;
    }

  } catch (err) {
    console.error(err);
    showError('Erro de conexão ao iniciar geração. Tente novamente.', '/questionario/', 'Refazer questionário', true);
    return;
  }

  // Polling assíncrono (prod com Redis)
  try {
    const diet = await pollJobStatus(jobId);
    hideCancelButton();
    renderDiet(diet);
    history.replaceState(null, '', 'dieta.html');
  } catch (err) {
    console.error(err);
    showError(err.message || 'Erro ao gerar dieta. Tente novamente.', '/questionario/', 'Refazer questionário', true);
  }
}

async function loadDiet() {
  const generate = new URLSearchParams(window.location.search).get('generate');

  if (generate === '1') {
    const jsonHeaders = { 'Content-Type': 'application/json' };

    // 1. Envia anamnese pendente se houver (fluxo de login intermediário)
    const pending = sessionStorage.getItem('anamneseData');
    if (pending) {
      document.getElementById('loading-msg').textContent = 'Enviando questionário...';
      try {
        const ar = await apiFetch(`${API_BASE}/anamnese`, { method: 'POST', headers: jsonHeaders, body: pending });
        if (!ar.ok) {
          const e = await ar.json().catch(() => ({}));
          showError(Object.values(e).flat().join(' ') || 'Erro ao salvar questionário.', '/questionario/', 'Voltar ao questionário');
          return;
        }
        sessionStorage.removeItem('anamneseData');
      } catch {
        showError('Erro de conexão ao salvar questionário.', '/questionario/', 'Voltar ao questionário');
        return;
      }
    }

    // 2. Inicia geração
    await generateDiet();

  } else {
    await fetchExistingDiet();
  }
}

async function fetchExistingDiet() {
  try {
    const res = await apiFetch(`${API_BASE}/diet`, { redirectOn401: false });
    if (res.status === 401) { localStorage.removeItem('mynutri_user'); showError('Faça login para ver sua dieta.', '/auth/', 'Fazer login'); return; }
    if (res.status === 404) { showError('Você ainda não possui um plano alimentar.', '/questionario/', 'Fazer questionário'); return; }
    if (!res.ok)            { showError('Não foi possível carregar sua dieta.'); return; }
    renderDiet(await res.json());
  } catch (err) {
    showError(`Erro de conexão. Verifique se o servidor está rodando. Erro: ${err.message}`);
  }
}

// ════════════════════════════════
//  DOWNLOAD PDF
// ════════════════════════════════
document.getElementById('btn-download-pdf').addEventListener('click', async () => {
  const dietId = dietData?.id;
  if (!dietId) return;

  const btn   = document.getElementById('btn-download-pdf');
  const label = document.getElementById('btn-pdf-label');
  btn.disabled  = true;
  label.textContent = 'Gerando PDF...';

  try {
    const res = await apiFetch(`${API_BASE}/diet/${dietId}/pdf`);

    if (!res.ok) {
      alert('Não foi possível gerar o PDF. Tente novamente.');
      return;
    }

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `mynutri-dieta.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch {
    alert('Erro de conexão ao baixar o PDF.');
  } finally {
    btn.disabled      = false;
    label.textContent = 'Baixar PDF';
  }
});

// ════════════════════════════════
//  CHAT DOCK — toggle listener
// ════════════════════════════════
document.getElementById('chat-dock-toggle').addEventListener('click', () => {
  const panel = document.getElementById('chat-dock-panel');
  panel.classList.contains('open') ? closeChatDock() : openChatDock();
});

// ════════════════════════════════
//  BOTÕES DE LOADING / ERRO
// ════════════════════════════════
document.getElementById('btn-cancel-generation').addEventListener('click', () => {
  window.location.href = '/questionario/';
});

document.getElementById('btn-retry-generation').addEventListener('click', () => {
  generateDiet();
});

loadDiet();

})();

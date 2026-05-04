(function () {
  const _user = JSON.parse(localStorage.getItem('mynutri_user') || 'null');

  initUserMenu({ requireAuth: false, logoutRedirect: '/' });

  const totalSteps = 5;
  let currentStep = 1;

  const form      = document.getElementById('questionnaire-form');
  const btnNext   = document.getElementById('btn-next');
  const btnBack   = document.getElementById('btn-back');
  const btnSubmit = document.getElementById('btn-submit');
  const stepInfo  = document.getElementById('step-info');

  // --- Validation per step ---
  function validateStep(step) {
    let valid = true;
    clearErrors(step);

    if (step === 1) {
      valid = validateRequired('nome') && valid;
      valid = validateNumber('idade', 10, 120) && valid;
      valid = validateRequired('sexo') && valid;
      valid = validateNumber('peso', 20, 400) && valid;
      valid = validateNumber('altura', 100, 250) && valid;
    }

    if (step === 2) {
      const selected = form.querySelector('input[name="objetivo"]:checked');
      if (!selected) { showError('objetivo'); valid = false; }
    }

    if (step === 3) {
      const selected = form.querySelector('input[name="atividade"]:checked');
      if (!selected) { showError('atividade'); valid = false; }
    }

    if (step === 5) {
      valid = validateRequired('refeicoes') && valid;
    }

    return valid;
  }

  function validateRequired(id) {
    const el = document.getElementById(id);
    if (!el.value.trim()) {
      el.classList.add('error');
      if (el.type === 'hidden' && el.parentElement.classList.contains('custom-select-wrapper')) {
        el.parentElement.querySelector('.custom-select-trigger').classList.add('error');
      }
      showError(id);
      return false;
    }
    return true;
  }

  function validateNumber(id, min, max) {
    const el = document.getElementById(id);
    const val = parseFloat(el.value);
    if (!el.value.trim() || isNaN(val) || val < min || val > max) {
      el.classList.add('error');
      showError(id);
      return false;
    }
    return true;
  }

  function showError(id) {
    const err = document.getElementById(id + '-error');
    if (err) err.classList.add('visible');
  }

  function clearErrors(step) {
    const stepEl = form.querySelector(`.form-step[data-step="${step}"]`);
    if (!stepEl) return;
    stepEl.querySelectorAll('.form-input, .form-select, .form-textarea, .custom-select-trigger').forEach(function (el) { el.classList.remove('error'); });
    stepEl.querySelectorAll('.form-error').forEach(function (el) { el.classList.remove('visible'); });
  }

  form.querySelectorAll('.form-input, .form-select, .form-textarea').forEach(function (el) {
    el.addEventListener('input', function () {
      el.classList.remove('error');
      const err = document.getElementById(el.id + '-error');
      if (err) err.classList.remove('visible');
    });
  });

  form.querySelectorAll('input[type="radio"]').forEach(function (radio) {
    radio.addEventListener('change', function () {
      const err = document.getElementById(radio.name + '-error');
      if (err) err.classList.remove('visible');
    });
  });

  // --- Navigation ---
  function goToStep(step) {
    const currentEl = form.querySelector(`.form-step[data-step="${currentStep}"]`);
    if (currentEl) currentEl.classList.remove('active');

    currentStep = step;

    const nextEl = form.querySelector(`.form-step[data-step="${step}"]`);
    if (nextEl) nextEl.classList.add('active');

    updateProgress();

    btnBack.classList.toggle('hidden', currentStep === 1);

    if (currentStep === totalSteps) {
      btnNext.style.display = 'none';
      btnSubmit.style.display = 'inline-flex';
    } else {
      btnNext.style.display = 'inline-flex';
      btnSubmit.style.display = 'none';
    }

    stepInfo.innerHTML = `Etapa <strong>${currentStep}</strong> de <strong>${totalSteps}</strong>`;
  }

  function updateProgress() {
    for (let i = 1; i <= totalSteps; i++) {
      const stepEl = document.querySelector(`.progress-step[data-step="${i}"]`);
      stepEl.classList.remove('active', 'completed');
      if (i < currentStep) stepEl.classList.add('completed');
      else if (i === currentStep) stepEl.classList.add('active');
    }

    for (let i = 1; i < totalSteps; i++) {
      const connector = document.querySelector(`.progress-connector[data-connector="${i}"]`);
      if (i < currentStep) connector.classList.add('completed');
      else connector.classList.remove('completed');
    }
  }

  btnNext.addEventListener('click', function () {
    if (validateStep(currentStep)) goToStep(currentStep + 1);
  });

  btnBack.addEventListener('click', function () {
    if (currentStep > 1) goToStep(currentStep - 1);
  });

  // --- Form Submit ---
  function showSubmitError(msg) {
    const el = document.getElementById('submit-error');
    el.style.display = 'block';
    el.textContent = msg;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function hideSubmitError() {
    document.getElementById('submit-error').style.display = 'none';
  }

  function resetSubmitBtn() {
    btnSubmit.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg> Gerar minha dieta`;
    btnSubmit.style.opacity = '1';
    btnSubmit.style.pointerEvents = '';
  }

  const SEXO_MAP     = { masculino: 'M', feminino: 'F', outro: 'O' };
  const OBJETIVO_MAP = { perda_peso: 'lose', manutencao: 'maintain', ganho_massa: 'gain', saude: 'maintain' };
  const ATIVIDADE_MAP = { sedentario: 'sedentary', leve: 'light', moderado: 'moderate', intenso: 'intense', atleta: 'athlete' };

  function collectFormData() {
    const formData = new FormData(form);
    const raw = {};
    for (const [key, value] of formData.entries()) {
      if (raw[key]) {
        raw[key] = Array.isArray(raw[key]) ? [...raw[key], value] : [raw[key], value];
      } else {
        raw[key] = value;
      }
    }

    const restricoesList = [];
    if (raw.tipo_dieta && raw.tipo_dieta !== 'onivoro') restricoesList.push(raw.tipo_dieta);
    if (raw.restricoes) {
      const checks = Array.isArray(raw.restricoes) ? raw.restricoes : [raw.restricoes];
      restricoesList.push(...checks);
    }
    if (raw.outras_restricoes && raw.outras_restricoes.trim()) {
      restricoesList.push(raw.outras_restricoes.trim());
    }

    const favs = raw.alimentos_favoritos || '';
    const obs  = (raw.observacoes || '').trim();
    const food_preferences = obs
      ? (favs ? `${favs}\nObservações: ${obs}` : `Observações: ${obs}`)
      : favs;

    return {
      idade: parseInt(raw.idade),
      sexo: SEXO_MAP[raw.sexo] || raw.sexo,
      peso: parseFloat(raw.peso),
      altura: parseFloat(raw.altura),
      objetivo: OBJETIVO_MAP[raw.objetivo] || raw.objetivo,
      nivel_atividade: ATIVIDADE_MAP[raw.atividade] || raw.atividade,
      meals_per_day: parseInt(raw.refeicoes) || 3,
      restricoes: restricoesList.join(', '),
      food_preferences,
      allergies: raw.alimentos_evitar || '',
    };
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    if (!validateStep(currentStep)) return;

    hideSubmitError();

    if (!_user) {
      sessionStorage.setItem('anamneseData', JSON.stringify(collectFormData()));
      btnSubmit.textContent = 'Redirecionando...';
      btnSubmit.style.opacity = '0.7';
      btnSubmit.style.pointerEvents = 'none';
      setTimeout(function () { window.location.href = '/auth/?intent=save_diet'; }, 800);
      return;
    }

    btnSubmit.textContent = 'Enviando questionário...';
    btnSubmit.style.opacity = '0.7';
    btnSubmit.style.pointerEvents = 'none';

    try {
      const anamneseRes = await apiFetch(`${API_BASE}/anamnese`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectFormData()),
      });

      if (!anamneseRes.ok) {
        const err = await anamneseRes.json();
        const msg = Object.values(err).flat().join(' ') || JSON.stringify(err);
        showSubmitError('Erro ao salvar questionário: ' + msg);
        resetSubmitBtn();
        return;
      }

      window.location.href = '/dieta/?generate=1';
    } catch (err) {
      showSubmitError('Erro de conexão com o servidor. Verifique se o Django está rodando.\n\nDetalhe: ' + err.message);
      resetSubmitBtn();
    }
  });

  // --- Tags & Autocomplete ---
  const ALIMENTOS_BRASIL = [
    "Frango", "Frango Grelhado", "Frango Assado", "Frango Empanado", "Frango Desfiado",
    "Carne Bovina", "Carne Moída", "Bife", "Alcatra", "Picanha", "Costela", "Churrasco",
    "Linguiça", "Calabresa", "Salsicha", "Presunto", "Peito de Peru",
    "Peixe", "Tilápia", "Salmão", "Atum", "Sardinha",
    "Ovo", "Ovo Frito", "Ovo Cozido", "Omelete",
    "Hambúrguer",
    "Leite", "Leite Integral", "Leite Desnatado", "Leite Condensado",
    "Iogurte", "Iogurte Natural", "Iogurte Grego",
    "Queijo Mussarela", "Queijo Prato", "Queijo Minas", "Queijo Coalho",
    "Requeijão", "Cream Cheese",
    "Arroz Branco", "Arroz Integral", "Macarrão", "Lasanha", "Nhoque",
    "Pão Francês", "Pão de Forma", "Pão Integral", "Pão de Queijo",
    "Batata", "Batata Frita", "Batata Doce", "Purê de Batata",
    "Mandioca", "Farofa", "Cuscuz", "Tapioca", "Milho", "Polenta",
    "Alface", "Tomate", "Cenoura", "Brócolis", "Couve", "Repolho",
    "Pepino", "Beterraba", "Abobrinha", "Berinjela",
    "Banana", "Maçã", "Laranja", "Uva", "Morango", "Manga",
    "Mamão", "Melancia", "Melão", "Abacaxi", "Maracujá",
    "Limão", "Pera", "Goiaba", "Açaí",
    "Chocolate", "Chocolate Amargo", "Brigadeiro", "Beijinho",
    "Bolo de Chocolate", "Bolo de Cenoura", "Bolo de Fubá",
    "Sorvete", "Doce de Leite", "Pudim", "Gelatina",
    "Açaí com Granola",
    "Café", "Café com Leite", "Chá",
    "Suco Natural", "Suco de Laranja", "Suco de Uva",
    "Refrigerante", "Refrigerante Zero",
    "Água de Coco", "Leite com Chocolate",
    "Pizza", "Hambúrguer Artesanal", "X-Burguer", "X-Salada",
    "Batata Frita com Cheddar", "Hot Dog",
    "Coxinha", "Pastel", "Esfiha", "Kibe", "Empada",
    "Feijão", "Feijão Preto", "Feijoada",
    "Arroz com Feijão", "Arroz Carreteiro",
    "Estrogonofe de Frango", "Estrogonofe de Carne",
    "Risoto", "Panqueca", "Macarronada",
    "Frango com Batata", "Carne com Batata",
    "Sanduíche Natural", "Misto Quente", "Torrada",
    "Pão com Ovo", "Pão com Manteiga",
    "Pão com Presunto e Queijo",
    "Wrap", "Crepioca",
    "Amendoim", "Castanha de Caju", "Castanha do Pará",
    "Pasta de Amendoim", "Granola", "Mel",
    "Azeite", "Manteiga", "Maionese", "Ketchup", "Mostarda",
  ];

  function setupTagsInput(wrapperId, dropdownId, hiddenId, isAvoid) {
    isAvoid = isAvoid || false;
    const wrapper     = document.getElementById(wrapperId);
    const input       = wrapper.querySelector('.tags-input-inner');
    const dropdown    = document.getElementById(dropdownId);
    const hiddenField = document.getElementById(hiddenId);
    const tags        = [];
    let highlightedIndex = -1;

    function updateHiddenValue() { hiddenField.value = tags.join(', '); }

    function renderTags() {
      wrapper.querySelectorAll('.tag-badge').forEach(function (el) { el.remove(); });
      tags.forEach(function (tagText, index) {
        const badge = document.createElement('div');
        badge.className = `tag-badge ${isAvoid ? 'badge-avoid' : ''}`;
        badge.innerHTML = `
          ${tagText}
          <button type="button" class="tag-badge-remove" data-index="${index}" aria-label="Remover">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        `;
        wrapper.insertBefore(badge, input);
      });
      updateHiddenValue();
    }

    function addTag(text) {
      const formatted = text.trim();
      if (formatted && !tags.includes(formatted)) {
        tags.push(formatted);
        renderTags();
      }
      input.value = '';
      closeDropdown();
    }

    function removeTag(index) { tags.splice(index, 1); renderTags(); }

    function closeDropdown() {
      dropdown.classList.remove('active');
      dropdown.innerHTML = '';
      highlightedIndex = -1;
    }

    function showDropdown(matches) {
      dropdown.innerHTML = '';
      if (matches.length === 0) { closeDropdown(); return; }
      matches.forEach(function (match, index) {
        const item = document.createElement('div');
        item.className = 'autocomplete-item';
        item.textContent = match;
        item.addEventListener('mousedown', function (e) { e.preventDefault(); addTag(match); });
        dropdown.appendChild(item);
      });
      dropdown.classList.add('active');
    }

    wrapper.addEventListener('click', function (e) {
      if (e.target.closest('.tag-badge-remove')) {
        const idx = parseInt(e.target.closest('.tag-badge-remove').getAttribute('data-index'));
        removeTag(idx);
        return;
      }
      input.focus();
    });

    input.addEventListener('focus', function () { wrapper.classList.add('focused'); });

    input.addEventListener('blur', function () {
      wrapper.classList.remove('focused');
      setTimeout(function () {
        if (input.value.trim().length > 0) addTag(input.value);
        closeDropdown();
      }, 150);
    });

    input.addEventListener('input', function () {
      const val = input.value.trim().toLowerCase();
      if (!val) { closeDropdown(); return; }
      const normalize = function (str) { return str.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); };
      const normalVal = normalize(val);
      const matches = ALIMENTOS_BRASIL.filter(function (item) {
        return normalize(item).includes(normalVal) && !tags.includes(item);
      }).slice(0, 8);
      showDropdown(matches);
    });

    input.addEventListener('keydown', function (e) {
      const items = dropdown.querySelectorAll('.autocomplete-item');
      if (e.key === 'Backspace' && input.value === '' && tags.length > 0) {
        removeTag(tags.length - 1);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (highlightedIndex >= 0 && items.length > 0) {
          addTag(items[highlightedIndex].textContent);
        } else if (input.value.trim().length > 0) {
          addTag(input.value);
        }
      } else if (e.key === 'ArrowDown' && items.length > 0) {
        e.preventDefault();
        highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
        items.forEach(function (item, idx) { item.classList.toggle('selected', idx === highlightedIndex); });
      } else if (e.key === 'ArrowUp' && items.length > 0) {
        e.preventDefault();
        highlightedIndex = Math.max(highlightedIndex - 1, 0);
        items.forEach(function (item, idx) { item.classList.toggle('selected', idx === highlightedIndex); });
      }
    });

    return addTag;
  }

  setupTagsInput('wrapper-favoritos', 'dropdown-favoritos', 'alimentos-favoritos', false);
  setupTagsInput('wrapper-evitar', 'dropdown-evitar', 'alimentos-evitar', true);

  // --- Pré-preenchimento ---
  const SEXO_REVERSE = { M: 'masculino', F: 'feminino', O: 'outro' };

  function _fillInput(id, value) {
    const el = document.getElementById(id);
    if (el && value != null && String(value) !== '') {
      el.value = value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function _selectCustomOption(wrapperId, value) {
    const wrapper = document.getElementById(wrapperId);
    if (!wrapper || !value) return;
    const option = wrapper.querySelector(`.custom-select-option[data-value="${value}"]`);
    if (option) option.click();
  }

  function _selectRadio(name, value) {
    const radio = document.querySelector(`input[name="${name}"][value="${value}"]`);
    if (!radio) return;
    radio.checked = true;
    radio.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function _applyPrefill(data) {
    if (_user?.nome) _fillInput('nome', _user.nome);
    if (data.idade)  _fillInput('idade', data.idade);
    if (data.sexo)   _selectCustomOption('custom-sexo', SEXO_REVERSE[data.sexo]);
    if (data.peso)   _fillInput('peso', data.peso);
    if (data.altura) _fillInput('altura', data.altura);
  }

  async function _prefillFromAnamnese() {
    if (!_user) return;

    if (_user?.nome) _fillInput('nome', _user.nome);

    try {
      const res = await apiFetch(`${API_BASE}/anamnese/last`);
      if (!res.ok) return;
      const data = await res.json();
      _applyPrefill(data);
      const notice = document.getElementById('prefill-notice');
      if (notice) notice.style.display = 'flex';
    } catch { /* falha silenciosa */ }
  }

  _prefillFromAnamnese();

  // --- Keyboard navigation ---
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.tagName !== 'TEXTAREA' && !e.target.classList.contains('tags-input-inner') && !e.target.classList.contains('custom-select-trigger')) {
      e.preventDefault();
      if (currentStep < totalSteps) btnNext.click();
      else btnSubmit.click();
    }
  });

  // --- Custom Selects ---
  function setupCustomSelects() {
    document.querySelectorAll('.custom-select-wrapper').forEach(function (wrapper) {
      const trigger = wrapper.querySelector('.custom-select-trigger');
      const label   = wrapper.querySelector('.custom-select-label');
      const hidden  = wrapper.querySelector('input[type="hidden"]');
      const options = wrapper.querySelectorAll('.custom-select-option');

      trigger.addEventListener('click', function () {
        document.querySelectorAll('.custom-select-wrapper').forEach(function (w) {
          if (w !== wrapper) w.classList.remove('open');
        });
        wrapper.classList.toggle('open');
      });

      trigger.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          wrapper.classList.toggle('open');
        }
      });

      options.forEach(function (opt) {
        opt.addEventListener('click', function () {
          label.textContent = opt.textContent;
          label.classList.remove('placeholder');
          hidden.value = opt.getAttribute('data-value');
          wrapper.classList.remove('error');
          trigger.classList.remove('error');
          const err = document.getElementById(hidden.id + '-error');
          if (err) err.classList.remove('visible');
          wrapper.classList.remove('open');
        });
      });

      document.addEventListener('click', function (e) {
        if (!wrapper.contains(e.target)) wrapper.classList.remove('open');
      });
    });
  }

  setupCustomSelects();
})();

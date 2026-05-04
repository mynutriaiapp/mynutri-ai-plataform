(function () {
  // --- Mobile nav ---
  const mobileToggle = document.getElementById('mobile-toggle');
  const nav = document.getElementById('nav');
  mobileToggle.addEventListener('click', function () {
    nav.classList.toggle('open');
    const spans = mobileToggle.querySelectorAll('span');
    if (nav.classList.contains('open')) {
      spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
      spans[1].style.opacity = '0';
      spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
    } else {
      spans[0].style.transform = '';
      spans[1].style.opacity = '';
      spans[2].style.transform = '';
    }
  });

  // --- User menu ---
  initUserMenu({
    requireAuth: false,
    logoutRedirect: '/',
    onUserLoaded: function (user) {
      const nomeField  = document.getElementById('contact-nome');
      const emailField = document.getElementById('contact-email');
      if (nomeField  && !nomeField.value)  nomeField.value  = user.nome  || '';
      if (emailField && !emailField.value) emailField.value = user.email || '';
    },
  });

  // --- Contact form ---
  document.getElementById('contact-form').addEventListener('submit', async function (e) {
    e.preventDefault();

    const form     = e.target;
    const btn      = document.getElementById('btn-contact-submit');
    const nome     = document.getElementById('contact-nome').value.trim();
    const email    = document.getElementById('contact-email').value.trim();
    const assunto  = document.getElementById('contact-assunto').value;
    const mensagem = document.getElementById('contact-mensagem').value.trim();

    function showFormError(msg) {
      let el = document.getElementById('contact-form-error');
      if (!el) {
        el = document.createElement('p');
        el.id = 'contact-form-error';
        el.style.cssText = 'color:#dc2626;font-size:.875rem;margin-top:-.25rem;margin-bottom:.5rem;';
        btn.parentElement.insertBefore(el, btn);
      }
      el.textContent = msg;
    }

    function clearFormError() {
      const el = document.getElementById('contact-form-error');
      if (el) el.textContent = '';
    }

    clearFormError();

    if (!nome || !email || !assunto || !mensagem) {
      showFormError('Por favor, preencha todos os campos obrigatórios.');
      return;
    }
    if (mensagem.length < 10) {
      showFormError('A mensagem deve ter pelo menos 10 caracteres.');
      return;
    }

    btn.disabled = true;
    const originalBtnHTML = btn.innerHTML;
    btn.innerHTML = 'Enviando…';

    try {
      const res = await fetch(`${API_BASE}/contact`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ nome, email, assunto, mensagem }),
      });

      if (res.ok) {
        document.getElementById('contact-form-title').style.display = 'none';
        form.style.display = 'none';
        document.getElementById('contact-success').style.display = 'flex';
      } else {
        const data = await res.json().catch(() => ({}));
        const msg = data?.error
          || (data?.errors ? Object.values(data.errors).flat().join(' ') : null)
          || 'Erro ao enviar. Tente novamente.';
        showFormError(msg);
      }
    } catch {
      showFormError('Sem conexão com o servidor. Verifique sua internet e tente novamente.');
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalBtnHTML;
    }
  });

  // --- FAQ Accordion ---
  document.querySelectorAll('.faq-question').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const item = btn.parentElement;
      const isOpen = item.classList.contains('open');
      document.querySelectorAll('.faq-item').forEach(function (i) { i.classList.remove('open'); });
      if (!isOpen) item.classList.add('open');
    });
  });
})();

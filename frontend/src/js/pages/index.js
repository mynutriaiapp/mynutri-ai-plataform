(function () {
  // --- User menu ---
  initUserMenu({ requireAuth: false, logoutRedirect: '/' });

  // --- Header scroll effect ---
  const header = document.getElementById('header');
  window.addEventListener('scroll', function () {
    header.classList.toggle('scrolled', window.scrollY > 40);
  });

  // --- Mobile nav toggle ---
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

  nav.querySelectorAll('.nav-link').forEach(function (link) {
    link.addEventListener('click', function () {
      nav.classList.remove('open');
      const spans = mobileToggle.querySelectorAll('span');
      spans[0].style.transform = '';
      spans[1].style.opacity = '';
      spans[2].style.transform = '';
    });
  });

  // --- Smooth scroll for anchor links ---
  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        e.preventDefault();
        const y = target.getBoundingClientRect().top + window.pageYOffset - 80;
        window.scrollTo({ top: y, behavior: 'smooth' });
      }
    });
  });

  // --- Animated counters for hero stats ---
  function animateCounter(element, target, suffix) {
    suffix = suffix || '';
    const duration  = 1500;
    const startTime = performance.now();

    function update(currentTime) {
      const elapsed  = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const easeOut  = 1 - Math.pow(1 - progress, 3);
      const val      = Math.round(target * easeOut);
      element.textContent = val.toLocaleString('pt-BR') + suffix;
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  const statsObserver = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        const stats = entry.target.querySelectorAll('.hero-stat-number');
        animateCounter(stats[0], 15, 'k+');
        animateCounter(stats[1], 98, '%');
        animateCounter(stats[2], 30, 's');
        statsObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  const heroStats = document.querySelector('.hero-stats');
  if (heroStats) statsObserver.observe(heroStats);

  // --- Testimonials carousel ---
  const grid       = document.getElementById('testimonials-grid');
  const prevBtn    = document.getElementById('carousel-prev');
  const nextBtn    = document.getElementById('carousel-next');
  const dotsEl     = document.getElementById('carousel-dots');
  const formBox    = document.getElementById('testimonial-form-box');
  const isLoggedIn = !!localStorage.getItem('mynutri_user');

  const PER_PAGE = 3;
  let currentPage = 0;
  let allTestimonials = [];

  const DEFAULTS = [
    { id: 'd1', nome: 'Tiago Leal',     avatar: 'TL', text: 'Site muito intuitivo e prático! Com certeza facilita muito todo o processo de organizar uma dieta.', rating: 5 },
    { id: 'd2', nome: 'Camila Moreira', avatar: 'CM', text: 'Sou vegetariana e sempre tive dificuldade em montar dietas equilibradas. O MyNutri AI entendeu todas as minhas restrições e criou algo perfeito.', rating: 5 },
    { id: 'd3', nome: 'Fernando Silva', avatar: 'FS', text: 'Perdi 8kg em 3 meses seguindo o plano que a IA gerou. O mais legal é que eu não senti fome e as receitas eram simples de fazer.', rating: 5 },
  ];

  function numPages() { return Math.max(1, Math.ceil(allTestimonials.length / PER_PAGE)); }

  function starsText(rating) { return '★'.repeat(rating) + '☆'.repeat(5 - rating); }

  function buildCard(t) {
    const card = document.createElement('div');
    card.className = 'testimonial-card';

    const starsEl = document.createElement('div');
    starsEl.className = 'testimonial-stars';
    starsEl.textContent = starsText(t.rating);

    const textEl = document.createElement('p');
    textEl.className = 'testimonial-text';
    textEl.textContent = '"' + t.text + '"';

    const avatarEl = document.createElement('div');
    avatarEl.className = 'testimonial-avatar';
    avatarEl.textContent = t.avatar;

    const nameEl = document.createElement('strong');
    nameEl.textContent = t.nome;

    const authorInfo = document.createElement('div');
    authorInfo.className = 'testimonial-author-info';
    authorInfo.appendChild(nameEl);

    const author = document.createElement('div');
    author.className = 'testimonial-author';
    author.appendChild(avatarEl);
    author.appendChild(authorInfo);

    card.appendChild(starsEl);
    card.appendChild(textEl);
    card.appendChild(author);
    return card;
  }

  function renderPage(page, direction) {
    const slice = allTestimonials.slice(page * PER_PAGE, (page + 1) * PER_PAGE);

    function swap() {
      grid.innerHTML = '';
      slice.forEach(function (t) { grid.appendChild(buildCard(t)); });
    }

    if (direction === 0) {
      grid.style.transition = 'opacity 0.3s ease';
      grid.style.opacity = '0';
      setTimeout(function () { swap(); grid.style.opacity = '1'; }, 250);
    } else {
      grid.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
      grid.style.opacity = '0';
      grid.style.transform = `translateX(${direction > 0 ? '-40px' : '40px'})`;

      setTimeout(function () {
        swap();
        grid.style.transition = 'none';
        grid.style.transform = `translateX(${direction > 0 ? '40px' : '-40px'})`;
        requestAnimationFrame(function () {
          requestAnimationFrame(function () {
            grid.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            grid.style.opacity = '1';
            grid.style.transform = 'translateX(0)';
          });
        });
      }, 240);
    }

    currentPage = page;
    updateControls();
  }

  function updateControls() {
    const pages = numPages();
    prevBtn.disabled = currentPage === 0;
    nextBtn.disabled = currentPage >= pages - 1;

    dotsEl.innerHTML = '';
    if (pages > 1) {
      for (let i = 0; i < pages; i++) {
        const dot = document.createElement('button');
        dot.className = 'carousel-dot' + (i === currentPage ? ' active' : '');
        dot.setAttribute('aria-label', `Página ${i + 1} de depoimentos`);
        dot.addEventListener('click', function () {
          if (i !== currentPage) renderPage(i, i > currentPage ? 1 : -1);
        });
        dotsEl.appendChild(dot);
      }
    }
  }

  prevBtn.addEventListener('click', function () {
    if (currentPage > 0) renderPage(currentPage - 1, -1);
  });

  nextBtn.addEventListener('click', function () {
    if (currentPage < numPages() - 1) renderPage(currentPage + 1, 1);
  });

  document.addEventListener('keydown', function (e) {
    const section = document.getElementById('depoimentos');
    const rect = section.getBoundingClientRect();
    const inView = rect.top < window.innerHeight && rect.bottom > 0;
    if (!inView) return;
    if (e.key === 'ArrowLeft' && currentPage > 0)                renderPage(currentPage - 1, -1);
    if (e.key === 'ArrowRight' && currentPage < numPages() - 1) renderPage(currentPage + 1, 1);
  });

  async function loadTestimonials() {
    try {
      const res = await fetch(`${API_BASE}/testimonials`);
      if (!res.ok) return;
      const data = await res.json();
      if (!data.length) return;
      allTestimonials = data;
      renderPage(0, 0);
    } catch {
      // Servidor offline — mantém cards padrão
    }
  }

  function buildForm() {
    formBox.innerHTML = '';

    const title = document.createElement('h3');
    title.textContent = 'Deixe seu depoimento';

    const subtitle = document.createElement('p');
    subtitle.textContent = 'Compartilhe sua experiência com o MyNutri AI.';

    const ratingLabel = document.createElement('label');
    ratingLabel.style.cssText = 'display:block;font-size:.875rem;font-weight:600;color:var(--text-primary);margin-bottom:8px;';
    ratingLabel.textContent = 'Sua nota';

    const starRating = document.createElement('div');
    starRating.className = 'star-rating';
    starRating.setAttribute('role', 'radiogroup');
    starRating.setAttribute('aria-label', 'Nota de 1 a 5 estrelas');
    for (let i = 5; i >= 1; i--) {
      const input = document.createElement('input');
      input.type = 'radio'; input.name = 'rating';
      input.id = `star${i}`; input.value = i;
      if (i === 5) input.checked = true;
      const label = document.createElement('label');
      label.htmlFor = `star${i}`;
      label.textContent = '★';
      label.setAttribute('aria-label', `${i} estrela${i > 1 ? 's' : ''}`);
      starRating.appendChild(input);
      starRating.appendChild(label);
    }

    const textLabel = document.createElement('label');
    textLabel.htmlFor = 'testimonial-text';
    textLabel.style.cssText = 'display:block;font-size:.875rem;font-weight:600;color:var(--text-primary);margin-bottom:8px;';
    textLabel.textContent = 'Seu depoimento';

    const textarea = document.createElement('textarea');
    textarea.id = 'testimonial-text';
    textarea.className = 'testimonial-textarea';
    textarea.placeholder = 'Conte como o MyNutri AI ajudou você…';
    textarea.maxLength = 500;

    const charCount = document.createElement('div');
    charCount.className = 'testimonial-char-count';
    charCount.textContent = '0 / 500';
    textarea.addEventListener('input', function () {
      const len = textarea.value.length;
      charCount.textContent = `${len} / 500`;
      charCount.classList.toggle('over', len > 500);
    });

    const submitRow = document.createElement('div');
    submitRow.className = 'testimonial-submit-row';
    const feedback = document.createElement('span');
    feedback.className = 'testimonial-feedback';
    const btn = document.createElement('button');
    btn.type = 'submit';
    btn.className = 'btn btn-primary';
    btn.textContent = 'Enviar depoimento';
    submitRow.appendChild(feedback);
    submitRow.appendChild(btn);

    const form = document.createElement('form');
    form.noValidate = true;
    form.appendChild(ratingLabel);
    form.appendChild(starRating);
    form.appendChild(textLabel);
    form.appendChild(textarea);
    form.appendChild(charCount);
    form.appendChild(submitRow);

    formBox.appendChild(title);
    formBox.appendChild(subtitle);
    formBox.appendChild(form);

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      feedback.textContent = '';
      feedback.className = 'testimonial-feedback';

      const text = textarea.value.trim();
      const ratingInput = form.querySelector('input[name="rating"]:checked');
      const rating = ratingInput ? parseInt(ratingInput.value, 10) : 5;

      if (!text || text.length < 10) {
        feedback.textContent = 'O depoimento deve ter pelo menos 10 caracteres.';
        feedback.classList.add('error');
        textarea.focus();
        return;
      }

      btn.disabled = true;
      btn.textContent = 'Enviando…';

      try {
        const res = await fetch(`${API_BASE}/testimonials`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ text, rating }),
        });
        const payload = await res.json();

        if (res.status === 401) {
          feedback.textContent = 'Sessão expirada. Faça login novamente.';
          feedback.classList.add('error');
          return;
        }
        if (!res.ok) {
          const msg = payload?.text?.[0] || payload?.rating?.[0] || payload?.error || 'Erro ao enviar. Tente novamente.';
          feedback.textContent = msg;
          feedback.classList.add('error');
          return;
        }

        allTestimonials.unshift(payload);
        renderPage(0, 0);

        textarea.value = '';
        charCount.textContent = '0 / 500';
        feedback.textContent = 'Depoimento enviado! Obrigado pela sua avaliação.';
        feedback.classList.add('success');
      } catch {
        feedback.textContent = 'Não foi possível enviar. Verifique sua conexão.';
        feedback.classList.add('error');
      } finally {
        btn.disabled = false;
        btn.textContent = 'Enviar depoimento';
      }
    });
  }

  // Init carousel with defaults while API loads
  allTestimonials = DEFAULTS.slice();
  updateControls();
  loadTestimonials();

  if (isLoggedIn) buildForm();
})();

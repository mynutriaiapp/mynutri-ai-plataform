/**
 * Scroll Reveal — MyNutri AI
 *
 * Observa todos os elementos com classe `.reveal` e adiciona `.visible`
 * quando entram no viewport, ativando a animação de entrada definida no CSS.
 * Cada elemento é observado apenas uma vez (unobserve após aparecer).
 */
(function () {
  function initScrollReveal() {
    const elements = document.querySelectorAll('.reveal');
    if (!elements.length) return;

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

    elements.forEach(function (el) { observer.observe(el); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initScrollReveal);
  } else {
    initScrollReveal();
  }
})();

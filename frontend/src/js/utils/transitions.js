/**
 * Page Transitions — MyNutri AI
 *
 * Adiciona uma classe `page-leaving` no <body> antes de navegar para outra
 * página, permitindo animação de saída via CSS (fade-out, etc.).
 * Ignora links externos, âncoras (#), mailto e links sem href.
 */
(function () {
  function navigateTo(url) {
    document.body.classList.add('page-leaving');
    setTimeout(() => { window.location.href = url; }, 260);
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('a[href]').forEach(function (link) {
      const href = link.getAttribute('href');
      if (!href || href.startsWith('#') || href.startsWith('http') || href.startsWith('mailto')) return;
      link.addEventListener('click', function (e) {
        e.preventDefault();
        navigateTo(href);
      });
    });
  });

  window.navigateTo = navigateTo;
})();

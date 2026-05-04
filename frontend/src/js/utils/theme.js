/**
 * Dark Mode System — MyNutri AI
 *
 * Auto-executa ao carregar:
 *   1. Aplica tema salvo em localStorage, ou preferência do sistema, ou claro.
 *   2. Liga o toggle (#theme-toggle) se existir na página.
 *   3. Sincroniza com mudanças na preferência do sistema (se usuário não escolheu).
 *
 * Deve ser incluído no <head> ou início do <body> para evitar FOUC.
 */
(function () {
  const THEME_KEY = 'mynutri_theme';
  const html = document.documentElement;

  function setTheme(theme) {
    if (theme === 'dark') {
      html.classList.add('dark');
      localStorage.setItem(THEME_KEY, 'dark');
    } else {
      html.classList.remove('dark');
      localStorage.setItem(THEME_KEY, 'light');
    }
  }

  function initializeTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) {
      setTheme(saved);
    } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setTheme('dark');
    } else {
      setTheme('light');
    }
  }

  function toggleTheme() {
    const isDark = html.classList.contains('dark');
    setTheme(isDark ? 'light' : 'dark');
  }

  initializeTheme();

  document.addEventListener('DOMContentLoaded', function () {
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
      themeToggle.addEventListener('click', toggleTheme);
    }
  });

  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      if (!localStorage.getItem(THEME_KEY)) {
        setTheme(e.matches ? 'dark' : 'light');
      }
    });
  }

  window.MyNutriTheme = { setTheme: setTheme, toggleTheme: toggleTheme };
})();

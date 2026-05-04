/**
 * Helpers compartilhados — MyNutri AI
 *
 * Funções utilitárias usadas em múltiplas páginas.
 * Disponibilizadas no escopo global (sem módulos ES) para compatibilidade
 * com os scripts inline existentes.
 */

/** Retorna as iniciais de um nome (até 2 palavras). */
function initials(name) {
  if (!name) return '?';
  return name.trim().split(/\s+/).slice(0, 2).map(w => w[0].toUpperCase()).join('');
}

/** Escapa HTML para evitar XSS ao inserir strings em innerHTML. */
function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Formata uma string ISO em data por extenso (pt-BR). Ex: "02 de maio de 2026". */
function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });
}

/**
 * Infere um rótulo legível para o objetivo de uma dieta a partir da
 * string armazenada no banco (goal_description).
 */
function goalLabel(raw) {
  if (!raw) return 'Plano alimentar';
  const lower = raw.toLowerCase();
  if (lower.includes('emagrecimento') || lower.includes('perda')  || lower.includes('loss'))     return 'Emagrecimento';
  if (lower.includes('ganho')         || lower.includes('hipertrofia') || lower.includes('gain')) return 'Ganho de Massa';
  if (lower.includes('manutenção')    || lower.includes('manutencao')  || lower.includes('maintain')) return 'Manutenção';
  return raw;
}

/**
 * Gerencia estado de carregamento de um botão passado por referência.
 * Usado em auth.html (login, register).
 * @param {HTMLElement} btn
 * @param {boolean} loading
 */
function setLoadingBtn(btn, loading) {
  btn.disabled = loading;
  btn.style.opacity = loading ? '0.7' : '1';
  btn.style.pointerEvents = loading ? 'none' : '';
  if (loading) btn.dataset.original = btn.textContent;
  else btn.textContent = btn.dataset.original || btn.textContent;
}

/**
 * Gerencia estado de carregamento via IDs de botão e spinner.
 * Usado em perfil.html (salvar dados, trocar senha).
 * @param {string} btnId
 * @param {string} spinnerId
 * @param {boolean} loading
 */
function setLoadingById(btnId, spinnerId, loading) {
  const btn = document.getElementById(btnId);
  const sp  = document.getElementById(spinnerId);
  if (btn) btn.disabled = loading;
  if (sp)  sp.style.display = loading ? 'block' : 'none';
}

/**
 * Exibe um toast temporário no elemento #sub-toast da página.
 * @param {string} msg
 * @param {'success'|'error'|'warning'} type
 */
function showToast(msg, type = 'success') {
  const t = document.getElementById('sub-toast');
  if (!t) return;
  t.textContent = msg;
  t.className = `sub-toast ${type} show`;
  clearTimeout(t._hideTimer);
  t._hideTimer = setTimeout(() => t.classList.remove('show'), 2800);
}

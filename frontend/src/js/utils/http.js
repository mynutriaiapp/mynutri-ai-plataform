/**
 * HTTP utils — MyNutri AI
 *
 * API_BASE   Prefixo de todas as chamadas à API (detecta localhost vs produção).
 * apiFetch   Wrapper sobre fetch com refresh automático de JWT em 401.
 */

const API_BASE =
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000/api/v1'
    : '/api/v1';

let _refreshing = null;

async function apiFetch(url, opts = {}) {
  const redirectOn401 = opts.redirectOn401 !== false;
  opts = { credentials: 'include', ...opts };
  delete opts.redirectOn401;

  let res = await fetch(url, opts);
  if (res.status !== 401) return res;

  if (!_refreshing) {
    _refreshing = fetch(`${API_BASE}/auth/token/refresh`, {
      method: 'POST',
      credentials: 'include',
    }).finally(() => { _refreshing = null; });
  }

  const refreshRes = await _refreshing;
  if (!refreshRes.ok) {
    localStorage.removeItem('mynutri_user');
    if (redirectOn401) window.location.href = '/auth/';
    return res;
  }

  return fetch(url, opts);
}

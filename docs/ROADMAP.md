# Roadmap — MyNutri AI

---

## ✅ MVP (Concluído — Março 2026)

- [x] Cadastro de usuário com email único
- [x] Login com JWT (access + refresh token)
- [x] Questionário de anamnese em 5 steps com validação
- [x] Integração com API de IA (OpenAI-compatible)
- [x] Geração automática de dieta com persistência no banco
- [x] Exibição do plano alimentar com calorias por refeição
- [x] CORS + rate limiting + segurança básica

---

## ✅ Versão 2 — Histórico, Dashboard e UX (Concluído — Maio 2026)

- [x] Histórico de dietas (`GET /api/v1/diet/list`)
- [x] Dieta por ID (`GET /api/v1/diet/<id>`)
- [x] Página `historico.html`
- [x] Dark mode toggle (com persistência e detecção de sistema)
- [x] Login com Google OAuth (`POST /api/v1/auth/google`)
- [x] Logout com limpeza de cookies HttpOnly (`POST /api/v1/auth/logout`)
- [x] Troca de senha (`POST /api/v1/user/change-password`)
- [x] Exportação do plano alimentar em PDF (`GET /api/v1/diet/<id>/pdf`)
- [x] Regeneração pontual de refeições (`PATCH /api/v1/diet/<id>/meal/<id>/regenerate`)
- [x] Desfazer regeneração (`POST /api/v1/diet/<id>/meal/<id>/undo`)
- [x] Sistema de depoimentos na landing page (`GET/POST /api/v1/testimonials`)
- [x] Geração assíncrona via Celery + polling por job_id
- [x] Pré-preenchimento de questionário com última anamnese (`GET /api/v1/anamnese/last`)
- [x] Testes automatizados com pytest (backend)
- [ ] Dashboard nutricional (`dashboard.html`)
- [ ] Testes de integração com Cypress (frontend)

---

## 🚀 Versão 3 — Deploy e Produção

- [ ] CI/CD com GitHub Actions
- [ ] Docker + docker-compose
- [ ] Deploy em servidor cloud (Render — `render.yaml` já configurado)
- [ ] Migração para PostgreSQL em produção
- [ ] Monitoramento de erros (Sentry — integração parcial no `settings.py`)
- [ ] CDN para assets frontend

---

## 📱 Versão 3.5 — Mobile e Integrações

- [ ] Integração com API de alimentos (FatSecretAPI)
- [ ] React Native app (iOS + Android)
- [ ] Integração com wearables (Fitbit, Apple Watch)
- [ ] Push notifications para refeições

---

## 🤖 Futuro — IA Avançada

- [ ] Nutricionista digital baseado em IA com memória de sessão
- [ ] Fine-tuning com feedback dos usuários
- [ ] Planos alimentares adaptativos (ajuste semana a semana)
- [ ] Geração de receitas automática
- [ ] Sistema de assinatura premium (SaaS)
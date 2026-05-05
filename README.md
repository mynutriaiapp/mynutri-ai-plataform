# 🥗 MyNutri AI

Plataforma inteligente para geração de **planos alimentares personalizados** utilizando **Inteligência Artificial**.

O **MyNutri AI** permite que usuários respondam um questionário nutricional e, com base nas respostas, a plataforma gera automaticamente um plano alimentar personalizado via IA.

> ⚠️ **Aviso:** A plataforma **não substitui a orientação de um nutricionista profissional**.

---

## 🚀 Funcionalidades

- 📋 Questionário nutricional em múltiplos steps com validação e pré-preenchimento
- 🔐 Autenticação completa via **JWT** (cadastro + login + refresh + logout)
- 🔑 Login com **Google OAuth**
- 🤖 Geração **assíncrona** de dieta com IA (polling via job_id)
- 🎯 Planos alimentares personalizados com calorias e macros por refeição
- 🔄 Regeneração pontual de refeições com suporte a desfazer
- 📊 Histórico completo de dietas do usuário
- 📄 Exportação do plano alimentar em **PDF**
- 🌙 **Dark mode** com persistência e detecção de preferência do sistema
- 💬 Sistema de depoimentos na landing page
- 🔑 Troca de senha autenticada
- 📧 Formulário de contato com envio de e-mail
- 📱 Interface moderna, responsiva e mobile-first

---

## 🛠️ Tecnologias

### Backend

- **Python 3.10+** + **Django 6.x**
- **Django REST Framework** — API REST
- **SimpleJWT** — autenticação via Bearer Token + cookies HttpOnly
- **Celery** — geração assíncrona de dieta (fallback síncrono em dev)
- **SQLite** (dev) / **PostgreSQL** (prod)
- **django-cors-headers** — CORS configurado

### Frontend

- **HTML5** + **CSS3** + **JavaScript** (vanilla)
- Sem frameworks front-end — SPA manual com fetch API
- Dark mode via CSS variables + `html.dark`

### Inteligência Artificial

- Integração com qualquer API **OpenAI-compatible** (OpenAI, Gemini, etc.)

---

## 📂 Estrutura do Projeto

```text
mynutri-ai-plataform/
│
├── mynutri/            # Configurações do projeto Django (settings, urls, wsgi)
├── user/               # App de autenticação, perfil e depoimentos
├── nutrition/          # App de anamnese, geração e exibição de dieta
│
├── frontend/
│   └── public/         # Páginas HTML estáticas (index, auth, questionario, dieta...)
│
├── docs/               # Documentação técnica do projeto
├── scripts/            # Scripts utilitários (validação de env, pre-commit hook)
│
├── .env.example        # Variáveis de ambiente necessárias
├── requirements.txt    # Dependências Python
└── manage.py
```

---

## ⚙️ Setup Local

### Pré-requisitos

- Python 3.10+
- Git

### Passo a passo

**1. Clone o repositório:**

```bash
git clone https://github.com/SEU_USUARIO/mynutri-ai-plataform.git
cd mynutri-ai-plataform
```

**2. Crie e ative o ambiente virtual:**

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

**3. Instale as dependências:**

```bash
pip install -r requirements.txt
```

**4. Configure as variáveis de ambiente:**

```bash
cp .env.example .env
```

Abra o `.env` e preencha as chaves obrigatórias:

- `SECRET_KEY` — chave secreta do Django
- `AI_API_KEY` — sua chave da OpenAI (ou Gemini)
- `AI_API_URL` — URL da API de IA

**5. Execute as migrações:**

```bash
python manage.py migrate
```

**6. (Opcional) Crie um superusuário para o Admin:**

```bash
python manage.py createsuperuser
```

**7. Inicie o servidor:**

```bash
python manage.py runserver
```

Acesse em `http://127.0.0.1:8000/`

---

## 🔌 Endpoints da API

| Método | Endpoint | Autenticação | Descrição |
|--------|----------|-------------|-----------|
| `POST` | `/api/v1/auth/register` | Pública | Cadastro + retorna token |
| `POST` | `/api/v1/auth/login` | Pública | Login por email/senha |
| `POST` | `/api/v1/auth/google` | Pública | Login/cadastro via Google OAuth |
| `POST` | `/api/v1/auth/token/refresh` | Pública | Renova access token |
| `POST` | `/api/v1/auth/logout` | Pública | Remove cookies de autenticação |
| `GET` | `/api/v1/user/profile` | JWT | Dados do usuário logado |
| `PATCH` | `/api/v1/user/profile` | JWT | Atualiza nome, telefone, data de nascimento |
| `POST` | `/api/v1/user/change-password` | JWT | Altera senha |
| `POST` | `/api/v1/contact` | Pública | Envia e-mail de contato |
| `GET` | `/api/v1/testimonials` | Pública | Lista depoimentos aprovados |
| `POST` | `/api/v1/testimonials` | JWT | Cria depoimento |
| `POST` | `/api/v1/anamnese` | JWT | Envia questionário nutricional |
| `GET` | `/api/v1/anamnese/last` | JWT | Última anamnese (pré-preenchimento) |
| `POST` | `/api/v1/diet/generate` | JWT | Enfileira geração de dieta (retorna job_id) |
| `GET` | `/api/v1/diet/status/<job_id>` | JWT | Polling do status de geração |
| `GET` | `/api/v1/diet` | JWT | Plano alimentar mais recente |
| `GET` | `/api/v1/diet/list` | JWT | Histórico completo de planos |
| `GET` | `/api/v1/diet/<id>` | JWT | Plano alimentar por ID |
| `GET` | `/api/v1/diet/<id>/pdf` | JWT | Download do plano em PDF |
| `PATCH` | `/api/v1/diet/<id>/substitutions` | JWT | Atualiza substituições de alimentos |
| `PATCH` | `/api/v1/diet/<diet_id>/meal/<meal_id>/regenerate` | JWT | Regenera uma refeição |
| `POST` | `/api/v1/diet/<diet_id>/meal/<meal_id>/undo` | JWT | Desfaz última regeneração |
| `GET` | `/health/` | Pública | Health check |

> Todos os endpoints protegidos aceitam `Authorization: Bearer <token>` ou cookie HttpOnly `access_token`.

---

## 📚 Documentação

A documentação técnica detalhada está na pasta **`docs/`**:

| Arquivo | Conteúdo |
|---------|----------|
| `API.md` | Contratos detalhados de cada endpoint |
| `ARCHITECTURE.md` | Arquitetura do sistema em 3 camadas |
| `DATABASE.md` | Schema do banco de dados |
| `ROADMAP.md` | Fases de desenvolvimento (MVP → V2 → V3) |
| `PROMPTS.md` | Arquitetura de prompts e pós-processamento da IA |
| `GIT_CONVENTION.md` | Convenções de branches e commits |
| `SECURITY.md` | Boas práticas e checklist de segurança |
| `SECURITY_SETUP.md` | Guia rápido de setup de segurança |
| `DARK_MODE_DOCUMENTATION.md` | Implementação do dark mode |

---

## 🔒 Segurança

- Variáveis sensíveis isoladas em `.env` (nunca commitadas)
- JWT com `ACCESS_TOKEN_LIFETIME` de 8h e refresh de 7 dias, servidos via cookies HttpOnly
- Rate limiting: `3/day` para geração de dieta, `3/day` para regeneração de refeição, `60/hour` para usuários autenticados, `5/hour` para contato
- CORS restritivo em produção (`DEBUG=False`)
- Pre-commit hook disponível em `scripts/pre-commit-hook`

---

## 📈 Próximas Etapas

- [ ] Dashboard nutricional
- [ ] Testes de integração com Cypress
- [ ] CI/CD com GitHub Actions
- [ ] Docker + docker-compose

---

## 📄 Licença

© 2026 MyNutri AI — Projeto proprietário. Código não pode ser copiado, modificado ou redistribuído sem autorização do autor.

---

## 👨‍💻 Autores

- **Gabriel Rezende** — [LinkedIn](https://www.linkedin.com/in/gabrielmrezende/)
- **Carlos Alberto**
- **Arthur Hoffmann** — [LinkedIn](https://www.linkedin.com/in/arthur-hoffmann-a2383226b/)
- **Pedro Antônio**

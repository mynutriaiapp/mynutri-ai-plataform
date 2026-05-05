# Arquitetura do Sistema — MyNutri AI

## Visão Geral

O MyNutri AI é uma plataforma web SaaS que gera planos alimentares personalizados via IA.
A arquitetura segue o padrão de **3 camadas** com separação completa entre Frontend e Backend (API REST).

---

## Camadas

### 1. Frontend (Estático)

Responsável exclusivamente pela interface do usuário. Não possui lógica de negócio.

**Páginas:**
| Arquivo | Rota | Descrição |
|---------|------|-----------|
| `index.html` | `/` | Landing Page com CTA e depoimentos |
| `auth.html` | `/auth` | Login e Cadastro (tabs) + Google OAuth |
| `questionario.html` | `/questionario` | Questionário em 5 steps |
| `dieta.html` | `/dieta` | Exibição do plano alimentar + regeneração de refeições |
| `historico.html` | `/historico` | Histórico completo de dietas do usuário |
| `perfil.html` | `/perfil` | Perfil e troca de senha |
| `contato.html` | `/contato` | Página de contato |
| `privacidade.html` | `/privacidade` | Política de privacidade |
| `termos.html` | `/termos` | Termos de uso |

**Tecnologias:** HTML5 + CSS3 + JavaScript vanilla (fetch API), dark mode via CSS variables + `html.dark`

---

### 2. Backend (API REST)

Responsável por toda a lógica de negócio, autenticação e integração com a IA.

**Framework:** Django 6.x + Django REST Framework  
**Autenticação:** SimpleJWT com cookies HttpOnly + Bearer Token  
**Base URL:** `http://127.0.0.1:8000/api/v1/`

**Apps Django:**

| App | Responsabilidade |
|-----|-----------------|
| `user` | CustomUser, Profile, Testimonial, autenticação JWT, Google OAuth |
| `nutrition` | Anamnese, DietPlan, Meal, DietJob, MealRegenerationLog, integração com IA |
| `mynutri` | Configurações globais, URL root |

**Rotas expostas:**

```
# Autenticação (user/urls_api.py)
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/google
POST   /api/v1/auth/google/callback
POST   /api/v1/auth/token/refresh
POST   /api/v1/auth/logout

# Usuário (user/urls_api.py)
GET    /api/v1/user/profile
PATCH  /api/v1/user/profile
POST   /api/v1/user/change-password
POST   /api/v1/contact
GET    /api/v1/testimonials
POST   /api/v1/testimonials

# Anamnese (nutrition/urls_api.py)
POST   /api/v1/anamnese
GET    /api/v1/anamnese/last

# Dieta (nutrition/urls_api.py)
POST   /api/v1/diet/generate
GET    /api/v1/diet/status/<job_id>
GET    /api/v1/diet
GET    /api/v1/diet/list
GET    /api/v1/diet/<id>
GET    /api/v1/diet/<id>/pdf
PATCH  /api/v1/diet/<id>/substitutions
PATCH  /api/v1/diet/<diet_id>/meal/<meal_id>/regenerate
POST   /api/v1/diet/<diet_id>/meal/<meal_id>/undo

# Sistema
GET    /health/
```

---

### 3. Banco de Dados

**Desenvolvimento:** SQLite (`db.sqlite3`)  
**Produção:** PostgreSQL (configurar via `DATABASE_URL` no `.env`)

**Modelos:**
| Modelo | App | Descrição |
|--------|-----|-----------|
| `CustomUser` | `user` | Extends `AbstractUser` — usa email como login |
| `Profile` | `user` | Dados nutricionais vinculados ao usuário (OneToOne) |
| `Testimonial` | `user` | Depoimentos de usuários para a landing page |
| `Anamnese` | `nutrition` | Respostas do questionário nutricional |
| `DietPlan` | `nutrition` | Plano alimentar gerado pela IA (JSON + campos extraídos) |
| `Meal` | `nutrition` | Refeições individuais de um DietPlan |
| `DietJob` | `nutrition` | Rastreia estado de geração assíncrona (pending→done/failed) |
| `MealRegenerationLog` | `nutrition` | Log de regeneração pontual + dados para undo |

---

## Fluxo Principal do Usuário

```
index.html
    └── Clica "Começar"
           └── auth.html (Cadastro/Login/Google OAuth)
                  └── [Token JWT em cookie HttpOnly + localStorage]
                         └── questionario.html (5 steps)
                                └── POST /api/v1/anamnese
                                       └── Redireciona para dieta.html?generate=1
                                              └── POST /api/v1/diet/generate
                                                     └── DietJob criado (pending)
                                                            └── Celery task enfileirada
                                                                   └── Polling GET /api/v1/diet/status/<job_id>
                                                                          └── status=done → exibe refeições + calorias
```

---

## Fluxo de Geração Assíncrona de Dieta

```
POST /api/v1/diet/generate
    ├── Verifica última Anamnese do usuário
    ├── Cria DietJob (status=pending)
    ├── Enfileira task Celery (ou executa sync como fallback)
    └── Retorna { job_id, status: "pending" }

Celery Worker (nutrition/tasks.py):
    ├── DietJob.status = processing
    ├── AIService.generate_diet(anamnese)
    │       ├── calculate_calories() → meta calórica
    │       ├── build_diet_prompt() → prompt dinâmico
    │       ├── Chama API IA (OpenAI-compatible, timeout 120s)
    │       ├── _normalize_diet_data() → recalcula totais dos alimentos
    │       └── _enforce_calorie_target() → escala porções se IA divergir >10%
    ├── DietPlan + Meals criados em bulk
    └── DietJob.status = done / failed

GET /api/v1/diet/status/<job_id>
    └── Retorna { status, diet_plan_id? }
```

---

## Integração com IA

- **Arquivo:** `nutrition/services.py` (`AIService`)
- **Protocolo:** HTTP POST para qualquer API OpenAI-compatible
- **Timeout:** 120 segundos
- **Rate limit:** 3 gerações por dia por usuário (via DRF `ScopedRateThrottle`)
- **Pós-processamento:** normalização de totais nutricionais + ajuste de porções por meta calórica

---

## Decisões de Design

| Decisão | Justificativa |
|---------|--------------|
| Frontend separado do Django | Independência de deploy; frontend pode ir para CDN |
| JWT via SimpleJWT + cookies HttpOnly | Stateless, seguro contra XSS; fallback em Bearer para clientes sem cookie |
| `CustomUser` com email como username | Evita campos duplicados e melhora UX |
| Anamnese separada do Profile | Permite múltiplas sessões de resposta; histórico preservado |
| `raw_response` JSONField | Preserva resposta completa da IA para reprocessamento futuro |
| `DietJob` para geração assíncrona | Evita timeout HTTP em geração demorada; permite UX com loading progressivo |
| `MealRegenerationLog` com `previous_raw_meal` | Permite undo completo sem precisar chamar a IA novamente |
| SQLite em dev | Zero configuração; migration para PostgreSQL é transparente com Django |
| Celery com fallback síncrono | Ambiente local sem Redis funciona normalmente; produção escala com workers |

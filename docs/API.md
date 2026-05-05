# Documentação da API — MyNutri AI

**Base URL:** `http://127.0.0.1:8000/api/v1`

Endpoints protegidos aceitam autenticação via:
- Header: `Authorization: Bearer <access_token>`
- Cookie HttpOnly: `access_token` (setado automaticamente em login/registro)

---

## Autenticação

### Criar conta

`POST /api/v1/auth/register`

**Permissão:** Pública

**Body (JSON):**
```json
{
  "nome": "Gabriel Rezende",
  "email": "gabriel@exemplo.com",
  "senha": "minhasenha123"
}
```

> `senha` deve ter no mínimo 8 caracteres.

**Resposta 201 Created:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "email": "gabriel@exemplo.com",
    "nome": "Gabriel"
  }
}
```

> Também seta cookies HttpOnly `access_token` e `refresh_token`.

**Resposta 400 Bad Request:**
```json
{ "email": ["Este email já está em uso."] }
```

---

### Login

`POST /api/v1/auth/login`

**Permissão:** Pública

**Body (JSON):**
```json
{
  "email": "gabriel@exemplo.com",
  "password": "minhasenha123"
}
```

**Resposta 200 OK:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

> Também seta cookies HttpOnly `access_token` e `refresh_token`.

**Resposta 401 Unauthorized:**
```json
{ "detail": "No active account found with the given credentials" }
```

---

### Login com Google OAuth

`POST /api/v1/auth/google`

**Permissão:** Pública

**Body (JSON):**
```json
{ "credential": "<id_token_do_google>" }
```

**Resposta 200 OK:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": 1,
    "email": "gabriel@gmail.com",
    "nome": "Gabriel"
  }
}
```

> Cria conta automaticamente se o email não existir. Seta cookies HttpOnly.

---

### Callback Google OAuth (redirect flow)

`POST /api/v1/auth/google/callback`

**Permissão:** Pública

Recebe o credential do Google via redirect. Seta cookies e redireciona para a aplicação.

---

### Renovar Token

`POST /api/v1/auth/token/refresh`

**Permissão:** Pública

**Body (JSON) — ou via cookie `refresh_token`:**
```json
{ "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." }
```

**Resposta 200 OK:**
```json
{ "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." }
```

---

### Logout

`POST /api/v1/auth/logout`

**Permissão:** Pública

Remove os cookies HttpOnly de autenticação.

**Resposta 200 OK:**
```json
{ "detail": "Logout realizado com sucesso." }
```

---

## Usuário

### Obter perfil

`GET /api/v1/user/profile`

**Permissão:** JWT obrigatório

**Resposta 200 OK:**
```json
{
  "id": 1,
  "nome": "Gabriel Rezende",
  "email": "gabriel@exemplo.com",
  "phone": "",
  "date_of_birth": null,
  "date_joined": "2026-03-30T15:00:00Z"
}
```

---

### Atualizar perfil

`PATCH /api/v1/user/profile`

**Permissão:** JWT obrigatório

**Body (JSON — campos opcionais):**
```json
{
  "first_name": "Gabriel",
  "last_name": "Rezende",
  "phone": "(11) 99999-9999",
  "date_of_birth": "2000-05-15"
}
```

**Resposta 200 OK:** Retorna o perfil atualizado (mesmo formato do GET).

---

### Alterar senha

`POST /api/v1/user/change-password`

**Permissão:** JWT obrigatório

**Body (JSON):**
```json
{
  "current_password": "senhaatual123",
  "new_password": "novasenha456"
}
```

**Resposta 200 OK:**
```json
{ "detail": "Senha alterada com sucesso." }
```

**Resposta 400 Bad Request:**
```json
{ "current_password": ["Senha atual incorreta."] }
```

---

### Contato

`POST /api/v1/contact`

**Permissão:** Pública (rate limit: 5/hora)

**Body (JSON):**
```json
{
  "name": "Gabriel",
  "email": "gabriel@exemplo.com",
  "message": "Olá, tenho uma dúvida..."
}
```

**Resposta 200 OK:**
```json
{ "detail": "Mensagem enviada com sucesso." }
```

---

### Depoimentos

`GET /api/v1/testimonials`

**Permissão:** Pública

**Resposta 200 OK:**
```json
[
  {
    "id": 1,
    "user": "Gabriel R.",
    "text": "Plataforma incrível! Perdi 5kg em 2 meses seguindo o plano.",
    "rating": 5,
    "created_at": "2026-04-10T14:00:00Z"
  }
]
```

`POST /api/v1/testimonials`

**Permissão:** JWT obrigatório

**Body (JSON):**
```json
{
  "text": "Plataforma incrível! Perdi 5kg em 2 meses seguindo o plano.",
  "rating": 5
}
```

**Resposta 201 Created:** Retorna o depoimento criado.

---

## Anamnese

### Enviar questionário nutricional

`POST /api/v1/anamnese`

**Permissão:** JWT obrigatório

**Body (JSON):**
```json
{
  "idade": 25,
  "sexo": "M",
  "peso": 70.5,
  "altura": 175.0,
  "nivel_atividade": "moderate",
  "objetivo": "lose",
  "meals_per_day": 5,
  "restricoes": "vegetariano, gluten",
  "food_preferences": "Frango, Arroz Integral, Brócolis",
  "allergies": "amendoim"
}
```

**Valores aceitos:**

| Campo | Valores válidos |
|-------|----------------|
| `sexo` | `"M"`, `"F"`, `"O"` |
| `nivel_atividade` | `"sedentary"`, `"light"`, `"moderate"`, `"intense"`, `"athlete"` |
| `objetivo` | `"lose"`, `"maintain"`, `"gain"` |

> Os campos `restricoes`, `food_preferences` e `allergies` são opcionais (string, máx. 500 chars).

**Resposta 201 Created:**
```json
{
  "id": 3,
  "idade": 25,
  "sexo": "M",
  "peso": "70.50",
  "altura": "175.00",
  "nivel_atividade": "moderate",
  "objetivo": "lose",
  "restricoes": "vegetariano, gluten",
  "food_preferences": "Frango, Arroz Integral, Brócolis",
  "allergies": "amendoim",
  "meals_per_day": 5,
  "answered_at": "2026-03-31T23:00:00Z"
}
```

---

### Buscar última anamnese

`GET /api/v1/anamnese/last`

**Permissão:** JWT obrigatório

Retorna a anamnese mais recente do usuário para pré-preenchimento do questionário.

**Resposta 200 OK:** Mesmo formato do POST.

**Resposta 404 Not Found:**
```json
{ "error": "Nenhuma anamnese encontrada." }
```

---

## Dieta

### Gerar dieta via IA (assíncrono)

`POST /api/v1/diet/generate`

**Permissão:** JWT obrigatório
**Rate limit:** 3 requisições por dia por usuário

**Body:** Nenhum (usa a última Anamnese registrada do usuário)

**Resposta 202 Accepted:**
```json
{
  "job_id": 42,
  "status": "pending"
}
```

> Use o `job_id` para fazer polling em `GET /api/v1/diet/status/<job_id>`.

**Resposta 400 Bad Request (sem anamnese):**
```json
{ "error": "Nenhuma anamnese encontrada. Responda o questionário primeiro." }
```

**Resposta 429 Too Many Requests:**
```json
{ "detail": "Request was throttled. Expected available in 86400 seconds." }
```

---

### Status do job de geração

`GET /api/v1/diet/status/<job_id>`

**Permissão:** JWT obrigatório

**Resposta enquanto processando:**
```json
{ "status": "pending" }
```
ou
```json
{ "status": "processing" }
```

**Resposta 200 OK (concluído):**
```json
{
  "status": "done",
  "diet_plan_id": 7
}
```

**Resposta 200 OK (falhou):**
```json
{
  "status": "failed",
  "error": "Falha ao gerar o plano alimentar via IA, tente novamente mais tarde."
}
```

---

### Buscar dieta mais recente

`GET /api/v1/diet`

**Permissão:** JWT obrigatório

**Resposta 200 OK:**
```json
{
  "id": 7,
  "calorias_totais": 2100,
  "goal_description": "Emagrecimento",
  "refeicoes": [
    {
      "nome_refeicao": "Café da manhã",
      "descricao_refeicao": "3 ovos mexidos + 2 fatias de pão integral + café sem açúcar",
      "calorias_estimadas": 380,
      "order": 0
    }
  ],
  "created_at": "2026-03-31T23:05:00Z"
}
```

**Resposta 404 Not Found:**
```json
{ "error": "Você ainda não possui um plano alimentar gerado." }
```

---

### Histórico de dietas

`GET /api/v1/diet/list`

**Permissão:** JWT obrigatório

**Resposta 200 OK:** Array com todos os planos alimentares do usuário (formato resumido, sem refeições).

---

### Plano alimentar por ID

`GET /api/v1/diet/<id>`

**Permissão:** JWT obrigatório

**Resposta 200 OK:** Mesmo formato detalhado do `GET /api/v1/diet`.

---

### Download em PDF

`GET /api/v1/diet/<id>/pdf`

**Permissão:** JWT obrigatório

**Resposta 200 OK:** Arquivo PDF com o plano alimentar (`Content-Type: application/pdf`).

---

### Atualizar substituições de alimentos

`PATCH /api/v1/diet/<id>/substitutions`

**Permissão:** JWT obrigatório

**Body (JSON):**
```json
{
  "substitutions": [
    {
      "food": "Arroz integral",
      "alternatives": ["Batata-doce", "Macarrão integral", "Quinoa"]
    }
  ]
}
```

**Resposta 200 OK:** Retorna o plano atualizado.

---

### Regenerar uma refeição

`PATCH /api/v1/diet/<diet_id>/meal/<meal_id>/regenerate`

**Permissão:** JWT obrigatório
**Rate limit:** 3 regenerações por dia por DietPlan

**Body (JSON — opcional):**
```json
{ "reason": "Não gosto de frango" }
```

**Resposta 200 OK:**
```json
{
  "meal_id": 12,
  "meal_name": "Almoço",
  "description": "150g tilápia grelhada + 150g arroz integral + salada de folhas",
  "calories": 520,
  "log_id": 5
}
```

**Resposta 429 Too Many Requests:**
```json
{ "error": "Limite de 3 regenerações por dia atingido para este plano." }
```

---

### Desfazer regeneração

`POST /api/v1/diet/<diet_id>/meal/<meal_id>/undo`

**Permissão:** JWT obrigatório

**Body:** Nenhum (desfaz a regeneração mais recente não desfeita da refeição)

**Resposta 200 OK:**
```json
{
  "meal_id": 12,
  "meal_name": "Almoço",
  "description": "150g frango grelhado + 150g arroz integral + salada de folhas",
  "calories": 550
}
```

**Resposta 404 Not Found:**
```json
{ "error": "Nenhuma regeneração disponível para desfazer." }
```

---

## Health Check

### Status do servidor

`GET /health/`

**Permissão:** Pública

**Resposta 200 OK:**
```json
{ "status": "ok" }
```

**Resposta 503 Service Unavailable:**
```json
{ "status": "error" }
```

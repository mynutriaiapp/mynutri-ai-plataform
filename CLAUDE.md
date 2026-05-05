# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandos essenciais

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar o servidor backend (API + frontend servido pelo Django)
python manage.py runserver

# Migrations
python manage.py makemigrations
python manage.py migrate

# Todos os testes
pytest

# Testes de um app específico
pytest nutrition/
pytest user/

# Um teste específico
pytest nutrition/test_services.py::NomeDoTeste

# Verificar configuração Django
python manage.py check
python manage.py check --deploy   # checklist de produção
```

> Os testes usam `mynutri/test_settings.py` (SQLite in-memory, throttle desabilitado, sem validação de vars de ambiente). Configurado via `pytest.ini`.

## Arquitetura

### Separação Frontend / Backend

O frontend é HTML/CSS/JS vanilla servido pelo próprio Django via `TemplateView`. As páginas ficam em `frontend/public/` e são mapeadas em `mynutri/urls.py`. Em produção, WhiteNoise serve os assets estáticos.

A API segue o prefixo `/api/v1/` e é dividida em dois grupos de rotas:
- `user/urls_api.py` → autenticação (JWT + Google OAuth), perfil, troca de senha, contato, depoimentos
- `nutrition/urls_api.py` → anamnese, geração assíncrona de dieta, histórico, PDF, substituições, regeneração de refeição

### Autenticação

`CustomUser` (`user/models.py`) estende `AbstractUser` usando **email como username** (o campo `username` é preenchido automaticamente com o email). `EmailTokenObtainPairView` sobrescreve o login padrão do SimpleJWT para aceitar `{ email, password }` em vez de `{ username, password }`. Os tokens retornados usam o campo `token` (não `access`) para consistência com o endpoint de registro.

### Fluxo de geração de dieta (assíncrono)

1. Usuário preenche o questionário → `POST /api/v1/anamnese` salva `Anamnese`
2. Frontend redireciona para `dieta.html?generate=1` → `POST /api/v1/diet/generate`
3. `DietGenerateAPIView` cria um `DietJob` (status=pending) e enfileira a task Celery; retorna `{ job_id }`
4. Frontend faz polling em `GET /api/v1/diet/status/<job_id>` até `status=done`
5. Worker Celery chama `AIService.generate_diet(anamnese)` em `nutrition/services.py`:
   - **Passo 1** (temp=0.55): LLM seleciona alimentos e quantidades (sem calcular macros)
   - **Backend**: `nutrition_db.py` calcula macros deterministicamente; `_adjust_to_calorie_target()` escala porções se desvio > 10%; `_round_portions()` arredonda para medidas práticas (11+ regras por categoria); `_enforce_allergies()` rejeita alérgenos; `_validate_macro_ratios()` valida limites fisiológicos
   - **Substituições**: `generate_meal_substitutions()` gera substituições sem IA
   - **Passos 2+3** em paralelo (temp=0.7): `_generate_notes()` e `_generate_explanation()` via `ThreadPoolExecutor`
6. `DietPlan` e múltiplos `Meal` são criados em bulk; `DietJob.status` atualizado para `done`

### Regeneração pontual de refeição

- `PATCH /api/v1/diet/<diet_id>/meal/<meal_id>/regenerate` → `MealRegenerateAPIView`
- Rate limit: 3 regenerações/dia por `DietPlan` (contado via `MealRegenerationLog`)
- Estado anterior salvo em `MealRegenerationLog` para suportar undo
- `POST /api/v1/diet/<diet_id>/meal/<meal_id>/undo` → `MealUndoAPIView` restaura o estado anterior

### Modelos de dados

- `CustomUser` → `Profile` (OneToOne, criado automaticamente no registro)
- `CustomUser` → `Testimonial[]` (depoimentos da landing page — `user/models.py`)
- `CustomUser` → `Anamnese[]` (múltiplas por usuário; a mais recente é usada para geração)
- `Anamnese` → `DietJob[]` (SET_NULL se anamnese deletada)
- `DietJob` → `DietPlan` (OneToOne, SET_NULL; rastreia estado pending→processing→done/failed)
- `DietPlan` → `Meal[]` (bulk_create; campo `order` define a sequência)
- `DietPlan` → `MealRegenerationLog[]` (histórico de regenerações com JSON anterior para undo)
- `DietPlan.raw_response` armazena o JSON completo (enriquecido com macros do backend)

### Rate limiting

Configurado no DRF via `DEFAULT_THROTTLE_RATES` em `settings.py`:
- `diet_generate`: 3/dia (ScopedRateThrottle na view)
- `contact`: 5/hora (AnonRateThrottle customizado)
- `user`: 60/hora, `anon`: 20/hora (globais)

Em testes, o throttle é desabilitado (`DEFAULT_THROTTLE_CLASSES: []`); o cache é limpo entre cada teste via fixture `autouse` em `conftest.py`.

### Variáveis de ambiente obrigatórias

`settings.py` valida `SECRET_KEY`, `AI_API_KEY` e `AI_API_URL` na inicialização e lança `ValueError` se ausentes. Para testes, usar `mynutri/test_settings.py` (não requer `.env`).

### Deploy

O arquivo `render.yaml` define a infraestrutura completa no Render (Web Service Python + PostgreSQL). O script `build.sh` executa `collectstatic` e `migrate` no build. Em dev, SQLite é usado automaticamente quando `DATABASE_URL` não está definido.

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
- `user/urls_api.py` → autenticação, perfil, contato
- `nutrition/urls_api.py` → anamnese, geração e consulta de dieta

### Autenticação

`CustomUser` (`user/models.py`) estende `AbstractUser` usando **email como username** (o campo `username` é preenchido automaticamente com o email). `EmailTokenObtainPairView` sobrescreve o login padrão do SimpleJWT para aceitar `{ email, password }` em vez de `{ username, password }`. Os tokens retornados usam o campo `token` (não `access`) para consistência com o endpoint de registro.

### Fluxo de geração de dieta

1. Usuário preenche o questionário → `POST /api/v1/anamnese` salva `Anamnese`
2. Frontend redireciona para `dieta.html?generate=1` → `POST /api/v1/diet/generate`
3. `DietGenerateAPIView` busca a última `Anamnese` do usuário e chama `AIService.generate_diet()`
4. `AIService` calcula o alvo calórico (`prompts.calculate_calories()`), monta o prompt (`prompts.build_diet_prompt()`), chama a API externa e parseia o JSON
5. Pós-processamento: `_normalize_diet_data()` recalcula totais a partir dos alimentos individuais; `_enforce_calorie_target()` escala as porções se a IA divergir >10% do alvo
6. `DietPlan` e múltiplos `Meal` são criados em bulk no banco

### Modelos de dados

- `CustomUser` → `Profile` (OneToOne, criado automaticamente no registro)
- `CustomUser` → `Anamnese` (múltiplas por usuário; a mais recente é usada para geração)
- `Anamnese` → `DietPlan` (SET_NULL se anamnese deletada)
- `DietPlan` → `Meal[]` (bulk_create; campo `order` define a sequência)
- `DietPlan.raw_response` armazena o JSON completo da IA para reprocessamento futuro

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

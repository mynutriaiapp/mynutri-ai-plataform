# Prompts de Inteligência Artificial — MyNutri AI

## Visão Geral da Arquitetura

A geração de dieta usa uma arquitetura de **múltiplos passos** em `nutrition/services.py` (`AIService`). O objetivo é eliminar a variabilidade de cálculo delegando aritmética ao backend e deixando a IA apenas com o trabalho criativo (seleção de alimentos, linguagem).

```
Passo 1 — LLM (temp=0.55): seleciona alimentos e quantidades (sem calcular macros)
  │
  ▼
Backend determinístico:
  ├── nutrition_db.py → calcula macros reais por alimento
  ├── _adjust_to_calorie_target() → escala porções se desvio > 10%
  ├── _round_portions() → arredonda para medidas práticas de consumo
  ├── _enforce_allergies() → rejeita plano se alérgeno detectado
  ├── _validate_macro_ratios() → rejeita se macros fora de limites fisiológicos
  └── generate_meal_substitutions() → gera substituições (sem IA)
  │
  ▼
Passo 2 (temp=0.7) — Notas + Explicação em paralelo (ThreadPoolExecutor)
  ├── _generate_notes()       → dicas práticas personalizadas
  └── _generate_explanation() → explicação científica (5 campos obrigatórios)
  │
  ▼
Persiste DietPlan + Meals no banco
```

---

## Passo 1 — Seleção de Alimentos

**Arquivo:** `nutrition/prompts.py` → `build_food_selection_prompt(anamnese)`  
**System prompt:** `SYSTEM_PROMPT_FOODS`  
**Temperature:** 0.55 (criatividade moderada)  
**`json_mode`:** True

### Campos utilizados da Anamnese

| Campo | Descrição |
|-------|-----------|
| `age` | Idade em anos |
| `gender` | Sexo (Masculino / Feminino / Outro) |
| `weight_kg` | Peso em kg |
| `height_cm` | Altura em cm |
| `activity_level` | Nível de atividade (display PT) |
| `goal` | Objetivo (display PT) |
| `food_preferences` | Preferências alimentares (ponto de partida) |
| `food_restrictions` | Restrições alimentares (evitar) |
| `allergies` | Alergias (proibido incluir) |
| `meals_per_day` | Número de refeições por dia |

### Cálculo calórico (backend, determinístico)

A meta calórica é calculada **antes** de chamar a IA via `calculate_calories(anamnese)`:

1. **TMB** via Mifflin-St Jeor
2. **TDEE** = TMB × fator de atividade
3. **Meta** = TDEE ajustado pelo objetivo:
   - `lose` → −500 kcal
   - `maintain` → neutro
   - `gain` → +400 kcal

A meta é fornecida à IA no prompt para que ela selecione alimentos coerentes com o volume calórico correto.

### Formato de resposta esperado (Passo 1)

```json
{
  "goal_description": "Emagrecimento saudável",
  "meals": [
    {
      "name": "Café da manhã",
      "time_suggestion": "07:00",
      "foods": [
        { "name": "Ovos mexidos", "quantity_g": 150, "quantity_text": "3 unidades" },
        { "name": "Pão integral", "quantity_g": 60,  "quantity_text": "2 fatias" }
      ]
    }
  ]
}
```

> A IA **não calcula** calorias nem macros — isso é feito deterministicamente pelo backend via `nutrition_db.py`.

---

## Pós-processamento Backend (entre Passo 1 e Passo 2)

### 1. Enriquecimento nutricional — `_enrich_foods_with_macros()`

Consulta `nutrition_db.py` para cada alimento. O banco tem 3 níveis de match:
- **exact**: correspondência exata pelo nome
- **fuzzy**: normalização de acentos/plurais
- **category**: categoria alimentar genérica
- **generic**: fallback 150 kcal/100g (se ≥20% dos alimentos cair aqui → retry)

### 2. Ajuste de porções — `_adjust_to_calorie_target()`

Se o total calculado divergir > 10% do alvo, escala as quantidades com hierarquia:
- Proteínas (frango, ovo, peixe…): cap ±15% — preserva adequação proteica
- Gorduras densas (azeite, castanhas…): cap ±20% — evita porções absurdas
- Carboidratos e vegetais: escala livre — absorvem o ajuste principal

### 3. Arredondamento — `_round_portions()`

11+ regras de arredondamento por categoria para medidas práticas de consumo:
- Óleos: múltiplos de 5g (colher de chá)
- Ovos: múltiplos de 50g (unidades)
- Carnes/peixes: múltiplos de 25g, mínimo 50g
- Arroz/massas/tubérculos: múltiplos de 50g

Cada alimento ganha o campo `quantity` com medida caseira (ex: `"300g (≈ 8 col. de sopa)"`).

### 4. Validações de segurança

- **`_enforce_allergies()`**: detecta alérgenos no plano via regex; levanta `AllergenViolation` (retry automático)
- **`_validate_macro_ratios()`**: rejeita se carboidratos > 65%, proteína < 15%, gordura < 15% das calorias, ou gordura > 1.2g/kg

### 5. Substituições — `generate_meal_substitutions()` (sem IA)

Geradas deterministicamente no backend com base nos alimentos do plano e nas alergias declaradas.

---

## Passo 2a — Notas Personalizadas

**Função:** `_generate_notes()`  
**System prompt:** `SYSTEM_PROMPT_NOTES`  
**Prompt dinâmico:** `build_notes_prompt(diet_data, anamnese, target_calories)`  
**Temperature:** 0.7  
**max_tokens:** 800

Falha silenciosamente — o plano é válido mesmo sem dicas.

### Formato de resposta esperado

```json
{
  "tips": [
    "Beba pelo menos 2 a 3 litros de água por dia.",
    "Prefira cozinhar as refeições com antecedência para facilitar a adesão."
  ],
  "meal_notes": {
    "Café da manhã": "Consuma até 30 minutos após acordar para otimizar o metabolismo.",
    "Almoço": "Mastigue devagar e evite distrações durante a refeição."
  }
}
```

---

## Passo 2b — Explicação Científica

**Função:** `_generate_explanation()`  
**System prompt:** `SYSTEM_PROMPT_EXPLANATION`  
**Prompt dinâmico:** `build_explanation_prompt(diet_data, anamnese, tmb, tdee, target_calories)`  
**Temperature:** 0.7  
**max_tokens:** 1200

Falha silenciosamente — o frontend tem fallback se `explanation` for `null`.

### Formato de resposta esperado (5 campos obrigatórios)

```json
{
  "calorie_calculation": "Sua TMB calculada é de 1.680 kcal...",
  "macro_distribution": "O plano distribui 150g de proteína (30%)...",
  "food_choices": "Escolhemos frango e tilápia como fontes proteicas...",
  "meal_structure": "As 5 refeições estão espaçadas em ~3h...",
  "goal_alignment": "Este déficit de 500 kcal levará à perda de ~0,5kg/semana..."
}
```

---

## Regeneração Pontual de Refeição

**Função:** `AIService.regenerate_meal()`  
**System prompt:** `SYSTEM_PROMPT_MEAL_REGEN`  
**Prompt dinâmico:** `build_meal_regen_prompt(diet_plan, meal_index, reason)`  
**Temperature:** 0.7 (mais criatividade para variedade)

O prompt inclui contexto completo do plano (outras refeições, meta calórica, perfil do usuário) para que a nova refeição seja coerente com o restante do dia. Após a resposta da IA, o mesmo pós-processamento do Passo 1 é aplicado (enriquecimento nutricional, arredondamento, validação de alergias).

---

## Mapeamento Final JSON → Banco de Dados

| Campo do diet_data | Campo `DietPlan` |
|--------------------|-----------------|
| `calories` | `total_calories` |
| `goal_description` | `goal_description` |
| dict completo (enriquecido) | `raw_response` |

| Campo do diet_data | Campo `Meal` |
|--------------------|-------------|
| `meals[].name` + `time_suggestion` | `meal_name` (ex: "Almoço (12:00)") |
| bullet points dos `foods[]` | `description` |
| soma de `foods[].calories` | `calories` |
| índice do array | `order` |

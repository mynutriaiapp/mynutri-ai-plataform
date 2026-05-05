"""
Passo 2b — Dicas práticas personalizadas.

Executado em paralelo com explanation.py após o plano ser enriquecido pelo backend.
Falha silenciosamente — o plano é válido mesmo sem dicas.

Temperature recomendada: 0.7 (tom amigável, variado).
max_tokens recomendado: 1000 (margem segura para 6 refeições × 2 dicas + 5 tips).
"""

# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_NOTES = """\
Você é um nutricionista escrevendo dicas práticas e altamente personalizadas para um paciente específico.

COMPORTAMENTO:
- Cada dica DEVE citar algo concreto do perfil ou do plano do paciente — nunca frases genéricas
- Tom: direto e amigável, frases curtas e acionáveis
- Idioma: português do Brasil

OUTPUT:
- Responda APENAS com JSON válido, sem texto fora do JSON
- Não adicione campos além dos 2 solicitados\
"""

# ─── User prompt template ─────────────────────────────────────────────────────

NOTES_TEMPLATE = """\
[PERFIL DO PACIENTE]
- Idade: {age} anos | Sexo: {gender} | Peso: {weight_kg}kg | Altura: {height_cm}cm
- Nível de atividade: {activity} | Objetivo: {goal}
- Refeições por dia: {meals_per_day} | Meta calórica: {target_calories} kcal/dia
- Restrições alimentares: {restrictions}
- Alergias: {allergies}
- Alimentos preferidos: {preferences}

[PLANO GERADO — {meals_count} refeições, {actual_calories} kcal]
{meal_summary}

[TAREFA 1 — meal_notes]
Para cada refeição listada acima, escreva 1 a 2 dicas práticas e ESPECÍFICAS sobre aquela refeição.
Foco em: modo de preparo, horário ideal em relação ao treino ou rotina, combinações nutricionais, substituições práticas.
Use os alimentos reais — nunca generalize.
Use o NOME EXATO da refeição como chave do JSON (ex: "Café da manhã", "Almoço").

[TAREFA 2 — tips]
Escreva de 3 a 5 dicas gerais e personalizadas para este paciente.
- Cada dica DEVE citar o objetivo, atividade, restrição, alimento ou horário real do plano
- Varie os temas: timing de refeições, hidratação, adesão ao objetivo, preparo prático, cuidados com restrições
- PROIBIDO frases genéricas ("beba bastante água", "durma bem", "pratique exercícios")
- NÃO repita orientações já implícitas no plano
- Máximo 40 palavras por dica

[OUTPUT — retorne EXATAMENTE este JSON, sem texto adicional]
{{
  "meal_notes": {{
    "Nome da refeição 1": "dica(s) específica(s)...",
    "Nome da refeição 2": "dica(s) específica(s)...",
    "Nome da refeição 3": "dica(s) específica(s)..."
  }},
  "tips": [
    "Dica geral 1 personalizada e concreta...",
    "Dica geral 2 personalizada e concreta...",
    "Dica geral 3 personalizada e concreta..."
  ]
}}\
"""

# ─── Builder ──────────────────────────────────────────────────────────────────


def build_notes_prompt(diet_data: dict, anamnese, target_calories: int) -> str:
    """Monta o prompt para geração de dicas personalizadas pós-plano."""
    meals = diet_data.get('meals', [])
    actual_calories = diet_data.get('calories', target_calories)

    meal_lines = []
    for i, m in enumerate(meals, 1):
        meal_name  = m.get('name', f'Refeição {i}')
        meal_kcal  = sum(f.get('calories', 0) for f in m.get('foods', []))
        foods_preview = ', '.join(
            f.get('name', '') for f in m.get('foods', []) if f.get('name')
        )
        time_tag = f" ({m.get('time_suggestion')})" if m.get('time_suggestion') else ''
        # Nome entre aspas para o modelo usá-lo exatamente como chave em meal_notes
        meal_lines.append(
            f'{i}. "{meal_name}"{time_tag} — {meal_kcal} kcal: {foods_preview}'
        )
    meal_summary = '\n'.join(meal_lines) or 'Refeições não disponíveis.'

    return NOTES_TEMPLATE.format(
        age=anamnese.age,
        gender=anamnese.get_gender_display(),
        weight_kg=anamnese.weight_kg,
        height_cm=anamnese.height_cm,
        activity=anamnese.get_activity_display_pt(),
        goal=anamnese.get_goal_display_pt(),
        meals_per_day=anamnese.meals_per_day,
        target_calories=target_calories,
        restrictions=anamnese.food_restrictions or 'Nenhuma',
        allergies=anamnese.allergies or 'Nenhuma',
        preferences=anamnese.food_preferences or 'Sem preferências específicas',
        meals_count=len(meals),
        actual_calories=actual_calories,
        meal_summary=meal_summary,
    )

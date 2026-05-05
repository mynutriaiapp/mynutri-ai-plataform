"""
Passo 2 — Explicação do plano alimentar.

O LLM recebe os valores calculados deterministicamente pelo backend
e escreve a explicação em linguagem natural. Nunca calcula nada.

Temperature recomendada: 0.7 (texto explicativo, tom amigável).
max_tokens recomendado: 1200.
"""

from ._calculations import calculate_calories as _calculate_calories
from ._constants import ACTIVITY_FACTORS, GOAL_ADJUSTMENT_LABELS

# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_EXPLANATION = """\
Você é um nutricionista explicando um plano alimentar ao paciente.

COMPORTAMENTO:
- Use os valores numéricos exatos fornecidos no prompt — nunca invente, estime ou arredonde dados
- Tom: técnico mas acessível, sem jargão excessivo; idioma português do Brasil
- Extensão por campo: 2 a 3 parágrafos curtos (máximo 100 palavras cada)
- Cite alimentos reais do plano, não exemplos genéricos

OUTPUT:
- Responda APENAS com JSON válido, sem texto fora do JSON
- Não adicione campos além dos 5 solicitados\
"""

# ─── User prompt template ─────────────────────────────────────────────────────

EXPLANATION_TEMPLATE = """\
[DADOS CALCULADOS PELO SISTEMA — use exatamente estes valores, não invente outros]
- Equação: Mifflin-St Jeor | Fórmula TMB: {tmb_formula}
- TMB: {tmb} kcal/dia | TDEE: {tdee} kcal/dia (fator de atividade: {activity_factor})
- Ajuste pelo objetivo: {goal_adjustment_label}
- Meta calórica: {target_calories} kcal/dia
- Total do plano: {actual_calories} kcal em {meals_count} refeições
- Macros: proteína {protein_g}g ({protein_pct}%) | carboidratos {carbs_g}g ({carbs_pct}%) | gordura {fat_g}g ({fat_pct}%)
- Proteína por kg: {protein_per_kg}g/kg (peso: {weight_kg}kg)
- Perfil: {age} anos, {gender}, atividade: {activity}, objetivo: {goal}

[REFEIÇÕES DO PLANO]
{meal_summary}

[TAREFA — escreva os 5 campos abaixo, cada um com 2 a 3 parágrafos curtos (máx. 100 palavras por campo)]

- "calorie_calculation": Mostre a equação Mifflin-St Jeor com os dados reais do usuário. Explique o fator de atividade e o ajuste pelo objetivo. Diga o que o déficit/superávit representa na prática.

- "macro_distribution": Explique cada macro com os gramas e percentuais reais. Por que essa distribuição serve ao objetivo. Quais alimentos do plano são as principais fontes de cada macro.

- "food_choices": Explique a lógica das combinações alimentares do plano usando os alimentos reais listados acima. Cite as duplas/trios nutricionalmente relevantes presentes no plano.

- "meal_structure": Explique o número e os horários das refeições. Para cada refeição, diga seu papel no plano (energia matinal, pós-treino, etc.) e a caloria aproximada.

- "goal_alignment": Explique o mecanismo fisiológico do plano para o objetivo declarado. Diga o que o usuário pode esperar de resultado em 4 semanas. Finalize com mensagem motivacional personalizada.

[OUTPUT — retorne APENAS este JSON, sem texto adicional]
{{
  "calorie_calculation": "...",
  "macro_distribution": "...",
  "food_choices": "...",
  "meal_structure": "...",
  "goal_alignment": "..."
}}\
"""

# ─── Builder ──────────────────────────────────────────────────────────────────


def build_explanation_prompt(
    diet_data: dict,
    anamnese,
    tmb: int,
    tdee: int,
    target_calories: int,
) -> str:
    """Monta o prompt do Passo 2 (explicação) com os valores reais já calculados."""
    w = float(anamnese.weight_kg)
    h = float(anamnese.height_cm)
    a = int(anamnese.age)

    if anamnese.gender == 'M':
        constant = '+5'
    elif anamnese.gender == 'F':
        constant = '−161'
    else:
        constant = '−78'
    tmb_formula = f'(10×{w}) + (6,25×{h}) − (5×{a}) {constant} = {tmb} kcal'

    activity_factor = ACTIVITY_FACTORS.get(anamnese.activity_level, 1.375)
    goal_adj_label  = GOAL_ADJUSTMENT_LABELS.get(anamnese.goal, 'Sem ajuste')

    macros         = diet_data.get('macros', {})
    actual_cal     = diet_data.get('calories', target_calories)
    protein_g      = macros.get('protein_g', 0)
    carbs_g        = macros.get('carbs_g', 0)
    fat_g          = macros.get('fat_g', 0)
    protein_kcal   = protein_g * 4
    carbs_kcal     = carbs_g   * 4
    fat_kcal       = fat_g     * 9
    total_macro_kcal = protein_kcal + carbs_kcal + fat_kcal or 1

    protein_pct = round(protein_kcal / total_macro_kcal * 100)
    carbs_pct   = round(carbs_kcal   / total_macro_kcal * 100)
    fat_pct     = round(fat_kcal     / total_macro_kcal * 100)
    protein_per_kg = round(protein_g / w, 1) if w else 0

    meals = diet_data.get('meals', [])
    meal_summary_lines = []
    for i, m in enumerate(meals, 1):
        foods     = m.get('foods', [])
        meal_cal  = sum(f.get('calories',  0) for f in foods)
        meal_prot = sum(f.get('protein_g', 0) for f in foods)
        food_names = ', '.join(f.get('name', '') for f in foods if f.get('name'))
        meal_summary_lines.append(
            f'{i}. {m.get("name", f"Refeição {i}")} ({m.get("time_suggestion", "—")}): '
            f'~{meal_cal} kcal | P:{round(meal_prot)}g | {food_names}'
        )
    meal_summary = '\n'.join(meal_summary_lines) or 'Refeições não disponíveis.'

    return EXPLANATION_TEMPLATE.format(
        tmb_formula=tmb_formula,
        tmb=tmb,
        tdee=tdee,
        activity_factor=activity_factor,
        goal_adjustment_label=goal_adj_label,
        target_calories=target_calories,
        actual_calories=actual_cal,
        meals_count=len(meals),
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        protein_pct=protein_pct,
        carbs_pct=carbs_pct,
        fat_pct=fat_pct,
        protein_per_kg=protein_per_kg,
        weight_kg=w,
        age=a,
        gender=anamnese.get_gender_display(),
        activity=anamnese.get_activity_display_pt(),
        goal=anamnese.get_goal_display_pt(),
        meal_summary=meal_summary,
    )

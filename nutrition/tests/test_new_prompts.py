"""
Testes dos novos módulos de prompts — MyNutri AI.

Cobre: estrutura modular (imports, __all__), conteúdo dos system prompts,
       builders (build_food_selection_prompt, build_explanation_prompt,
       build_notes_prompt, build_meal_regen_prompt), GOAL_CONTEXT.
Testes puramente unitários — sem banco de dados.
"""

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anamnese(
    weight=75.0,
    height=175.0,
    age=25,
    gender='M',
    activity='moderate',
    goal='lose',
    meals=3,
    preferences='Frango, Arroz',
    restrictions='',
    allergies='',
):
    a = MagicMock()
    a.weight_kg = weight
    a.height_cm = height
    a.age = age
    a.gender = gender
    a.activity_level = activity
    a.goal = goal
    a.meals_per_day = meals
    a.food_preferences = preferences
    a.food_restrictions = restrictions
    a.allergies = allergies

    gender_labels = {'M': 'Masculino', 'F': 'Feminino', 'O': 'Outro'}
    activity_labels = {
        'sedentary': 'Sedentário',
        'light': 'Levemente ativo',
        'moderate': 'Moderadamente ativo',
        'intense': 'Muito ativo',
        'athlete': 'Atleta',
    }
    goal_labels = {
        'lose': 'Emagrecimento',
        'maintain': 'Manutenção',
        'gain': 'Hipertrofia / Ganho de Massa',
    }
    a.get_gender_display.return_value = gender_labels.get(gender, 'Masculino')
    a.get_activity_display_pt.return_value = activity_labels.get(activity, 'Moderadamente ativo')
    a.get_goal_display_pt.return_value = goal_labels.get(goal, 'Emagrecimento')
    return a


def _diet_data(n_meals=3, calories=2000):
    meals = []
    for i in range(n_meals):
        names = ["Café da manhã", "Almoço", "Jantar"]
        meals.append({
            "name": names[i] if i < len(names) else f"Refeição {i + 1}",
            "time_suggestion": f"0{7 + i * 4}:00",
            "foods": [
                {"name": "Frango grelhado", "quantity_g": 130, "calories": 220, "protein_g": 28, "carbs_g": 0, "fat_g": 10},
                {"name": "Arroz cozido", "quantity_g": 150, "calories": 200, "protein_g": 4, "carbs_g": 44, "fat_g": 1},
            ],
        })
    return {
        "goal_description": "Dieta de emagrecimento",
        "calories": calories,
        "macros": {"protein_g": 150, "carbs_g": 200, "fat_g": 60},
        "meals": meals,
    }


def _diet_plan_mock(n_meals=3, calories=2000):
    plan = MagicMock()
    plan.raw_response = _diet_data(n_meals, calories)
    plan.anamnese = _anamnese()
    return plan


# ---------------------------------------------------------------------------
# Backward compatibility — imports via __init__
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_importa_calculate_calories(self):
        from nutrition.prompts import calculate_calories
        assert callable(calculate_calories)

    def test_importa_calculate_macros(self):
        from nutrition.prompts import calculate_macros
        assert callable(calculate_macros)

    def test_importa_build_meal_distribution_hint(self):
        from nutrition.prompts import build_meal_distribution_hint
        assert callable(build_meal_distribution_hint)

    def test_importa_build_food_selection_prompt(self):
        from nutrition.prompts import build_food_selection_prompt
        assert callable(build_food_selection_prompt)

    def test_importa_build_explanation_prompt(self):
        from nutrition.prompts import build_explanation_prompt
        assert callable(build_explanation_prompt)

    def test_importa_build_notes_prompt(self):
        from nutrition.prompts import build_notes_prompt
        assert callable(build_notes_prompt)

    def test_importa_build_meal_regen_prompt(self):
        from nutrition.prompts import build_meal_regen_prompt
        assert callable(build_meal_regen_prompt)

    def test_importa_system_prompts(self):
        from nutrition.prompts import (
            SYSTEM_PROMPT_FOODS,
            SYSTEM_PROMPT_EXPLANATION,
            SYSTEM_PROMPT_NOTES,
            SYSTEM_PROMPT_MEAL_REGEN,
        )
        assert isinstance(SYSTEM_PROMPT_FOODS, str)
        assert isinstance(SYSTEM_PROMPT_EXPLANATION, str)
        assert isinstance(SYSTEM_PROMPT_NOTES, str)
        assert isinstance(SYSTEM_PROMPT_MEAL_REGEN, str)

    def test_importa_templates(self):
        from nutrition.prompts import (
            FOOD_SELECTION_TEMPLATE,
            EXPLANATION_TEMPLATE,
            NOTES_TEMPLATE,
            MEAL_REGEN_TEMPLATE,
        )
        assert '{age}' in FOOD_SELECTION_TEMPLATE
        assert '{tmb}' in EXPLANATION_TEMPLATE
        assert '{meal_summary}' in NOTES_TEMPLATE
        assert '{meal_name}' in MEAL_REGEN_TEMPLATE

    def test_importa_goal_context(self):
        from nutrition.prompts import GOAL_CONTEXT
        assert isinstance(GOAL_CONTEXT, dict)
        assert set(GOAL_CONTEXT.keys()) >= {'lose', 'maintain', 'gain'}

    def test_all_exporta_simbolos_publicos(self):
        import nutrition.prompts as p
        for symbol in p.__all__:
            assert hasattr(p, symbol), f"__all__ inclui '{symbol}' mas não está no módulo"


# ---------------------------------------------------------------------------
# GOAL_CONTEXT
# ---------------------------------------------------------------------------

class TestGoalContext:
    def test_todos_os_objetivos_presentes(self):
        from nutrition.prompts import GOAL_CONTEXT
        assert 'lose' in GOAL_CONTEXT
        assert 'maintain' in GOAL_CONTEXT
        assert 'gain' in GOAL_CONTEXT

    def test_valores_sao_strings_nao_vazias(self):
        from nutrition.prompts import GOAL_CONTEXT
        for key, value in GOAL_CONTEXT.items():
            assert isinstance(value, str)
            assert len(value) > 10, f"GOAL_CONTEXT['{key}'] parece vazio"

    def test_emagrecimento_menciona_proteina(self):
        from nutrition.prompts import GOAL_CONTEXT
        assert 'proteína' in GOAL_CONTEXT['lose'].lower() or 'proteina' in GOAL_CONTEXT['lose'].lower()

    def test_ganho_menciona_carboidrato(self):
        from nutrition.prompts import GOAL_CONTEXT
        assert 'carboidrato' in GOAL_CONTEXT['gain'].lower()

    def test_ganho_menciona_superavit_ou_energia(self):
        from nutrition.prompts import GOAL_CONTEXT
        text = GOAL_CONTEXT['gain'].lower()
        assert 'superavit' in text or 'energia' in text or 'superávit' in text


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_FOODS
# ---------------------------------------------------------------------------

class TestSystemPromptFoods:
    def test_menciona_variedade(self):
        from nutrition.prompts import SYSTEM_PROMPT_FOODS
        assert 'variedade' in SYSTEM_PROMPT_FOODS.lower() or 'variados' in SYSTEM_PROMPT_FOODS.lower()

    def test_menciona_anti_manipulacao(self):
        from nutrition.prompts import SYSTEM_PROMPT_FOODS
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'manipul' in text or 'instrução' in text or 'instrucao' in text

    def test_menciona_alimentos_proibidos(self):
        from nutrition.prompts import SYSTEM_PROMPT_FOODS
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'pizza' in text or 'hamburguer' in text or 'lasanha' in text

    def test_menciona_proteina_obrigatoria(self):
        from nutrition.prompts import SYSTEM_PROMPT_FOODS
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'proteína' in text or 'proteina' in text

    def test_menciona_portugues_brasil(self):
        from nutrition.prompts import SYSTEM_PROMPT_FOODS
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'brasil' in text or 'português' in text or 'portugues' in text

    def test_menciona_json(self):
        from nutrition.prompts import SYSTEM_PROMPT_FOODS
        assert 'JSON' in SYSTEM_PROMPT_FOODS


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_EXPLANATION
# ---------------------------------------------------------------------------

class TestSystemPromptExplanation:
    def test_menciona_json(self):
        from nutrition.prompts import SYSTEM_PROMPT_EXPLANATION
        assert 'JSON' in SYSTEM_PROMPT_EXPLANATION

    def test_menciona_limite_palavras(self):
        from nutrition.prompts import SYSTEM_PROMPT_EXPLANATION
        text = SYSTEM_PROMPT_EXPLANATION.lower()
        assert 'palavras' in text or '100' in text

    def test_menciona_5_campos(self):
        from nutrition.prompts import SYSTEM_PROMPT_EXPLANATION
        assert '5' in SYSTEM_PROMPT_EXPLANATION


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_NOTES
# ---------------------------------------------------------------------------

class TestSystemPromptNotes:
    def test_menciona_json(self):
        from nutrition.prompts import SYSTEM_PROMPT_NOTES
        assert 'JSON' in SYSTEM_PROMPT_NOTES

    def test_menciona_personalizacao(self):
        from nutrition.prompts import SYSTEM_PROMPT_NOTES
        text = SYSTEM_PROMPT_NOTES.lower()
        assert 'personaliz' in text

    def test_menciona_genericas_proibidas(self):
        from nutrition.prompts import SYSTEM_PROMPT_NOTES
        text = SYSTEM_PROMPT_NOTES.lower()
        assert 'genéric' in text or 'generic' in text


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_MEAL_REGEN
# ---------------------------------------------------------------------------

class TestSystemPromptMealRegen:
    def test_menciona_uma_refeicao(self):
        from nutrition.prompts import SYSTEM_PROMPT_MEAL_REGEN
        text = SYSTEM_PROMPT_MEAL_REGEN.lower()
        assert 'uma' in text and ('refeição' in text or 'refei' in text)

    def test_menciona_alergias(self):
        from nutrition.prompts import SYSTEM_PROMPT_MEAL_REGEN
        text = SYSTEM_PROMPT_MEAL_REGEN.lower()
        assert 'alergi' in text

    def test_menciona_json(self):
        from nutrition.prompts import SYSTEM_PROMPT_MEAL_REGEN
        assert 'JSON' in SYSTEM_PROMPT_MEAL_REGEN

    def test_menciona_seguranca(self):
        from nutrition.prompts import SYSTEM_PROMPT_MEAL_REGEN
        text = SYSTEM_PROMPT_MEAL_REGEN.lower()
        assert 'segurança' in text or 'seguranca' in text or 'instrução' in text


# ---------------------------------------------------------------------------
# build_food_selection_prompt
# ---------------------------------------------------------------------------

class TestBuildFoodSelectionPrompt:
    def test_retorna_string(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese()
        result = build_food_selection_prompt(a)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_inclui_perfil_usuario(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese(weight=80, age=30, gender='F')
        result = build_food_selection_prompt(a)
        assert '80' in result
        assert '30' in result

    def test_inclui_meta_calorica(self):
        from nutrition.prompts import build_food_selection_prompt, calculate_calories
        a = _anamnese()
        _, _, target = calculate_calories(a)
        result = build_food_selection_prompt(a)
        assert str(target) in result

    def test_inclui_preferencias(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese(preferences='Salmão, Quinoa')
        result = build_food_selection_prompt(a)
        assert 'Salmão' in result or 'Salm' in result

    def test_inclui_restricoes(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese(restrictions='Glúten, Lactose')
        result = build_food_selection_prompt(a)
        assert 'Glúten' in result or 'Gluten' in result

    def test_inclui_alergias(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese(allergies='Amendoim, Camarão')
        result = build_food_selection_prompt(a)
        assert 'Amendoim' in result

    def test_inclui_goal_context_emagrecimento(self):
        from nutrition.prompts import build_food_selection_prompt, GOAL_CONTEXT
        a = _anamnese(goal='lose')
        result = build_food_selection_prompt(a)
        # O texto do GOAL_CONTEXT deve estar no prompt
        context_fragment = GOAL_CONTEXT['lose'][:30]
        assert context_fragment in result

    def test_inclui_goal_context_ganho(self):
        from nutrition.prompts import build_food_selection_prompt, GOAL_CONTEXT
        a = _anamnese(goal='gain')
        result = build_food_selection_prompt(a)
        context_fragment = GOAL_CONTEXT['gain'][:30]
        assert context_fragment in result

    def test_sem_preferencias_inclui_instrucao_simplicidade(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese(preferences='', restrictions='', allergies='')
        result = build_food_selection_prompt(a)
        assert 'simpl' in result.lower() or 'mercado' in result.lower()

    def test_distribuicao_calorica_incluida(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese(meals=3)
        result = build_food_selection_prompt(a)
        assert 'kcal' in result
        assert 'Café da manhã' in result

    def test_n_refeicoes_na_distribuicao(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese(meals=5)
        result = build_food_selection_prompt(a)
        assert 'Lanche' in result

    def test_json_estrutura_incluida(self):
        from nutrition.prompts import build_food_selection_prompt
        a = _anamnese()
        result = build_food_selection_prompt(a)
        assert '"meals"' in result
        assert '"foods"' in result


# ---------------------------------------------------------------------------
# build_explanation_prompt
# ---------------------------------------------------------------------------

class TestBuildExplanationPrompt:
    def test_retorna_string(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_inclui_tmb(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        assert '1724' in result

    def test_inclui_tdee(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        assert '2671' in result

    def test_inclui_meta_calorica(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        assert '2221' in result

    def test_formula_tmb_homem(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese(gender='M')
        data = _diet_data()
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        assert '+5' in result

    def test_formula_tmb_mulher(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese(gender='F')
        data = _diet_data()
        result = build_explanation_prompt(data, a, tmb=1289, tdee=1547, target_calories=1547)
        assert '161' in result

    def test_inclui_nomes_refeicoes(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese()
        data = _diet_data(n_meals=3)
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        assert 'Café da manhã' in result
        assert 'Almoço' in result

    def test_inclui_macros(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese()
        data = _diet_data()
        data['macros'] = {'protein_g': 150, 'carbs_g': 200, 'fat_g': 60}
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        assert '150' in result
        assert '200' in result
        assert '60' in result

    def test_inclui_5_campos_output(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        assert 'calorie_calculation' in result
        assert 'macro_distribution' in result
        assert 'food_choices' in result
        assert 'meal_structure' in result
        assert 'goal_alignment' in result

    def test_inclui_proteina_por_kg(self):
        from nutrition.prompts import build_explanation_prompt
        a = _anamnese(weight=75)
        data = _diet_data()
        data['macros'] = {'protein_g': 150, 'carbs_g': 200, 'fat_g': 60}
        result = build_explanation_prompt(data, a, tmb=1724, tdee=2671, target_calories=2221)
        # 150g / 75kg = 2.0g/kg
        assert '2.0' in result


# ---------------------------------------------------------------------------
# build_notes_prompt
# ---------------------------------------------------------------------------

class TestBuildNotesPrompt:
    def test_retorna_string(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_notes_prompt(data, a, target_calories=2221)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_inclui_nomes_refeicoes_com_aspas(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese()
        data = _diet_data(n_meals=3)
        result = build_notes_prompt(data, a, target_calories=2221)
        assert '"Café da manhã"' in result
        assert '"Almoço"' in result

    def test_inclui_alimentos_reais(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_notes_prompt(data, a, target_calories=2221)
        assert 'Frango grelhado' in result

    def test_inclui_perfil_usuario(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese(age=30, weight=80)
        data = _diet_data()
        result = build_notes_prompt(data, a, target_calories=2221)
        assert '30' in result
        assert '80' in result

    def test_inclui_meta_calorica(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_notes_prompt(data, a, target_calories=2221)
        assert '2221' in result

    def test_inclui_restricoes(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese(restrictions='Glúten')
        data = _diet_data()
        result = build_notes_prompt(data, a, target_calories=2221)
        assert 'Glúten' in result or 'Gluten' in result

    def test_json_output_tem_meal_notes_e_tips(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_notes_prompt(data, a, target_calories=2221)
        assert '"meal_notes"' in result
        assert '"tips"' in result

    def test_tarefa_1_e_2_presentes(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_notes_prompt(data, a, target_calories=2221)
        assert 'TAREFA 1' in result
        assert 'TAREFA 2' in result

    def test_menciona_limite_palavras_nas_dicas(self):
        from nutrition.prompts import build_notes_prompt
        a = _anamnese()
        data = _diet_data()
        result = build_notes_prompt(data, a, target_calories=2221)
        assert '40' in result and 'palavra' in result.lower()


# ---------------------------------------------------------------------------
# build_meal_regen_prompt
# ---------------------------------------------------------------------------

class TestBuildMealRegenPrompt:
    def test_retorna_string(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=1)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_inclui_nome_da_refeicao(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0)
        assert 'Café da manhã' in result

    def test_inclui_outras_refeicoes(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0)
        # As outras refeições devem aparecer no contexto
        assert 'Almoço' in result
        assert 'Jantar' in result

    def test_nao_inclui_refeicao_atual_nas_outras(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=1)
        # Refeição 1 (index=1) é "Almoço" — não deve aparecer como "outra refeição"
        # mas aparece como [REFEIÇÃO A SUBSTITUIR]
        assert 'REFEIÇÃO A SUBSTITUIR' in result

    def test_inclui_calorias_da_refeicao(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0)
        # Café da manhã tem 2 alimentos: 220 + 200 = 420 kcal
        assert '420' in result

    def test_inclui_meta_proteica(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0)
        assert 'proteica' in result.lower() or 'proteína' in result.lower() or 'protein' in result.lower()

    def test_inclui_alimentos_atuais(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0)
        assert 'Frango grelhado' in result

    def test_reason_incluido_quando_fornecido(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0, reason='Não gosto de frango')
        assert 'Não gosto de frango' in result

    def test_reason_vazio_nao_inclui_label(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0, reason='')
        assert 'Motivo informado' not in result

    def test_reason_truncado_em_200_chars(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        reason_longo = 'x' * 300
        result = build_meal_regen_prompt(plan, meal_index=0, reason=reason_longo)
        assert 'x' * 201 not in result
        assert 'x' * 200 in result

    def test_inclui_perfil_usuario(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock()
        plan.anamnese = _anamnese(age=30, weight=85)
        result = build_meal_regen_prompt(plan, meal_index=0)
        assert '30' in result
        assert '85' in result

    def test_inclui_json_output(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0)
        assert '"foods"' in result
        assert '"name"' in result
        assert '"quantity_g"' in result

    def test_inclui_numero_da_refeicao(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=1)
        assert '2' in result  # meal_num=2 (index+1)
        assert '3' in result  # total_meals=3

    def test_nenhuma_restricao_informada(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock()
        plan.anamnese = _anamnese(restrictions='', allergies='')
        result = build_meal_regen_prompt(plan, meal_index=0)
        assert 'Nenhuma' in result

    def test_refeicao_index_0_funciona(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=0)
        assert result is not None

    def test_refeicao_ultima_index_funciona(self):
        from nutrition.prompts import build_meal_regen_prompt
        plan = _diet_plan_mock(n_meals=3)
        result = build_meal_regen_prompt(plan, meal_index=2)
        assert result is not None

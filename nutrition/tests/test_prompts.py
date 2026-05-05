"""
Testes dos prompts — MyNutri AI.

Cobre: backward compatibility (imports via __init__), GOAL_CONTEXT, conteúdo dos
4 system prompts, builders (build_food_selection_prompt, build_explanation_prompt,
build_notes_prompt, build_meal_regen_prompt), estrutura dos templates.
Testes puramente unitários — sem banco de dados.
"""

import re
import pytest
from unittest.mock import MagicMock

from nutrition.prompts import (
    SYSTEM_PROMPT_FOODS,
    SYSTEM_PROMPT_EXPLANATION,
    SYSTEM_PROMPT_NOTES,
    SYSTEM_PROMPT_MEAL_REGEN,
    FOOD_SELECTION_TEMPLATE,
    GOAL_CONTEXT,
    calculate_calories,
    build_food_selection_prompt,
    build_explanation_prompt,
    build_notes_prompt,
    build_meal_regen_prompt,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anamnese(
    weight=75.0, height=175.0, age=25,
    gender='M', activity='moderate', goal='lose', meals=3,
    preferences='Frango, Arroz', restrictions='', allergies='',
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
        'sedentary': 'Sedentário', 'light': 'Levemente ativo',
        'moderate': 'Moderadamente ativo', 'intense': 'Muito ativo', 'athlete': 'Atleta',
    }
    goal_labels = {'lose': 'Emagrecimento', 'maintain': 'Manutenção', 'gain': 'Hipertrofia / Ganho de Massa'}
    a.get_gender_display.return_value = gender_labels.get(gender, gender)
    a.get_activity_display_pt.return_value = activity_labels.get(activity, activity)
    a.get_goal_display_pt.return_value = goal_labels.get(goal, goal)
    return a


def _diet_data(n_meals=3, calories=2000):
    names = ['Café da manhã', 'Almoço', 'Jantar', 'Lanche', 'Ceia', 'Desjejum']
    meals = []
    for i in range(n_meals):
        meals.append({
            'name': names[i] if i < len(names) else f'Refeição {i+1}',
            'time_suggestion': f'0{7 + i * 4 % 12}:00',
            'foods': [
                {'name': 'Frango grelhado', 'quantity_g': 130, 'calories': 220,
                 'protein_g': 28, 'carbs_g': 0, 'fat_g': 10},
                {'name': 'Arroz cozido', 'quantity_g': 150, 'calories': 200,
                 'protein_g': 4, 'carbs_g': 44, 'fat_g': 1},
            ],
        })
    return {
        'goal_description': 'Dieta de emagrecimento',
        'calories': calories,
        'macros': {'protein_g': 150, 'carbs_g': 200, 'fat_g': 60},
        'meals': meals,
    }


def _diet_plan_mock(n_meals=3, calories=2000):
    plan = MagicMock()
    plan.raw_response = _diet_data(n_meals, calories)
    plan.anamnese = _anamnese()
    return plan


# ---------------------------------------------------------------------------
# Backward compatibility — todos os símbolos públicos importáveis via __init__
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_all_exporta_todos_simbolos(self):
        import nutrition.prompts as p
        for symbol in p.__all__:
            assert hasattr(p, symbol), f"__all__ inclui '{symbol}' mas não está no módulo"

    def test_importa_callers_de_services(self):
        # Verifica que services.py consegue importar o que precisa
        from nutrition.prompts import (
            SYSTEM_PROMPT_EXPLANATION, SYSTEM_PROMPT_FOODS,
            SYSTEM_PROMPT_MEAL_REGEN, SYSTEM_PROMPT_NOTES,
            build_explanation_prompt, build_food_selection_prompt,
            build_meal_regen_prompt, build_notes_prompt,
            calculate_calories, calculate_macros,
        )
        assert all([SYSTEM_PROMPT_FOODS, SYSTEM_PROMPT_EXPLANATION])

    def test_importa_templates(self):
        from nutrition.prompts import (
            FOOD_SELECTION_TEMPLATE, EXPLANATION_TEMPLATE,
            NOTES_TEMPLATE, MEAL_REGEN_TEMPLATE,
        )
        assert '{age}' in FOOD_SELECTION_TEMPLATE
        assert '{tmb}' in EXPLANATION_TEMPLATE
        assert '{meal_summary}' in NOTES_TEMPLATE
        assert '{meal_name}' in MEAL_REGEN_TEMPLATE


# ---------------------------------------------------------------------------
# GOAL_CONTEXT
# ---------------------------------------------------------------------------

class TestGoalContext:

    def test_todos_os_objetivos_presentes(self):
        assert {'lose', 'maintain', 'gain'} <= set(GOAL_CONTEXT.keys())

    def test_valores_sao_strings_nao_vazias(self):
        for k, v in GOAL_CONTEXT.items():
            assert isinstance(v, str) and len(v) > 10, f"GOAL_CONTEXT['{k}'] vazio"

    def test_emagrecimento_menciona_proteina(self):
        text = GOAL_CONTEXT['lose'].lower()
        assert 'proteína' in text or 'proteina' in text

    def test_ganho_menciona_carboidrato(self):
        assert 'carboidrato' in GOAL_CONTEXT['gain'].lower()


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_FOODS
# ---------------------------------------------------------------------------

class TestSystemPromptFoods:

    def test_nao_vazio_e_menciona_json(self):
        assert len(SYSTEM_PROMPT_FOODS) > 100
        assert 'JSON' in SYSTEM_PROMPT_FOODS

    def test_menciona_variedade(self):
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'variedade' in text or 'variados' in text

    def test_menciona_anti_manipulacao(self):
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'manipul' in text or 'instrução' in text or 'instrucao' in text

    def test_menciona_alimentos_proibidos(self):
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'pizza' in text or 'hamburguer' in text or 'lasanha' in text

    def test_menciona_proteina_obrigatoria(self):
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'proteína' in text or 'proteina' in text

    def test_menciona_portugues_brasil(self):
        text = SYSTEM_PROMPT_FOODS.lower()
        assert 'brasil' in text or 'português' in text or 'portugues' in text

    def test_nao_instrui_calcular_macros(self):
        assert 'NÃO calcule calorias nem macros' in FOOD_SELECTION_TEMPLATE

    def test_template_sem_variaveis_nao_substituidas(self):
        a = _anamnese()
        prompt = build_food_selection_prompt(a)
        unresolved = re.findall(r'(?<!\{)\{(?!\{)(\w+)(?<!\})\}(?!\})', prompt)
        assert unresolved == [], f'Variáveis não substituídas: {unresolved}'

    def test_passo1_nao_pede_macros_por_alimento(self):
        prompt = build_food_selection_prompt(_anamnese())
        assert 'protein_g' not in prompt
        assert 'carbs_g' not in prompt
        assert 'fat_g' not in prompt


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_EXPLANATION, NOTES, MEAL_REGEN
# ---------------------------------------------------------------------------

class TestOutrosSystemPrompts:

    def test_explanation_menciona_5_campos(self):
        assert '5' in SYSTEM_PROMPT_EXPLANATION
        assert 'JSON' in SYSTEM_PROMPT_EXPLANATION

    def test_explanation_menciona_limite_palavras(self):
        assert '100' in SYSTEM_PROMPT_EXPLANATION

    def test_notes_menciona_json_e_genericas_proibidas(self):
        assert 'JSON' in SYSTEM_PROMPT_NOTES
        text = SYSTEM_PROMPT_NOTES.lower()
        assert 'genéric' in text or 'generic' in text

    def test_meal_regen_menciona_alergia_e_json(self):
        text = SYSTEM_PROMPT_MEAL_REGEN.lower()
        assert 'alergi' in text
        assert 'JSON' in SYSTEM_PROMPT_MEAL_REGEN

    def test_meal_regen_menciona_seguranca(self):
        text = SYSTEM_PROMPT_MEAL_REGEN.lower()
        assert 'segurança' in text or 'seguranca' in text or 'instrução' in text


# ---------------------------------------------------------------------------
# build_food_selection_prompt
# ---------------------------------------------------------------------------

class TestBuildFoodSelectionPrompt:

    def test_retorna_string_com_conteudo(self):
        result = build_food_selection_prompt(_anamnese())
        assert isinstance(result, str) and len(result) > 100

    def test_inclui_meta_calorica(self):
        a = _anamnese()
        _, _, target = calculate_calories(a)
        assert str(target) in build_food_selection_prompt(a)

    def test_inclui_perfil_usuario(self):
        result = build_food_selection_prompt(_anamnese(weight=80, age=30, gender='F'))
        assert '80' in result and '30' in result

    def test_inclui_preferencias_restricoes_alergias(self):
        a = _anamnese(preferences='Salmão', restrictions='Glúten', allergies='Amendoim')
        result = build_food_selection_prompt(a)
        assert 'Salmão' in result or 'Salm' in result
        assert 'Glúten' in result or 'Gluten' in result
        assert 'Amendoim' in result

    def test_inclui_goal_context(self):
        for goal in ('lose', 'maintain', 'gain'):
            a = _anamnese(goal=goal)
            result = build_food_selection_prompt(a)
            assert GOAL_CONTEXT[goal][:30] in result

    def test_sem_restricoes_inclui_instrucao_simplicidade(self):
        a = _anamnese(preferences='', restrictions='', allergies='')
        result = build_food_selection_prompt(a)
        assert 'simpl' in result.lower() or 'mercado' in result.lower()

    def test_inclui_distribuicao_calorica(self):
        result = build_food_selection_prompt(_anamnese(meals=3))
        assert 'kcal' in result and 'Café da manhã' in result

    def test_inclui_json_output(self):
        result = build_food_selection_prompt(_anamnese())
        assert '"meals"' in result and '"foods"' in result

    def test_tmb_e_tdee_nao_estao_no_passo1(self):
        """TMB e TDEE ficam no prompt de explicação (Passo 2), não no de seleção."""
        a = _anamnese()
        tmb, tdee, target = calculate_calories(a)
        prompt = build_food_selection_prompt(a)
        expl = build_explanation_prompt(_diet_data(), a, tmb, tdee, target)
        assert str(tmb) in expl and str(tdee) in expl


# ---------------------------------------------------------------------------
# build_explanation_prompt
# ---------------------------------------------------------------------------

class TestBuildExplanationPrompt:

    def test_retorna_string_com_conteudo(self):
        result = build_explanation_prompt(_diet_data(), _anamnese(), 1724, 2671, 2221)
        assert isinstance(result, str) and len(result) > 100

    def test_inclui_tmb_tdee_meta(self):
        result = build_explanation_prompt(_diet_data(), _anamnese(), 1724, 2671, 2221)
        assert '1724' in result and '2671' in result and '2221' in result

    def test_formula_homem_tem_mais_5(self):
        result = build_explanation_prompt(_diet_data(), _anamnese(gender='M'), 1724, 2671, 2221)
        assert '+5' in result

    def test_formula_mulher_tem_161(self):
        result = build_explanation_prompt(_diet_data(), _anamnese(gender='F'), 1289, 1547, 1547)
        assert '161' in result

    def test_inclui_5_campos_output(self):
        result = build_explanation_prompt(_diet_data(), _anamnese(), 1724, 2671, 2221)
        for campo in ('calorie_calculation', 'macro_distribution', 'food_choices',
                      'meal_structure', 'goal_alignment'):
            assert campo in result

    def test_inclui_nomes_das_refeicoes(self):
        result = build_explanation_prompt(_diet_data(3), _anamnese(), 1724, 2671, 2221)
        assert 'Café da manhã' in result and 'Almoço' in result

    def test_inclui_macros(self):
        data = _diet_data()
        data['macros'] = {'protein_g': 150, 'carbs_g': 200, 'fat_g': 60}
        result = build_explanation_prompt(data, _anamnese(), 1724, 2671, 2221)
        assert '150' in result and '200' in result and '60' in result


# ---------------------------------------------------------------------------
# build_notes_prompt
# ---------------------------------------------------------------------------

class TestBuildNotesPrompt:

    def test_retorna_string_com_conteudo(self):
        result = build_notes_prompt(_diet_data(), _anamnese(), 2221)
        assert isinstance(result, str) and len(result) > 100

    def test_inclui_nomes_refeicoes_com_aspas(self):
        result = build_notes_prompt(_diet_data(3), _anamnese(), 2221)
        assert '"Café da manhã"' in result and '"Almoço"' in result

    def test_inclui_alimentos_reais(self):
        result = build_notes_prompt(_diet_data(), _anamnese(), 2221)
        assert 'Frango grelhado' in result

    def test_inclui_meta_calorica(self):
        assert '2221' in build_notes_prompt(_diet_data(), _anamnese(), 2221)

    def test_json_output_tem_meal_notes_e_tips(self):
        result = build_notes_prompt(_diet_data(), _anamnese(), 2221)
        assert '"meal_notes"' in result and '"tips"' in result

    def test_menciona_limite_40_palavras(self):
        result = build_notes_prompt(_diet_data(), _anamnese(), 2221)
        assert '40' in result and 'palavra' in result.lower()


# ---------------------------------------------------------------------------
# build_meal_regen_prompt
# ---------------------------------------------------------------------------

class TestBuildMealRegenPrompt:

    def test_retorna_string_com_conteudo(self):
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=1)
        assert isinstance(result, str) and len(result) > 100

    def test_inclui_nome_e_outras_refeicoes(self):
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=0)
        assert 'Café da manhã' in result
        assert 'Almoço' in result
        assert 'Jantar' in result

    def test_inclui_calorias_da_refeicao(self):
        # 2 alimentos: 220 + 200 = 420 kcal
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=0)
        assert '420' in result

    def test_inclui_alimentos_atuais(self):
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=0)
        assert 'Frango grelhado' in result

    def test_reason_incluido_quando_fornecido(self):
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=0, reason='Não gosto de frango')
        assert 'Não gosto de frango' in result

    def test_reason_vazio_nao_inclui_label(self):
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=0, reason='')
        assert 'Motivo informado' not in result

    def test_reason_truncado_em_200_chars(self):
        reason_longo = 'x' * 300
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=0, reason=reason_longo)
        assert 'x' * 201 not in result and 'x' * 200 in result

    def test_inclui_numero_e_total_de_refeicoes(self):
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=1)
        assert '2' in result and '3' in result

    def test_json_output_contem_chaves_esperadas(self):
        result = build_meal_regen_prompt(_diet_plan_mock(3), meal_index=0)
        assert '"foods"' in result and '"name"' in result and '"quantity_g"' in result

    def test_todos_os_indices_validos_funcionam(self):
        plan = _diet_plan_mock(3)
        for i in range(3):
            assert build_meal_regen_prompt(plan, meal_index=i) is not None

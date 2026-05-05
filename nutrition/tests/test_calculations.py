"""
Testes dos cálculos determinísticos — MyNutri AI.

Cobre: calculate_calories (Mifflin-St Jeor), calculate_macros (3 passos),
       build_meal_distribution_hint, banco nutricional (lookup_food_nutrition),
       _recalculate_totals, _adjust_to_calorie_target.
Testes puramente unitários — sem banco de dados (exceto TestNutritionDB que usa o arquivo TACO).
"""

import pytest
from unittest.mock import MagicMock, patch

from nutrition.prompts import calculate_calories, calculate_macros, build_meal_distribution_hint
from nutrition.prompts._constants import (
    ACTIVITY_FACTORS,
    GOAL_ADJUSTMENTS,
    MEAL_PLANS,
    MIN_CALORIES,
    PROTEIN_MIN_PER_KG,
    PROTEIN_MAX_PER_KG,
    FAT_MIN_PER_KG,
    FAT_MAX_PER_KG,
)
from nutrition.services import AIService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anamnese(
    weight=75.0, height=175.0, age=25,
    gender='M', activity='moderate', goal='lose', meals=3,
):
    a = MagicMock()
    a.weight_kg = weight
    a.height_cm = height
    a.age = age
    a.gender = gender
    a.activity_level = activity
    a.goal = goal
    a.meals_per_day = meals
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


# ---------------------------------------------------------------------------
# calculate_calories — Mifflin-St Jeor
# ---------------------------------------------------------------------------

class TestCalculateCalories:

    def test_retorna_tupla_de_tres_inteiros(self):
        tmb, tdee, target = calculate_calories(_anamnese())
        assert isinstance(tmb, int) and isinstance(tdee, int) and isinstance(target, int)

    def test_tmb_masculino_formula_correta(self):
        tmb, _, _ = calculate_calories(_anamnese(75, 175, 25, 'M'))
        assert tmb == round((10 * 75) + (6.25 * 175) - (5 * 25) + 5)

    def test_tmb_feminino_formula_correta(self):
        tmb, _, _ = calculate_calories(_anamnese(60, 165, 30, 'F'))
        assert tmb == round((10 * 60) + (6.25 * 165) - (5 * 30) - 161)

    def test_tmb_outro_genero_usa_media(self):
        tmb, _, _ = calculate_calories(_anamnese(70, 170, 28, 'O'))
        assert tmb == round((10 * 70) + (6.25 * 170) - (5 * 28) - 78)

    def test_tdee_aplica_fator_sedentario(self):
        tmb, tdee, _ = calculate_calories(_anamnese(activity='sedentary', goal='maintain'))
        assert abs(tdee - tmb * 1.2) <= 2

    def test_tdee_aplica_fator_moderado(self):
        tmb, tdee, _ = calculate_calories(_anamnese(activity='moderate', goal='maintain'))
        assert abs(tdee - tmb * 1.55) <= 2

    def test_tdee_aplica_fator_atleta(self):
        tmb, tdee, _ = calculate_calories(_anamnese(activity='athlete', goal='maintain'))
        assert abs(tdee - tmb * 1.9) <= 2

    def test_objetivo_emagrecer_aplica_deficit(self):
        _, tdee, target = calculate_calories(_anamnese(activity='moderate', goal='lose'))
        assert target == max(round(tdee - 450), 1500)

    def test_objetivo_manutencao_sem_ajuste(self):
        _, tdee, target = calculate_calories(_anamnese(activity='moderate', goal='maintain'))
        assert target == tdee

    def test_objetivo_ganho_aplica_superavit(self):
        _, tdee, target = calculate_calories(_anamnese(activity='moderate', goal='gain'))
        assert target == round(tdee + 350)

    def test_piso_seguranca_masculino_1500_kcal(self):
        _, _, target = calculate_calories(_anamnese(40, 150, 60, 'M', 'sedentary', 'lose'))
        assert target >= MIN_CALORIES['M']

    def test_piso_seguranca_feminino_1200_kcal(self):
        _, _, target = calculate_calories(_anamnese(35, 145, 60, 'F', 'sedentary', 'lose'))
        assert target >= MIN_CALORIES['F']

    def test_piso_seguranca_outro_genero_1350_kcal(self):
        _, _, target = calculate_calories(_anamnese(38, 148, 60, 'O', 'sedentary', 'lose'))
        assert target >= MIN_CALORIES['O']

    def test_calories_sao_positivas(self):
        for goal in ('lose', 'maintain', 'gain'):
            for gender in ('M', 'F', 'O'):
                tmb, tdee, target = calculate_calories(_anamnese(gender=gender, goal=goal))
                assert tmb > 0 and tdee > 0 and target > 0

    def test_tdee_maior_que_tmb(self):
        tmb, tdee, _ = calculate_calories(_anamnese(activity='sedentary'))
        assert tdee > tmb

    def test_ativo_tem_meta_maior_que_sedentario(self):
        _, _, t_sed = calculate_calories(_anamnese(activity='sedentary', goal='maintain'))
        _, _, t_atl = calculate_calories(_anamnese(activity='athlete', goal='maintain'))
        assert t_atl > t_sed

    def test_hipertrofia_tem_meta_maior_que_emagrecer(self):
        _, _, t_lose = calculate_calories(_anamnese(goal='lose'))
        _, _, t_gain = calculate_calories(_anamnese(goal='gain'))
        assert t_gain > t_lose

    def test_todos_niveis_atividade_crescentes(self):
        levels = ['sedentary', 'light', 'moderate', 'intense', 'athlete']
        targets = []
        for level in levels:
            _, _, t = calculate_calories(_anamnese(activity=level, goal='maintain'))
            targets.append(t)
        assert targets == sorted(targets)

    def test_activity_desconhecida_usa_light(self):
        _, tdee1, _ = calculate_calories(_anamnese(activity='unknown', goal='maintain'))
        _, tdee2, _ = calculate_calories(_anamnese(activity='light', goal='maintain'))
        assert tdee1 == tdee2


# ---------------------------------------------------------------------------
# calculate_macros — 3 passos: proteína, gordura, carboidrato
# ---------------------------------------------------------------------------

class TestCalculateMacros:

    def test_retorna_todas_chaves(self):
        a = _anamnese()
        _, _, target = calculate_calories(a)
        macros = calculate_macros(a, target)
        assert {'protein_g', 'protein_pct', 'protein_per_kg', 'fat_g', 'fat_pct',
                'fat_per_kg', 'carbs_g', 'carbs_pct'} == set(macros.keys())

    def test_percentuais_somam_100(self):
        for goal in ('lose', 'maintain', 'gain'):
            a = _anamnese(goal=goal)
            _, _, target = calculate_calories(a)
            m = calculate_macros(a, target)
            assert abs(m['protein_pct'] + m['fat_pct'] + m['carbs_pct'] - 100) <= 2

    def test_proteina_respeita_minimo_por_kg(self):
        for goal in ('lose', 'maintain', 'gain'):
            a = _anamnese(75, goal=goal)
            _, _, t = calculate_calories(a)
            assert calculate_macros(a, t)['protein_g'] >= round(75 * PROTEIN_MIN_PER_KG)

    def test_proteina_respeita_maximo_por_kg(self):
        for goal in ('lose', 'maintain', 'gain'):
            a = _anamnese(75, goal=goal)
            _, _, t = calculate_calories(a)
            assert calculate_macros(a, t)['protein_g'] <= round(75 * PROTEIN_MAX_PER_KG)

    def test_proteina_nao_excede_40pct_calorias(self):
        a = _anamnese(120, 185, 25, 'M', 'sedentary', 'lose')
        _, _, t = calculate_calories(a)
        m = calculate_macros(a, t)
        assert m['protein_g'] * 4 <= t * 0.40 + 4

    def test_gordura_respeita_minimo_por_kg(self):
        for goal in ('lose', 'maintain', 'gain'):
            a = _anamnese(75, goal=goal)
            _, _, t = calculate_calories(a)
            assert calculate_macros(a, t)['fat_g'] >= round(75 * FAT_MIN_PER_KG)

    def test_gordura_nao_excede_35pct_calorias(self):
        a = _anamnese(120, 185, 25, 'M', 'sedentary', 'lose')
        _, _, t = calculate_calories(a)
        m = calculate_macros(a, t)
        assert m['fat_g'] * 9 <= t * 0.35 + 9

    def test_carboidratos_sao_resto(self):
        a = _anamnese()
        _, _, t = calculate_calories(a)
        m = calculate_macros(a, t)
        kcal = m['protein_g'] * 4 + m['fat_g'] * 9 + m['carbs_g'] * 4
        assert abs(kcal - t) <= 10

    def test_carboidratos_nao_negativos(self):
        a = _anamnese(120, 185, 25, 'M', 'sedentary', 'lose')
        _, _, t = calculate_calories(a)
        assert calculate_macros(a, t)['carbs_g'] >= 0

    def test_ganho_tem_mais_carboidratos(self):
        a_gain = _anamnese(goal='gain')
        a_lose = _anamnese(goal='lose')
        _, _, t_gain = calculate_calories(a_gain)
        _, _, t_lose = calculate_calories(a_lose)
        assert calculate_macros(a_gain, t_gain)['carbs_g'] > calculate_macros(a_lose, t_lose)['carbs_g']

    def test_protein_per_kg_emagrecimento(self):
        a = _anamnese(goal='lose')
        _, _, t = calculate_calories(a)
        assert calculate_macros(a, t)['protein_per_kg'] == 2.0

    def test_protein_per_kg_manutencao(self):
        a = _anamnese(goal='maintain')
        _, _, t = calculate_calories(a)
        assert calculate_macros(a, t)['protein_per_kg'] == 1.6


# ---------------------------------------------------------------------------
# build_meal_distribution_hint
# ---------------------------------------------------------------------------

class TestBuildMealDistributionHint:

    def test_3_refeicoes_inclui_3_linhas(self):
        lines = [l for l in build_meal_distribution_hint(3, 2000).strip().split('\n') if l.strip()]
        assert len(lines) == 3

    def test_6_refeicoes_inclui_6_linhas(self):
        lines = [l for l in build_meal_distribution_hint(6, 2000).strip().split('\n') if l.strip()]
        assert len(lines) == 6

    def test_nomes_em_3_refeicoes(self):
        hint = build_meal_distribution_hint(3, 2000)
        assert 'Café da manhã' in hint
        assert 'Almoço' in hint
        assert 'Jantar' in hint

    def test_calorias_somam_total(self):
        import re
        hint = build_meal_distribution_hint(3, 2000)
        vals = [int(m) for m in re.findall(r'~(\d+) kcal', hint)]
        assert abs(sum(vals) - 2000) <= 10

    def test_percentuais_somam_100(self):
        import re
        hint = build_meal_distribution_hint(4, 2000)
        pcts = [int(m) for m in re.findall(r'\((\d+)%\)', hint)]
        assert sum(pcts) == 100

    def test_refeicoes_fora_do_plano_distribuicao_uniforme(self):
        hint = build_meal_distribution_hint(7, 1400)
        lines = [l for l in hint.strip().split('\n') if l.strip()]
        assert len(lines) == 7
        assert 'Refeição 1' in hint

    def test_formato_linha_contem_kcal_e_pct(self):
        for line in build_meal_distribution_hint(3, 2100).strip().split('\n'):
            if line.strip():
                assert 'kcal' in line and '%' in line


# ---------------------------------------------------------------------------
# Banco nutricional — lookup_food_nutrition
# ---------------------------------------------------------------------------

class TestNutritionDB:

    def test_lookup_alimento_conhecido(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Frango grelhado', 100)
        assert r['calories'] > 0
        assert r['protein_g'] > 0
        assert r['carbs_g'] == 0.0

    def test_lookup_alimento_desconhecido_retorna_fallback_150kcal(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('xyzw_nunca_existira_abc123', 100)
        assert r['calories'] == 150
        assert r['_source'] == 'generic'

    def test_lookup_quantidade_zero(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Arroz branco', 0)
        assert r['calories'] == 0

    def test_lookup_proporcional_a_quantidade(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r100 = lookup_food_nutrition('Banana', 100)
        r200 = lookup_food_nutrition('Banana', 200)
        assert r200['calories'] == r100['calories'] * 2

    def test_source_exact_em_alimento_conhecido(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        assert lookup_food_nutrition('Frango grelhado', 100)['_source'] == 'exact'

    def test_source_generic_em_alimento_desconhecido(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        assert lookup_food_nutrition('zzzzz_inexistente_xxxxxxx', 100)['_source'] == 'generic'

    def test_source_invalid_em_input_vazio(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        assert lookup_food_nutrition('', 100)['_source'] == 'invalid'
        assert lookup_food_nutrition('Frango', 0)['_source'] == 'invalid'

    def test_wrap_frango_resolve_como_frango(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Wrap de frango', 200)
        assert r['protein_g'] > 0
        assert r['carbs_g'] == 0.0  # tortilha ignorada — comportamento documentado


# ---------------------------------------------------------------------------
# _recalculate_totals
# ---------------------------------------------------------------------------

class TestRecalculateTotals:

    @pytest.fixture
    def service(self):
        return AIService()

    def test_soma_calorias_de_todos_os_foods(self, service):
        data = {'meals': [
            {'foods': [
                {'calories': 300, 'protein_g': 30, 'carbs_g': 20, 'fat_g': 10},
                {'calories': 200, 'protein_g': 10, 'carbs_g': 30, 'fat_g': 5},
            ]},
            {'foods': [
                {'calories': 500, 'protein_g': 40, 'carbs_g': 50, 'fat_g': 15},
            ]},
        ]}
        r = service._recalculate_totals(data)
        assert r['calories'] == 1000
        assert r['macros']['protein_g'] == 80
        assert r['macros']['carbs_g'] == 100
        assert r['macros']['fat_g'] == 30

    def test_sobrescreve_declarado_pela_ia(self, service):
        data = {
            'calories': 9999,
            'macros': {'protein_g': 999, 'carbs_g': 999, 'fat_g': 999},
            'meals': [{'foods': [{'calories': 400, 'protein_g': 30, 'carbs_g': 50, 'fat_g': 10}]}],
        }
        r = service._recalculate_totals(data)
        assert r['calories'] == 400
        assert r['macros']['protein_g'] == 30

    def test_meals_vazia(self, service):
        r = service._recalculate_totals({'meals': []})
        assert r['calories'] == 0
        assert r['macros']['protein_g'] == 0

    def test_food_sem_calories_conta_zero(self, service):
        data = {'meals': [{'foods': [
            {'name': 'sem caloria', 'protein_g': 10, 'carbs_g': 5, 'fat_g': 2},
            {'calories': 200, 'protein_g': 20, 'carbs_g': 30, 'fat_g': 8},
        ]}]}
        assert service._recalculate_totals(data)['calories'] == 200

    def test_multiplas_refeicoes_soma_corretamente(self, service):
        data = {'meals': [
            {'foods': [{'calories': 300, 'protein_g': 30, 'carbs_g': 30, 'fat_g': 5}]},
            {'foods': [{'calories': 400, 'protein_g': 20, 'carbs_g': 60, 'fat_g': 8}]},
        ]}
        r = service._recalculate_totals(data)
        assert r['calories'] == 700
        assert r['macros']['protein_g'] == 50


# ---------------------------------------------------------------------------
# _adjust_to_calorie_target
# ---------------------------------------------------------------------------

class TestAdjustToCalorieTarget:

    @pytest.fixture
    def service(self):
        return AIService()

    def test_sem_divergencia_nao_altera(self, service):
        data = {'calories': 1800, 'meals': [{'foods': [
            {'name': 'Arroz', 'quantity_g': 100, 'calories': 900,
             'protein_g': 50, 'carbs_g': 100, 'fat_g': 20},
            {'name': 'Frango', 'quantity_g': 100, 'calories': 900,
             'protein_g': 50, 'carbs_g': 100, 'fat_g': 20},
        ]}]}
        assert service._adjust_to_calorie_target(data, 1800)['calories'] == 1800

    def test_tolerancia_9_porcento_nao_escala(self, service):
        data = {'calories': 1820, 'meals': [{'foods': [
            {'name': 'Arroz branco', 'quantity_g': 100, 'quantity_text': '100g',
             'calories': 1820, 'protein_g': 50, 'carbs_g': 200, 'fat_g': 45},
        ]}]}
        r = service._adjust_to_calorie_target(data, 2000)
        assert r['meals'][0]['foods'][0]['quantity_g'] == 100

    @patch('nutrition.services.lookup_food_nutrition')
    def test_escala_nao_proteica_sem_restricao(self, mock_lookup, service):
        mock_lookup.side_effect = lambda name, qty: {
            'calories': int(qty * 5), 'protein_g': qty * 0.25,
            'carbs_g': qty * 0.60, 'fat_g': qty * 0.10,
        }
        data = {'calories': 1000, 'meals': [{'foods': [
            {'name': 'Arroz', 'quantity_g': 100, 'quantity_text': '100g',
             'calories': 500, 'protein_g': 25, 'carbs_g': 60, 'fat_g': 10},
            {'name': 'Batata doce', 'quantity_g': 100, 'quantity_text': '100g',
             'calories': 500, 'protein_g': 25, 'carbs_g': 60, 'fat_g': 10},
        ]}]}
        r = service._adjust_to_calorie_target(data, 2000)
        assert r['calories'] == 2000

    @patch('nutrition.services.lookup_food_nutrition')
    def test_proteina_tem_cap_15pct(self, mock_lookup, service):
        mock_lookup.side_effect = lambda name, qty: {
            'calories': int(qty * 5), 'protein_g': qty * 0.25,
            'carbs_g': qty * 0.60, 'fat_g': qty * 0.10,
        }
        data = {'calories': 1000, 'meals': [{'foods': [
            {'name': 'Frango grelhado', 'quantity_g': 100, 'quantity_text': '100g',
             'calories': 1000, 'protein_g': 25, 'carbs_g': 60, 'fat_g': 10},
        ]}]}
        r = service._adjust_to_calorie_target(data, 2000)
        # scale=2, cap proteína=1.15 → 100*1.15=115g
        assert r['meals'][0]['foods'][0]['quantity_g'] == 115

    def test_target_zero_nao_altera(self, service):
        data = {'calories': 1800, 'meals': []}
        assert service._adjust_to_calorie_target(data, 0)['calories'] == 1800

    def test_calories_zero_nao_altera(self, service):
        data = {'calories': 0, 'meals': []}
        assert service._adjust_to_calorie_target(data, 1800)['calories'] == 0


# ---------------------------------------------------------------------------
# _enrich_foods_with_macros — stats por camada
# ---------------------------------------------------------------------------

class TestEnrichFoodsStats:

    @pytest.fixture
    def service(self):
        return AIService()

    def test_retorna_tupla_dict_stats(self, service):
        data = {'meals': [{'foods': [
            {'name': 'Frango grelhado', 'quantity_g': 100, 'quantity_text': '100g'},
        ]}]}
        result, stats = service._enrich_foods_with_macros(data)
        assert isinstance(stats, dict)
        assert stats['total'] == 1

    def test_stats_categoriza_exact_e_generic(self, service):
        data = {'meals': [{'foods': [
            {'name': 'Frango grelhado', 'quantity_g': 100, 'quantity_text': '100g'},
            {'name': 'zzzzzzz_inexistente_xxxxxxx', 'quantity_g': 100, 'quantity_text': '100g'},
        ]}]}
        _, stats = service._enrich_foods_with_macros(data)
        assert stats['total'] == 2
        assert stats['exact'] >= 1
        assert stats['generic'] == 1
        assert 'zzzzzzz_inexistente_xxxxxxx' in stats['generic_names']

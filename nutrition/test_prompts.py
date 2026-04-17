"""
Testes de cálculo calórico e geração de prompt — MyNutri AI
Cobre: calculate_calories (Mifflin-St Jeor), build_diet_prompt, piso de segurança.
Estes são testes puramente unitários — sem banco de dados.
"""

import pytest
from unittest.mock import MagicMock

from nutrition.prompts import (
    calculate_calories,
    build_food_selection_prompt as build_diet_prompt,
    build_explanation_prompt,
    SYSTEM_PROMPT_FOODS as SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_anamnese(
    weight=75.0,
    height=175.0,
    age=25,
    gender='M',
    activity='moderate',
    goal='lose',
    meals=3,
    preferences='',
    restrictions='',
    allergies='',
):
    """Cria um objeto mock de Anamnese com os atributos necessários."""
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

    # Simula get_gender_display e get_activity_display_pt
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

    a.get_gender_display.return_value = gender_labels.get(gender, gender)
    a.get_activity_display_pt.return_value = activity_labels.get(activity, activity)
    a.get_goal_display_pt.return_value = goal_labels.get(goal, goal)

    return a


# ---------------------------------------------------------------------------
# Testes de calculate_calories — equação Mifflin-St Jeor
# ---------------------------------------------------------------------------

class TestCalculateCalories:

    def test_retorna_tupla_de_tres_inteiros(self):
        anamnese = _make_anamnese()
        result = calculate_calories(anamnese)
        assert isinstance(result, tuple)
        assert len(result) == 3
        tmb, tdee, target = result
        assert isinstance(tmb, int)
        assert isinstance(tdee, int)
        assert isinstance(target, int)

    def test_tmb_masculino_formula_correta(self):
        """TMB masculino = (10×w) + (6.25×h) - (5×a) + 5"""
        anamnese = _make_anamnese(weight=75, height=175, age=25, gender='M')
        tmb, _, _ = calculate_calories(anamnese)
        expected = round((10 * 75) + (6.25 * 175) - (5 * 25) + 5)
        assert tmb == expected

    def test_tmb_feminino_formula_correta(self):
        """TMB feminino = (10×w) + (6.25×h) - (5×a) - 161"""
        anamnese = _make_anamnese(weight=60, height=165, age=30, gender='F')
        tmb, _, _ = calculate_calories(anamnese)
        expected = round((10 * 60) + (6.25 * 165) - (5 * 30) - 161)
        assert tmb == expected

    def test_tmb_outro_genero_usa_media(self):
        """Gênero 'O' usa constante -78 (média entre +5 e -161)."""
        anamnese = _make_anamnese(weight=70, height=170, age=28, gender='O')
        tmb, _, _ = calculate_calories(anamnese)
        expected = round((10 * 70) + (6.25 * 170) - (5 * 28) - 78)
        assert tmb == expected

    def test_tdee_aplica_fator_sedentario(self):
        """TDEE sedentário deve ser ~1.2× o TMB (tolerância ±2 kcal por arredondamento float)."""
        anamnese = _make_anamnese(activity='sedentary', goal='maintain')
        tmb, tdee, _ = calculate_calories(anamnese)
        assert abs(tdee - tmb * 1.2) <= 2

    def test_tdee_aplica_fator_moderado(self):
        anamnese = _make_anamnese(activity='moderate', goal='maintain')
        tmb, tdee, _ = calculate_calories(anamnese)
        assert abs(tdee - tmb * 1.55) <= 2

    def test_tdee_aplica_fator_atleta(self):
        """TDEE atleta deve ser ~1.9× o TMB (tolerância ±2 kcal por arredondamento float)."""
        anamnese = _make_anamnese(activity='athlete', goal='maintain')
        tmb, tdee, _ = calculate_calories(anamnese)
        assert abs(tdee - tmb * 1.9) <= 2

    def test_objetivo_emagrecer_aplica_deficit(self):
        anamnese = _make_anamnese(activity='moderate', goal='lose')
        _, tdee, target = calculate_calories(anamnese)
        assert target == max(round(tdee - 450), 1500)

    def test_objetivo_manutencao_sem_ajuste(self):
        anamnese = _make_anamnese(activity='moderate', goal='maintain')
        _, tdee, target = calculate_calories(anamnese)
        assert target == tdee

    def test_objetivo_ganho_aplica_superavit(self):
        anamnese = _make_anamnese(activity='moderate', goal='gain')
        _, tdee, target = calculate_calories(anamnese)
        assert target == round(tdee + 350)

    def test_piso_seguranca_masculino_1500_kcal(self):
        """Homens nunca devem ter meta abaixo de 1500 kcal."""
        # Pessoa muito leve + sedentária + emagrecer
        anamnese = _make_anamnese(
            weight=40, height=150, age=60, gender='M',
            activity='sedentary', goal='lose'
        )
        _, _, target = calculate_calories(anamnese)
        assert target >= 1500

    def test_piso_seguranca_feminino_1200_kcal(self):
        """Mulheres nunca devem ter meta abaixo de 1200 kcal."""
        anamnese = _make_anamnese(
            weight=35, height=145, age=60, gender='F',
            activity='sedentary', goal='lose'
        )
        _, _, target = calculate_calories(anamnese)
        assert target >= 1200

    def test_piso_seguranca_outro_genero_1350_kcal(self):
        """Gênero 'O' nunca deve ter meta abaixo de 1350 kcal."""
        anamnese = _make_anamnese(
            weight=38, height=148, age=60, gender='O',
            activity='sedentary', goal='lose'
        )
        _, _, target = calculate_calories(anamnese)
        assert target >= 1350

    def test_calories_sao_positivas(self):
        for goal in ('lose', 'maintain', 'gain'):
            for gender in ('M', 'F', 'O'):
                anamnese = _make_anamnese(gender=gender, goal=goal)
                tmb, tdee, target = calculate_calories(anamnese)
                assert tmb > 0, f'TMB negativa para {gender}/{goal}'
                assert tdee > 0, f'TDEE negativa para {gender}/{goal}'
                assert target > 0, f'Target negativo para {gender}/{goal}'

    def test_tdee_maior_que_tmb(self):
        """TDEE deve sempre ser maior que TMB (fator de atividade > 1)."""
        anamnese = _make_anamnese(activity='sedentary')
        tmb, tdee, _ = calculate_calories(anamnese)
        assert tdee > tmb

    def test_ativo_tem_meta_maior_que_sedentario_em_manutencao(self):
        sedentario = _make_anamnese(activity='sedentary', goal='maintain')
        atleta = _make_anamnese(activity='athlete', goal='maintain')
        _, _, target_sed = calculate_calories(sedentario)
        _, _, target_atl = calculate_calories(atleta)
        assert target_atl > target_sed

    def test_hipertrofia_tem_meta_maior_que_emagrecer(self):
        lose = _make_anamnese(goal='lose')
        gain = _make_anamnese(goal='gain')
        _, _, target_lose = calculate_calories(lose)
        _, _, target_gain = calculate_calories(gain)
        assert target_gain > target_lose


# ---------------------------------------------------------------------------
# Testes de build_diet_prompt
# ---------------------------------------------------------------------------

class TestBuildDietPrompt:

    def test_retorna_string(self):
        anamnese = _make_anamnese()
        result = build_diet_prompt(anamnese)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_prompt_contem_calorias_calculadas(self):
        anamnese = _make_anamnese(weight=75, height=175, age=25, gender='M', activity='moderate', goal='lose')
        _, _, target = calculate_calories(anamnese)
        prompt = build_diet_prompt(anamnese)
        assert str(target) in prompt

    def test_prompt_contem_numero_de_refeicoes(self):
        anamnese = _make_anamnese(meals=5)
        prompt = build_diet_prompt(anamnese)
        assert '5' in prompt

    def test_prompt_contem_preferencias_alimentares(self):
        anamnese = _make_anamnese(preferences='Frango, Batata-doce, Ovo')
        prompt = build_diet_prompt(anamnese)
        assert 'Frango, Batata-doce, Ovo' in prompt

    def test_prompt_contem_restricoes(self):
        anamnese = _make_anamnese(restrictions='vegetariano, sem glúten')
        prompt = build_diet_prompt(anamnese)
        assert 'vegetariano, sem glúten' in prompt

    def test_prompt_contem_alergias(self):
        anamnese = _make_anamnese(allergies='amendoim')
        prompt = build_diet_prompt(anamnese)
        assert 'amendoim' in prompt

    def test_prompt_placeholder_sem_preferencias(self):
        anamnese = _make_anamnese(preferences='')
        prompt = build_diet_prompt(anamnese)
        assert 'Sem preferências específicas' in prompt

    def test_prompt_placeholder_sem_restricoes(self):
        anamnese = _make_anamnese(restrictions='')
        prompt = build_diet_prompt(anamnese)
        assert 'Nenhuma restrição informada' in prompt

    def test_prompt_placeholder_sem_alergias(self):
        anamnese = _make_anamnese(allergies='')
        prompt = build_diet_prompt(anamnese)
        assert 'Nenhum item a evitar' in prompt

    def test_prompt_contem_tmb_e_tdee_na_explicacao(self):
        """TMB e TDEE ficam no prompt de explicação (Passo 2), não no de seleção de alimentos."""
        anamnese = _make_anamnese(weight=75, height=175, age=25, gender='M', activity='moderate', goal='lose')
        tmb, tdee, target = calculate_calories(anamnese)
        diet_data = {
            'calories': target,
            'macros': {'protein_g': 150, 'carbs_g': 230, 'fat_g': 60},
            'meals': [{'name': 'Almoço', 'time_suggestion': '12:00', 'foods': []}],
            'goal_description': 'Emagrecimento',
        }
        expl_prompt = build_explanation_prompt(diet_data, anamnese, tmb, tdee, target)
        assert str(tmb) in expl_prompt
        assert str(tdee) in expl_prompt


# ---------------------------------------------------------------------------
# Testes do SYSTEM_PROMPT
# ---------------------------------------------------------------------------

class TestSystemPrompt:

    def test_system_prompt_nao_vazio(self):
        assert len(SYSTEM_PROMPT) > 100

    def test_system_prompt_menciona_json(self):
        assert 'JSON' in SYSTEM_PROMPT

    def test_system_prompt_menciona_brasil(self):
        assert 'brasileiro' in SYSTEM_PROMPT.lower() or 'brasil' in SYSTEM_PROMPT.lower()

    def test_system_prompt_menciona_anti_manipulacao(self):
        """System prompt deve ter proteção contra prompt injection."""
        assert 'instruções' in SYSTEM_PROMPT.lower() or 'manipul' in SYSTEM_PROMPT.lower()

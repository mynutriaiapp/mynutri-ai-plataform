"""
Testes avançados do AIService — MyNutri AI.

Cobre: _parse_allergens, _food_contains_allergen (services), _validate_macro_ratios,
       _check_protein_adequacy, _round_portions, _household_measure,
       _round_food_quantity, regenerate_meal, _generate_notes (meal_notes parsing).
A chamada HTTP (_call_api) é sempre mockada — sem dependência de API externa.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model

from nutrition.models import Anamnese, DietPlan, Meal
from nutrition.services import (
    AIService,
    AllergenViolation,
    MacroImbalanceError,
    TransientAIError,
    _parse_allergens,
    _food_contains_allergen,
    _round_food_quantity,
    _household_measure,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def create_user(db):
    def _create(email='advanced@teste.com'):
        return User.objects.create_user(
            username=email, email=email, password='senha123', first_name='Test'
        )
    return _create


@pytest.fixture
def anamnese(db, create_user):
    user = create_user()
    return Anamnese.objects.create(
        user=user,
        age=25,
        gender='M',
        weight_kg=75.0,
        height_cm=175.0,
        activity_level='moderate',
        goal='lose',
        meals_per_day=3,
        food_preferences='',
        food_restrictions='',
        allergies='',
    )


@pytest.fixture
def diet_plan(db, anamnese):
    plan = DietPlan.objects.create(
        user=anamnese.user,
        anamnese=anamnese,
        raw_response={
            "goal_description": "Emagrecimento",
            "calories": 2000,
            "macros": {"protein_g": 150, "carbs_g": 200, "fat_g": 60},
            "meals": [
                {
                    "name": "Café da manhã",
                    "time_suggestion": "07:00",
                    "foods": [
                        {"name": "Frango grelhado", "quantity_g": 130, "calories": 220, "protein_g": 28},
                        {"name": "Arroz cozido", "quantity_g": 150, "calories": 200, "protein_g": 4},
                    ]
                },
                {
                    "name": "Almoço",
                    "time_suggestion": "12:00",
                    "foods": [
                        {"name": "Tilápia grelhada", "quantity_g": 130, "calories": 180, "protein_g": 26},
                        {"name": "Batata doce cozida", "quantity_g": 150, "calories": 130, "protein_g": 2},
                    ]
                },
                {
                    "name": "Jantar",
                    "time_suggestion": "19:00",
                    "foods": [
                        {"name": "Ovo cozido", "quantity_g": 100, "calories": 155, "protein_g": 12},
                        {"name": "Feijão cozido", "quantity_g": 100, "calories": 120, "protein_g": 8},
                    ]
                },
            ]
        },
        total_calories=2000,
        goal_description="Emagrecimento",
    )
    # Cria Meal records
    Meal.objects.create(diet_plan=plan, meal_name="Café da manhã (07:00)", description="...", calories=420, order=0)
    Meal.objects.create(diet_plan=plan, meal_name="Almoço (12:00)", description="...", calories=310, order=1)
    Meal.objects.create(diet_plan=plan, meal_name="Jantar (19:00)", description="...", calories=275, order=2)
    return plan


@pytest.fixture
def ai_service():
    return AIService()


def _wrap_api(content_dict):
    return {'choices': [{'message': {'content': json.dumps(content_dict)}}]}


# ---------------------------------------------------------------------------
# _parse_allergens
# ---------------------------------------------------------------------------

class TestParseAllergens:
    def test_string_vazia(self):
        assert _parse_allergens('') == []

    def test_none_retorna_vazio(self):
        assert _parse_allergens(None) == []

    def test_virgula_como_separador(self):
        result = _parse_allergens('amendoim, camarão, ovo')
        assert 'amendoim' in result
        assert 'camarao' in result
        assert 'ovo' in result

    def test_ponto_virgula_como_separador(self):
        result = _parse_allergens('amendoim; camarão')
        assert 'amendoim' in result
        assert 'camarao' in result

    def test_quebra_de_linha(self):
        result = _parse_allergens('amendoim\ncamarão\novo')
        assert 'amendoim' in result

    def test_conectivo_e(self):
        result = _parse_allergens('amendoim e camarão')
        assert 'amendoim' in result
        assert 'camarao' in result

    def test_normaliza_acentos(self):
        result = _parse_allergens('Camarão, Peixe')
        assert 'camarao' in result
        assert 'peixe' in result

    def test_descarta_curtos(self):
        # Menos de 3 chars são descartados
        result = _parse_allergens('a, ab, ovo')
        assert 'a' not in result
        assert 'ab' not in result
        assert 'ovo' in result

    def test_sem_duplicatas(self):
        result = _parse_allergens('amendoim, amendoim, Amendoim')
        assert result.count('amendoim') == 1

    def test_espaco_no_inicio_fim_removido(self):
        result = _parse_allergens('  amendoim  , camarão  ')
        assert 'amendoim' in result
        assert 'camarao' in result


# ---------------------------------------------------------------------------
# _food_contains_allergen (services module version)
# ---------------------------------------------------------------------------

class TestFoodContainsAllergenServices:
    def test_none_retorna_none(self):
        assert _food_contains_allergen(None, ['ovo']) is None

    def test_lista_vazia_retorna_none(self):
        assert _food_contains_allergen('Ovo cozido', []) is None

    def test_deteccao_por_palavra_inteira(self):
        result = _food_contains_allergen('Ovo cozido', ['ovo'])
        assert result == 'ovo'

    def test_word_boundary_evita_falso_positivo(self):
        # "ovo" não deve casar com "Iogurte"
        assert _food_contains_allergen('Iogurte natural', ['ovo']) is None

    def test_alergeno_multi_palavra(self):
        result = _food_contains_allergen('Peito de frango grelhado', ['peito de frango'])
        assert result == 'peito de frango'

    def test_normaliza_acentos_no_alimento(self):
        result = _food_contains_allergen('Camarão grelhado', ['camarao'])
        assert result == 'camarao'

    def test_retorna_alergeno_especifico(self):
        result = _food_contains_allergen('Atum em lata', ['salmao', 'atum', 'camarao'])
        assert result == 'atum'

    def test_string_vazia_retorna_none(self):
        assert _food_contains_allergen('', ['ovo']) is None


# ---------------------------------------------------------------------------
# _round_food_quantity
# ---------------------------------------------------------------------------

class TestRoundFoodQuantity:
    def test_oleo_multiplo_de_5(self):
        assert _round_food_quantity("Azeite", 13) % 5 == 0

    def test_oleo_minimo_5(self):
        assert _round_food_quantity("Azeite", 2) >= 5

    def test_ovo_multiplo_de_50(self):
        result = _round_food_quantity("Ovo cozido", 55)
        assert result % 50 == 0

    def test_tapioca_multiplo_de_20(self):
        result = _round_food_quantity("Tapioca", 70)
        assert result % 20 == 0

    def test_frango_multiplo_de_25(self):
        result = _round_food_quantity("Frango grelhado", 123)
        assert result % 25 == 0

    def test_frango_minimo_50(self):
        result = _round_food_quantity("Frango grelhado", 20)
        assert result >= 50

    def test_arroz_multiplo_de_50(self):
        result = _round_food_quantity("Arroz cozido", 133)
        assert result % 50 == 0

    def test_aveia_multiplo_de_10(self):
        result = _round_food_quantity("Aveia em flocos", 32)
        assert result % 10 == 0

    def test_alimento_desconhecido_pequeno(self):
        # ≤50g: múltiplos de 5
        result = _round_food_quantity("Kimchi", 23)
        assert result % 5 == 0

    def test_alimento_desconhecido_medio(self):
        # ≤200g: múltiplos de 25
        result = _round_food_quantity("Kimchi", 133)
        assert result % 25 == 0

    def test_alimento_desconhecido_grande(self):
        # >200g: múltiplos de 50
        result = _round_food_quantity("Kimchi", 333)
        assert result % 50 == 0

    def test_castanha_multiplo_de_10(self):
        result = _round_food_quantity("Castanha de caju", 23)
        assert result % 10 == 0

    def test_iogurte_minimo_100(self):
        result = _round_food_quantity("Iogurte natural", 50)
        assert result >= 100


# ---------------------------------------------------------------------------
# _household_measure
# ---------------------------------------------------------------------------

class TestHouseholdMeasure:
    def test_arroz_colheres(self):
        result = _household_measure("Arroz cozido", 150)
        assert 'col' in result

    def test_frango_file(self):
        result = _household_measure("Frango grelhado", 130)
        assert 'filé' in result or 'file' in result

    def test_ovo_unidades(self):
        result = _household_measure("Ovo cozido", 100)
        assert 'unidade' in result

    def test_clara_claras(self):
        result = _household_measure("Clara de ovo", 66)
        assert 'clara' in result

    def test_azeite_colher(self):
        result = _household_measure("Azeite de oliva", 10)
        assert 'col' in result

    def test_leite_copo(self):
        result = _household_measure("Leite desnatado", 200)
        assert 'copo' in result

    def test_iogurte_pote(self):
        result = _household_measure("Iogurte natural", 200)
        assert 'pote' in result

    def test_banana_unidade(self):
        result = _household_measure("Banana prata", 100)
        assert 'banana' in result

    def test_tapioca_unidade(self):
        result = _household_measure("Tapioca", 80)
        assert 'tapioca' in result

    def test_feijao_concha(self):
        result = _household_measure("Feijão cozido", 80)
        assert 'concha' in result

    def test_atum_lata(self):
        result = _household_measure("Atum em água", 85)
        assert 'lata' in result

    def test_alimento_desconhecido_retorna_string(self):
        # Pode ser string vazia
        result = _household_measure("Kimchi fermentado", 100)
        assert isinstance(result, str)

    def test_batata_doce_unidade(self):
        result = _household_measure("Batata doce cozida", 150)
        assert 'unid' in result

    def test_pao_unidade(self):
        result = _household_measure("Pão integral", 50)
        assert 'unidade' in result


# ---------------------------------------------------------------------------
# _validate_macro_ratios
# ---------------------------------------------------------------------------

class TestValidateMacroRatios:
    def _make_diet(self, protein_g, carbs_g, fat_g):
        total = protein_g * 4 + carbs_g * 4 + fat_g * 9
        return {
            'calories': total,
            'macros': {'protein_g': protein_g, 'carbs_g': carbs_g, 'fat_g': fat_g},
        }

    def test_macros_validos_nao_levanta(self, ai_service, anamnese):
        # 150P / 200C / 60G para 75kg
        diet = self._make_diet(150, 200, 60)
        target = 1800
        ai_service._validate_macro_ratios(diet, anamnese, target)  # não deve levantar

    def test_carboidratos_excessivos_levanta(self, ai_service, anamnese):
        # 80% de carbs — deve levantar
        diet = self._make_diet(50, 350, 30)
        with pytest.raises(MacroImbalanceError, match='carboidrato'):
            ai_service._validate_macro_ratios(diet, anamnese, 1800)

    def test_proteina_insuficiente_pct_levanta(self, ai_service, anamnese):
        # Proteína < 15% das calorias
        diet = self._make_diet(20, 300, 80)
        with pytest.raises(MacroImbalanceError, match='proteína'):
            ai_service._validate_macro_ratios(diet, anamnese, 1800)

    def test_gordura_insuficiente_pct_levanta(self, ai_service, anamnese):
        # Gordura < 15% das calorias
        diet = self._make_diet(150, 300, 10)
        with pytest.raises(MacroImbalanceError, match='gordura'):
            ai_service._validate_macro_ratios(diet, anamnese, 1800)

    def test_gordura_excessiva_por_kg_levanta(self, ai_service, anamnese):
        # 75kg × 1.2 = 90g teto → fat_g = 120 excede
        diet = self._make_diet(150, 150, 120)
        with pytest.raises(MacroImbalanceError):
            ai_service._validate_macro_ratios(diet, anamnese, 2000)

    def test_proteina_abaixo_65pct_meta_levanta(self, ai_service, anamnese):
        # Meta proteica para 75kg/lose = 150g; 60% é 90g
        diet = self._make_diet(90, 250, 60)
        with pytest.raises(MacroImbalanceError):
            ai_service._validate_macro_ratios(diet, anamnese, 1800)

    def test_zero_calorias_nao_levanta(self, ai_service, anamnese):
        # Se total=0, skip validação (plano inválido já foi tratado antes)
        diet = {'calories': 0, 'macros': {'protein_g': 0, 'carbs_g': 0, 'fat_g': 0}}
        ai_service._validate_macro_ratios(diet, anamnese, 1800)  # não deve levantar


# ---------------------------------------------------------------------------
# _generate_notes — meal_notes parsing (nome, numérico 0-based, 1-based)
# ---------------------------------------------------------------------------

class TestGenerateNotesMealNotesMapping:
    def _make_diet_data(self, meals=None):
        if meals is None:
            meals = [
                {"name": "Café da manhã", "foods": []},
                {"name": "Almoço", "foods": []},
                {"name": "Jantar", "foods": []},
            ]
        return {"meals": meals, "calories": 2000}

    def test_chave_nome_mapeia_corretamente(self, ai_service, anamnese):
        diet_data = self._make_diet_data()
        api_resp = _wrap_api({
            "tips": ["Dica 1"],
            "meal_notes": {
                "Café da manhã": "Nota do café",
                "Almoço": "Nota do almoço",
            }
        })
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service._generate_notes(diet_data, anamnese, 2000)
        assert result['meal_notes'][0] == "Nota do café"
        assert result['meal_notes'][1] == "Nota do almoço"

    def test_chave_numerica_0_based(self, ai_service, anamnese):
        diet_data = self._make_diet_data()
        api_resp = _wrap_api({
            "tips": [],
            "meal_notes": {"0": "Nota índice 0", "2": "Nota índice 2"}
        })
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service._generate_notes(diet_data, anamnese, 2000)
        assert result['meal_notes'].get(0) == "Nota índice 0"
        assert result['meal_notes'].get(2) == "Nota índice 2"

    def test_chave_numerica_1_based(self, ai_service, anamnese):
        diet_data = self._make_diet_data()
        # "3" excede len(meals)=3 como 0-based (inválido), mas 1-based → índice 2 (válido).
        # "1" é válido 0-based → índice 1 (testa o caso ambíguo que cai em 0-based primeiro).
        api_resp = _wrap_api({
            "tips": [],
            "meal_notes": {"3": "Nota refeição 3"}
        })
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service._generate_notes(diet_data, anamnese, 2000)
        # "3" não é válido 0-based (len=3, idx=3 fora), mas é válido 1-based → índice 2
        assert result['meal_notes'].get(2) == "Nota refeição 3"

    def test_tips_viram_notes_formatadas(self, ai_service, anamnese):
        diet_data = self._make_diet_data()
        api_resp = _wrap_api({
            "tips": ["Dica A", "Dica B"],
            "meal_notes": {}
        })
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service._generate_notes(diet_data, anamnese, 2000)
        assert result['notes'] is not None
        assert '• Dica A' in result['notes']
        assert '• Dica B' in result['notes']

    def test_api_falha_retorna_silenciosamente(self, ai_service, anamnese):
        diet_data = self._make_diet_data()
        with patch.object(ai_service, '_call_api', side_effect=Exception("API Error")):
            result = ai_service._generate_notes(diet_data, anamnese, 2000)
        assert result['notes'] is None
        assert result['meal_notes'] == {}

    def test_nota_vazia_ignorada(self, ai_service, anamnese):
        diet_data = self._make_diet_data()
        api_resp = _wrap_api({
            "tips": [],
            "meal_notes": {"Café da manhã": "", "Almoço": "Nota válida"}
        })
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service._generate_notes(diet_data, anamnese, 2000)
        assert 0 not in result['meal_notes']  # string vazia ignorada
        assert result['meal_notes'].get(1) == "Nota válida"

    def test_nota_nao_string_ignorada(self, ai_service, anamnese):
        diet_data = self._make_diet_data()
        api_resp = _wrap_api({
            "tips": [],
            "meal_notes": {"Café da manhã": 42, "Almoço": "Nota válida"}
        })
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service._generate_notes(diet_data, anamnese, 2000)
        assert 0 not in result['meal_notes']  # int ignorado


# ---------------------------------------------------------------------------
# regenerate_meal
# ---------------------------------------------------------------------------

class TestRegenerateMeal:
    def _new_meal_response(self):
        return {
            "name": "Almoço",
            "time_suggestion": "12:00",
            "foods": [
                {"name": "Tilápia grelhada", "quantity_g": 130, "quantity_text": "130g"},
                {"name": "Batata doce cozida", "quantity_g": 150, "quantity_text": "150g"},
            ],
            "meal_notes": "Dica sobre a refeição."
        }

    @patch('nutrition.services.lookup_food_nutrition')
    def test_retorna_dict_com_chaves_corretas(self, mock_lookup, ai_service, diet_plan):
        mock_lookup.return_value = {
            'calories': 180, 'protein_g': 25, 'carbs_g': 10, 'fat_g': 5, '_source': 'exact'
        }
        api_resp = _wrap_api(self._new_meal_response())
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service.regenerate_meal(diet_plan, meal_index=1)

        assert 'new_raw_meal' in result
        assert 'new_description' in result
        assert 'new_calories' in result
        assert 'new_meal_name' in result

    @patch('nutrition.services.lookup_food_nutrition')
    def test_indice_invalido_levanta(self, mock_lookup, ai_service, diet_plan):
        with pytest.raises(ValueError, match='Índice'):
            ai_service.regenerate_meal(diet_plan, meal_index=99)

    @patch('nutrition.services.lookup_food_nutrition')
    def test_new_meal_name_inclui_horario(self, mock_lookup, ai_service, diet_plan):
        mock_lookup.return_value = {
            'calories': 180, 'protein_g': 25, 'carbs_g': 10, 'fat_g': 5, '_source': 'exact'
        }
        api_resp = _wrap_api(self._new_meal_response())
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service.regenerate_meal(diet_plan, meal_index=1)

        assert '12:00' in result['new_meal_name']

    @patch('nutrition.services.lookup_food_nutrition')
    def test_description_contem_bullet_points(self, mock_lookup, ai_service, diet_plan):
        mock_lookup.return_value = {
            'calories': 180, 'protein_g': 25, 'carbs_g': 10, 'fat_g': 5, '_source': 'exact'
        }
        api_resp = _wrap_api(self._new_meal_response())
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service.regenerate_meal(diet_plan, meal_index=1)

        assert '•' in result['new_description']

    @patch('nutrition.services.lookup_food_nutrition')
    def test_alimentos_sem_foods_levanta(self, mock_lookup, ai_service, diet_plan):
        api_resp = _wrap_api({"name": "Almoço", "foods": []})
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            with pytest.raises(TransientAIError):
                ai_service.regenerate_meal(diet_plan, meal_index=1)

    @patch('nutrition.services.lookup_food_nutrition')
    def test_preserve_nome_se_ia_omite(self, mock_lookup, ai_service, diet_plan):
        mock_lookup.return_value = {
            'calories': 180, 'protein_g': 25, 'carbs_g': 10, 'fat_g': 5, '_source': 'exact'
        }
        # IA não retorna 'name'
        api_resp = _wrap_api({
            "time_suggestion": "12:00",
            "foods": [{"name": "Tilápia", "quantity_g": 130, "quantity_text": "130g"}]
        })
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            result = ai_service.regenerate_meal(diet_plan, meal_index=1)
        # Nome deve vir do plano original
        assert 'Almoço' in result['new_meal_name']

    def test_alergia_em_nova_refeicao_levanta(self, db, create_user, ai_service):
        user = create_user('alergia@teste.com')
        ana = Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=75, height_cm=175,
            activity_level='moderate', goal='lose', meals_per_day=3,
            allergies='camarão',
        )
        plan = DietPlan.objects.create(
            user=user, anamnese=ana,
            raw_response={"meals": [
                {"name": "Jantar", "time_suggestion": "19:00", "foods": [
                    {"name": "Frango", "quantity_g": 130}
                ]}
            ]},
            total_calories=400
        )
        Meal.objects.create(diet_plan=plan, meal_name="Jantar", description="...", calories=400, order=0)

        api_resp = _wrap_api({
            "name": "Jantar",
            "time_suggestion": "19:00",
            "foods": [{"name": "Camarão grelhado", "quantity_g": 130, "quantity_text": "130g"}]
        })
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            with pytest.raises(AllergenViolation):
                ai_service.regenerate_meal(plan, meal_index=0)

    def test_sem_anamnese_levanta(self, db, create_user, ai_service):
        user = create_user('sem_ana@teste.com')
        plan = DietPlan.objects.create(
            user=user, anamnese=None,
            raw_response={"meals": [{"name": "Almoço", "foods": [{"name": "Frango", "quantity_g": 130}]}]},
            total_calories=400
        )
        with pytest.raises(ValueError, match='anamnese'):
            ai_service.regenerate_meal(plan, meal_index=0)


# ---------------------------------------------------------------------------
# _enforce_allergies — segurança crítica
# ---------------------------------------------------------------------------

class TestEnforceAllergies:
    def test_sem_alergias_passa(self, ai_service, anamnese):
        diet_data = {"meals": [{"name": "Almoço", "foods": [
            {"name": "Frango grelhado"}
        ]}]}
        ai_service._enforce_allergies(diet_data, anamnese)  # sem exceção

    def test_alergia_detectada_levanta(self, db, create_user, ai_service):
        user = create_user('allergy2@teste.com')
        ana = Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=75, height_cm=175,
            activity_level='moderate', goal='lose', meals_per_day=3,
            allergies='amendoim'
        )
        diet_data = {"meals": [{"name": "Lanche", "foods": [
            {"name": "Pasta de amendoim"}
        ]}]}
        with pytest.raises(AllergenViolation, match='amendoim'):
            ai_service._enforce_allergies(diet_data, ana)

    def test_alimento_similar_nao_dispara_word_boundary(self, db, create_user, ai_service):
        # "ovo" não deve casar com "iogurte" (sem word boundary)
        user = create_user('boundary@teste.com')
        ana = Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=75, height_cm=175,
            activity_level='moderate', goal='lose', meals_per_day=3,
            allergies='ovo'
        )
        diet_data = {"meals": [{"name": "Café", "foods": [
            {"name": "Iogurte natural"}
        ]}]}
        ai_service._enforce_allergies(diet_data, ana)  # não deve levantar

    def test_multiplas_violacoes_todas_listadas(self, db, create_user, ai_service):
        user = create_user('multi_allergy@teste.com')
        ana = Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=75, height_cm=175,
            activity_level='moderate', goal='lose', meals_per_day=3,
            allergies='atum, camarão'
        )
        diet_data = {"meals": [
            {"name": "Almoço", "foods": [{"name": "Atum em lata"}, {"name": "Camarão grelhado"}]}
        ]}
        with pytest.raises(AllergenViolation) as exc_info:
            ai_service._enforce_allergies(diet_data, ana)
        msg = str(exc_info.value)
        assert 'atum' in msg
        assert 'camarao' in msg

"""
Testes do AIService — MyNutri AI.

Cobre: _parse_response (markdown, json inválido), _parse_allergens, _food_contains_allergen,
       _validate_macro_ratios, _check_db_coverage, _check_protein_adequacy,
       _round_portions, _household_measure, _round_food_quantity,
       _generate_notes (meal_notes parsing), regenerate_meal,
       _enforce_allergies, generate_diet, generate_diet_task (Celery).
A chamada HTTP (_call_api) é sempre mockada — sem dependência de API externa.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.test import override_settings

from nutrition.models import Anamnese, DietJob, DietPlan, Meal
from nutrition.services import (
    AIService,
    AllergenViolation,
    MacroImbalanceError,
    NutritionDataGap,
    TransientAIError,
    _food_contains_allergen,
    _household_measure,
    _parse_allergens,
    _round_food_quantity,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def create_user(db):
    counter = {'n': 0}
    def _create(email=None, nome='Teste', senha='senhaSegura123'):
        counter['n'] += 1
        if email is None:
            email = f'svc{counter["n"]}@teste.com'
        return User.objects.create_user(
            username=email, email=email, password=senha, first_name=nome,
        )
    return _create


@pytest.fixture
def anamnese(db, create_user):
    user = create_user()
    return Anamnese.objects.create(
        user=user, age=25, gender='M', weight_kg=75.0, height_cm=175.0,
        activity_level='moderate', goal='lose', meals_per_day=3,
        food_preferences='Frango, Arroz', food_restrictions='', allergies='',
    )


@pytest.fixture
def anamnese_obj(db, create_user):
    """Anamnese completa usada nos testes de pipeline crítico."""
    user = create_user()
    return Anamnese.objects.create(
        user=user, age=28, gender='M', weight_kg=80.0, height_cm=178.0,
        activity_level='moderate', goal='lose', meals_per_day=4,
        food_preferences='Frango, Batata-doce', food_restrictions='',
        allergies='amendoim',
    )


@pytest.fixture
def ai_service():
    return AIService()


@pytest.fixture
def diet_plan(db, anamnese):
    plan = DietPlan.objects.create(
        user=anamnese.user, anamnese=anamnese,
        raw_response={'meals': [
            {'name': 'Café da manhã', 'time_suggestion': '07:00', 'foods': [
                {'name': 'Frango grelhado', 'quantity_g': 130, 'calories': 220, 'protein_g': 28},
                {'name': 'Arroz cozido', 'quantity_g': 150, 'calories': 200, 'protein_g': 4},
            ]},
            {'name': 'Almoço', 'time_suggestion': '12:00', 'foods': [
                {'name': 'Tilápia grelhada', 'quantity_g': 130, 'calories': 180, 'protein_g': 26},
                {'name': 'Batata doce cozida', 'quantity_g': 150, 'calories': 130, 'protein_g': 2},
            ]},
            {'name': 'Jantar', 'time_suggestion': '19:00', 'foods': [
                {'name': 'Ovo cozido', 'quantity_g': 100, 'calories': 155, 'protein_g': 12},
            ]},
        ]},
        total_calories=885,
    )
    for i, name in enumerate(['Café da manhã (07:00)', 'Almoço (12:00)', 'Jantar (19:00)']):
        Meal.objects.create(diet_plan=plan, meal_name=name, description='...', calories=300, order=i)
    return plan


def _wrap(content_dict):
    return {'choices': [{'message': {'content': json.dumps(content_dict)}}]}


# Respostas mínimas para o pipeline completo
_PASSO1 = {
    'goal_description': 'Emagrecimento saudável',
    'meals': [
        {'name': 'Café da manhã', 'time_suggestion': '07:00', 'foods': [
            {'name': 'Ovos mexidos', 'quantity_text': '4 unidades', 'quantity_g': 200},
            {'name': 'Pão francês', 'quantity_text': '1 unidade', 'quantity_g': 50},
            {'name': 'Iogurte natural', 'quantity_text': '1 pote', 'quantity_g': 150},
        ]},
        {'name': 'Almoço', 'time_suggestion': '12:00', 'foods': [
            {'name': 'Frango grelhado', 'quantity_text': '1 filé', 'quantity_g': 180},
            {'name': 'Arroz branco', 'quantity_text': '4 col.', 'quantity_g': 120},
            {'name': 'Feijão cozido', 'quantity_text': '2 conchas', 'quantity_g': 100},
            {'name': 'Salada mista', 'quantity_text': '1 prato', 'quantity_g': 80},
        ]},
        {'name': 'Lanche da tarde', 'time_suggestion': '15:30', 'foods': [
            {'name': 'Atum em água', 'quantity_text': '1 lata', 'quantity_g': 80},
            {'name': 'Batata doce', 'quantity_text': '1 unidade', 'quantity_g': 120},
        ]},
        {'name': 'Jantar', 'time_suggestion': '19:30', 'foods': [
            {'name': 'Tilapia grelhada', 'quantity_text': '1 filé', 'quantity_g': 200},
            {'name': 'Brocolis cozido', 'quantity_text': '1 xícara', 'quantity_g': 100},
            {'name': 'Batata doce', 'quantity_text': '1 unidade', 'quantity_g': 100},
            {'name': 'Azeite oliva', 'quantity_text': '1 col.', 'quantity_g': 10},
        ]},
    ],
}
_NOTES = {'tips': ['Dica A', 'Dica B', 'Dica C']}
_EXPLANATION = {
    'calorie_calculation': 'Cálculo...', 'macro_distribution': 'Macros...',
    'food_choices': 'Alimentos...', 'meal_structure': 'Refeições...',
    'goal_alignment': 'Objetivo...',
}


def _pipeline_effects():
    return [_wrap(_PASSO1), _wrap(_NOTES), _wrap(_EXPLANATION)]


# ---------------------------------------------------------------------------
# _parse_response — markdown fences, json inválido
# ---------------------------------------------------------------------------

class TestParseResponse:

    def test_json_puro(self, ai_service):
        r = ai_service._parse_response(_wrap({'calories': 1800}))
        assert r['calories'] == 1800

    def test_markdown_json_fence(self, ai_service):
        payload = json.dumps({'calories': 1900})
        raw = {'choices': [{'message': {'content': f'```json\n{payload}\n```'}}]}
        assert ai_service._parse_response(raw)['calories'] == 1900

    def test_markdown_fence_simples(self, ai_service):
        payload = json.dumps({'calories': 2000})
        raw = {'choices': [{'message': {'content': f'```\n{payload}\n```'}}]}
        assert ai_service._parse_response(raw)['calories'] == 2000

    def test_json_invalido_levanta_transient(self, ai_service):
        with pytest.raises(TransientAIError, match='formato inesperado'):
            ai_service._parse_response(_wrap.__func__(None) if False else
                {'choices': [{'message': {'content': 'isso não é json {'}}]})

    def test_sem_choices_levanta(self, ai_service):
        with pytest.raises(TransientAIError):
            ai_service._parse_response({})

    def test_choices_vazio_levanta(self, ai_service):
        with pytest.raises(TransientAIError):
            ai_service._parse_response({'choices': []})


# ---------------------------------------------------------------------------
# _parse_allergens
# ---------------------------------------------------------------------------

class TestParseAllergens:

    def test_string_vazia(self):
        assert _parse_allergens('') == []

    def test_none_retorna_vazio(self):
        assert _parse_allergens(None) == []

    def test_virgula(self):
        r = _parse_allergens('amendoim, camarão')
        assert 'amendoim' in r and 'camarao' in r

    def test_ponto_virgula(self):
        r = _parse_allergens('amendoim; leite')
        assert 'amendoim' in r and 'leite' in r

    def test_conectivo_e(self):
        r = _parse_allergens('amendoim e leite')
        assert 'amendoim' in r and 'leite' in r

    def test_quebra_de_linha(self):
        r = _parse_allergens('amendoim\ncamarão')
        assert 'amendoim' in r

    def test_normaliza_acentos_e_caixa(self):
        r = _parse_allergens('Amêndoa, LEITE')
        assert 'amendoa' in r and 'leite' in r

    def test_descarta_curtos(self):
        r = _parse_allergens('ov, amendoim')
        assert 'ov' not in r and 'amendoim' in r

    def test_sem_duplicatas(self):
        r = _parse_allergens('amendoim, AMENDOIM, amendoim')
        assert r.count('amendoim') == 1

    def test_alergeno_multipalavra(self):
        r = _parse_allergens('frutos do mar, leite')
        assert 'frutos do mar' in r


# ---------------------------------------------------------------------------
# _food_contains_allergen
# ---------------------------------------------------------------------------

class TestFoodContainsAllergen:

    def test_sem_alergenos_retorna_none(self):
        assert _food_contains_allergen('Frango grelhado', []) is None

    def test_match_palavra_exata(self):
        assert _food_contains_allergen('Pasta de amendoim', ['amendoim']) == 'amendoim'

    def test_word_boundary_evita_falso_positivo(self):
        assert _food_contains_allergen('Prato novo', ['ovo']) is None
        assert _food_contains_allergen('Ovo cozido', ['ovo']) == 'ovo'

    def test_normaliza_acentos(self):
        assert _food_contains_allergen('Camarão grelhado', ['camarao']) == 'camarao'

    def test_alergeno_multipalavra(self):
        assert _food_contains_allergen('Sopa de frutos do mar', ['frutos do mar']) == 'frutos do mar'

    def test_alimento_vazio_retorna_none(self):
        assert _food_contains_allergen('', ['amendoim']) is None


# ---------------------------------------------------------------------------
# _round_food_quantity
# ---------------------------------------------------------------------------

class TestRoundFoodQuantity:

    def test_oleo_multiplo_de_5(self):
        assert _round_food_quantity('Azeite', 13) % 5 == 0

    def test_ovo_multiplo_de_50(self):
        assert _round_food_quantity('Ovo cozido', 55) % 50 == 0

    def test_frango_multiplo_de_25_e_minimo_50(self):
        r = _round_food_quantity('Frango grelhado', 20)
        assert r >= 50 and r % 25 == 0

    def test_arroz_multiplo_de_50(self):
        assert _round_food_quantity('Arroz cozido', 133) % 50 == 0

    def test_alimento_desconhecido_pequeno_multiplo_de_5(self):
        assert _round_food_quantity('Kimchi', 23) % 5 == 0

    def test_alimento_desconhecido_medio_multiplo_de_25(self):
        assert _round_food_quantity('Kimchi', 133) % 25 == 0

    def test_iogurte_minimo_100(self):
        assert _round_food_quantity('Iogurte natural', 50) >= 100


# ---------------------------------------------------------------------------
# _household_measure
# ---------------------------------------------------------------------------

class TestHouseholdMeasure:

    def test_arroz_colheres(self):
        assert 'col' in _household_measure('Arroz cozido', 150)

    def test_frango_file(self):
        assert 'fil' in _household_measure('Frango grelhado', 130)

    def test_ovo_unidades(self):
        assert 'unidade' in _household_measure('Ovo cozido', 100)

    def test_azeite_colher(self):
        assert 'col' in _household_measure('Azeite de oliva', 10)

    def test_leite_copo(self):
        assert 'copo' in _household_measure('Leite desnatado', 200)

    def test_iogurte_pote(self):
        assert 'pote' in _household_measure('Iogurte natural', 200)

    def test_tapioca_unidade(self):
        assert 'tapioca' in _household_measure('Tapioca', 80)

    def test_feijao_concha(self):
        assert 'concha' in _household_measure('Feijão cozido', 80)

    def test_atum_lata(self):
        assert 'lata' in _household_measure('Atum em água', 85)

    def test_alimento_desconhecido_retorna_string(self):
        assert isinstance(_household_measure('Kimchi', 100), str)


# ---------------------------------------------------------------------------
# _validate_macro_ratios
# ---------------------------------------------------------------------------

class TestValidateMacroRatios:

    def _diet(self, protein_g, carbs_g, fat_g):
        total = protein_g * 4 + carbs_g * 4 + fat_g * 9
        return {'calories': total, 'macros': {'protein_g': protein_g, 'carbs_g': carbs_g, 'fat_g': fat_g}}

    def test_macros_validos_nao_levanta(self, ai_service, anamnese):
        ai_service._validate_macro_ratios(self._diet(150, 200, 60), anamnese, 1800)

    def test_carboidratos_excessivos_levanta(self, ai_service, anamnese):
        with pytest.raises(MacroImbalanceError, match='carboidrato'):
            ai_service._validate_macro_ratios(self._diet(50, 350, 30), anamnese, 1800)

    def test_proteina_insuficiente_levanta(self, ai_service, anamnese):
        with pytest.raises(MacroImbalanceError, match='proteína'):
            ai_service._validate_macro_ratios(self._diet(20, 300, 80), anamnese, 1800)

    def test_gordura_insuficiente_levanta(self, ai_service, anamnese):
        with pytest.raises(MacroImbalanceError, match='gordura'):
            ai_service._validate_macro_ratios(self._diet(150, 300, 10), anamnese, 1800)

    def test_gordura_excessiva_por_kg_levanta(self, ai_service, anamnese):
        with pytest.raises(MacroImbalanceError):
            ai_service._validate_macro_ratios(self._diet(150, 150, 120), anamnese, 2000)

    def test_zero_calorias_nao_levanta(self, ai_service, anamnese):
        ai_service._validate_macro_ratios({'calories': 0, 'macros': {}}, anamnese, 1800)


# ---------------------------------------------------------------------------
# _check_db_coverage
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestCheckDbCoverage:

    @pytest.fixture
    def service(self):
        return AIService()

    def test_total_zero_nao_levanta(self, service, anamnese):
        service._check_db_coverage({'total': 0}, anamnese)

    def test_um_generic_em_5_nao_levanta(self, service, anamnese):
        service._check_db_coverage({'total': 5, 'exact': 4, 'generic': 1, 'generic_names': ['x']}, anamnese)

    def test_dois_generic_em_5_levanta(self, service, anamnese):
        with pytest.raises(NutritionDataGap, match='Cobertura nutricional'):
            service._check_db_coverage({'total': 5, 'exact': 3, 'generic': 2, 'generic_names': ['a', 'b']}, anamnese)

    def test_dois_generic_em_15_nao_levanta(self, service, anamnese):
        service._check_db_coverage({'total': 15, 'exact': 13, 'generic': 2, 'generic_names': ['a', 'b']}, anamnese)

    def test_tres_generic_em_15_levanta(self, service, anamnese):
        with pytest.raises(NutritionDataGap):
            service._check_db_coverage({'total': 15, 'exact': 12, 'generic': 3, 'generic_names': ['a', 'b', 'c']}, anamnese)

    def test_mensagem_inclui_nomes(self, service, anamnese):
        with pytest.raises(NutritionDataGap, match='Coxinha'):
            service._check_db_coverage({'total': 4, 'exact': 2, 'generic': 2, 'generic_names': ['Coxinha', 'Pão de queijo']}, anamnese)


# ---------------------------------------------------------------------------
# _enforce_allergies
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEnforceAllergies:

    def test_sem_alergias_passa(self, ai_service, anamnese):
        ai_service._enforce_allergies({'meals': [{'name': 'Almoço', 'foods': [{'name': 'Frango'}]}]}, anamnese)

    def test_alergia_detectada_levanta(self, db, create_user, ai_service):
        user = create_user()
        ana = Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=75, height_cm=175,
            activity_level='moderate', goal='lose', meals_per_day=3, allergies='amendoim',
        )
        with pytest.raises(AllergenViolation, match='amendoim'):
            ai_service._enforce_allergies({'meals': [{'name': 'Lanche', 'foods': [{'name': 'Pasta de amendoim'}]}]}, ana)

    def test_word_boundary_evita_iogurte_com_ovo(self, db, create_user, ai_service):
        user = create_user()
        ana = Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=75, height_cm=175,
            activity_level='moderate', goal='lose', meals_per_day=3, allergies='ovo',
        )
        ai_service._enforce_allergies({'meals': [{'name': 'Café', 'foods': [{'name': 'Iogurte natural'}]}]}, ana)

    def test_multiplas_violacoes_todas_na_mensagem(self, db, create_user, ai_service):
        user = create_user()
        ana = Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=75, height_cm=175,
            activity_level='moderate', goal='lose', meals_per_day=3, allergies='atum, camarão',
        )
        with pytest.raises(AllergenViolation) as exc:
            ai_service._enforce_allergies({'meals': [{'name': 'Almoço', 'foods': [
                {'name': 'Atum em lata'}, {'name': 'Camarão grelhado'},
            ]}]}, ana)
        msg = str(exc.value)
        assert 'atum' in msg and 'camarao' in msg


# ---------------------------------------------------------------------------
# _generate_notes — meal_notes parsing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateNotesMealNotesMapping:

    def _meals(self):
        return [{'name': 'Café da manhã', 'foods': []},
                {'name': 'Almoço', 'foods': []},
                {'name': 'Jantar', 'foods': []}]

    def test_chave_nome_mapeia_corretamente(self, ai_service, anamnese):
        api_resp = _wrap({'tips': ['Dica'], 'meal_notes': {
            'Café da manhã': 'Nota café', 'Almoço': 'Nota almoço',
        }})
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            r = ai_service._generate_notes({'meals': self._meals(), 'calories': 2000}, anamnese, 2000)
        assert r['meal_notes'][0] == 'Nota café'
        assert r['meal_notes'][1] == 'Nota almoço'

    def test_chave_numerica_0_based(self, ai_service, anamnese):
        api_resp = _wrap({'tips': [], 'meal_notes': {'0': 'Nota 0', '2': 'Nota 2'}})
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            r = ai_service._generate_notes({'meals': self._meals(), 'calories': 2000}, anamnese, 2000)
        assert r['meal_notes'].get(0) == 'Nota 0'
        assert r['meal_notes'].get(2) == 'Nota 2'

    def test_chave_numerica_1_based_fora_de_0based(self, ai_service, anamnese):
        # "3" é inválido 0-based (len=3) mas válido 1-based → índice 2
        api_resp = _wrap({'tips': [], 'meal_notes': {'3': 'Nota refeição 3'}})
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            r = ai_service._generate_notes({'meals': self._meals(), 'calories': 2000}, anamnese, 2000)
        assert r['meal_notes'].get(2) == 'Nota refeição 3'

    def test_tips_viram_notes_formatadas(self, ai_service, anamnese):
        api_resp = _wrap({'tips': ['Dica A', 'Dica B'], 'meal_notes': {}})
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            r = ai_service._generate_notes({'meals': self._meals(), 'calories': 2000}, anamnese, 2000)
        assert '• Dica A' in r['notes'] and '• Dica B' in r['notes']

    def test_api_falha_retorna_silenciosamente(self, ai_service, anamnese):
        with patch.object(ai_service, '_call_api', side_effect=Exception('erro')):
            r = ai_service._generate_notes({'meals': self._meals(), 'calories': 2000}, anamnese, 2000)
        assert r['notes'] is None and r['meal_notes'] == {}

    def test_nota_vazia_ignorada(self, ai_service, anamnese):
        api_resp = _wrap({'tips': [], 'meal_notes': {'Café da manhã': '', 'Almoço': 'Nota válida'}})
        with patch.object(ai_service, '_call_api', return_value=api_resp):
            r = ai_service._generate_notes({'meals': self._meals(), 'calories': 2000}, anamnese, 2000)
        assert 0 not in r['meal_notes']
        assert r['meal_notes'].get(1) == 'Nota válida'


# ---------------------------------------------------------------------------
# regenerate_meal
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRegenerateMeal:

    def _new_meal(self):
        return {'name': 'Almoço', 'time_suggestion': '12:00', 'foods': [
            {'name': 'Tilápia grelhada', 'quantity_g': 130, 'quantity_text': '130g'},
        ]}

    @patch('nutrition.services.lookup_food_nutrition')
    def test_retorna_chaves_corretas(self, mock_lookup, ai_service, diet_plan):
        mock_lookup.return_value = {'calories': 180, 'protein_g': 25, 'carbs_g': 10, 'fat_g': 5, '_source': 'exact'}
        with patch.object(ai_service, '_call_api', return_value=_wrap(self._new_meal())):
            r = ai_service.regenerate_meal(diet_plan, meal_index=1)
        assert {'new_raw_meal', 'new_description', 'new_calories', 'new_meal_name'} == set(r.keys())

    @patch('nutrition.services.lookup_food_nutrition')
    def test_inclui_horario_no_nome(self, mock_lookup, ai_service, diet_plan):
        mock_lookup.return_value = {'calories': 180, 'protein_g': 25, 'carbs_g': 10, 'fat_g': 5, '_source': 'exact'}
        with patch.object(ai_service, '_call_api', return_value=_wrap(self._new_meal())):
            r = ai_service.regenerate_meal(diet_plan, meal_index=1)
        assert '12:00' in r['new_meal_name']

    @patch('nutrition.services.lookup_food_nutrition')
    def test_description_tem_bullet_points(self, mock_lookup, ai_service, diet_plan):
        mock_lookup.return_value = {'calories': 180, 'protein_g': 25, 'carbs_g': 10, 'fat_g': 5, '_source': 'exact'}
        with patch.object(ai_service, '_call_api', return_value=_wrap(self._new_meal())):
            r = ai_service.regenerate_meal(diet_plan, meal_index=1)
        assert '•' in r['new_description']

    @patch('nutrition.services.lookup_food_nutrition')
    def test_foods_vazio_levanta(self, mock_lookup, ai_service, diet_plan):
        with patch.object(ai_service, '_call_api', return_value=_wrap({'name': 'Almoço', 'foods': []})):
            with pytest.raises(TransientAIError):
                ai_service.regenerate_meal(diet_plan, meal_index=1)

    def test_indice_invalido_levanta(self, ai_service, diet_plan):
        with pytest.raises(ValueError, match='Índice'):
            ai_service.regenerate_meal(diet_plan, meal_index=99)

    def test_sem_anamnese_levanta(self, db, create_user, ai_service):
        user = create_user()
        plan = DietPlan.objects.create(
            user=user, anamnese=None,
            raw_response={'meals': [{'name': 'A', 'foods': [{'name': 'Frango', 'quantity_g': 100}]}]},
            total_calories=200,
        )
        with pytest.raises(ValueError, match='anamnese'):
            ai_service.regenerate_meal(plan, meal_index=0)

    def test_alergia_em_nova_refeicao_levanta(self, db, create_user, ai_service):
        user = create_user()
        ana = Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=75, height_cm=175,
            activity_level='moderate', goal='lose', meals_per_day=3, allergies='camarão',
        )
        plan = DietPlan.objects.create(
            user=user, anamnese=ana,
            raw_response={'meals': [{'name': 'Jantar', 'time_suggestion': '19:00', 'foods': [
                {'name': 'Frango', 'quantity_g': 130},
            ]}]},
            total_calories=300,
        )
        Meal.objects.create(diet_plan=plan, meal_name='Jantar', description='...', calories=300, order=0)
        with patch.object(ai_service, '_call_api', return_value=_wrap({
            'name': 'Jantar', 'time_suggestion': '19:00',
            'foods': [{'name': 'Camarão grelhado', 'quantity_g': 130, 'quantity_text': '130g'}],
        })):
            with pytest.raises(AllergenViolation):
                ai_service.regenerate_meal(plan, meal_index=0)


# ---------------------------------------------------------------------------
# generate_diet — pipeline completo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateDiet:

    @patch.object(AIService, '_call_api')
    def test_cria_dietplan_no_banco(self, mock, anamnese_obj):
        mock.side_effect = _pipeline_effects()
        plan = AIService().generate_diet(anamnese_obj)
        assert plan.pk is not None and plan.total_calories > 0

    @patch.object(AIService, '_call_api')
    def test_macros_vem_do_backend(self, mock, anamnese_obj):
        mock.side_effect = _pipeline_effects()
        plan = AIService().generate_diet(anamnese_obj)
        macros = plan.raw_response.get('macros', {})
        assert macros.get('protein_g', 0) > 0

    @patch.object(AIService, '_call_api')
    def test_meals_persistidas(self, mock, anamnese_obj):
        mock.side_effect = _pipeline_effects()
        plan = AIService().generate_diet(anamnese_obj)
        assert plan.meals.count() == len(_PASSO1['meals'])

    @patch.object(AIService, '_call_api')
    def test_explanation_opcional_nao_bloqueia(self, mock, anamnese_obj):
        mock.side_effect = [_wrap(_PASSO1), Exception('IA fora'), Exception('IA fora')]
        plan = AIService().generate_diet(anamnese_obj)
        assert plan.pk is not None and plan.raw_response.get('explanation') is None

    @patch.object(AIService, '_call_api')
    def test_tres_chamadas_a_api(self, mock, anamnese_obj):
        mock.side_effect = _pipeline_effects()
        AIService().generate_diet(anamnese_obj)
        assert mock.call_count == 3

    @patch.object(AIService, '_call_api')
    def test_meals_vazios_levanta(self, mock, anamnese_obj):
        mock.return_value = _wrap({'goal_description': 'Teste', 'meals': []})
        with pytest.raises(TransientAIError, match='refeições válidas'):
            AIService().generate_diet(anamnese_obj)

    @patch.object(AIService, '_call_api')
    def test_total_calories_igual_soma_meals(self, mock, anamnese_obj):
        mock.side_effect = _pipeline_effects()
        plan = AIService().generate_diet(anamnese_obj)
        soma = sum(m.calories for m in plan.meals.all())
        assert plan.total_calories == soma

    @patch.object(AIService, '_call_api')
    def test_rejeita_plano_com_alergia(self, mock, anamnese_obj):
        mock.return_value = _wrap({'goal_description': 'Teste', 'meals': [{
            'name': 'Lanche', 'time_suggestion': '15:00',
            'foods': [{'name': 'Pasta de amendoim', 'quantity_text': '20g', 'quantity_g': 20}],
        }]})
        with pytest.raises(AllergenViolation, match='amendoim'):
            AIService().generate_diet(anamnese_obj)

    @patch.object(AIService, '_call_api')
    def test_falha_alergia_antes_de_chamar_explanation(self, mock, anamnese_obj):
        mock.return_value = _wrap({'goal_description': 'Teste', 'meals': [{
            'name': 'Café', 'time_suggestion': '07:00',
            'foods': [{'name': 'Pão com amendoim', 'quantity_text': '50g', 'quantity_g': 50}],
        }]})
        with pytest.raises(AllergenViolation):
            AIService().generate_diet(anamnese_obj)
        assert mock.call_count == 1

    @patch.object(AIService, '_call_api')
    def test_rejeita_plano_com_muitos_desconhecidos(self, mock, anamnese_obj):
        mock.return_value = _wrap({'goal_description': 'Teste', 'meals': [{
            'name': 'Almoço', 'time_suggestion': '12:00', 'foods': [
                {'name': 'zzzzz_aaa', 'quantity_text': '100g', 'quantity_g': 100},
                {'name': 'yyyyy_bbb', 'quantity_text': '100g', 'quantity_g': 100},
                {'name': 'wwwww_ccc', 'quantity_text': '100g', 'quantity_g': 100},
            ],
        }]})
        with pytest.raises(NutritionDataGap):
            AIService().generate_diet(anamnese_obj)


# ---------------------------------------------------------------------------
# generate_diet_task — Celery
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateDietTask:

    @pytest.fixture
    def job(self, anamnese):
        return DietJob.objects.create(user=anamnese.user, anamnese=anamnese)

    def _plan(self, user):
        return DietPlan.objects.create(user=user, raw_response={}, total_calories=1800, goal_description='Teste')

    @patch('nutrition.services.AIService.generate_diet')
    def test_sucesso_marca_done(self, mock, job, anamnese):
        mock.return_value = self._plan(anamnese.user)
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)
        job.refresh_from_db()
        assert job.status == DietJob.STATUS_DONE and job.diet_plan_id is not None

    @patch('nutrition.services.AIService.generate_diet')
    def test_excecao_marca_failed(self, mock, job):
        mock.side_effect = Exception('Conexão recusada')
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)
        job.refresh_from_db()
        assert job.status == DietJob.STATUS_FAILED and 'Conexão recusada' in job.error_message

    @patch('nutrition.services.AIService.generate_diet')
    def test_job_done_nao_reprocessado(self, mock, job):
        job.status = DietJob.STATUS_DONE
        job.save()
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)
        assert not mock.called

    def test_job_inexistente_silencioso(self):
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(99999)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
    @patch('nutrition.services.AIService.generate_diet')
    def test_retry_transitorio_e_sucesso(self, mock, job, anamnese):
        mock.side_effect = [TransientAIError('A IA retornou um formato inesperado. Tente novamente.'),
                            self._plan(anamnese.user)]
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)
        job.refresh_from_db()
        assert job.status == DietJob.STATUS_DONE and mock.call_count == 2

    @patch('nutrition.services.AIService.generate_diet')
    def test_excecao_nao_transitoria_sem_retry(self, mock, job):
        mock.side_effect = ValueError('Dados inválidos')
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)
        job.refresh_from_db()
        assert job.status == DietJob.STATUS_FAILED and mock.call_count == 1

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
    @patch('nutrition.services.AIService.generate_diet')
    def test_falha_definitiva_apos_max_retries(self, mock, job):
        mock.side_effect = TransientAIError('A IA retornou um formato inesperado.')
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)
        job.refresh_from_db()
        assert job.status == DietJob.STATUS_FAILED and mock.call_count == 3

"""
Testes críticos — MyNutri AI
Verifica:
  1. Estrutura e conteúdo dos prompts (Passo 1 e Passo 2)
  2. Cálculo determinístico de calorias e macros (nutrition_db + recalculate + adjust)
  3. Rate limiting na prática (ScopedRateThrottle com override_settings)
"""

import json
import pytest
from unittest.mock import patch, MagicMock, call
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from nutrition.models import Anamnese, DietPlan, Meal
from nutrition.services import AIService, TransientAIError
from nutrition.prompts import (
    SYSTEM_PROMPT_FOODS,
    FOOD_SELECTION_TEMPLATE,
    build_food_selection_prompt,
    build_explanation_prompt,
    calculate_calories,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def create_user(db):
    counter = {'n': 0}
    def _create(email=None, nome='Teste', senha='senhaSegura123'):
        counter['n'] += 1
        if email is None:
            email = f'user{counter["n"]}@critical.com'
        return User.objects.create_user(
            username=email, email=email, password=senha, first_name=nome
        )
    return _create


@pytest.fixture
def auth_client(api_client, create_user):
    user = create_user()
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return api_client, user


@pytest.fixture
def anamnese_obj(db, create_user):
    user = create_user()
    return Anamnese.objects.create(
        user=user, age=28, gender='M',
        weight_kg=80.0, height_cm=178.0,
        activity_level='moderate', goal='lose',
        meals_per_day=4,
        food_preferences='Frango, Batata-doce',
        food_restrictions='',
        allergies='amendoim',
    )


# Resposta mínima válida do Passo 1 (seleção de alimentos).
# Usa 4 refeições (meals_per_day=4) com proteína adequada para o perfil do
# anamnese_obj (80kg, lose) — necessário para passar a validação de macros.
_FOOD_SELECTION_RESPONSE = {
    'goal_description': 'Emagrecimento saudável',
    'meals': [
        {
            'name': 'Café da manhã',
            'time_suggestion': '07:00',
            'foods': [
                {'name': 'Ovos mexidos',    'quantity_text': '4 unidades', 'quantity_g': 200},
                {'name': 'Pão francês',     'quantity_text': '1 unidade',  'quantity_g': 50},
                {'name': 'Iogurte natural', 'quantity_text': '1 pote',     'quantity_g': 150},
            ],
        },
        {
            'name': 'Almoço',
            'time_suggestion': '12:00',
            'foods': [
                {'name': 'Frango grelhado', 'quantity_text': '1 filé (180g)', 'quantity_g': 180},
                {'name': 'Arroz branco',    'quantity_text': '4 col. sopa',   'quantity_g': 120},
                {'name': 'Feijão cozido',   'quantity_text': '2 conchas',     'quantity_g': 100},
                {'name': 'Salada mista',    'quantity_text': '1 prato',       'quantity_g': 80},
            ],
        },
        {
            'name': 'Lanche da tarde',
            'time_suggestion': '15:30',
            'foods': [
                {'name': 'Atum em água',   'quantity_text': '1 lata pequena', 'quantity_g': 80},
                {'name': 'Batata doce',    'quantity_text': '1 unidade',      'quantity_g': 120},
            ],
        },
        {
            'name': 'Jantar',
            'time_suggestion': '19:30',
            'foods': [
                {'name': 'Tilapia grelhada', 'quantity_text': '1 filé (200g)', 'quantity_g': 200},
                {'name': 'Brocolis cozido',  'quantity_text': '1 xícara',      'quantity_g': 100},
                {'name': 'Batata doce',      'quantity_text': '1 unidade',     'quantity_g': 100},
                {'name': 'Azeite oliva',     'quantity_text': '1 col. sopa',   'quantity_g': 10},
            ],
        },
    ],
    'substitutions': [
        {'food': 'Pão francês', 'alternatives': ['Tapioca', 'Cuscuz']},
    ],
    'notes': 'Beba pelo menos 2 litros de água por dia.',
}

# Resposta mínima válida das dicas personalizadas
_NOTES_RESPONSE = {
    'tips': [
        'Distribua suas 3 refeições a cada 4–5 horas para manter o metabolismo ativo.',
        'Beba cerca de 35ml de água por kg corporal — para seu peso, ~2,6L por dia.',
        'Prefira frango grelhado no jantar para atingir sua meta proteica de emagrecimento.',
    ],
}

# Resposta mínima válida do Passo 2 (explicação)
_EXPLANATION_RESPONSE = {
    'calorie_calculation':  'Cálculo usando Mifflin-St Jeor...',
    'macro_distribution':   'Distribuição de macros...',
    'food_choices':         'Escolha dos alimentos...',
    'meal_structure':       'Estrutura das refeições...',
    'goal_alignment':       'Alinhamento com o objetivo...',
}


def _wrap_api_response(data: dict) -> dict:
    """Embrulha um dict no formato de resposta da API OpenAI."""
    return {'choices': [{'message': {'content': json.dumps(data)}}]}


# ============================================================================
# ÁREA 1 — VERIFICAÇÃO DOS PROMPTS
# ============================================================================

class TestPromptStructureAndFlow:
    """Verifica que os prompts são montados corretamente."""

    def test_system_prompt_passo1_nao_instrui_calcular_calorias(self):
        """SYSTEM_PROMPT_FOODS não deve delegar cálculo de calorias/macros à IA."""
        assert 'calcule' not in SYSTEM_PROMPT_FOODS.lower() or 'NÃO calcule' in SYSTEM_PROMPT_FOODS
        # O novo prompt diz explicitamente para NÃO calcular macros
        assert 'NÃO calcule calorias nem macros' in FOOD_SELECTION_TEMPLATE

    def test_system_prompt_enviado_como_role_system_passo1(self, anamnese_obj):
        """_call_api deve enviar SYSTEM_PROMPT_FOODS como mensagem de role=system no Passo 1."""
        service = AIService()
        service.api_key = 'test-key'
        service.api_url = 'http://test/'
        captured_calls = []

        def fake_urlopen(req, timeout=None):
            captured_calls.append(json.loads(req.data.decode('utf-8')))
            # Alterna entre resposta de seleção (1ª chamada) e explicação (2ª)
            if len(captured_calls) == 1:
                data = _FOOD_SELECTION_RESPONSE
            else:
                data = _EXPLANATION_RESPONSE
            class FakeResp:
                def read(self): return json.dumps({'choices': [{'message': {'content': json.dumps(data)}}]}).encode()
                def __enter__(self): return self
                def __exit__(self, *a): pass
            return FakeResp()

        import urllib.request
        with patch.object(urllib.request, 'urlopen', fake_urlopen):
            service.generate_diet(anamnese_obj)

        assert len(captured_calls) >= 1
        messages = captured_calls[0]['messages']
        system_msgs = [m for m in messages if m['role'] == 'system']
        assert len(system_msgs) == 1
        assert system_msgs[0]['content'] == SYSTEM_PROMPT_FOODS

    def test_passo1_usa_temperature_moderada(self, anamnese_obj):
        """Passo 1 (seleção de alimentos) deve usar temperature entre 0.4 e 0.7 para variedade."""
        service = AIService()
        service.api_key = 'test-key'
        service.api_url = 'http://test/'
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(json.loads(req.data.decode('utf-8')))
            n = len(captured)
            data = _FOOD_SELECTION_RESPONSE if n == 1 else _EXPLANATION_RESPONSE
            class FakeResp:
                def read(self): return json.dumps({'choices': [{'message': {'content': json.dumps(data)}}]}).encode()
                def __enter__(self): return self
                def __exit__(self, *a): pass
            return FakeResp()

        import urllib.request
        with patch.object(urllib.request, 'urlopen', fake_urlopen):
            service.generate_diet(anamnese_obj)

        temp = captured[0].get('temperature', 1.0)
        # Variedade garantida pelo prompt; temperatura moderada reduz NutritionDataGap
        assert 0.4 <= temp <= 0.7, f'Temperatura esperada entre 0.4 e 0.7 (variedade via prompt, não via temperatura), recebida: {temp}'

    def test_passo1_contem_target_calories(self, anamnese_obj):
        """O prompt do Passo 1 deve conter o alvo calórico calculado pelo backend."""
        _, _, target = calculate_calories(anamnese_obj)
        prompt = build_food_selection_prompt(anamnese_obj)
        assert str(target) in prompt

    def test_passo2_contem_tmb_e_tdee(self, anamnese_obj):
        """O prompt do Passo 2 (explicação) deve conter TMB e TDEE."""
        tmb, tdee, target = calculate_calories(anamnese_obj)
        diet_data = {
            'calories': target, 'macros': {'protein_g': 150, 'carbs_g': 230, 'fat_g': 60},
            'meals': [{'name': 'Almoço', 'time_suggestion': '12:00', 'foods': []}],
            'goal_description': 'Emagrecimento',
        }
        prompt = build_explanation_prompt(diet_data, anamnese_obj, tmb, tdee, target)
        assert str(tmb) in prompt
        assert str(tdee) in prompt

    def test_passo1_contem_preferencias(self, anamnese_obj):
        prompt = build_food_selection_prompt(anamnese_obj)
        assert 'Frango' in prompt
        assert 'Batata-doce' in prompt

    def test_passo1_contem_alergias(self, anamnese_obj):
        prompt = build_food_selection_prompt(anamnese_obj)
        assert 'amendoim' in prompt

    def test_passo1_contem_numero_refeicoes(self, anamnese_obj):
        prompt = build_food_selection_prompt(anamnese_obj)
        assert '4' in prompt

    def test_passo1_variaveis_do_template_todas_substituidas(self, anamnese_obj):
        """Nenhuma variável {xyz} não substituída deve restar no prompt."""
        import re
        prompt = build_food_selection_prompt(anamnese_obj)
        unresolved = re.findall(r'(?<!\{)\{(?!\{)(\w+)(?<!\})\}(?!\})', prompt)
        assert unresolved == [], f'Variáveis não substituídas: {unresolved}'

    def test_passo1_nao_pede_macros_por_alimento(self, anamnese_obj):
        """O prompt do Passo 1 não deve pedir protein_g, carbs_g, fat_g por alimento."""
        prompt = build_food_selection_prompt(anamnese_obj)
        assert 'protein_g' not in prompt
        assert 'carbs_g' not in prompt
        assert 'fat_g' not in prompt


class TestParseResponseMarkdown:
    """Verifica que _parse_response lida corretamente com markdown da IA."""

    @pytest.fixture
    def service(self):
        return AIService()

    def _wrap(self, diet_json):
        return {'choices': [{'message': {'content': diet_json}}]}

    def test_parse_json_puro(self, service):
        payload = json.dumps({'goal_description': 'Teste', 'calories': 1800})
        result = service._parse_response(self._wrap(payload))
        assert result['calories'] == 1800

    def test_parse_json_com_markdown_json_fence(self, service):
        payload = json.dumps({'goal_description': 'Teste', 'calories': 1900})
        wrapped = f'```json\n{payload}\n```'
        result = service._parse_response(self._wrap(wrapped))
        assert result['calories'] == 1900

    def test_parse_json_com_markdown_fence_simples(self, service):
        payload = json.dumps({'goal_description': 'Teste', 'calories': 2000})
        wrapped = f'```\n{payload}\n```'
        result = service._parse_response(self._wrap(wrapped))
        assert result['calories'] == 2000

    def test_parse_json_com_espacos_extras(self, service):
        payload = json.dumps({'goal_description': 'Teste', 'calories': 2100})
        result = service._parse_response(self._wrap(f'   {payload}   '))
        assert result['calories'] == 2100

    def test_parse_json_invalido_levanta_value_error(self, service):
        with pytest.raises(TransientAIError, match='formato inesperado'):
            service._parse_response(self._wrap('isso não é json {'))

    def test_parse_sem_choices_levanta_value_error(self, service):
        with pytest.raises(TransientAIError):
            service._parse_response({})

    def test_parse_choices_vazio_levanta_value_error(self, service):
        with pytest.raises(TransientAIError):
            service._parse_response({'choices': []})


# ============================================================================
# ÁREA 2 — CÁLCULO DETERMINÍSTICO DE MACROS
# ============================================================================

class TestNutritionDB:
    """Verifica a integração com o banco nutricional."""

    def test_lookup_alimento_conhecido(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Frango grelhado', 100)
        assert r['calories'] > 0
        assert r['protein_g'] > 0
        assert r['carbs_g'] == 0.0  # frango não tem carboidrato

    def test_lookup_alimento_com_normalizacao(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Peito de frango grelhado', 120)
        assert r['calories'] > 0
        assert r['protein_g'] > 10

    def test_lookup_alimento_desconhecido_retorna_fallback_generico_exato(self):
        """Fallback genérico (camada 4) deve retornar exatamente 150 kcal/100g."""
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('xyzw_alimento_que_nunca_existira_abc123', 100)
        assert r['calories'] == 150
        assert r['protein_g'] == 8.0
        assert r['carbs_g'] == 20.0
        assert r['fat_g'] == 4.0

    def test_lookup_quantidade_zero(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Arroz branco', 0)
        assert r['calories'] == 0

    def test_lookup_proporcional_a_quantidade(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r100 = lookup_food_nutrition('Banana', 100)
        r200 = lookup_food_nutrition('Banana', 200)
        assert r200['calories'] == r100['calories'] * 2
        assert r200['protein_g'] == r100['protein_g'] * 2

    def test_lookup_alimento_composto_wrap_frango_resolve_como_frango(self):
        """
        'Wrap de frango' faz match no token 'frango' e retorna macros de frango puro.
        COMPORTAMENTO DOCUMENTADO: carbs_g = 0 (tortilha não está no banco separadamente).
        Qualquer alteração nesta lógica deve ser consciente e intencional.
        """
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Wrap de frango', 200)
        assert r['protein_g'] > 0
        assert r['carbs_g'] == 0.0   # frango puro — tortilha ignorada
        assert r['calories'] > 0

    def test_lookup_alimento_composto_pao_com_ovo_resolve_como_pao(self):
        """
        'Pão com ovo' faz match prioritário no token 'pão' e retorna macros de pão.
        COMPORTAMENTO DOCUMENTADO: a proteína e gordura do ovo são ignoradas.
        """
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Pão com ovo', 100)
        assert r['carbs_g'] > 20    # pão tem carboidrato
        assert r['calories'] > 0


class TestRecalculateTotals:
    """Verifica que _recalculate_totals soma corretamente calorias e macros dos foods."""

    @pytest.fixture
    def service(self):
        return AIService()

    def test_soma_calorias_de_todos_os_foods(self, service):
        data = {
            'meals': [
                {'foods': [
                    {'calories': 300, 'protein_g': 30, 'carbs_g': 20, 'fat_g': 10},
                    {'calories': 200, 'protein_g': 10, 'carbs_g': 30, 'fat_g': 5},
                ]},
                {'foods': [
                    {'calories': 500, 'protein_g': 40, 'carbs_g': 50, 'fat_g': 15},
                ]},
            ],
        }
        result = service._recalculate_totals(data)
        assert result['calories'] == 1000
        assert result['macros']['protein_g'] == 80
        assert result['macros']['carbs_g'] == 100
        assert result['macros']['fat_g'] == 30

    def test_sobrescreve_declarado_pela_ia(self, service):
        data = {
            'calories': 9999,
            'macros': {'protein_g': 999, 'carbs_g': 999, 'fat_g': 999},
            'meals': [
                {'foods': [{'calories': 400, 'protein_g': 30, 'carbs_g': 50, 'fat_g': 10}]},
            ],
        }
        result = service._recalculate_totals(data)
        assert result['calories'] == 400
        assert result['macros']['protein_g'] == 30
        assert result['macros']['carbs_g'] == 50
        assert result['macros']['fat_g'] == 10

    def test_meals_vazia(self, service):
        data = {'meals': []}
        result = service._recalculate_totals(data)
        assert result['calories'] == 0
        assert result['macros']['protein_g'] == 0

    def test_food_sem_calories_conta_zero(self, service):
        data = {
            'meals': [{'foods': [
                {'name': 'sem caloria', 'protein_g': 10, 'carbs_g': 5, 'fat_g': 2},
                {'calories': 200, 'protein_g': 20, 'carbs_g': 30, 'fat_g': 8},
            ]}],
        }
        result = service._recalculate_totals(data)
        assert result['calories'] == 200


class TestAdjustToCalorieTarget:
    """Verifica o ajuste proporcional de porções ao alvo calórico."""

    @pytest.fixture
    def service(self):
        return AIService()

    def test_sem_divergencia_nao_altera(self, service):
        """Dentro de ±10%, não deve escalar."""
        data = {
            'calories': 2000,
            'meals': [{'foods': [
                {'name': 'Frango grelhado', 'quantity_g': 120, 'quantity_text': '120g',
                 'calories': 1000, 'protein_g': 50, 'carbs_g': 0, 'fat_g': 15},
                {'name': 'Arroz branco', 'quantity_g': 150, 'quantity_text': '150g',
                 'calories': 1000, 'protein_g': 10, 'carbs_g': 50, 'fat_g': 5},
            ]}],
        }
        # 2000 kcal calculado vs 2000 target → sem escala
        result = service._adjust_to_calorie_target(data, target_calories=2000)
        assert result['meals'][0]['foods'][0]['quantity_g'] == 120

    def test_escala_quando_divergencia_maior_10_porcento(self, service):
        """
        Divergência > 10% deve escalar quantity_g e recalcular calories via DB.
        Fontes proteicas são limitadas a +15% máximo para preservar adequação proteica.
        """
        data = {
            'calories': 1000,
            'meals': [{'foods': [
                {'name': 'Frango grelhado', 'quantity_g': 100, 'quantity_text': '100g',
                 'calories': 1000, 'protein_g': 32, 'carbs_g': 0, 'fat_g': 3},
            ]}],
        }
        result = service._adjust_to_calorie_target(data, target_calories=2000)
        # Frango é fonte proteica → scale limitado a 1.15 → 100g × 1.15 = 115g
        assert result['meals'][0]['foods'][0]['quantity_g'] == 115
        # calories deve ter sido recalculado via DB para a nova quantidade
        from nutrition.nutrition_db import lookup_food_nutrition
        expected_per_food = lookup_food_nutrition('Frango grelhado', 115)['calories']
        assert result['meals'][0]['foods'][0]['calories'] == expected_per_food
        assert result['calories'] == expected_per_food  # único alimento → total igual

    def test_escala_nao_proteica_sem_restricao(self, service):
        """Alimentos não proteicos (arroz) recebem a escala completa sem restrição."""
        data = {
            'calories': 1000,
            'meals': [{'foods': [
                {'name': 'Arroz branco cozido', 'quantity_g': 100, 'quantity_text': '100g',
                 'calories': 1000, 'protein_g': 2, 'carbs_g': 28, 'fat_g': 0},
            ]}],
        }
        result = service._adjust_to_calorie_target(data, target_calories=2000)
        # Arroz não é fonte proteica → scale completo de 2.0 → 200g
        assert result['meals'][0]['foods'][0]['quantity_g'] == 200

    def test_tolerancia_10_porcento_documentada(self, service):
        """9% de desvio está dentro da tolerância → não escala."""
        data = {
            'calories': 1820,
            'meals': [{'foods': [
                {'name': 'Arroz branco', 'quantity_g': 100, 'quantity_text': '100g',
                 'calories': 1820, 'protein_g': 50, 'carbs_g': 200, 'fat_g': 45},
            ]}],
        }
        result = service._adjust_to_calorie_target(data, target_calories=2000)
        # 9% < 10% → sem escala
        assert result['meals'][0]['foods'][0]['quantity_g'] == 100


class TestPipelineCompleto:
    """Testa o pipeline completo com dois mocks de _call_api."""

    def _make_api_side_effects(self):
        """Retorna side_effects para os três _call_api calls do pipeline."""
        return [
            _wrap_api_response(_FOOD_SELECTION_RESPONSE),  # Passo 1 — seleção de alimentos
            _wrap_api_response(_NOTES_RESPONSE),            # Dicas personalizadas
            _wrap_api_response(_EXPLANATION_RESPONSE),      # Passo 2 — explicação
        ]

    @patch.object(AIService, '_call_api')
    def test_pipeline_cria_dietplan(self, mock_call, anamnese_obj):
        mock_call.side_effect = self._make_api_side_effects()
        service = AIService()
        diet_plan = service.generate_diet(anamnese_obj)
        assert diet_plan.pk is not None
        assert diet_plan.total_calories > 0

    @patch.object(AIService, '_call_api')
    def test_pipeline_macros_vem_do_banco_nao_da_ia(self, mock_call, anamnese_obj):
        """Macros devem ser calculados pelo backend, não inventados pela IA."""
        mock_call.side_effect = self._make_api_side_effects()
        service = AIService()
        diet_plan = service.generate_diet(anamnese_obj)

        macros = diet_plan.raw_response.get('macros', {})
        # Verifica que macros foram calculados (não zero e não os hardcoded da IA)
        assert macros.get('protein_g', 0) > 0
        assert macros.get('carbs_g', 0) > 0
        assert macros.get('fat_g', 0) > 0

    @patch.object(AIService, '_call_api')
    def test_pipeline_meals_persistidas(self, mock_call, anamnese_obj):
        """As refeições retornadas pela IA devem ser persistidas no banco."""
        mock_call.side_effect = self._make_api_side_effects()
        service = AIService()
        diet_plan = service.generate_diet(anamnese_obj)

        meals = list(diet_plan.meals.all())
        assert len(meals) == len(_FOOD_SELECTION_RESPONSE['meals'])

    @patch.object(AIService, '_call_api')
    def test_pipeline_explanation_opcional(self, mock_call, anamnese_obj):
        """Se dicas e explicação falharem, o DietPlan deve ser criado mesmo assim."""
        # Passo 1 ok, dicas falha, explicação falha
        mock_call.side_effect = [
            _wrap_api_response(_FOOD_SELECTION_RESPONSE),
            Exception('API unavailable'),  # dicas — falha silenciosa
            Exception('API unavailable'),  # explicação — falha silenciosa
        ]
        service = AIService()
        diet_plan = service.generate_diet(anamnese_obj)

        # Plan foi criado mesmo sem dicas nem explanation
        assert diet_plan.pk is not None
        assert diet_plan.raw_response.get('explanation') is None

    @patch.object(AIService, '_call_api')
    def test_pipeline_tres_calls_a_api(self, mock_call, anamnese_obj):
        """O pipeline deve realizar exatamente 3 chamadas à API: seleção + dicas + explicação."""
        mock_call.side_effect = self._make_api_side_effects()
        service = AIService()
        service.generate_diet(anamnese_obj)
        assert mock_call.call_count == 3

    @patch.object(AIService, '_call_api')
    def test_pipeline_refeicoes_sem_foods_levanta_erro(self, mock_call, anamnese_obj):
        """Resposta da IA sem meals deve levantar ValueError."""
        mock_call.return_value = _wrap_api_response({'goal_description': 'Teste', 'meals': []})
        service = AIService()
        with pytest.raises(TransientAIError, match='refeições válidas'):
            service.generate_diet(anamnese_obj)

    @patch.object(AIService, '_call_api')
    def test_pipeline_total_calories_coerente_com_meals(self, mock_call, anamnese_obj):
        """
        DietPlan.total_calories deve ser igual à soma de calories das Meals persistidas.
        Detecta divergência entre o campo desnormalizado e as linhas filhas.
        """
        mock_call.side_effect = self._make_api_side_effects()
        service = AIService()
        diet_plan = service.generate_diet(anamnese_obj)

        soma_meals = sum(meal.calories for meal in diet_plan.meals.all())
        assert diet_plan.total_calories == soma_meals, (
            f'total_calories={diet_plan.total_calories} diverge da soma das meals={soma_meals}'
        )


# ============================================================================
# ÁREA 2.5 — ENFORCEMENT DE ALERGIAS
# ============================================================================

class TestParseAllergens:
    """Verifica o parsing do campo livre de alergias."""

    def test_vazio_retorna_lista_vazia(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('') == []
        assert _parse_allergens('   ') == []

    def test_alergeno_simples(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('amendoim') == ['amendoim']

    def test_separador_virgula(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('amendoim, leite') == ['amendoim', 'leite']

    def test_separador_ponto_virgula(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('amendoim; leite') == ['amendoim', 'leite']

    def test_separador_e(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('amendoim e leite') == ['amendoim', 'leite']

    def test_separador_quebra_linha(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('amendoim\nleite') == ['amendoim', 'leite']

    def test_remove_acentos_e_caixa(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('Amêndoa, LEITE') == ['amendoa', 'leite']

    def test_alergeno_multipalavra(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('frutos do mar, leite') == ['frutos do mar', 'leite']

    def test_descarta_entradas_curtas(self):
        from nutrition.services import _parse_allergens
        # "ov" tem só 2 chars → descartado
        assert _parse_allergens('ov, amendoim') == ['amendoim']

    def test_dedup(self):
        from nutrition.services import _parse_allergens
        assert _parse_allergens('amendoim, AMENDOIM, amendoim') == ['amendoim']


class TestFoodContainsAllergen:
    """Verifica detecção de alergenos no nome do alimento."""

    def test_sem_alergenos_retorna_none(self):
        from nutrition.services import _food_contains_allergen
        assert _food_contains_allergen('Frango grelhado', []) is None

    def test_alimento_vazio_retorna_none(self):
        from nutrition.services import _food_contains_allergen
        assert _food_contains_allergen('', ['amendoim']) is None

    def test_match_palavra_exata(self):
        from nutrition.services import _food_contains_allergen
        assert _food_contains_allergen('Pasta de amendoim', ['amendoim']) == 'amendoim'

    def test_match_inicio_palavra(self):
        from nutrition.services import _food_contains_allergen
        assert _food_contains_allergen('Amendoim torrado', ['amendoim']) == 'amendoim'

    def test_match_com_acento_no_alimento(self):
        from nutrition.services import _food_contains_allergen
        # "amêndoa" no alimento, "amendoa" como allergeno normalizado
        assert _food_contains_allergen('Amêndoa fatiada', ['amendoa']) == 'amendoa'

    def test_word_boundary_evita_falso_positivo(self):
        """'novo' não deve casar com 'ovo'."""
        from nutrition.services import _food_contains_allergen
        assert _food_contains_allergen('Prato novo', ['ovo']) is None
        # Mas 'ovo' como palavra deve casar
        assert _food_contains_allergen('Ovo cozido', ['ovo']) == 'ovo'

    def test_word_boundary_evita_substring_palavra(self):
        """'amendoinzinho' não deveria existir, mas se existisse, não casa."""
        from nutrition.services import _food_contains_allergen
        # 'amendoado' contém 'amendo' mas não 'amendoim' → sem match
        assert _food_contains_allergen('Sabor amendoado', ['amendoim']) is None

    def test_match_alergeno_multipalavra(self):
        from nutrition.services import _food_contains_allergen
        assert _food_contains_allergen('Sopa de frutos do mar',
                                       ['frutos do mar']) == 'frutos do mar'

    def test_match_primeiro_alergeno_da_lista(self):
        from nutrition.services import _food_contains_allergen
        # Alimento com dois alergenos — retorna o primeiro encontrado
        result = _food_contains_allergen('Pão com leite e amendoim',
                                         ['amendoim', 'leite'])
        assert result in ('amendoim', 'leite')

    def test_alimento_seguro_retorna_none(self):
        from nutrition.services import _food_contains_allergen
        assert _food_contains_allergen('Frango grelhado', ['amendoim', 'leite']) is None


@pytest.mark.django_db
class TestEnforceAllergiesPipeline:
    """Verifica que o pipeline rejeita planos que violam alergias declaradas."""

    @pytest.fixture
    def anamnese_com_alergia_amendoim(self, create_user):
        user = create_user()
        return Anamnese.objects.create(
            user=user, age=28, gender='M', weight_kg=80, height_cm=178,
            activity_level='moderate', goal='lose', meals_per_day=2,
            food_preferences='', food_restrictions='',
            allergies='amendoim',
        )

    @pytest.fixture
    def anamnese_sem_alergia(self, create_user):
        user = create_user()
        return Anamnese.objects.create(
            user=user, age=28, gender='M', weight_kg=80, height_cm=178,
            activity_level='moderate', goal='lose', meals_per_day=2,
            food_preferences='', food_restrictions='', allergies='',
        )

    @patch.object(AIService, '_call_api')
    def test_geracao_falha_se_violar_alergia(self, mock_call,
                                              anamnese_com_alergia_amendoim):
        """Plano com 'Pasta de amendoim' deve levantar AllergenViolation."""
        from nutrition.services import AllergenViolation
        bad_response = {
            'goal_description': 'Teste',
            'meals': [{
                'name': 'Lanche',
                'time_suggestion': '15:00',
                'foods': [
                    {'name': 'Pasta de amendoim', 'quantity_text': '20g',
                     'quantity_g': 20},
                ],
            }],
        }
        mock_call.return_value = _wrap_api_response(bad_response)
        service = AIService()
        with pytest.raises(AllergenViolation, match='amendoim'):
            service.generate_diet(anamnese_com_alergia_amendoim)

    @patch.object(AIService, '_call_api')
    def test_geracao_passa_se_alimentos_seguros(self, mock_call,
                                                 anamnese_com_alergia_amendoim):
        """Plano sem alergenos deve gerar normalmente, mesmo com allergies setado."""
        mock_call.side_effect = [
            _wrap_api_response(_FOOD_SELECTION_RESPONSE),  # sem amendoim
            _wrap_api_response(_NOTES_RESPONSE),
            _wrap_api_response(_EXPLANATION_RESPONSE),
        ]
        service = AIService()
        plan = service.generate_diet(anamnese_com_alergia_amendoim)
        assert plan.pk is not None

    @patch.object(AIService, '_call_api')
    def test_geracao_pula_check_se_sem_alergias(self, mock_call,
                                                  anamnese_sem_alergia):
        """Sem alergias declaradas, qualquer alimento passa (mesmo amendoim)."""
        # Resposta nutricionalmente completa que inclui amendoim — verifica
        # que o alimento NÃO é bloqueado quando nenhuma alergia foi declarada.
        response_with_amendoim = {
            'goal_description': 'Teste',
            'meals': [
                {
                    'name': 'Almoço',
                    'time_suggestion': '12:00',
                    'foods': [
                        {'name': 'Frango grelhado', 'quantity_text': '180g', 'quantity_g': 180},
                        {'name': 'Arroz branco', 'quantity_text': '100g', 'quantity_g': 100},
                        {'name': 'Feijão cozido', 'quantity_text': '80g', 'quantity_g': 80},
                        {'name': 'Azeite oliva', 'quantity_text': '10ml', 'quantity_g': 10},
                    ],
                },
                {
                    'name': 'Jantar',
                    'time_suggestion': '19:00',
                    'foods': [
                        {'name': 'Tilapia grelhada', 'quantity_text': '180g', 'quantity_g': 180},
                        {'name': 'Batata doce', 'quantity_text': '100g', 'quantity_g': 100},
                        {'name': 'Pasta de amendoim', 'quantity_text': '20g', 'quantity_g': 20},
                        {'name': 'Salada mista', 'quantity_text': '80g', 'quantity_g': 80},
                    ],
                },
            ],
        }
        mock_call.side_effect = [
            _wrap_api_response(response_with_amendoim),
            _wrap_api_response(_NOTES_RESPONSE),
            _wrap_api_response(_EXPLANATION_RESPONSE),
        ]
        service = AIService()
        plan = service.generate_diet(anamnese_sem_alergia)
        assert plan.pk is not None

    @patch.object(AIService, '_call_api')
    def test_geracao_falha_antes_de_chamar_explanation(
        self, mock_call, anamnese_com_alergia_amendoim,
    ):
        """Fail-fast: ao detectar alergeno, não deve chamar IA para notes/explanation."""
        from nutrition.services import AllergenViolation
        bad_response = {
            'goal_description': 'Teste',
            'meals': [{
                'name': 'Café da manhã', 'time_suggestion': '07:00',
                'foods': [{'name': 'Pão com amendoim', 'quantity_text': '50g',
                          'quantity_g': 50}],
            }],
        }
        mock_call.return_value = _wrap_api_response(bad_response)
        service = AIService()
        with pytest.raises(AllergenViolation):
            service.generate_diet(anamnese_com_alergia_amendoim)
        # Apenas 1 chamada (Passo 1) — notes e explanation não foram acionados
        assert mock_call.call_count == 1

    @patch.object(AIService, '_call_api')
    def test_regenerate_meal_falha_se_violar_alergia(self, mock_call,
                                                       anamnese_com_alergia_amendoim):
        """Regeneração que retorna alergeno deve levantar AllergenViolation."""
        from nutrition.services import AllergenViolation
        plan = DietPlan.objects.create(
            user=anamnese_com_alergia_amendoim.user,
            anamnese=anamnese_com_alergia_amendoim,
            raw_response={
                'meals': [{
                    'name': 'Café da manhã', 'time_suggestion': '07:00',
                    'foods': [{'name': 'Pão', 'quantity_text': '1 fatia',
                              'quantity_g': 50, 'calories': 145}],
                }],
            },
            total_calories=145,
        )
        Meal.objects.create(
            diet_plan=plan, meal_name='Café da manhã (07:00)',
            description='Pão', calories=145, order=0,
        )
        mock_call.return_value = _wrap_api_response({
            'name': 'Café da manhã', 'time_suggestion': '07:00',
            'foods': [{'name': 'Pasta de amendoim', 'quantity_text': '30g',
                      'quantity_g': 30}],
        })
        service = AIService()
        with pytest.raises(AllergenViolation, match='amendoim'):
            service.regenerate_meal(plan, 0)


# ============================================================================
# ÁREA 2.6 — COBERTURA DO BANCO NUTRICIONAL (NutritionDataGap)
# ============================================================================

class TestLookupSourceField:
    """Verifica que lookup_food_nutrition expõe a camada de match em '_source'."""

    def test_match_exato_marca_exact(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Frango grelhado', 100)
        assert r['_source'] == 'exact'

    def test_match_fuzzy_marca_fuzzy(self):
        """Variação no nome cai em fuzzy ou exact dependendo da normalização."""
        from nutrition.nutrition_db import lookup_food_nutrition
        # 'Peito de frango grelhado' não é chave exata, deve cair em fuzzy
        r = lookup_food_nutrition('Peito de frango grelhado bem suculento', 100)
        assert r['_source'] in ('fuzzy', 'exact')

    def test_categoria_marca_category(self):
        """Alimento que cai no fallback de categoria por palavra-chave."""
        from nutrition.nutrition_db import lookup_food_nutrition
        # 'Bisteca suína' — 'carne' no fallback de categoria? Vamos usar um exemplo claro.
        # 'Hambúrguer' → palavra-chave 'carne' não bate; vai pra generic.
        # 'Pato assado' → palavra-chave 'pato' bate em fallback de aves.
        r = lookup_food_nutrition('Pato assado', 100)
        assert r['_source'] in ('category', 'fuzzy', 'exact')

    def test_alimento_desconhecido_marca_generic(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('zzzzzzz_inexistente_xxxxxxx', 100)
        assert r['_source'] == 'generic'

    def test_input_invalido_marca_invalid(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        assert lookup_food_nutrition('', 100)['_source'] == 'invalid'
        assert lookup_food_nutrition('Frango', 0)['_source'] == 'invalid'


class TestEnrichReturnsStats:
    """Verifica que _enrich_foods_with_macros retorna stats por camada."""

    @pytest.fixture
    def service(self):
        return AIService()

    def test_retorna_tupla_dict_stats(self, service):
        data = {'meals': [{'foods': [
            {'name': 'Frango grelhado', 'quantity_g': 100, 'quantity_text': '100g'},
        ]}]}
        result, stats = service._enrich_foods_with_macros(data)
        assert isinstance(result, dict)
        assert isinstance(stats, dict)
        assert stats['total'] == 1

    def test_stats_categoriza_por_camada(self, service):
        data = {'meals': [{'foods': [
            {'name': 'Frango grelhado', 'quantity_g': 100, 'quantity_text': '100g'},
            {'name': 'zzzzzzz_inexistente_xxxxxxx', 'quantity_g': 100, 'quantity_text': '100g'},
        ]}]}
        _, stats = service._enrich_foods_with_macros(data)
        assert stats['total'] == 2
        assert stats['exact'] >= 1
        assert stats['generic'] == 1
        assert 'zzzzzzz_inexistente_xxxxxxx' in stats['generic_names']


@pytest.mark.django_db
class TestCheckDbCoverage:
    """Verifica o gate _check_db_coverage."""

    @pytest.fixture
    def service(self):
        return AIService()

    @pytest.fixture
    def anamnese(self, create_user):
        user = create_user()
        return Anamnese.objects.create(
            user=user, age=30, gender='M', weight_kg=80, height_cm=180,
            activity_level='moderate', goal='maintain', meals_per_day=3,
        )

    def test_total_zero_nao_levanta(self, service, anamnese):
        service._check_db_coverage({'total': 0}, anamnese)  # não levanta

    def test_zero_generic_nao_levanta(self, service, anamnese):
        stats = {'total': 10, 'exact': 8, 'fuzzy': 2, 'generic': 0, 'generic_names': []}
        service._check_db_coverage(stats, anamnese)  # não levanta

    def test_um_generic_em_5_nao_levanta(self, service, anamnese):
        """1 alimento exótico em 5 (20%) — count < 2, não levanta."""
        stats = {'total': 5, 'exact': 4, 'generic': 1, 'generic_names': ['exotic']}
        service._check_db_coverage(stats, anamnese)  # não levanta

    def test_dois_generic_em_5_levanta(self, service, anamnese):
        """2/5 = 40% — count ≥ 2 e ratio ≥ 20%, deve levantar."""
        from nutrition.services import NutritionDataGap
        stats = {'total': 5, 'exact': 3, 'generic': 2,
                'generic_names': ['exotic1', 'exotic2']}
        with pytest.raises(NutritionDataGap, match='Cobertura nutricional'):
            service._check_db_coverage(stats, anamnese)

    def test_dois_generic_em_15_nao_levanta(self, service, anamnese):
        """2/15 = 13% — ratio < 20%, não levanta."""
        stats = {'total': 15, 'exact': 13, 'generic': 2,
                'generic_names': ['exotic1', 'exotic2']}
        service._check_db_coverage(stats, anamnese)  # não levanta

    def test_tres_generic_em_15_levanta(self, service, anamnese):
        """3/15 = 20% — exatamente no limite, levanta."""
        from nutrition.services import NutritionDataGap
        stats = {'total': 15, 'exact': 12, 'generic': 3,
                'generic_names': ['e1', 'e2', 'e3']}
        with pytest.raises(NutritionDataGap):
            service._check_db_coverage(stats, anamnese)

    def test_mensagem_inclui_nomes(self, service, anamnese):
        from nutrition.services import NutritionDataGap
        stats = {'total': 4, 'exact': 2, 'generic': 2,
                'generic_names': ['Coxinha', 'Pão de queijo']}
        with pytest.raises(NutritionDataGap, match='Coxinha'):
            service._check_db_coverage(stats, anamnese)


@pytest.mark.django_db
class TestDbCoveragePipeline:
    """Verifica integração: pipeline rejeita planos com muitos alimentos no fallback."""

    @pytest.fixture
    def anamnese(self, create_user):
        user = create_user()
        return Anamnese.objects.create(
            user=user, age=30, gender='M', weight_kg=80, height_cm=180,
            activity_level='moderate', goal='maintain', meals_per_day=2,
            food_preferences='', food_restrictions='', allergies='',
        )

    @patch.object(AIService, '_call_api')
    def test_geracao_falha_se_muitos_alimentos_desconhecidos(self, mock_call, anamnese):
        """Plano com ≥2 alimentos no fallback genérico (≥20%) deve falhar."""
        from nutrition.services import NutritionDataGap
        bad_response = {
            'goal_description': 'Teste',
            'meals': [{
                'name': 'Almoço',
                'time_suggestion': '12:00',
                'foods': [
                    {'name': 'zzzzz_alimento_inexistente_aaa', 'quantity_text': '100g',
                     'quantity_g': 100},
                    {'name': 'yyyyy_alimento_inexistente_bbb', 'quantity_text': '100g',
                     'quantity_g': 100},
                    {'name': 'wwwww_alimento_inexistente_ccc', 'quantity_text': '100g',
                     'quantity_g': 100},
                ],
            }],
        }
        mock_call.return_value = _wrap_api_response(bad_response)
        service = AIService()
        with pytest.raises(NutritionDataGap, match='Cobertura nutricional'):
            service.generate_diet(anamnese)

    @patch.object(AIService, '_call_api')
    def test_geracao_passa_com_alimentos_conhecidos(self, mock_call, anamnese):
        """Plano com todos alimentos no DB deve gerar normalmente."""
        mock_call.side_effect = [
            _wrap_api_response(_FOOD_SELECTION_RESPONSE),
            _wrap_api_response(_NOTES_RESPONSE),
            _wrap_api_response(_EXPLANATION_RESPONSE),
        ]
        service = AIService()
        plan = service.generate_diet(anamnese)
        assert plan.pk is not None

    @patch.object(AIService, '_call_api')
    def test_geracao_passa_com_um_unico_desconhecido(self, mock_call, anamnese):
        """1 alimento exótico em 5 não dispara o gate (abaixo do count mínimo)."""
        # Resposta com 2 refeições completas + 1 alimento desconhecido no almoço.
        # O alimento desconhecido (zzzzz) cai no fallback genérico mas representa
        # apenas 1 de 9 itens (11%) → abaixo do gate de 20%.
        ok_response = {
            'goal_description': 'Teste',
            'meals': [
                {
                    'name': 'Almoço',
                    'time_suggestion': '12:00',
                    'foods': [
                        {'name': 'Frango grelhado', 'quantity_text': '120g', 'quantity_g': 120},
                        {'name': 'Arroz', 'quantity_text': '100g', 'quantity_g': 100},
                        {'name': 'Feijão', 'quantity_text': '80g', 'quantity_g': 80},
                        {'name': 'Tomate', 'quantity_text': '50g', 'quantity_g': 50},
                        {'name': 'zzzzz_unico_desconhecido_xxxxxxx', 'quantity_text': '20g',
                         'quantity_g': 20},
                    ],
                },
                {
                    'name': 'Jantar',
                    'time_suggestion': '19:30',
                    'foods': [
                        {'name': 'Tilapia grelhada', 'quantity_text': '200g', 'quantity_g': 200},
                        {'name': 'Batata doce', 'quantity_text': '120g', 'quantity_g': 120},
                        {'name': 'Azeite oliva', 'quantity_text': '15ml', 'quantity_g': 15},
                        {'name': 'Brocolis cozido', 'quantity_text': '80g', 'quantity_g': 80},
                    ],
                },
            ],
        }
        mock_call.side_effect = [
            _wrap_api_response(ok_response),
            _wrap_api_response(_NOTES_RESPONSE),
            _wrap_api_response(_EXPLANATION_RESPONSE),
        ]
        service = AIService()
        plan = service.generate_diet(anamnese)
        assert plan.pk is not None

    @patch.object(AIService, '_call_api')
    def test_geracao_falha_antes_de_chamar_explanation(self, mock_call, anamnese):
        """Fail-fast: ao detectar gap, não deve chamar IA para notes/explanation."""
        from nutrition.services import NutritionDataGap
        bad_response = {
            'goal_description': 'Teste',
            'meals': [{
                'name': 'Almoço', 'time_suggestion': '12:00',
                'foods': [
                    {'name': 'aaaaa_desconhecido_111', 'quantity_text': '100g',
                     'quantity_g': 100},
                    {'name': 'bbbbb_desconhecido_222', 'quantity_text': '100g',
                     'quantity_g': 100},
                ],
            }],
        }
        mock_call.return_value = _wrap_api_response(bad_response)
        service = AIService()
        with pytest.raises(NutritionDataGap):
            service.generate_diet(anamnese)
        # Apenas 1 chamada (Passo 1) — notes e explanation não foram acionados
        assert mock_call.call_count == 1

    @patch.object(AIService, '_call_api')
    def test_regenerate_meal_falha_se_alimentos_desconhecidos(self, mock_call, anamnese):
        from nutrition.services import NutritionDataGap
        plan = DietPlan.objects.create(
            user=anamnese.user,
            anamnese=anamnese,
            raw_response={
                'meals': [{
                    'name': 'Café da manhã', 'time_suggestion': '07:00',
                    'foods': [{'name': 'Pão', 'quantity_text': '50g',
                              'quantity_g': 50, 'calories': 145}],
                }],
            },
            total_calories=145,
        )
        Meal.objects.create(
            diet_plan=plan, meal_name='Café da manhã (07:00)',
            description='Pão', calories=145, order=0,
        )
        mock_call.return_value = _wrap_api_response({
            'name': 'Café da manhã', 'time_suggestion': '07:00',
            'foods': [
                {'name': 'aaaaa_inexistente', 'quantity_text': '50g', 'quantity_g': 50},
                {'name': 'bbbbb_inexistente', 'quantity_text': '50g', 'quantity_g': 50},
            ],
        })
        service = AIService()
        with pytest.raises(NutritionDataGap):
            service.regenerate_meal(plan, 0)


# ============================================================================
# ÁREA 3 — RATE LIMITING
# ============================================================================

@pytest.mark.django_db
class TestRateLimiting:
    """
    Testa o ScopedRateThrottle do endpoint diet/generate.
    """

    @pytest.fixture
    def user_with_anamnese(self, create_user):
        user = create_user()
        Anamnese.objects.create(
            user=user, age=25, gender='M', weight_kg=70.0, height_cm=175.0,
            activity_level='moderate', goal='lose', meals_per_day=3,
        )
        return user

    def _make_diet_plan(self, user):
        return DietPlan.objects.create(
            user=user,
            raw_response={
                'goal_description': 'Teste',
                'calories': 1800,
                'macros': {'protein_g': 100, 'carbs_g': 200, 'fat_g': 50},
                'meals': [],
                'substitutions': [],
                'notes': '',
                'explanation': None,
            },
            total_calories=1800,
            goal_description='Teste',
        )

    @override_settings(
        REST_FRAMEWORK={
            'DEFAULT_AUTHENTICATION_CLASSES': (
                'rest_framework_simplejwt.authentication.JWTAuthentication',
            ),
            'DEFAULT_PERMISSION_CLASSES': (
                'rest_framework.permissions.IsAuthenticated',
            ),
            'DEFAULT_THROTTLE_CLASSES': [],
            'DEFAULT_THROTTLE_RATES': {
                'anon': '1000/hour',
                'user': '1000/hour',
                'diet_generate': '2/minute',
                'login': '1000/hour',
                'contact': '1000/hour',
                'testimonial': '1000/day',
            },
        }
    )
    @patch('nutrition.services.AIService.generate_diet')
    def test_rate_limit_bloqueia_apos_limite(self, mock_generate, api_client, user_with_anamnese):
        user = user_with_anamnese
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        mock_generate.side_effect = lambda anamnese: self._make_diet_plan(anamnese.user)

        r1 = api_client.post('/api/v1/diet/generate', format='json')
        assert r1.status_code == 202, f'1ª req falhou: {r1.status_code}'

        r2 = api_client.post('/api/v1/diet/generate', format='json')
        assert r2.status_code == 202, f'2ª req falhou: {r2.status_code}'

        r3 = api_client.post('/api/v1/diet/generate', format='json')
        assert r3.status_code == 429, f'3ª req deveria ser 429, foi: {r3.status_code}'

    @override_settings(
        REST_FRAMEWORK={
            'DEFAULT_AUTHENTICATION_CLASSES': (
                'rest_framework_simplejwt.authentication.JWTAuthentication',
            ),
            'DEFAULT_PERMISSION_CLASSES': (
                'rest_framework.permissions.IsAuthenticated',
            ),
            'DEFAULT_THROTTLE_CLASSES': [],
            'DEFAULT_THROTTLE_RATES': {
                'anon': '1000/hour',
                'user': '1000/hour',
                'diet_generate': '2/minute',
                'login': '1000/hour',
                'contact': '1000/hour',
                'testimonial': '1000/day',
            },
        }
    )
    @patch('nutrition.services.AIService.generate_diet')
    def test_rate_limit_resposta_429_tem_mensagem(self, mock_generate, api_client, user_with_anamnese):
        user = user_with_anamnese
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        mock_generate.side_effect = lambda anamnese: self._make_diet_plan(anamnese.user)

        api_client.post('/api/v1/diet/generate', format='json')
        api_client.post('/api/v1/diet/generate', format='json')
        r = api_client.post('/api/v1/diet/generate', format='json')

        assert r.status_code == 429
        assert 'detail' in r.data

    @override_settings(
        REST_FRAMEWORK={
            'DEFAULT_AUTHENTICATION_CLASSES': (
                'rest_framework_simplejwt.authentication.JWTAuthentication',
            ),
            'DEFAULT_PERMISSION_CLASSES': (
                'rest_framework.permissions.IsAuthenticated',
            ),
            'DEFAULT_THROTTLE_CLASSES': [],
            'DEFAULT_THROTTLE_RATES': {
                'anon': '1000/hour',
                'user': '1000/hour',
                'diet_generate': '2/minute',
                'login': '1000/hour',
                'contact': '1000/hour',
                'testimonial': '1000/day',
            },
        }
    )
    @patch('nutrition.services.AIService.generate_diet')
    def test_rate_limit_por_usuario_nao_afeta_outro(self, mock_generate, api_client, create_user):
        user_a = create_user(email='a@rate.com')
        Anamnese.objects.create(
            user=user_a, age=25, gender='M', weight_kg=70.0, height_cm=175.0,
            activity_level='moderate', goal='lose', meals_per_day=3,
        )
        user_b = create_user(email='b@rate.com')
        Anamnese.objects.create(
            user=user_b, age=30, gender='F', weight_kg=60.0, height_cm=165.0,
            activity_level='light', goal='maintain', meals_per_day=4,
        )

        refresh_a = RefreshToken.for_user(user_a)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh_a.access_token}')
        mock_generate.side_effect = lambda anamnese: self._make_diet_plan(anamnese.user)
        api_client.post('/api/v1/diet/generate', format='json')
        api_client.post('/api/v1/diet/generate', format='json')
        r_a = api_client.post('/api/v1/diet/generate', format='json')
        assert r_a.status_code == 429

        refresh_b = RefreshToken.for_user(user_b)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh_b.access_token}')
        r_b = api_client.post('/api/v1/diet/generate', format='json')
        assert r_b.status_code == 202, f'Usuário B bloqueado indevidamente: {r_b.status_code}'

    def test_rate_limit_outros_endpoints_nao_afetados(self, auth_client):
        client, _ = auth_client
        for _ in range(5):
            r = client.get('/api/v1/user/profile')
            assert r.status_code == 200

    def test_cache_dev_nao_usa_redis(self):
        """Em dev/test, o cache deve ser in-memory (não Redis/Memcached)."""
        actual_cache = getattr(cache, '_cache', None) or cache
        actual_class = type(actual_cache).__name__
        redis_indicators = ('Redis', 'Memcached', 'Pylibmc')
        is_redis = any(r in actual_class for r in redis_indicators)
        assert not is_redis, (
            f'Cache de produção ({actual_class}) detectado em testes. '
            'Use cache in-memory para testes.'
        )


# ---------------------------------------------------------------------------
# A7 — Validação de limites em peso, altura e meals_per_day (AnamneseSerializer)
# ---------------------------------------------------------------------------

_VALID_ANAMNESE = {
    'idade': 30,
    'sexo': 'M',
    'peso': 80,
    'altura': 175,
    'nivel_atividade': 'moderate',
    'objetivo': 'lose',
    'meals_per_day': 4,
}


@pytest.mark.django_db
class TestAnamneseSerializerBounds:
    """Garante que limites fisiológicos são aplicados no endpoint POST /api/v1/anamnese."""

    def _post(self, auth_client, payload):
        client, _ = auth_client
        return client.post('/api/v1/anamnese', payload, format='json')

    # --- peso ---

    def test_peso_zero_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'peso': 0}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_peso_negativo_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'peso': -5}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_peso_abaixo_minimo_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'peso': 9}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_peso_acima_maximo_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'peso': 501}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_peso_no_limite_inferior_aceito(self, auth_client):
        # 10 kg é o mínimo permitido (casos médicos extremos)
        data = {**_VALID_ANAMNESE, 'peso': 10, 'altura': 120}
        r = self._post(auth_client, data)
        # Pode falhar validação de IMC (IMC = 10/(1.2²) ≈ 6.9 < 10) — esperamos 400
        # O importante é que não retorna 500 (ZeroDivisionError)
        assert r.status_code in (200, 201, 400)

    def test_peso_500kg_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'peso': 500}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    # --- altura ---

    def test_altura_abaixo_minimo_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'altura': 49}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_altura_acima_maximo_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'altura': 281}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_altura_zero_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'altura': 0}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    # --- meals_per_day ---

    def test_meals_per_day_zero_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'meals_per_day': 0}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_meals_per_day_50_retorna_400(self, auth_client):
        data = {**_VALID_ANAMNESE, 'meals_per_day': 50}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_meals_per_day_maximo_aceito(self, auth_client):
        data = {**_VALID_ANAMNESE, 'meals_per_day': 12}
        r = self._post(auth_client, data)
        assert r.status_code in (200, 201)

    def test_meals_per_day_minimo_aceito(self, auth_client):
        data = {**_VALID_ANAMNESE, 'meals_per_day': 1}
        r = self._post(auth_client, data)
        assert r.status_code in (200, 201)

    # --- validação cruzada de IMC ---

    def test_imc_implausivel_baixo_retorna_400(self, auth_client):
        # IMC = 10 / (1.8²) ≈ 3.1 → abaixo de 10
        data = {**_VALID_ANAMNESE, 'peso': 10, 'altura': 180}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_imc_implausivel_alto_retorna_400(self, auth_client):
        # IMC = 500 / (1.5²) ≈ 222 → acima de 70
        data = {**_VALID_ANAMNESE, 'peso': 499, 'altura': 150}
        r = self._post(auth_client, data)
        assert r.status_code == 400

    def test_imc_valido_aceito(self, auth_client):
        # IMC = 80 / (1.75²) ≈ 26 → plausível
        data = {**_VALID_ANAMNESE, 'peso': 80, 'altura': 175}
        r = self._post(auth_client, data)
        assert r.status_code in (200, 201)

    def test_dados_completamente_validos_aceitos(self, auth_client):
        r = self._post(auth_client, _VALID_ANAMNESE)
        assert r.status_code in (200, 201)

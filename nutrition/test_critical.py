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
from nutrition.services import AIService
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


# Resposta mínima válida do Passo 1 (seleção de alimentos)
_FOOD_SELECTION_RESPONSE = {
    'goal_description': 'Emagrecimento saudável',
    'meals': [
        {
            'name': 'Café da manhã',
            'time_suggestion': '07:00',
            'foods': [
                {'name': 'Ovos mexidos', 'quantity_text': '3 unidades', 'quantity_g': 150},
                {'name': 'Pão francês', 'quantity_text': '1 unidade', 'quantity_g': 50},
            ],
        },
        {
            'name': 'Almoço',
            'time_suggestion': '12:00',
            'foods': [
                {'name': 'Frango grelhado', 'quantity_text': '1 filé (120g)', 'quantity_g': 120},
                {'name': 'Arroz branco', 'quantity_text': '4 col. sopa', 'quantity_g': 120},
                {'name': 'Feijão cozido', 'quantity_text': '2 conchas', 'quantity_g': 100},
            ],
        },
    ],
    'substitutions': [
        {'food': 'Pão francês', 'alternatives': ['Tapioca', 'Cuscuz']},
    ],
    'notes': 'Beba pelo menos 2 litros de água por dia.',
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

    def test_passo1_usa_temperature_baixo(self, anamnese_obj):
        """Passo 1 (seleção de alimentos) deve usar temperature <= 0.4 para consistência."""
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

        assert captured[0].get('temperature', 1.0) <= 0.4

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
        with pytest.raises(ValueError, match='formato inesperado'):
            service._parse_response(self._wrap('isso não é json {'))

    def test_parse_sem_choices_levanta_value_error(self, service):
        with pytest.raises(ValueError):
            service._parse_response({})

    def test_parse_choices_vazio_levanta_value_error(self, service):
        with pytest.raises(ValueError):
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

    def test_lookup_alimento_desconhecido_retorna_fallback(self):
        from nutrition.nutrition_db import lookup_food_nutrition
        r = lookup_food_nutrition('Alimento completamente desconhecido xyz', 100)
        assert r['calories'] > 0  # fallback genérico

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
        """Divergência > 10% deve escalar quantity_g."""
        data = {
            'calories': 1000,
            'meals': [{'foods': [
                {'name': 'Frango grelhado', 'quantity_g': 100, 'quantity_text': '100g',
                 'calories': 1000, 'protein_g': 32, 'carbs_g': 0, 'fat_g': 3},
            ]}],
        }
        result = service._adjust_to_calorie_target(data, target_calories=2000)
        # quantity_g deve ter dobrado (scale ≈ 2.0)
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
        """Retorna side_effects para os dois _call_api calls."""
        return [
            _wrap_api_response(_FOOD_SELECTION_RESPONSE),   # Passo 1
            _wrap_api_response(_EXPLANATION_RESPONSE),      # Passo 2
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
        """Se a geração de explicação falhar, o DietPlan deve ser criado mesmo assim."""
        # Passo 1 ok, Passo 2 falha
        mock_call.side_effect = [
            _wrap_api_response(_FOOD_SELECTION_RESPONSE),
            Exception('API unavailable'),
        ]
        service = AIService()
        diet_plan = service.generate_diet(anamnese_obj)

        # Plan foi criado mesmo sem explanation
        assert diet_plan.pk is not None
        assert diet_plan.raw_response.get('explanation') is None

    @patch.object(AIService, '_call_api')
    def test_pipeline_dois_calls_a_api(self, mock_call, anamnese_obj):
        """O pipeline deve realizar exatamente 2 chamadas à API."""
        mock_call.side_effect = self._make_api_side_effects()
        service = AIService()
        service.generate_diet(anamnese_obj)
        assert mock_call.call_count == 2

    @patch.object(AIService, '_call_api')
    def test_pipeline_refeicoes_sem_foods_levanta_erro(self, mock_call, anamnese_obj):
        """Resposta da IA sem meals deve levantar ValueError."""
        mock_call.return_value = _wrap_api_response({'goal_description': 'Teste', 'meals': []})
        service = AIService()
        with pytest.raises(ValueError, match='refeições válidas'):
            service.generate_diet(anamnese_obj)


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

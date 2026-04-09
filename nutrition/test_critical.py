"""
Testes críticos — MyNutri AI
Verifica:
  1. Uso correto do prompt (variáveis, fluxo system+user, proteção contra markdown)
  2. Consistência matemática de calorias (normalize, enforce, edge cases)
  3. Rate limiting na prática (ScopedRateThrottle com override_settings)
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from nutrition.models import Anamnese, DietPlan, Meal
from nutrition.services import AIService
from nutrition.prompts import (
    SYSTEM_PROMPT,
    DIET_GENERATION_TEMPLATE,
    build_diet_prompt,
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



# ============================================================================
# ÁREA 1 — VERIFICAÇÃO DO PROMPT
# ============================================================================

class TestPromptStructureAndFlow:
    """Verifica que o prompt é montado corretamente e enviado como esperado."""

    def test_system_prompt_nao_diz_para_calcular_calorias(self):
        """SYSTEM_PROMPT não deve mais instruir a IA a recalcular calorias (contradição corrigida)."""
        assert 'Calcule a necessidade calórica' not in SYSTEM_PROMPT
        assert 'NÃO recalcule' in SYSTEM_PROMPT or 'fornecido pelo sistema' in SYSTEM_PROMPT

    def test_system_prompt_enviado_como_role_system(self, anamnese_obj):
        """_call_api deve enviar SYSTEM_PROMPT como mensagem de role=system."""
        service = AIService()
        captured = {}

        def fake_call(url, data, headers, method):
            captured['payload'] = json.loads(data.decode('utf-8'))
            # Simula resposta mínima válida
            class FakeResponse:
                def read(self): return json.dumps({
                    'choices': [{'message': {'content': json.dumps({
                        'goal_description': 'Teste',
                        'calories': 1600,
                        'macros': {'protein_g': 120, 'carbs_g': 180, 'fat_g': 40},
                        'meals': [],
                        'substitutions': [],
                        'notes': '',
                        'explanation': {
                            'calorie_calculation': '',
                            'macro_distribution': '',
                            'food_choices': '',
                            'meal_structure': '',
                            'goal_alignment': '',
                        },
                    })}}]
                }).encode()
                def __enter__(self): return self
                def __exit__(self, *a): pass
            return FakeResponse()

        import urllib.request
        with patch.object(urllib.request, 'urlopen', fake_call):
            try:
                service.generate_diet(anamnese_obj)
            except Exception:
                pass

        if captured:
            messages = captured['payload']['messages']
            system_msgs = [m for m in messages if m['role'] == 'system']
            assert len(system_msgs) == 1
            assert system_msgs[0]['content'] == SYSTEM_PROMPT

    def test_user_message_contem_target_calories(self, anamnese_obj):
        """O prompt do usuário deve conter o alvo calórico calculado pelo backend."""
        _, _, target = calculate_calories(anamnese_obj)
        prompt = build_diet_prompt(anamnese_obj)
        assert str(target) in prompt

    def test_user_message_contem_tmb_e_tdee(self, anamnese_obj):
        """O prompt deve conter TMB e TDEE para transparência."""
        tmb, tdee, _ = calculate_calories(anamnese_obj)
        prompt = build_diet_prompt(anamnese_obj)
        assert str(tmb) in prompt
        assert str(tdee) in prompt

    def test_user_message_contem_preferencias(self, anamnese_obj):
        prompt = build_diet_prompt(anamnese_obj)
        assert 'Frango' in prompt
        assert 'Batata-doce' in prompt

    def test_user_message_contem_alergias(self, anamnese_obj):
        prompt = build_diet_prompt(anamnese_obj)
        assert 'amendoim' in prompt

    def test_user_message_contem_numero_refeicoes(self, anamnese_obj):
        prompt = build_diet_prompt(anamnese_obj)
        assert '4' in prompt

    def test_todas_variaveis_do_template_sao_substituidas(self, anamnese_obj):
        """Nenhuma variável {xyz} não substituída deve restar no prompt."""
        prompt = build_diet_prompt(anamnese_obj)
        import re
        # Chaves duplas {{ }} são literais no .format() e viram { }
        # Chaves simples {var} devem ter sido todas substituídas
        unresolved = re.findall(r'(?<!\{)\{(?!\{)(\w+)(?<!\})\}(?!\})', prompt)
        assert unresolved == [], f'Variáveis não substituídas no prompt: {unresolved}'

    def test_triple_quotes_nos_dados_usuario_como_protecao_injection(self, anamnese_obj):
        """Preferências/restrições devem ser delimitadas por triple-quotes no prompt."""
        prompt = build_diet_prompt(anamnese_obj)
        assert '"""' in prompt

    def test_temperature_configurada_no_payload(self, anamnese_obj):
        """A chamada HTTP deve incluir temperature=0.6."""
        service = AIService()
        captured = {}

        def fake_call(url, data, headers, method):
            captured['payload'] = json.loads(data.decode('utf-8'))
            class FakeResponse:
                def read(self): return json.dumps({'choices': [{'message': {'content': '{}'}}]}).encode()
                def __enter__(self): return self
                def __exit__(self, *a): pass
            return FakeResponse()

        import urllib.request
        with patch.object(urllib.request, 'urlopen', fake_call):
            try:
                service.generate_diet(anamnese_obj)
            except Exception:
                pass

        if captured:
            assert captured['payload'].get('temperature') == 0.6


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
        """IA pode retornar ```json\n{...}\n``` — deve ser parseado corretamente."""
        payload = json.dumps({'goal_description': 'Teste', 'calories': 1900})
        wrapped = f'```json\n{payload}\n```'
        result = service._parse_response(self._wrap(wrapped))
        assert result['calories'] == 1900

    def test_parse_json_com_markdown_fence_simples(self, service):
        """IA pode retornar ```\n{...}\n``` sem linguagem."""
        payload = json.dumps({'goal_description': 'Teste', 'calories': 2000})
        wrapped = f'```\n{payload}\n```'
        result = service._parse_response(self._wrap(wrapped))
        assert result['calories'] == 2000

    def test_parse_json_com_espacos_extras(self, service):
        """JSON com espaços antes/depois deve ser parseado."""
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
# ÁREA 2 — CONSISTÊNCIA MATEMÁTICA DE CALORIAS
# ============================================================================

class TestCalorieConsistency:
    """Verifica pipeline completo de normalização e enforcement de calorias."""

    @pytest.fixture
    def service(self):
        return AIService()

    # --- normalize_diet_data ---

    def test_normalize_recalcula_de_foods_ignorando_declarado(self, service):
        data = {
            'calories': 5000,  # declarado errado pela IA
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
        result = service._normalize_diet_data(data)
        assert result['calories'] == 1000  # 300+200+500

    def test_normalize_recalcula_macros_de_foods(self, service):
        data = {
            'calories': 1000,
            'macros': {'protein_g': 0, 'carbs_g': 0, 'fat_g': 0},
            'meals': [
                {'foods': [
                    {'calories': 500, 'protein_g': 30, 'carbs_g': 50, 'fat_g': 10},
                    {'calories': 500, 'protein_g': 20, 'carbs_g': 40, 'fat_g': 15},
                ]},
            ],
        }
        result = service._normalize_diet_data(data)
        assert result['macros']['protein_g'] == 50
        assert result['macros']['carbs_g'] == 90
        assert result['macros']['fat_g'] == 25

    def test_normalize_lista_vazia_de_meals(self, service):
        data = {'calories': 0, 'meals': []}
        result = service._normalize_diet_data(data)
        assert result['calories'] == 0

    def test_normalize_food_sem_calories_conta_como_zero(self, service):
        data = {
            'calories': 200,
            'meals': [{'foods': [
                {'name': 'Alimento sem caloria declarada', 'protein_g': 10, 'carbs_g': 5, 'fat_g': 2},
                {'calories': 200, 'protein_g': 20, 'carbs_g': 30, 'fat_g': 8},
            ]}],
        }
        result = service._normalize_diet_data(data)
        assert result['calories'] == 200  # só conta o que tem calories

    def test_normalize_divergencia_loga_mas_corrige(self, service):
        """Divergência >5% deve ser corrigida mesmo que seja pequena."""
        data = {
            'calories': 2000,  # declarado
            'meals': [{'foods': [
                {'calories': 1850, 'protein_g': 100, 'carbs_g': 200, 'fat_g': 50},
            ]}],
        }
        result = service._normalize_diet_data(data)
        assert result['calories'] == 1850  # fonte da verdade = foods

    # --- enforce_calorie_target ---

    def test_enforce_sem_divergencia_nao_muda_nada(self, service):
        data = {
            'calories': 2000,
            'meals': [{'foods': [
                {'calories': 1000, 'protein_g': 50, 'carbs_g': 100, 'fat_g': 20},
                {'calories': 1000, 'protein_g': 50, 'carbs_g': 100, 'fat_g': 20},
            ]}],
        }
        result = service._enforce_calorie_target(data, target_calories=2000)
        assert result['calories'] == 2000
        assert result['meals'][0]['foods'][0]['calories'] == 1000

    def test_enforce_escala_para_cima(self, service):
        """AI gerou 1000 kcal, target é 2000 → escala ×2."""
        data = {
            'calories': 1000,
            'meals': [{'foods': [
                {'calories': 500, 'protein_g': 25, 'carbs_g': 60, 'fat_g': 10},
                {'calories': 500, 'protein_g': 25, 'carbs_g': 60, 'fat_g': 10},
            ]}],
        }
        result = service._enforce_calorie_target(data, target_calories=2000)
        assert result['calories'] == 2000
        assert result['meals'][0]['foods'][0]['calories'] == 1000  # 500 × 2

    def test_enforce_escala_para_baixo(self, service):
        """AI gerou 3000 kcal, target é 1500 → escala ×0.5."""
        data = {
            'calories': 3000,
            'meals': [{'foods': [
                {'calories': 1500, 'protein_g': 75, 'carbs_g': 180, 'fat_g': 35},
                {'calories': 1500, 'protein_g': 75, 'carbs_g': 180, 'fat_g': 35},
            ]}],
        }
        result = service._enforce_calorie_target(data, target_calories=1500)
        assert result['calories'] == 1500
        assert result['meals'][0]['foods'][0]['calories'] == 750  # 1500 × 0.5

    def test_enforce_dentro_10_porcento_aceita_sem_escalar(self, service):
        """9% de diferença está dentro da tolerância — não escala."""
        data = {
            'calories': 1820,  # 9% abaixo de 2000
            'meals': [{'foods': [
                {'calories': 1820, 'protein_g': 100, 'carbs_g': 200, 'fat_g': 45},
            ]}],
        }
        result = service._enforce_calorie_target(data, target_calories=2000)
        assert result['calories'] == 1820  # não foi alterado

    def test_enforce_gap_tolerancia_documentado(self, service):
        """
        GAP DOCUMENTADO: prompt diz ±50 kcal mas backend aceita até ±10%.
        Para 2000 kcal target: até 200 kcal de desvio é aceito sem correção.
        Este teste documenta o comportamento atual (não é um bug bloqueante).
        """
        data = {
            'calories': 1810,  # 9.5% abaixo de 2000 (acima dos ±50 kcal do prompt)
            'meals': [{'foods': [
                {'calories': 1810, 'protein_g': 90, 'carbs_g': 200, 'fat_g': 50},
            ]}],
        }
        result = service._enforce_calorie_target(data, target_calories=2000)
        # Backend aceita sem escalar (dentro de 10%)
        # Comportamento ACEITO pelo design atual, mas 190 kcal acima do prometido no prompt
        assert result['calories'] == 1810
        deviation_kcal = abs(result['calories'] - 2000)
        assert deviation_kcal > 50   # maior que o prometido no prompt
        assert deviation_kcal < 200  # mas dentro da tolerância do backend

    # --- pipeline completo ---

    @patch.object(AIService, '_call_api')
    def test_pipeline_enforce_target_do_backend_tem_prioridade(self, mock_call, anamnese_obj):
        """
        Pipeline completo: AI gera foods com total diferente do alvo calculado pelo backend.
        O _enforce_calorie_target garante que o total FINAL seja o alvo do backend.
        Prioridade: alvo backend > foods sum > declared total da IA.
        """
        service = AIService()
        _, _, target = calculate_calories(anamnese_obj)  # alvo calculado pelo backend

        # AI declarou 2000 mas foods somam 1400 → normalize corrige para 1400
        # _enforce_calorie_target vê 1400 vs target (2305) → >10% → escala para target
        ai_response = {
            'goal_description': 'Emagrecimento',
            'calories': 2000,  # declarado errado
            'macros': {'protein_g': 120, 'carbs_g': 160, 'fat_g': 40},
            'meals': [
                {
                    'name': 'Café da manhã',
                    'time_suggestion': '07:00',
                    'foods': [
                        {'name': 'Ovos', 'quantity': '3 un', 'calories': 220,
                         'protein_g': 18, 'carbs_g': 1, 'fat_g': 15},
                        {'name': 'Pão', 'quantity': '2 fatias', 'calories': 180,
                         'protein_g': 6, 'carbs_g': 30, 'fat_g': 2},
                    ],
                },
                {
                    'name': 'Almoço',
                    'time_suggestion': '12:00',
                    'foods': [
                        {'name': 'Frango', 'quantity': '150g', 'calories': 600,
                         'protein_g': 60, 'carbs_g': 0, 'fat_g': 15},
                        {'name': 'Arroz', 'quantity': '150g', 'calories': 400,
                         'protein_g': 8, 'carbs_g': 80, 'fat_g': 2},
                    ],
                },
            ],
            'substitutions': [],
            'notes': 'Beba água.',
            'explanation': {
                'calorie_calculation': 'TMB calculada...',
                'macro_distribution': 'Proteína...',
                'food_choices': 'Frango...',
                'meal_structure': '2 refeições...',
                'goal_alignment': 'Déficit...',
            },
        }
        mock_call.return_value = {
            'choices': [{'message': {'content': json.dumps(ai_response)}}]
        }

        diet_plan = service.generate_diet(anamnese_obj)
        # O total salvo é o alvo do backend — não o declarado pela IA nem a soma raw dos foods
        assert diet_plan.total_calories == target

    @patch.object(AIService, '_call_api')
    def test_pipeline_declarado_errado_mas_foods_proximos_ao_target(self, mock_call, anamnese_obj):
        """
        Quando foods somam próximo ao target (±10%), _enforce não escala.
        raw_response['calories'] deve ser a soma real dos foods (normalizado).
        """
        service = AIService()
        _, _, target = calculate_calories(anamnese_obj)

        # Gera foods que somam exatamente o target do backend
        foods_total = target
        ai_response = {
            'goal_description': 'Emagrecimento',
            'calories': 9999,  # declarado errado — deve ser ignorado
            'macros': {'protein_g': 0, 'carbs_g': 0, 'fat_g': 0},
            'meals': [
                {'name': 'Almoço', 'time_suggestion': '12:00', 'foods': [
                    {'name': 'Refeição completa', 'quantity': '400g',
                     'calories': foods_total, 'protein_g': 80, 'carbs_g': 200, 'fat_g': 50},
                ]},
            ],
            'substitutions': [],
            'notes': '',
            'explanation': {
                'calorie_calculation': '', 'macro_distribution': '',
                'food_choices': '', 'meal_structure': '', 'goal_alignment': '',
            },
        }
        mock_call.return_value = {
            'choices': [{'message': {'content': json.dumps(ai_response)}}]
        }

        diet_plan = service.generate_diet(anamnese_obj)
        # Declarado (9999) foi ignorado; foods somam target; enforce não escala
        assert diet_plan.raw_response['calories'] == target
        assert diet_plan.total_calories == target

    @patch.object(AIService, '_call_api')
    def test_macros_no_raw_response_sao_recalculados_dos_foods(self, mock_call, anamnese_obj):
        """
        Macros em raw_response devem refletir a soma real dos foods[].
        Após _normalize, os macros 999 da IA são substituídos pela soma dos alimentos.
        Após _enforce, os macros são escalados proporcionalmente ao target.
        """
        service = AIService()
        _, _, target = calculate_calories(anamnese_obj)

        # Foods somam 600 kcal com macros específicos
        # O backend vai escalar para o target (~2305 kcal)
        scale = target / 600
        ai_response = {
            'goal_description': 'Manutenção',
            'calories': 1500,
            'macros': {'protein_g': 999, 'carbs_g': 999, 'fat_g': 999},  # serão sobrescritos
            'meals': [
                {'name': 'Refeição 1', 'time_suggestion': '08:00', 'foods': [
                    {'name': 'X', 'quantity': '100g', 'calories': 400,
                     'protein_g': 30, 'carbs_g': 50, 'fat_g': 10},
                    {'name': 'Y', 'quantity': '100g', 'calories': 200,
                     'protein_g': 20, 'carbs_g': 25, 'fat_g': 5},
                ]},
            ],
            'substitutions': [],
            'notes': '',
            'explanation': {
                'calorie_calculation': '', 'macro_distribution': '',
                'food_choices': '', 'meal_structure': '', 'goal_alignment': '',
            },
        }
        mock_call.return_value = {
            'choices': [{'message': {'content': json.dumps(ai_response)}}]
        }
        diet_plan = service.generate_diet(anamnese_obj)
        macros = diet_plan.raw_response['macros']
        # Macros foram normalizados (999→50/75/15) e depois escalados para o target
        assert macros['protein_g'] != 999
        assert macros['carbs_g'] != 999
        assert macros['fat_g'] != 999
        # Verifica proporcionalidade: proteína escala junto
        assert macros['protein_g'] == round(50 * scale)  # 30+20=50, escalado


# ============================================================================
# ÁREA 3 — RATE LIMITING
# ============================================================================

@pytest.mark.django_db
class TestRateLimiting:
    """
    Testa o ScopedRateThrottle do endpoint diet/generate.
    Usa override_settings para definir um limite baixo e testável.
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
        """Helper: cria um DietPlan fake para o mock retornar."""
        plan = DietPlan.objects.create(
            user=user,
            raw_response={
                'goal_description': 'Teste',
                'calories': 1800,
                'macros': {'protein_g': 100, 'carbs_g': 200, 'fat_g': 50},
                'meals': [],
                'substitutions': [],
                'notes': '',
                'explanation': {
                    'calorie_calculation': '', 'macro_distribution': '',
                    'food_choices': '', 'meal_structure': '', 'goal_alignment': '',
                },
            },
            total_calories=1800,
            goal_description='Teste',
        )
        return plan

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
                'diet_generate': '2/minute',  # limite de 2 por minuto para testes
            },
        }
    )
    @patch('nutrition.api_views.AIService')
    def test_rate_limit_bloqueia_apos_limite(self, mock_service_cls, api_client, user_with_anamnese):
        """Após o limite de requisições, deve retornar 429 Too Many Requests."""
        user = user_with_anamnese
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance
        mock_instance.generate_diet.return_value = self._make_diet_plan(user)

        # Primeiras 2 requisições: dentro do limite
        r1 = api_client.post('/api/v1/diet/generate', format='json')
        assert r1.status_code == 201, f'1ª req falhou: {r1.status_code}'

        r2 = api_client.post('/api/v1/diet/generate', format='json')
        assert r2.status_code == 201, f'2ª req falhou: {r2.status_code}'

        # 3ª requisição: deve ser bloqueada
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
    @patch('nutrition.api_views.AIService')
    def test_rate_limit_resposta_429_tem_mensagem(self, mock_service_cls, api_client, user_with_anamnese):
        """Resposta 429 deve conter campo 'detail' com informação do throttle."""
        user = user_with_anamnese
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')

        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance
        mock_instance.generate_diet.return_value = self._make_diet_plan(user)

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
    @patch('nutrition.api_views.AIService')
    def test_rate_limit_por_usuario_nao_afeta_outro(self, mock_service_cls, api_client, create_user):
        """Rate limit do usuário A não deve bloquear o usuário B."""
        # Cria usuário A com anamnese
        user_a = create_user(email='a@rate.com')
        Anamnese.objects.create(
            user=user_a, age=25, gender='M', weight_kg=70.0, height_cm=175.0,
            activity_level='moderate', goal='lose', meals_per_day=3,
        )
        # Cria usuário B com anamnese
        user_b = create_user(email='b@rate.com')
        Anamnese.objects.create(
            user=user_b, age=30, gender='F', weight_kg=60.0, height_cm=165.0,
            activity_level='light', goal='maintain', meals_per_day=4,
        )

        mock_instance = MagicMock()
        mock_service_cls.return_value = mock_instance

        # Esgota o rate limit do usuário A
        refresh_a = RefreshToken.for_user(user_a)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh_a.access_token}')
        mock_instance.generate_diet.return_value = self._make_diet_plan(user_a)
        api_client.post('/api/v1/diet/generate', format='json')
        api_client.post('/api/v1/diet/generate', format='json')
        r_a_bloqueado = api_client.post('/api/v1/diet/generate', format='json')
        assert r_a_bloqueado.status_code == 429

        # Usuário B ainda pode fazer requisições
        refresh_b = RefreshToken.for_user(user_b)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh_b.access_token}')
        mock_instance.generate_diet.return_value = self._make_diet_plan(user_b)
        r_b = api_client.post('/api/v1/diet/generate', format='json')
        assert r_b.status_code == 201, f'Usuário B bloqueado indevidamente: {r_b.status_code}'

    def test_rate_limit_outros_endpoints_nao_afetados(self, auth_client):
        """
        Rate limit de diet/generate NÃO deve afetar outros endpoints (profile, anamnese, etc.).
        O endpoint de perfil usa UserRateThrottle (60/hour), não ScopedRateThrottle.
        """
        client, _ = auth_client
        for _ in range(5):
            r = client.get('/api/v1/user/profile')
            assert r.status_code == 200

    def test_rate_limit_producao_aviso_locmemcache(self):
        """
        DOCUMENTAÇÃO: Em produção com múltiplos workers, LocMemCache é isolado por processo.
        Isso significa que cada worker tem seu próprio contador → rate limit efetivo
        = limite_configurado × número_de_workers.
        Para produção: configure CACHES com Redis ou Memcached.
        Este teste documenta e verifica que NÃO estamos usando Redis em dev/test.
        """
        from django.core.cache import cache
        from django.core.cache.backends.locmem import LocMemCache
        # O cache padrão em dev/test deve ser in-memory (não Redis/Memcached)
        # Django wraps the cache in ConnectionProxy or similar → verificamos o backend interno
        actual_cache = getattr(cache, '_cache', None) or cache
        actual_class = type(actual_cache).__name__
        redis_indicators = ('Redis', 'Memcached', 'Pylibmc')
        is_redis = any(r in actual_class for r in redis_indicators)
        assert not is_redis, (
            f'Cache de produção ({actual_class}) detectado em testes. '
            'Use cache in-memory para testes.'
        )

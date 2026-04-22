"""
Testes do AIService e generate_diet_task — MyNutri AI
Cobre: _parse_response, _recalculate_totals, _adjust_to_calorie_target, generate_diet,
       e o fluxo completo da task Celery (status transitions, retry logic).
A chamada HTTP (_call_api) é sempre mockada — sem dependência de API externa.
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.test import override_settings

from nutrition.models import Anamnese, DietJob, DietPlan, Meal
from nutrition.services import AIService

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def create_user(db):
    def _create(email='ai@teste.com'):
        return User.objects.create_user(
            username=email, email=email, password='senha123', first_name='Teste'
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
        food_preferences='Frango, Arroz',
        food_restrictions='',
        allergies='',
    )


@pytest.fixture
def ai_service():
    return AIService()


def _wrap_api(content_dict: dict) -> dict:
    return {'choices': [{'message': {'content': json.dumps(content_dict)}}]}


def _make_api_response(calories=1800, meals=None):
    """Resposta genérica — usada apenas em TestParseResponse."""
    if meals is None:
        meals = [
            {
                'name': 'Café da manhã',
                'time_suggestion': '07:00',
                'foods': [
                    {'name': 'Ovos', 'quantity': '3 un', 'calories': 220,
                     'protein_g': 18, 'carbs_g': 1, 'fat_g': 15},
                ],
            },
        ]
    return _wrap_api({
        'goal_description': 'Emagrecimento saudável',
        'calories': calories,
        'macros': {'protein_g': 109, 'carbs_g': 138, 'fat_g': 29},
        'meals': meals,
        'substitutions': [],
        'notes': 'Beba 2L de água.',
    })


def _make_passo1_response():
    """Resposta do Passo 1 — seleção de alimentos sem macros."""
    return _wrap_api({
        'goal_description': 'Emagrecimento saudável',
        'meals': [
            {
                'name': 'Café da manhã',
                'time_suggestion': '07:00',
                'foods': [
                    {'name': 'Ovos mexidos', 'quantity_text': '3 unidades', 'quantity_g': 150},
                    {'name': 'Pão integral', 'quantity_text': '2 fatias', 'quantity_g': 60},
                ],
            },
            {
                'name': 'Almoço',
                'time_suggestion': '12:00',
                'foods': [
                    {'name': 'Frango grelhado', 'quantity_text': '150g', 'quantity_g': 150},
                    {'name': 'Arroz branco cozido', 'quantity_text': '150g', 'quantity_g': 150},
                    {'name': 'Feijão cozido', 'quantity_text': '2 conchas', 'quantity_g': 160},
                ],
            },
            {
                'name': 'Jantar',
                'time_suggestion': '19:00',
                'foods': [
                    {'name': 'Tilápia grelhada', 'quantity_text': '150g', 'quantity_g': 150},
                    {'name': 'Batata-doce cozida', 'quantity_text': '150g', 'quantity_g': 150},
                ],
            },
        ],
        'substitutions': [],
        'notes': 'Beba 2L de água.',
    })


def _make_passo2_response():
    """Resposta do Passo 2 — explicação."""
    return _wrap_api({
        'calorie_calculation': 'TMB calculada via Mifflin-St Jeor...',
        'macro_distribution': 'Proteína 2g/kg...',
        'food_choices': 'Frango incluso nas preferências...',
        'meal_structure': '3 refeições bem distribuídas...',
        'goal_alignment': 'Déficit de 450 kcal para emagrecimento...',
    })


# ---------------------------------------------------------------------------
# Testes de _parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:

    def test_parse_resposta_valida(self, ai_service):
        raw = _make_api_response()
        result = ai_service._parse_response(raw)
        assert result['goal_description'] == 'Emagrecimento saudável'
        assert result['calories'] == 1800

    def test_parse_resposta_sem_choices(self, ai_service):
        with pytest.raises(ValueError):
            ai_service._parse_response({})

    def test_parse_resposta_json_invalido(self, ai_service):
        raw = {'choices': [{'message': {'content': 'não é json {'}}]}
        with pytest.raises(ValueError):
            ai_service._parse_response(raw)

    def test_parse_resposta_choices_vazio(self, ai_service):
        with pytest.raises(ValueError):
            ai_service._parse_response({'choices': []})


# ---------------------------------------------------------------------------
# Testes de _recalculate_totals
# ---------------------------------------------------------------------------

class TestRecalculateTotals:

    def test_recalcula_calorias_a_partir_dos_alimentos(self, ai_service):
        """Deve ignorar o 'calories' original e recalcular a partir dos foods."""
        data = {
            'calories': 9999,
            'meals': [
                {'foods': [
                    {'calories': 200, 'protein_g': 20, 'carbs_g': 10, 'fat_g': 5},
                    {'calories': 300, 'protein_g': 10, 'carbs_g': 40, 'fat_g': 8},
                ]}
            ],
        }
        result = ai_service._recalculate_totals(data)
        assert result['calories'] == 500

    def test_recalcula_macros_a_partir_dos_alimentos(self, ai_service):
        data = {
            'calories': 500,
            'macros': {'protein_g': 0, 'carbs_g': 0, 'fat_g': 0},
            'meals': [
                {'foods': [
                    {'calories': 200, 'protein_g': 20, 'carbs_g': 10, 'fat_g': 5},
                    {'calories': 300, 'protein_g': 10, 'carbs_g': 40, 'fat_g': 8},
                ]}
            ],
        }
        result = ai_service._recalculate_totals(data)
        assert result['macros']['protein_g'] == 30
        assert result['macros']['carbs_g'] == 50
        assert result['macros']['fat_g'] == 13

    def test_sem_alimentos_retorna_zero(self, ai_service):
        data = {'calories': 0, 'meals': []}
        result = ai_service._recalculate_totals(data)
        assert result['calories'] == 0

    def test_multiplas_refeicoes_soma_corretamente(self, ai_service):
        data = {
            'calories': 0,
            'meals': [
                {'foods': [{'calories': 300, 'protein_g': 30, 'carbs_g': 30, 'fat_g': 5}]},
                {'foods': [{'calories': 400, 'protein_g': 20, 'carbs_g': 60, 'fat_g': 8}]},
            ],
        }
        result = ai_service._recalculate_totals(data)
        assert result['calories'] == 700
        assert result['macros']['protein_g'] == 50
        assert result['macros']['carbs_g'] == 90
        assert result['macros']['fat_g'] == 13


# ---------------------------------------------------------------------------
# Testes de _adjust_to_calorie_target
# ---------------------------------------------------------------------------

class TestAdjustToCalorieTarget:

    def test_sem_divergencia_nao_altera(self, ai_service):
        """Dentro de ±10%, não deve escalar."""
        data = {
            'calories': 1800,
            'meals': [
                {'foods': [{'name': 'Arroz', 'quantity_g': 100, 'calories': 900,
                            'protein_g': 50, 'carbs_g': 100, 'fat_g': 20}]},
                {'foods': [{'name': 'Frango', 'quantity_g': 100, 'calories': 900,
                            'protein_g': 50, 'carbs_g': 100, 'fat_g': 20}]},
            ],
        }
        result = ai_service._adjust_to_calorie_target(data, target_calories=1800)
        assert result['calories'] == 1800

    @patch('nutrition.services.lookup_food_nutrition')
    def test_com_grande_divergencia_escala_quantidades(self, mock_lookup, ai_service):
        """Divergência >10% deve escalar quantity_g e recalcular macros."""
        def _scaled_lookup(name, qty):
            return {
                'calories': int(qty * 5),
                'protein_g': round(qty * 0.25, 1),
                'carbs_g': round(qty * 0.60, 1),
                'fat_g': round(qty * 0.10, 1),
            }
        mock_lookup.side_effect = _scaled_lookup

        data = {
            'calories': 1000,
            'meals': [
                {'foods': [
                    {'name': 'Arroz', 'quantity_g': 100, 'quantity_text': '100g',
                     'calories': 500, 'protein_g': 25, 'carbs_g': 60, 'fat_g': 10},
                    {'name': 'Frango', 'quantity_g': 100, 'quantity_text': '100g',
                     'calories': 500, 'protein_g': 25, 'carbs_g': 60, 'fat_g': 10},
                ]},
            ],
        }
        result = ai_service._adjust_to_calorie_target(data, target_calories=2000)
        # scale=2 → quantity_g: 100→200 → lookup retorna 200*5=1000 por alimento
        assert result['calories'] == 2000
        assert result['meals'][0]['foods'][0]['calories'] == 1000

    def test_target_zero_nao_altera(self, ai_service):
        data = {'calories': 1800, 'meals': []}
        result = ai_service._adjust_to_calorie_target(data, target_calories=0)
        assert result['calories'] == 1800

    def test_calories_zero_nao_altera(self, ai_service):
        data = {'calories': 0, 'meals': []}
        result = ai_service._adjust_to_calorie_target(data, target_calories=1800)
        assert result['calories'] == 0


# ---------------------------------------------------------------------------
# Testes de generate_diet (integração interna com mock HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateDiet:

    @patch.object(AIService, '_call_api')
    def test_gera_dietplan_no_banco(self, mock_call, ai_service, anamnese):
        mock_call.side_effect = [_make_passo1_response(), _make_passo2_response()]
        diet_plan = ai_service.generate_diet(anamnese)
        assert DietPlan.objects.filter(id=diet_plan.id).exists()

    @patch.object(AIService, '_call_api')
    def test_gera_meals_no_banco(self, mock_call, ai_service, anamnese):
        mock_call.side_effect = [_make_passo1_response(), _make_passo2_response()]
        diet_plan = ai_service.generate_diet(anamnese)
        assert Meal.objects.filter(diet_plan=diet_plan).count() == 3

    @patch.object(AIService, '_call_api')
    def test_dietplan_salvo_com_calories_positivas(self, mock_call, ai_service, anamnese):
        mock_call.side_effect = [_make_passo1_response(), _make_passo2_response()]
        diet_plan = ai_service.generate_diet(anamnese)
        assert diet_plan.total_calories > 0

    @patch.object(AIService, '_call_api')
    def test_dietplan_vinculado_ao_usuario_correto(self, mock_call, ai_service, anamnese):
        mock_call.side_effect = [_make_passo1_response(), _make_passo2_response()]
        diet_plan = ai_service.generate_diet(anamnese)
        assert diet_plan.user == anamnese.user

    @patch.object(AIService, '_call_api')
    def test_dietplan_vinculado_a_anamnese(self, mock_call, ai_service, anamnese):
        mock_call.side_effect = [_make_passo1_response(), _make_passo2_response()]
        diet_plan = ai_service.generate_diet(anamnese)
        assert diet_plan.anamnese == anamnese

    @patch.object(AIService, '_call_api')
    def test_meal_com_horario_no_nome(self, mock_call, ai_service, anamnese):
        """Horário sugerido deve ser incluído no nome da refeição."""
        mock_call.side_effect = [_make_passo1_response(), _make_passo2_response()]
        diet_plan = ai_service.generate_diet(anamnese)
        primeira_meal = diet_plan.meals.order_by('order').first()
        assert '07:00' in primeira_meal.meal_name

    @patch.object(AIService, '_call_api')
    def test_meal_descricao_lista_alimentos(self, mock_call, ai_service, anamnese):
        """Descrição da refeição deve conter os nomes dos alimentos."""
        mock_call.side_effect = [_make_passo1_response(), _make_passo2_response()]
        diet_plan = ai_service.generate_diet(anamnese)
        primeira_meal = diet_plan.meals.order_by('order').first()
        assert 'Ovos' in primeira_meal.description

    def test_sem_api_key_levanta_value_error(self, anamnese):
        service = AIService()
        service.api_key = ''
        service.api_url = ''
        with pytest.raises((ValueError, Exception)):
            service._call_api('prompt', 'system')

    @patch.object(AIService, '_call_api')
    def test_resposta_invalida_da_ia_levanta_exception(self, mock_call, ai_service, anamnese):
        mock_call.return_value = {'choices': [{'message': {'content': 'json inválido {'}}]}
        with pytest.raises((ValueError, Exception)):
            ai_service.generate_diet(anamnese)

    @patch.object(AIService, '_call_api')
    def test_passo2_falha_nao_impede_criacao_do_dietplan(self, mock_call, ai_service, anamnese):
        """Falha no Passo 2 (explicação) não deve cancelar a geração."""
        invalid_passo2 = {'choices': [{'message': {'content': 'json inválido {'}}]}
        mock_call.side_effect = [_make_passo1_response(), invalid_passo2]
        diet_plan = ai_service.generate_diet(anamnese)
        assert DietPlan.objects.filter(id=diet_plan.id).exists()


# ---------------------------------------------------------------------------
# Testes da task Celery — generate_diet_task
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGenerateDietTask:
    """
    Testa os fluxos da task Celery generate_diet_task:
    status transitions, retry automático e tratamento de erros.
    Roda de forma síncrona via CELERY_TASK_ALWAYS_EAGER=True nas test_settings.
    """

    @pytest.fixture
    def job(self, anamnese):
        return DietJob.objects.create(user=anamnese.user, anamnese=anamnese)

    def _make_diet_plan(self, user):
        return DietPlan.objects.create(
            user=user, raw_response={}, total_calories=1800, goal_description='Teste'
        )

    @patch('nutrition.services.AIService.generate_diet')
    def test_task_marca_job_como_done_em_sucesso(self, mock_generate, job, anamnese):
        """Geração bem-sucedida deve transicionar o job para STATUS_DONE."""
        mock_generate.return_value = self._make_diet_plan(anamnese.user)
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)

        job.refresh_from_db()
        assert job.status == DietJob.STATUS_DONE
        assert job.diet_plan_id is not None

    @patch('nutrition.services.AIService.generate_diet')
    def test_task_marca_job_como_failed_em_excecao_generica(self, mock_generate, job):
        """Exceção não tratada deve marcar o job como STATUS_FAILED."""
        mock_generate.side_effect = Exception('Conexão recusada pela API')
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)

        job.refresh_from_db()
        assert job.status == DietJob.STATUS_FAILED
        assert 'Conexão recusada pela API' in job.error_message

    @patch('nutrition.services.AIService.generate_diet')
    def test_task_ignora_job_com_status_diferente_de_pending(self, mock_generate, job):
        """Job já em STATUS_DONE não deve ser reprocessado."""
        from nutrition.models import DietJob
        job.status = DietJob.STATUS_DONE
        job.save()

        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)

        assert not mock_generate.called
        job.refresh_from_db()
        assert job.status == DietJob.STATUS_DONE

    def test_task_job_inexistente_retorna_silenciosamente(self):
        """DietJob.DoesNotExist não deve propagar exceção."""
        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(99999)  # não existe — deve ser ignorado silenciosamente

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
    @patch('nutrition.services.AIService.generate_diet')
    def test_task_retry_em_erro_transitorio_e_sucesso_no_segundo(self, mock_generate, job, anamnese):
        """ValueError com frase retryable deve disparar retry; deve completar no segundo attempt.
        CELERY_TASK_EAGER_PROPAGATES=False é necessário para que self.retry() re-execute
        a task em eager mode em vez de propagar a exceção Retry.
        """
        diet_plan = self._make_diet_plan(anamnese.user)
        mock_generate.side_effect = [
            ValueError('A IA retornou um json inválido. Tente novamente.'),
            diet_plan,
        ]

        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)

        job.refresh_from_db()
        assert job.status == DietJob.STATUS_DONE
        assert mock_generate.call_count == 2

    @patch('nutrition.services.AIService.generate_diet')
    def test_task_erro_nao_transitorio_falha_imediatamente(self, mock_generate, job):
        """ValueError sem frase retryable deve ir direto para STATUS_FAILED sem retry."""
        mock_generate.side_effect = ValueError('Dados da anamnese inválidos')

        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)

        job.refresh_from_db()
        assert job.status == DietJob.STATUS_FAILED
        assert mock_generate.call_count == 1  # sem retry

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=False)
    @patch('nutrition.services.AIService.generate_diet')
    def test_task_falha_definitiva_apos_max_retries(self, mock_generate, job):
        """Após esgotar max_retries (2), o job deve terminar em STATUS_FAILED.
        CELERY_TASK_EAGER_PROPAGATES=False permite que os retries sejam executados
        em eager mode sem propagar a exceção Retry.
        """
        mock_generate.side_effect = ValueError('json inválido: unexpected token')

        from nutrition.tasks import generate_diet_task
        generate_diet_task.delay(job.pk)

        job.refresh_from_db()
        assert job.status == DietJob.STATUS_FAILED
        # max_retries=2 → 3 chamadas no total (tentativa original + 2 retries)
        assert mock_generate.call_count == 3

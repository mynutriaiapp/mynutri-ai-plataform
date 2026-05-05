import logging
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone

# Jobs em 'processing' por mais deste tempo são considerados travados (worker morreu)
_STUCK_JOB_TIMEOUT = timedelta(minutes=5)
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from .models import Anamnese, DietJob, DietPlan, Meal, MealRegenerationLog
from .serializers import AnamneseSerializer, DietPlanSerializer, DietPlanSummarySerializer
from .tasks import generate_diet_task
from .pdf_generator import generate_diet_pdf

logger = logging.getLogger(__name__)


class AnamneseAPIView(APIView):
    """
    POST /api/anamnese
    Salva as respostas do questionário nutricional do usuário logado.
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AnamneseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        anamnese = serializer.save(user=request.user)
        return Response(
            AnamneseSerializer(anamnese).data,
            status=status.HTTP_201_CREATED,
        )


class AnamneseLastAPIView(APIView):
    """
    GET /api/v1/anamnese/last
    Retorna a anamnese mais recente do usuário logado para pré-preenchimento do questionário.
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        anamnese = (
            Anamnese.objects.filter(user=request.user)
            .order_by('-answered_at')
            .first()
        )
        if not anamnese:
            return Response(
                {'detail': 'Nenhuma anamnese encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AnamneseSerializer(anamnese).data, status=status.HTTP_200_OK)


class DietGenerateAPIView(APIView):
    """
    POST /api/v1/diet/generate
    Enfileira a geração de dieta via Celery e retorna imediatamente com o job_id.

    Fluxo assíncrono:
        1. Cria DietJob(status='pending')
        2. Enfileira generate_diet_task via Celery
        3. Retorna 202 Accepted + {"job_id": <id>}
        4. Frontend faz polling em GET /api/v1/diet/status/<job_id>

    Modo síncrono (dev sem Redis / CELERY_TASK_ALWAYS_EAGER=True):
        O Celery executa a task inline antes de retornar — o job já estará
        'done' ou 'failed' na primeira chamada de polling.

    Requer: Authorization: Bearer <token>
    Limite: 3 gerações por dia por usuário.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'diet_generate'

    def post(self, request):
        anamnese = (
            Anamnese.objects.filter(user=request.user)
            .order_by('-answered_at')
            .first()
        )

        if not anamnese:
            return Response(
                {'error': 'Nenhuma anamnese encontrada. Responda o questionário primeiro.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Bloqueia se já houver um job em andamento para este usuário.
        # Exceção: jobs em 'processing' por mais de 15 min são considerados travados
        # (worker morreu/reiniciou) e marcados como failed para desbloquear o usuário.
        in_progress = DietJob.objects.filter(
            user=request.user,
            status__in=[DietJob.STATUS_PENDING, DietJob.STATUS_PROCESSING],
        ).first()
        if in_progress:
            stuck_cutoff = timezone.now() - _STUCK_JOB_TIMEOUT
            if (
                in_progress.status == DietJob.STATUS_PROCESSING
                and in_progress.updated_at < stuck_cutoff
            ):
                in_progress.status = DietJob.STATUS_FAILED
                in_progress.error_message = (
                    'Geração interrompida: o servidor foi reiniciado durante o processamento. '
                    'Tente gerar sua dieta novamente.'
                )
                in_progress.save(update_fields=['status', 'error_message', 'updated_at'])
                logger.warning('DietJob#%s marcado como failed (travado).', in_progress.pk)
            else:
                return Response(
                    {'job_id': in_progress.pk, 'status': in_progress.status},
                    status=status.HTTP_202_ACCEPTED,
                )

        job = DietJob.objects.create(user=request.user, anamnese=anamnese)

        # delay() enfileira no Redis (prod) ou executa inline (dev com always_eager)
        generate_diet_task.delay(job.pk)

        logger.info('DietJob#%s criado para usuário %s.', job.pk, request.user.id)

        return Response({'job_id': job.pk, 'status': job.status}, status=status.HTTP_202_ACCEPTED)


class DietJobStatusAPIView(APIView):
    """
    GET /api/v1/diet/status/<job_id>
    Retorna o estado atual de um job de geração de dieta.

    Resposta:
        pending/processing: {"status": "...", "diet_plan_id": null}
        done:               {"status": "done", "diet_plan_id": <id>}
        failed:             {"status": "failed", "error": "<mensagem>"}

    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        try:
            job = DietJob.objects.get(pk=job_id, user=request.user)
        except DietJob.DoesNotExist:
            return Response({'error': 'Job não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        # Auto-recuperação: job travado em 'processing' sem atualização por 15+ min
        # indica que o worker morreu — converte para 'failed' para o frontend exibir erro.
        if job.status == DietJob.STATUS_PROCESSING:
            stuck_cutoff = timezone.now() - _STUCK_JOB_TIMEOUT
            if job.updated_at < stuck_cutoff:
                job.status = DietJob.STATUS_FAILED
                job.error_message = (
                    'Geração interrompida: o servidor foi reiniciado durante o processamento. '
                    'Tente gerar sua dieta novamente.'
                )
                job.save(update_fields=['status', 'error_message', 'updated_at'])
                logger.warning('DietJob#%s detectado como travado via polling — marcado como failed.', job.pk)

        payload = {'status': job.status, 'diet_plan_id': None}

        if job.status == DietJob.STATUS_DONE and job.diet_plan_id:
            payload['diet_plan_id'] = job.diet_plan_id

        if job.status == DietJob.STATUS_FAILED:
            payload['error'] = job.error_message or 'Falha ao gerar dieta. Tente novamente.'

        return Response(payload, status=status.HTTP_200_OK)


class DietAPIView(APIView):
    """
    GET /api/diet
    Retorna o plano alimentar mais recente do usuário logado.
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        diet_plan = (
            DietPlan.objects.filter(user=request.user)
            .prefetch_related('meals')
            .order_by('-created_at')
            .first()
        )

        if not diet_plan:
            return Response(
                {'error': 'Você ainda não possui um plano alimentar gerado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(DietPlanSerializer(diet_plan).data, status=status.HTTP_200_OK)


class DietListAPIView(APIView):
    """
    GET /api/v1/diet/list
    Retorna o histórico de planos alimentares do usuário logado (paginado, 10/página).
    Parâmetros: ?page=<n>
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]
    PAGE_SIZE = 10

    def get(self, request):
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page = 1

        offset = (page - 1) * self.PAGE_SIZE
        qs = DietPlan.objects.filter(user=request.user).order_by('-created_at')
        total = qs.count()
        diet_plans = qs[offset:offset + self.PAGE_SIZE]

        serializer = DietPlanSummarySerializer(diet_plans, many=True)
        return Response({
            'results': serializer.data,
            'count': total,
            'page': page,
            'total_pages': max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE),
        }, status=status.HTTP_200_OK)


class DietDetailAPIView(APIView):
    """
    GET /api/v1/diet/<id>
    Retorna um plano alimentar específico do usuário logado pelo ID.
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            diet_plan = (
                DietPlan.objects.prefetch_related('meals')
                .get(pk=pk, user=request.user)
            )
        except DietPlan.DoesNotExist:
            return Response(
                {'error': 'Plano alimentar não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(DietPlanSerializer(diet_plan).data, status=status.HTTP_200_OK)


class DietSubstitutionsAPIView(APIView):
    """
    PATCH /api/v1/diet/<id>/substitutions
    Substitui a lista de substituições de um DietPlan do usuário autenticado.
    Body: { "substitutions": [{ "food": "...", "alternatives": ["...", ...] }] }
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        try:
            diet_plan = DietPlan.objects.get(pk=pk, user=request.user)
        except DietPlan.DoesNotExist:
            return Response(
                {'error': 'Plano alimentar não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        substitutions = request.data.get('substitutions')
        if not isinstance(substitutions, list):
            return Response(
                {'error': 'O campo "substitutions" deve ser uma lista.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(substitutions) > 50:
            return Response(
                {'error': 'Máximo de 50 substituições permitido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        errors = []
        for i, item in enumerate(substitutions):
            if not isinstance(item, dict):
                errors.append(f'Item {i}: formato inválido.')
                continue
            food = (item.get('food') or '').strip()
            alts = item.get('alternatives')
            if not food:
                errors.append(f'Item {i}: "food" não pode ser vazio.')
            elif len(food) > 100:
                errors.append(f'Item {i}: "food" excede 100 caracteres.')
            if not isinstance(alts, list) or not alts:
                errors.append(f'Item {i}: "alternatives" deve ser uma lista não vazia.')
            else:
                for j, alt in enumerate(alts):
                    if not isinstance(alt, str) or not alt.strip():
                        errors.append(f'Item {i}, alternativa {j}: não pode ser vazia.')
                    elif len(alt) > 100:
                        errors.append(f'Item {i}, alternativa {j}: excede 100 caracteres.')
        if errors:
            return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

        cleaned = [
            {
                'food': item['food'].strip(),
                'alternatives': [a.strip() for a in item['alternatives']
                                 if isinstance(a, str) and a.strip()],
            }
            for item in substitutions
        ]

        raw = dict(diet_plan.raw_response or {})
        raw['substitutions'] = cleaned
        diet_plan.raw_response = raw
        diet_plan.save(update_fields=['raw_response'])

        return Response({'substitutions': cleaned}, status=status.HTTP_200_OK)


class DietPDFAPIView(APIView):
    """
    GET /api/v1/diet/<id>/pdf
    Gera e retorna o plano alimentar em formato PDF.
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            diet_plan = (
                DietPlan.objects
                .select_related('user', 'anamnese')
                .prefetch_related('meals')
                .get(pk=pk, user=request.user)
            )
        except DietPlan.DoesNotExist:
            return Response(
                {'error': 'Plano alimentar não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            pdf_bytes = generate_diet_pdf(diet_plan)
        except Exception:
            logger.exception('Erro ao gerar PDF para DietPlan#%s', pk)
            return Response(
                {'error': 'Não foi possível gerar o PDF. Tente novamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        date_str  = diet_plan.created_at.strftime('%Y-%m-%d') if diet_plan.created_at else 'dieta'
        filename  = f'mynutri-dieta-{date_str}.pdf'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class MealRegenerateAPIView(APIView):
    """
    PATCH /api/v1/diet/<diet_pk>/meal/<meal_pk>/regenerate
    Regenera pontualmente uma refeição sem alterar as demais do plano.

    Body (opcional): { "reason": "não gostei dos alimentos" }

    Resposta: dados atualizados da refeição + meals_raw_entry + macros totais.

    Limites:
      - 3 regenerações por dia por DietPlan (contagem em MealRegenerationLog)
      - Usuário só pode regenerar refeições do seu próprio plano
    """

    permission_classes = [IsAuthenticated]
    DAILY_LIMIT = 3

    def patch(self, request, diet_pk, meal_pk):
        try:
            diet_plan = (
                DietPlan.objects
                .prefetch_related('meals')
                .select_related('anamnese')
                .get(pk=diet_pk, user=request.user)
            )
        except DietPlan.DoesNotExist:
            return Response(
                {'error': 'Plano alimentar não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            meal = diet_plan.meals.get(pk=meal_pk)
        except Meal.DoesNotExist:
            return Response(
                {'error': 'Refeição não encontrada neste plano.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ── Rate limit: 3 regenerações por dia por DietPlan ──────────────────
        cutoff = timezone.now() - timedelta(days=1)
        daily_count = MealRegenerationLog.objects.filter(
            diet_plan=diet_plan,
            created_at__gte=cutoff,
            is_undone=False,
        ).count()

        if daily_count >= self.DAILY_LIMIT:
            return Response(
                {
                    'error': (
                        f'Limite de {self.DAILY_LIMIT} regenerações por dia atingido '
                        'para este plano. Tente novamente amanhã.'
                    ),
                    'regenerations_remaining': 0,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        # ── Validações ────────────────────────────────────────────────────────
        reason = (request.data.get('reason') or '').strip()
        if len(reason) > 300:
            return Response(
                {'error': '"reason" não pode exceder 300 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not diet_plan.anamnese_id:
            return Response(
                {'error': 'Não é possível regenerar: plano sem anamnese associada.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw = diet_plan.raw_response or {}
        meals_raw = raw.get('meals', [])
        meal_index = meal.order

        if meal_index >= len(meals_raw):
            return Response(
                {'error': 'Índice de refeição desatualizado. Recarregue a página.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Salva estado anterior para undo ───────────────────────────────────
        prev_description = meal.description
        prev_calories    = meal.calories
        prev_raw_meal    = meals_raw[meal_index]

        # ── Chama AIService ───────────────────────────────────────────────────
        from .services import AIService, DietGenerationError
        service = AIService()

        try:
            result = service.regenerate_meal(diet_plan, meal_index, reason)
        except (ValueError, DietGenerationError) as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception(
                'Erro ao regenerar refeição %d do DietPlan#%d', meal_index, diet_plan.pk
            )
            return Response(
                {'error': 'Falha ao regenerar a refeição. Tente novamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ── Atualiza Meal ─────────────────────────────────────────────────────
        meal.meal_name   = result['new_meal_name']
        meal.description = result['new_description']
        meal.calories    = result['new_calories']
        meal.save(update_fields=['meal_name', 'description', 'calories'])

        # ── Atualiza raw_response e recalcula totais ──────────────────────────
        raw_copy = dict(raw)
        meals_copy = list(raw_copy.get('meals', []))
        meals_copy[meal_index] = result['new_raw_meal']
        raw_copy['meals'] = meals_copy

        total_cal  = 0
        total_prot = 0.0
        total_carb = 0.0
        total_fat  = 0.0
        for m in meals_copy:
            for f in m.get('foods', []):
                total_cal  += f.get('calories',  0) or 0
                total_prot += f.get('protein_g', 0) or 0
                total_carb += f.get('carbs_g',   0) or 0
                total_fat  += f.get('fat_g',     0) or 0

        raw_copy['calories'] = total_cal
        raw_copy['macros'] = {
            'protein_g': round(total_prot),
            'carbs_g':   round(total_carb),
            'fat_g':     round(total_fat),
        }

        # Regenera substituições contextuais com o plano atualizado
        from .substitutions import generate_meal_substitutions
        from .services import _parse_allergens
        allergens_list = _parse_allergens(
            (diet_plan.anamnese.allergies or '') if diet_plan.anamnese else ''
        )
        raw_copy['substitutions'] = generate_meal_substitutions(meals_copy, allergens_list)

        diet_plan.raw_response  = raw_copy
        diet_plan.total_calories = total_cal
        diet_plan.save(update_fields=['raw_response', 'total_calories'])

        # ── Registra log (auditoria + undo) ───────────────────────────────────
        log = MealRegenerationLog.objects.create(
            diet_plan=diet_plan,
            meal=meal,
            user=request.user,
            reason=reason,
            previous_description=prev_description,
            previous_calories=prev_calories,
            previous_raw_meal=prev_raw_meal,
        )

        remaining = self.DAILY_LIMIT - (daily_count + 1)

        return Response(
            {
                'meal': {
                    'id':          meal.pk,
                    'meal_name':   meal.meal_name,
                    'description': meal.description,
                    'calories':    meal.calories,
                    'order':       meal.order,
                },
                'meals_raw_entry':         result['new_raw_meal'],
                'macros':                  raw_copy['macros'],
                'total_calories':          total_cal,
                'log_id':                  log.pk,
                'regenerations_remaining': remaining,
            },
            status=status.HTTP_200_OK,
        )


class MealUndoAPIView(APIView):
    """
    POST /api/v1/diet/<diet_pk>/meal/<meal_pk>/undo
    Desfaz a última regeneração de uma refeição, restaurando o estado anterior.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, diet_pk, meal_pk):
        try:
            diet_plan = (
                DietPlan.objects
                .get(pk=diet_pk, user=request.user)
            )
        except DietPlan.DoesNotExist:
            return Response(
                {'error': 'Plano alimentar não encontrado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            meal = Meal.objects.get(pk=meal_pk, diet_plan=diet_plan)
        except Meal.DoesNotExist:
            return Response(
                {'error': 'Refeição não encontrada neste plano.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Busca a última regeneração não desfeita desta refeição
        last_log = (
            MealRegenerationLog.objects
            .filter(diet_plan=diet_plan, meal=meal, is_undone=False)
            .first()
        )

        if not last_log:
            return Response(
                {'error': 'Nenhuma regeneração disponível para desfazer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Restaura Meal ─────────────────────────────────────────────────────
        prev_raw = last_log.previous_raw_meal
        time_sug  = prev_raw.get('time_suggestion', '')
        meal_name = prev_raw.get('name', meal.meal_name)
        meal.meal_name   = f'{meal_name} ({time_sug})' if time_sug else meal_name
        meal.description = last_log.previous_description
        meal.calories    = last_log.previous_calories
        meal.save(update_fields=['meal_name', 'description', 'calories'])

        # ── Restaura raw_response ─────────────────────────────────────────────
        raw_copy = dict(diet_plan.raw_response or {})
        meals_copy = list(raw_copy.get('meals', []))
        meal_index = meal.order

        if 0 <= meal_index < len(meals_copy):
            meals_copy[meal_index] = prev_raw
            raw_copy['meals'] = meals_copy

            total_cal  = 0
            total_prot = 0.0
            total_carb = 0.0
            total_fat  = 0.0
            for m in meals_copy:
                for f in m.get('foods', []):
                    total_cal  += f.get('calories',  0) or 0
                    total_prot += f.get('protein_g', 0) or 0
                    total_carb += f.get('carbs_g',   0) or 0
                    total_fat  += f.get('fat_g',     0) or 0

            raw_copy['calories'] = total_cal
            raw_copy['macros'] = {
                'protein_g': round(total_prot),
                'carbs_g':   round(total_carb),
                'fat_g':     round(total_fat),
            }
            diet_plan.raw_response   = raw_copy
            diet_plan.total_calories = total_cal
            diet_plan.save(update_fields=['raw_response', 'total_calories'])

        # Marca o log como desfeito (mantém para auditoria)
        last_log.is_undone = True
        last_log.save(update_fields=['is_undone'])

        return Response(
            {
                'meal': {
                    'id':          meal.pk,
                    'meal_name':   meal.meal_name,
                    'description': meal.description,
                    'calories':    meal.calories,
                    'order':       meal.order,
                },
                'meals_raw_entry': prev_raw,
                'macros':          raw_copy.get('macros'),
                'total_calories':  raw_copy.get('calories'),
            },
            status=status.HTTP_200_OK,
        )

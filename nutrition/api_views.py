import logging

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle

from .models import Anamnese, DietJob, DietPlan
from .serializers import AnamneseSerializer, DietPlanSerializer, DietPlanSummarySerializer
from .tasks import generate_diet_task

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

        # Bloqueia se já houver um job em andamento para este usuário
        in_progress = DietJob.objects.filter(
            user=request.user,
            status__in=[DietJob.STATUS_PENDING, DietJob.STATUS_PROCESSING],
        ).first()
        if in_progress:
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
    Retorna o histórico completo de planos alimentares do usuário logado,
    ordenado do mais recente para o mais antigo.
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        diet_plans = (
            DietPlan.objects.filter(user=request.user)
            .order_by('-created_at')
        )
        serializer = DietPlanSummarySerializer(diet_plans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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

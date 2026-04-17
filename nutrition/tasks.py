"""
Tasks Celery para geração assíncrona de dietas.

Em produção (com Redis):
    O worker executa esta task em processo separado, liberando o gunicorn
    para servir outras requisições enquanto a IA processa.

Em dev (sem Redis / CELERY_TASK_ALWAYS_EAGER=True):
    A task roda de forma síncrona no mesmo processo Django — comportamento
    idêntico ao antigo fluxo síncrono, sem necessidade de worker separado.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


_RETRYABLE_PHRASES = ('formato inesperado', 'json inválido', 'json válido')


@shared_task(bind=True, max_retries=2, name='nutrition.tasks.generate_diet')
def generate_diet_task(self, job_id: int) -> None:
    """
    Executa a geração de dieta via IA para um DietJob existente.

    Retry automático (até 2 tentativas com intervalo de 15s) para falhas
    transitórias de JSON inválido ou formato inesperado da IA.
    Falhas permanentes (API key inválida, anamnese ausente) não são retentadas.
    """
    from .models import DietJob
    from .services import AIService

    try:
        job = DietJob.objects.select_related('anamnese', 'user').get(pk=job_id)
    except DietJob.DoesNotExist:
        logger.error('generate_diet_task: DietJob#%s não encontrado.', job_id)
        return

    if job.status not in (DietJob.STATUS_PENDING,):
        logger.warning(
            'generate_diet_task: DietJob#%s ignorado — status atual: %s.',
            job_id, job.status,
        )
        return

    job.status = DietJob.STATUS_PROCESSING
    job.save(update_fields=['status', 'updated_at'])

    logger.info(
        'generate_diet_task: iniciando geração para DietJob#%s (usuário %s, tentativa %d/%d).',
        job_id, job.user_id, self.request.retries + 1, self.max_retries + 1,
    )

    try:
        service = AIService()
        diet_plan = service.generate_diet(job.anamnese)

        job.status = DietJob.STATUS_DONE
        job.diet_plan = diet_plan
        job.save(update_fields=['status', 'diet_plan', 'updated_at'])

        logger.info(
            'generate_diet_task: DietJob#%s concluído → DietPlan#%s.',
            job_id, diet_plan.pk,
        )

    except ValueError as exc:
        # Falha transitória (JSON inválido, formato inesperado) — tenta novamente
        error_msg = str(exc).lower()
        is_transient = any(phrase in error_msg for phrase in _RETRYABLE_PHRASES)

        if is_transient and self.request.retries < self.max_retries:
            logger.warning(
                'generate_diet_task: DietJob#%s — falha transitória, reagendando retry %d. Erro: %s',
                job_id, self.request.retries + 1, exc,
            )
            # Volta para pending para que o retry passe pela guarda de status
            job.status = DietJob.STATUS_PENDING
            job.save(update_fields=['status', 'updated_at'])
            raise self.retry(exc=exc, countdown=15)

        # Falha definitiva
        job.status = DietJob.STATUS_FAILED
        job.error_message = str(exc)
        job.save(update_fields=['status', 'error_message', 'updated_at'])
        logger.error('generate_diet_task: DietJob#%s falhou definitivamente — %s', job_id, exc)

    except Exception as exc:
        job.status = DietJob.STATUS_FAILED
        job.error_message = str(exc)
        job.save(update_fields=['status', 'error_message', 'updated_at'])
        logger.error(
            'generate_diet_task: DietJob#%s falhou — %s',
            job_id, exc, exc_info=True,
        )

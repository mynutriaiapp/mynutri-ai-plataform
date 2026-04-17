# Garante que o app Celery é carregado quando o Django inicializa,
# permitindo que @shared_task funcione corretamente em todos os módulos.
from .celery import app as celery_app

__all__ = ('celery_app',)

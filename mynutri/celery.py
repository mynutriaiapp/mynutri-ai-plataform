"""
Configuração do Celery para o projeto MyNutri AI.

Worker em produção:
    celery -A mynutri worker --loglevel=info --concurrency=2

Dev sem Redis (tasks rodam de forma síncrona via CELERY_TASK_ALWAYS_EAGER):
    Basta rodar o Django normalmente — nenhum worker necessário.
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mynutri.settings')

app = Celery('mynutri')

# Lê toda configuração com prefixo CELERY_ do settings.py do Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover tasks em todos os INSTALLED_APPS (procura por <app>/tasks.py)
app.autodiscover_tasks()

from django.urls import path
from .api_views import (
    AnamneseAPIView,
    DietGenerateAPIView,
    DietJobStatusAPIView,
    DietAPIView,
    DietListAPIView,
    DietDetailAPIView,
)

urlpatterns = [
    # POST /api/v1/anamnese               → Salva respostas do questionário nutricional
    path('anamnese', AnamneseAPIView.as_view(), name='api-anamnese'),

    # POST /api/v1/diet/generate          → Enfileira geração de dieta (retorna job_id)
    path('diet/generate', DietGenerateAPIView.as_view(), name='api-diet-generate'),

    # GET  /api/v1/diet/status/<job_id>   → Polling do estado de um job de geração
    path('diet/status/<int:job_id>', DietJobStatusAPIView.as_view(), name='api-diet-status'),

    # GET  /api/v1/diet                   → Retorna o plano alimentar mais recente
    path('diet', DietAPIView.as_view(), name='api-diet'),

    # GET  /api/v1/diet/list              → Histórico completo de planos alimentares
    path('diet/list', DietListAPIView.as_view(), name='api-diet-list'),

    # GET  /api/v1/diet/<id>              → Plano alimentar específico por ID
    path('diet/<int:pk>', DietDetailAPIView.as_view(), name='api-diet-detail'),
]

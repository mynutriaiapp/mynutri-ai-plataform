from django.urls import path
from .views import (
    AnamneseAPIView,
    AnamneseLastAPIView,
    DietGenerateAPIView,
    DietJobStatusAPIView,
    DietAPIView,
    DietListAPIView,
    DietDetailAPIView,
    DietSubstitutionsAPIView,
    DietPDFAPIView,
    MealRegenerateAPIView,
    MealUndoAPIView,
)

app_name = 'nutrition'

urlpatterns = [
    # POST /api/v1/anamnese               → Salva respostas do questionário nutricional
    path('anamnese', AnamneseAPIView.as_view(), name='api-anamnese'),

    # GET  /api/v1/anamnese/last          → Retorna a anamnese mais recente (pré-preenchimento)
    path('anamnese/last', AnamneseLastAPIView.as_view(), name='api-anamnese-last'),

    # POST /api/v1/diet/generate          → Enfileira geração de dieta (retorna job_id)
    path('diet/generate', DietGenerateAPIView.as_view(), name='api-diet-generate'),

    # GET  /api/v1/diet/status/<job_id>   → Polling do estado de um job de geração
    path('diet/status/<int:job_id>', DietJobStatusAPIView.as_view(), name='api-diet-status'),

    # GET  /api/v1/diet                   → Retorna o plano alimentar mais recente
    path('diet', DietAPIView.as_view(), name='api-diet'),

    # GET  /api/v1/diet/list              → Histórico completo de planos alimentares
    path('diet/list', DietListAPIView.as_view(), name='api-diet-list'),

    # PATCH /api/v1/diet/<id>/substitutions → Atualiza substituições de alimentos
    path('diet/<int:pk>/substitutions', DietSubstitutionsAPIView.as_view(), name='api-diet-substitutions'),

    # GET  /api/v1/diet/<id>/pdf          → Baixa o plano alimentar em PDF
    path('diet/<int:pk>/pdf', DietPDFAPIView.as_view(), name='api-diet-pdf'),

    # PATCH /api/v1/diet/<diet_pk>/meal/<meal_pk>/regenerate → Regenera uma refeição
    path(
        'diet/<int:diet_pk>/meal/<int:meal_pk>/regenerate',
        MealRegenerateAPIView.as_view(),
        name='api-meal-regenerate',
    ),

    # POST /api/v1/diet/<diet_pk>/meal/<meal_pk>/undo → Desfaz última regeneração
    path(
        'diet/<int:diet_pk>/meal/<int:meal_pk>/undo',
        MealUndoAPIView.as_view(),
        name='api-meal-undo',
    ),

    # GET  /api/v1/diet/<id>              → Plano alimentar específico por ID
    path('diet/<int:pk>', DietDetailAPIView.as_view(), name='api-diet-detail'),
]

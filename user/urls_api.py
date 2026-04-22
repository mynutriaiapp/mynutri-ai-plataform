from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .api_views import RegisterAPIView, ProfileAPIView, EmailTokenObtainPairView, ContactAPIView, GoogleAuthAPIView

urlpatterns = [
    # POST /api/v1/auth/register  → Criação de conta + retorna token JWT
    path('auth/register', RegisterAPIView.as_view(), name='api-register'),

    # POST /api/v1/auth/login     → Login com email/senha → retorna token + refresh
    path('auth/login', EmailTokenObtainPairView.as_view(), name='api-login'),

    # POST /api/v1/auth/google    → Login/cadastro via Google OAuth → retorna token + refresh
    path('auth/google', GoogleAuthAPIView.as_view(), name='api-google-auth'),

    # POST /api/v1/auth/token/refresh → Renova o access token usando o refresh token
    path('auth/token/refresh', TokenRefreshView.as_view(), name='api-token-refresh'),

    # GET /api/v1/user/profile    → Dados do usuário logado
    path('user/profile', ProfileAPIView.as_view(), name='api-profile'),

    # POST /api/v1/contact        → Envia e-mail de contato (público, rate-limit 5/h)
    path('contact', ContactAPIView.as_view(), name='api-contact'),
]

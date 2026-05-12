from django.urls import path
from .views import (
    RegisterAPIView, ProfileAPIView, EmailTokenObtainPairView,
    ContactAPIView, GoogleAuthAPIView, GoogleOAuthCallbackView, TestimonialAPIView,
    LogoutAPIView, CookieTokenRefreshView, ChangePasswordAPIView, DeleteAccountAPIView,
)

app_name = 'user'

urlpatterns = [
    # POST /api/v1/auth/register       → Criação de conta + retorna token JWT + seta cookies
    path('auth/register', RegisterAPIView.as_view(), name='api-register'),

    # POST /api/v1/auth/login          → Login com email/senha → retorna token + refresh + seta cookies
    path('auth/login', EmailTokenObtainPairView.as_view(), name='api-login'),

    # POST /api/v1/auth/google         → Login/cadastro via Google OAuth (callback fetch) → retorna token + refresh + seta cookies
    path('auth/google', GoogleAuthAPIView.as_view(), name='api-google-auth'),

    # POST /api/v1/auth/google/callback → Recebe credential do Google redirect flow → seta cookies + redireciona
    path('auth/google/callback', GoogleOAuthCallbackView.as_view(), name='api-google-callback'),

    # POST /api/v1/auth/token/refresh  → Renova access token via cookie HttpOnly ou body JSON
    path('auth/token/refresh', CookieTokenRefreshView.as_view(), name='api-token-refresh'),

    # POST /api/v1/auth/logout         → Remove cookies HttpOnly de autenticação
    path('auth/logout', LogoutAPIView.as_view(), name='api-logout'),

    # GET   /api/v1/user/profile       → Dados do usuário logado
    # PATCH /api/v1/user/profile       → Atualiza nome, telefone, data de nascimento
    path('user/profile', ProfileAPIView.as_view(), name='api-profile'),

    # POST /api/v1/user/change-password → Altera senha (requer current_password + new_password)
    path('user/change-password', ChangePasswordAPIView.as_view(), name='api-change-password'),

    # DELETE /api/v1/user/delete-account → Exclui permanentemente a conta (requer senha)
    path('user/delete-account', DeleteAccountAPIView.as_view(), name='api-delete-account'),

    # POST /api/v1/contact             → Envia e-mail de contato (público, rate-limit 5/h)
    path('contact', ContactAPIView.as_view(), name='api-contact'),

    # GET  /api/v1/testimonials        → Lista depoimentos aprovados (público)
    # POST /api/v1/testimonials        → Cria depoimento (requer autenticação)
    path('testimonials', TestimonialAPIView.as_view(), name='api-testimonials'),
]

import logging

import requests as http_requests

from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework import status, serializers as drf_serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from user.models import Profile

from .forms import ContatoForm
from .models import Testimonial
from .serializers import (
    RegisterSerializer, UserProfileSerializer, UpdateProfileSerializer,
    TestimonialReadSerializer, TestimonialCreateSerializer,
)

logger = logging.getLogger(__name__)

User = get_user_model()


# =============================================================================
# Cookie helpers
# =============================================================================

def _set_auth_cookies(response, access_token, refresh_token):
    """Define os cookies HttpOnly para access e refresh tokens."""
    secure = not settings.DEBUG
    response.set_cookie(
        'mynutri_access',
        str(access_token),
        max_age=8 * 3600,       # 8 horas — igual ao ACCESS_TOKEN_LIFETIME
        httponly=True,
        secure=secure,
        samesite='Lax',
        path='/',
    )
    response.set_cookie(
        'mynutri_refresh',
        str(refresh_token),
        max_age=7 * 24 * 3600,  # 7 dias — igual ao REFRESH_TOKEN_LIFETIME
        httponly=True,
        secure=secure,
        samesite='Lax',
        path='/',
    )


def _clear_auth_cookies(response):
    """Remove os cookies de autenticação (logout)."""
    response.delete_cookie('mynutri_access', path='/')
    response.delete_cookie('mynutri_refresh', path='/')


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Substitui o campo 'username' por 'email' na autenticação JWT.
    Como o sistema usa username=email internamente, apenas renomeamos o campo.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'] = drf_serializers.EmailField()
        del self.fields[self.username_field]

    def validate(self, attrs):
        attrs[self.username_field] = attrs.pop('email', '').lower()
        return super().validate(attrs)


class LoginThrottle(AnonRateThrottle):
    """5 tentativas de login por 10 minutos por IP — previne brute force."""
    scope = 'login'

    def parse_rate(self, rate):
        # DRF doesn't support multi-minute periods; hardcode 5 per 10 minutes
        return (5, 600)


class EmailTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/login
    Aceita { email, password } e retorna { token, refresh, user }.
    O campo 'user' é incluído para que o frontend possa salvar os dados
    do usuário no localStorage sem precisar de uma chamada adicional.
    """
    serializer_class = EmailTokenObtainPairSerializer
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Renomeia 'access' → 'token' para consistência com /auth/register
            response.data['token'] = response.data.pop('access')

            # Anexa dados básicos do usuário — evita chamada extra ao /user/profile
            try:
                email = request.data.get('email', '').lower()
                user = User.objects.get(email=email)
                response.data['user'] = {
                    'id':   user.id,
                    'email': user.email,
                    'nome': user.get_full_name() or user.first_name or user.email,
                }
            except User.DoesNotExist:
                pass  # não interrompe o fluxo; o token já foi retornado

            _set_auth_cookies(response, response.data['token'], response.data['refresh'])

        return response


class RegisterAPIView(APIView):
    """
    POST /api/auth/register
    Cria uma nova conta e retorna o token JWT imediatamente,
    permitindo que o usuário já fique autenticado após o cadastro.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()

        # Gera par de tokens JWT para o novo usuário
        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                'token': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'nome': user.first_name,
                },
            },
            status=status.HTTP_201_CREATED,
        )
        _set_auth_cookies(response, refresh.access_token, refresh)
        return response


class ContactThrottle(AnonRateThrottle):
    """5 envios por hora por IP — protege contra spam no formulário de contato."""
    scope = 'contact'


class ContactAPIView(APIView):
    """
    POST /api/v1/contact
    Recebe o formulário de contato, valida e envia e-mail para mynutriai.app@gmail.com.
    Aberto ao público (AllowAny), com rate-limit de 5/hora por IP.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ContactThrottle]

    def post(self, request):
        form = ContatoForm(request.data)
        if not form.is_valid():
            return Response({'errors': form.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = form.cleaned_data
        nome     = data['nome']
        email    = data['email']
        assunto  = data['assunto']
        mensagem = data['mensagem']

        body_lines = []

        # Inclui info do usuário autenticado (se logado)
        if request.user.is_authenticated:
            body_lines += [
                f'[Usuário autenticado: {request.user.email} — ID {request.user.id}]',
                '',
            ]

        body_lines += [
            f'Nome: {nome}',
            f'E-mail: {email}',
            f'Assunto: {assunto}',
            '',
            'Mensagem:',
            mensagem,
        ]

        try:
            send_mail(
                subject=f'[MyNutri AI - Contato] {assunto}',
                message='\n'.join(body_lines),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.CONTACT_EMAIL],
                fail_silently=False,
            )
            logger.info('Contact email sent — from=%s subject=%s', email, assunto)
        except Exception as exc:
            logger.error('Contact email failed — %s', exc, exc_info=True)
            return Response(
                {'error': 'Não foi possível enviar sua mensagem. Tente novamente mais tarde.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({'message': 'Mensagem enviada com sucesso.'}, status=status.HTTP_200_OK)


class GoogleAuthAPIView(APIView):
    """
    POST /api/v1/auth/google
    Recebe { id_token } do Google Sign-In, valida com a API do Google
    e retorna JWT do sistema (mesmo formato de /auth/login e /auth/register).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        id_token = request.data.get('id_token')
        if not id_token:
            return Response({'error': 'id_token é obrigatório.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            resp = http_requests.get(
                'https://oauth2.googleapis.com/tokeninfo',
                params={'id_token': id_token},
                timeout=5,
            )
        except http_requests.RequestException as exc:
            logger.error('Google tokeninfo request failed — %s', exc)
            return Response({'error': 'Não foi possível validar o token Google.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if resp.status_code != 200:
            return Response({'error': 'Token Google inválido ou expirado.'}, status=status.HTTP_401_UNAUTHORIZED)

        google_data = resp.json()
        email = google_data.get('email', '').lower()
        if not email:
            return Response({'error': 'E-mail não retornado pelo Google.'}, status=status.HTTP_400_BAD_REQUEST)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': google_data.get('given_name', ''),
                'last_name': google_data.get('family_name', ''),
            },
        )

        if created:
            Profile.objects.get_or_create(user=user)
            logger.info('New user created via Google OAuth — email=%s', email)

        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                'token': str(refresh.access_token),
                'refresh': str(refresh),
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'nome': user.get_full_name() or user.first_name or email,
                },
            },
            status=status.HTTP_200_OK,
        )
        _set_auth_cookies(response, refresh.access_token, refresh)
        return response


@method_decorator(csrf_exempt, name='dispatch')
class GoogleOAuthCallbackView(APIView):
    """
    POST /api/v1/auth/google/callback
    Recebe { credential, g_csrf_token } do Google Sign-In no modo redirect.
    Google envia um POST form-encoded após autenticação; esta view valida o
    double-submit CSRF do Google, processa o credential e redireciona para /dieta/.
    Usa @csrf_exempt porque o CSRF aqui é gerenciado pelo próprio Google.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        credential = request.POST.get('credential') or request.data.get('credential', '')
        g_csrf_body = request.POST.get('g_csrf_token') or request.data.get('g_csrf_token', '')
        g_csrf_cookie = request.COOKIES.get('g_csrf_token', '')

        if not g_csrf_body or not g_csrf_cookie or g_csrf_body != g_csrf_cookie:
            logger.warning('Google OAuth callback: CSRF mismatch body=%s cookie=%s', g_csrf_body, g_csrf_cookie)
            return HttpResponseRedirect('/auth/?google_error=csrf')

        if not credential:
            return HttpResponseRedirect('/auth/?google_error=no_credential')

        try:
            resp = http_requests.get(
                'https://oauth2.googleapis.com/tokeninfo',
                params={'id_token': credential},
                timeout=5,
            )
        except http_requests.RequestException as exc:
            logger.error('Google tokeninfo failed in callback — %s', exc)
            return HttpResponseRedirect('/auth/?google_error=service_unavailable')

        if resp.status_code != 200:
            return HttpResponseRedirect('/auth/?google_error=invalid_token')

        google_data = resp.json()
        email = google_data.get('email', '').lower()
        if not email:
            return HttpResponseRedirect('/auth/?google_error=no_email')

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'first_name': google_data.get('given_name', ''),
                'last_name': google_data.get('family_name', ''),
            },
        )
        if created:
            Profile.objects.get_or_create(user=user)
            logger.info('New user via Google OAuth redirect — email=%s', email)

        refresh = RefreshToken.for_user(user)
        response = HttpResponseRedirect('/dieta/')
        _set_auth_cookies(response, refresh.access_token, refresh)
        return response


class LogoutAPIView(APIView):
    """
    POST /api/v1/auth/logout
    Remove os cookies HttpOnly de autenticação. Seguro para AllowAny porque
    limpar um cookie inválido não representa risco.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        response = Response({'message': 'Logout realizado com sucesso.'})
        _clear_auth_cookies(response)
        return response


class CookieTokenRefreshView(APIView):
    """
    POST /api/v1/auth/token/refresh
    Aceita o refresh token do cookie HttpOnly 'mynutri_refresh' ou do body JSON.
    Retorna novo access token e atualiza os cookies.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_raw = request.data.get('refresh') or request.COOKIES.get('mynutri_refresh')
        if not refresh_raw:
            return Response(
                {'detail': 'Refresh token não encontrado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TokenRefreshSerializer(data={'refresh': refresh_raw})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])

        access = serializer.validated_data['access']
        new_refresh = serializer.validated_data.get('refresh', refresh_raw)

        response = Response({'token': str(access)})
        _set_auth_cookies(response, access, new_refresh)
        return response


class TestimonialThrottle(AnonRateThrottle):
    """3 depoimentos por dia por IP para usuários não autenticados (fallback)."""
    scope = 'testimonial'


class TestimonialAPIView(APIView):
    """
    GET  /api/v1/testimonials  — lista os depoimentos aprovados (público)
    POST /api/v1/testimonials  — cria um novo depoimento (requer autenticação)
    """

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = Testimonial.objects.filter(is_approved=True).select_related('user')[:30]
        serializer = TestimonialReadSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        from django.utils import timezone
        today = timezone.now().date()
        today_count = Testimonial.objects.filter(
            user=request.user,
            created_at__date=today,
        ).count()
        if today_count >= 3:
            return Response(
                {'error': 'Você já enviou 3 depoimentos hoje. Tente novamente amanhã.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = TestimonialCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        testimonial = serializer.save(user=request.user)
        logger.info('New testimonial — user=%s rating=%s', request.user.email, testimonial.rating)
        return Response(TestimonialReadSerializer(testimonial).data, status=status.HTTP_201_CREATED)


class ProfileAPIView(APIView):
    """
    GET  /api/v1/user/profile  — retorna dados do usuário autenticado
    PATCH /api/v1/user/profile  — atualiza first_name, last_name, phone, date_of_birth
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UpdateProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(UserProfileSerializer(request.user).data, status=status.HTTP_200_OK)


class ChangePasswordAPIView(APIView):
    """
    POST /api/v1/user/change-password
    Altera a senha do usuário autenticado.
    Body: { current_password, new_password }
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')

        if not current_password or not new_password:
            return Response(
                {'error': 'current_password e new_password são obrigatórios.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(current_password):
            return Response(
                {'error': 'Senha atual incorreta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 8:
            return Response(
                {'error': 'A nova senha deve ter pelo menos 8 caracteres.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if current_password == new_password:
            return Response(
                {'error': 'A nova senha deve ser diferente da senha atual.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        request.user.set_password(new_password)
        request.user.save(update_fields=['password'])
        logger.info('Password changed — user_id=%d', request.user.id)

        return Response({'message': 'Senha alterada com sucesso.'}, status=status.HTTP_200_OK)


class DeleteAccountAPIView(APIView):
    """
    DELETE /api/v1/user/delete-account
    Exclui permanentemente a conta do usuário autenticado e todos os dados relacionados.
    Body: { password } — confirmação obrigatória de senha
    Requer: Authorization: Bearer <token>
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        password = request.data.get('password', '')

        if not password:
            return Response(
                {'error': 'A senha é obrigatória para confirmar a exclusão da conta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(password):
            return Response(
                {'error': 'Senha incorreta. Não foi possível excluir a conta.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_id = request.user.id
        user_email = request.user.email
        request.user.delete()
        logger.info('Account permanently deleted — user_id=%d email=%s', user_id, user_email)

        return Response({'message': 'Conta excluída com sucesso.'}, status=status.HTTP_200_OK)

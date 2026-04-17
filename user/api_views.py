import logging

from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

from rest_framework import status, serializers as drf_serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .forms import ContatoForm
from .serializers import RegisterSerializer, UserProfileSerializer, UpdateProfileSerializer

logger = logging.getLogger(__name__)

User = get_user_model()


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


class EmailTokenObtainPairView(TokenObtainPairView):
    """
    POST /api/auth/login
    Aceita { email, password } e retorna { token, refresh, user }.
    O campo 'user' é incluído para que o frontend possa salvar os dados
    do usuário no localStorage sem precisar de uma chamada adicional.
    """
    serializer_class = EmailTokenObtainPairSerializer

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
        return Response(
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

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class CookieJWTAuthentication(JWTAuthentication):
    """
    Autentica usando o cookie HttpOnly 'mynutri_access'.
    Fallback automático para header 'Authorization: Bearer' (API clients e testes).

    Tokens inválidos/expirados no cookie são ignorados silenciosamente (retornam None)
    para não bloquear views públicas (AllowAny) quando o usuário tem cookie obsoleto.
    """

    def authenticate(self, request):
        # 1. Header Authorization presente → comportamento padrão do simplejwt
        if self.get_header(request):
            return super().authenticate(request)

        # 2. Cookie HttpOnly
        raw_token = request.COOKIES.get('mynutri_access')
        if not raw_token:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
            return self.get_user(validated_token), validated_token
        except (InvalidToken, TokenError):
            # Token expirado ou inválido no cookie — não bloqueia views públicas.
            # Views que exigem autenticação rejeitarão a requisição via IsAuthenticated.
            return None

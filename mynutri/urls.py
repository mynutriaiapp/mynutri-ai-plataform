from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.generic import TemplateView
from django.views.decorators.cache import cache_page
from django.db import connection

# 1 hora para páginas estáticas que não mudam por sessão
_CACHE_1H = cache_page(60 * 60)
# Páginas autenticadas não devem ser cacheadas no browser (dados pessoais)
_CACHE_NO_STORE = cache_page(0)


def health_check(request):
    try:
        connection.ensure_connection()
        return JsonResponse({'status': 'ok'})
    except Exception:
        return JsonResponse({'status': 'error'}, status=503)


urlpatterns = [
    # Frontend pages — páginas públicas cacheadas por 1h; páginas autenticadas sem cache
    path('', _CACHE_1H(TemplateView.as_view(template_name='index.html')), name='home'),
    path('auth/', _CACHE_1H(TemplateView.as_view(template_name='auth.html')), name='auth'),
    path('dieta/', _CACHE_NO_STORE(TemplateView.as_view(template_name='dieta.html')), name='dieta'),
    path('perfil/', _CACHE_NO_STORE(TemplateView.as_view(template_name='perfil.html')), name='perfil'),
    path('questionario/', _CACHE_NO_STORE(TemplateView.as_view(template_name='questionario.html')), name='questionario'),
    path('historico/', _CACHE_NO_STORE(TemplateView.as_view(template_name='historico.html')), name='historico'),
    path('contato/', _CACHE_1H(TemplateView.as_view(template_name='contato.html')), name='contato'),
    path('privacidade/', _CACHE_1H(TemplateView.as_view(template_name='privacidade.html')), name='privacidade'),
    path('termos/', _CACHE_1H(TemplateView.as_view(template_name='termos.html')), name='termos'),
    # Backend
    path('health/', health_check, name='health-check'),
    path('admin/', admin.site.urls),
    path('api/v1/', include('user.urls_api', namespace='user')),
    path('api/v1/', include('nutrition.urls_api', namespace='nutrition')),
]

from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.views.generic import TemplateView
from django.db import connection


def health_check(request):
    try:
        connection.ensure_connection()
        return JsonResponse({'status': 'ok'})
    except Exception:
        return JsonResponse({'status': 'error'}, status=503)


urlpatterns = [
    # Frontend pages
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
    path('auth/', TemplateView.as_view(template_name='auth.html'), name='auth'),
    path('dieta/', TemplateView.as_view(template_name='dieta.html'), name='dieta'),
    path('perfil/', TemplateView.as_view(template_name='perfil.html'), name='perfil'),
    path('questionario/', TemplateView.as_view(template_name='questionario.html'), name='questionario'),
    path('historico/', TemplateView.as_view(template_name='historico.html'), name='historico'),
    path('contato/', TemplateView.as_view(template_name='contato.html'), name='contato'),
    path('privacidade/', TemplateView.as_view(template_name='privacidade.html'), name='privacidade'),
    path('termos/', TemplateView.as_view(template_name='termos.html'), name='termos'),
    # Backend
    path('health/', health_check, name='health-check'),
    path('admin/', admin.site.urls),
    path('api/v1/', include('user.urls_api', namespace='user')),
    path('api/v1/', include('nutrition.urls_api', namespace='nutrition')),
]

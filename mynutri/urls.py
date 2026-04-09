"""
URL configuration for mynutri project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse
from django.db import connection


def health_check(request):
    """Endpoint de health check — verifica conectividade com o banco."""
    try:
        connection.ensure_connection()
        return JsonResponse({'status': 'ok'})
    except Exception:
        return JsonResponse({'status': 'error'}, status=503)


urlpatterns = [
    # Health check (sem autenticação)
    path('health/', health_check, name='health-check'),

    # Painel de administração do Django
    path('admin/', admin.site.urls),

    # ===========================================================================
    # API REST — todos os endpoints sob /api/v1/
    # ===========================================================================
    path('api/v1/', include('user.urls_api')),
    path('api/v1/', include('nutrition.urls_api')),
]

"""
Django settings — MyNutri AI
Funciona tanto em desenvolvimento (SQLite + DEBUG=True) quanto em produção (PostgreSQL + Render).
"""

import os
import logging
from pathlib import Path
from datetime import timedelta

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carrega .env local (ignorado em produção — o Render injeta as vars diretamente)
load_dotenv(BASE_DIR / '.env')

# =============================================================================
# Validação de variáveis obrigatórias
# =============================================================================
_REQUIRED_VARS = {
    'SECRET_KEY': 'Django secret key (gere com: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")',
    'AI_API_KEY': 'Chave da API de IA (OpenAI, Gemini, etc.)',
    'AI_API_URL': 'URL do endpoint da API de IA',
}

for _var, _desc in _REQUIRED_VARS.items():
    if not os.getenv(_var):
        raise ValueError(
            f'\n❌ Variável "{_var}" não configurada.\n'
            f'   {_desc}\n'
            f'   Configure em .env (local) ou nas Environment Variables do Render.\n'
        )

# =============================================================================
# Core
# =============================================================================
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

# ALLOWED_HOSTS: lista do .env + domínio automático do Render ou Railway
_allowed = os.getenv('ALLOWED_HOSTS', '').split(',') if os.getenv('ALLOWED_HOSTS') else []
_render_host = os.getenv('RENDER_EXTERNAL_HOSTNAME')    # injetado automaticamente pelo Render
_railway_host = os.getenv('RAILWAY_PUBLIC_DOMAIN')      # injetado automaticamente pelo Railway
for _auto_host in (_render_host, _railway_host):
    if _auto_host:
        _allowed.append(_auto_host)
ALLOWED_HOSTS = [h.strip() for h in _allowed if h.strip()] or (['localhost', '127.0.0.1'] if DEBUG else [])

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# Apps
# =============================================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    # Projeto
    'user',
    'nutrition',
]

# =============================================================================
# Middleware — WhiteNoise logo após SecurityMiddleware
# =============================================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',       # serve static sem nginx
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mynutri.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'frontend' / 'public'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mynutri.wsgi.application'

# =============================================================================
# Banco de Dados
# Dev: SQLite (padrão se DATABASE_URL não estiver setado)
# Prod: PostgreSQL via DATABASE_URL (Render injeta automaticamente)
# =============================================================================
_db_url = os.getenv('DATABASE_URL', f'sqlite:///{BASE_DIR / "db.sqlite3"}')

# dj-database-url 2.x: conn_max_age recomendado para produção
DATABASES = {
    'default': dj_database_url.parse(
        _db_url,
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# =============================================================================
# Autenticação
# =============================================================================
AUTH_USER_MODEL = 'user.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =============================================================================
# Internacionalização
# =============================================================================
LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

# =============================================================================
# Arquivos estáticos — WhiteNoise + collectstatic
# =============================================================================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATICFILES_DIRS = [BASE_DIR / 'frontend']

# =============================================================================
# Django REST Framework
# =============================================================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/hour',
        'user': '60/hour',
        'diet_generate': '3/day',
    },
}

# =============================================================================
# SimpleJWT
# =============================================================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# =============================================================================
# CORS
# Dev: libera tudo. Prod: usa CORS_ALLOWED_ORIGINS do .env
# Formato: CORS_ALLOWED_ORIGINS=https://meusite.com,https://www.meusite.com
# =============================================================================
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    _cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', '')
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(',') if o.strip()]

CORS_ALLOW_CREDENTIALS = True

# =============================================================================
# Segurança — ativo apenas em produção (DEBUG=False)
# =============================================================================
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000        # 1 ano
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# =============================================================================
# Logging — INFO em dev, WARNING em prod, erros sempre visíveis
# =============================================================================
_log_level = os.getenv('LOG_LEVEL', 'INFO' if DEBUG else 'WARNING')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {module}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': _log_level,
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': _log_level,
            'propagate': False,
        },
        'nutrition': {
            'handlers': ['console'],
            'level': 'INFO',  # logs da IA sempre visíveis
            'propagate': False,
        },
    },
}

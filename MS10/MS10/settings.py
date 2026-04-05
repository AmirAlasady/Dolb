# MS10/MS10/settings.py

from datetime import timedelta
from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')
SESSION_COOKIE_NAME = "proj_sessionid10"
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    # This fallback should ideally not be hit if .env is loaded correctly
    # or if the environment variable is set directly in the deployment environment.
    SECRET_KEY = 'django-insecure-fallback-dev-key-!!change-me!!'
    print("WARNING: DJANGO_SECRET_KEY not found in environment or .env. Using fallback. THIS IS INSECURE FOR PRODUCTION.")

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = ['*']


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'data',
    'data_internals',
    'messaging',
    'storages',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'MS10.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'MS10.wsgi.application'


# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',},
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'


# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Authentication
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "data.custom_auth.ForceTokenUserJWTAuthentication",
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '20000/day'
    }
}


SIMPLE_JWT = {
    "SIGNING_KEY": JWT_SECRET_KEY,
    "VERIFYING_KEY": JWT_SECRET_KEY,
    "ISSUER": os.getenv('JWT_ISSUER', "https://ms1.auth-service.com"),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "LEEWAY": timedelta(seconds=10),
    "ALGORITHM": "HS256",
    "USER_ID_CLAIM": "user_id",
    "USER_ID_FIELD": "id",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser",
    "UPDATE_LAST_LOGIN": False,
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False, 
}

RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://agent_foundry_user:agent_foundry_pass@localhost:5672/')
PROJECT_SERVICE_URL = os.getenv('PROJECT_SERVICE_URL')


# ==============================================================================
# ==============================================================================
# 
#               ██████╗  ██╗██╗      █████╗ ████████╗
#               ██╔══██╗ ██║██║     ██╔══██╗╚══██╔══╝
#               ██████╔╝ ██║██║     ███████║   ██║   
#               ██╔═══╝  ██║██║     ██╔══██║   ██║   
#               ██║      ██║███████╗██║  ██║   ██║   
#               ╚═╝      ╚═╝╚══════╝╚═╝  ╚═╝   ╚═╝   
#
#               THE DEFINITIVE FIX FOR MINIO/S3 IS HERE
#
# ==============================================================================
# ==============================================================================

# 1. Basic credentials and location info from .env
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
AWS_S3_ENDPOINT_URL = os.getenv('AWS_S3_ENDPOINT_URL') # e.g., "http://localhost:9000"
AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME')
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

# 2. FORCE HTTP URLS. This is the most important setting to prevent the SSLError.
AWS_S3_SECURE_URLS = False

# 3. UNSET CUSTOM DOMAIN. Let django-storages build the URL from the endpoint.
#    By setting this to None, we force django-storages to derive the URL from
#    AWS_S3_ENDPOINT_URL, which correctly includes the 'http://' protocol.
#    This prevents the library from defaulting to HTTPS.
AWS_S3_CUSTOM_DOMAIN = None

# 4. Use the modern STORAGES setting to define the backend.
STORAGES = {
    "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
    "staticfiles": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
}
# Legacy setting for compatibility.
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
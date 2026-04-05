
from datetime import timedelta
import os
from pathlib import Path
from datetime import timedelta
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
from datetime import timedelta

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
SESSION_COOKIE_NAME = "proj_sessionid7"
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
# REST Framework
JWT_SECRET_KEY = os.getenv('JWT_SECRET_KEY')
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
    'rest_framework.authtoken',
    'tools',
    'tools_internals',
    'messaging',
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

ROOT_URLCONF = 'MS7.urls'

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

WSGI_APPLICATION = 'MS7.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'






# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_AUTHENTICATION_CLASSES": (
             
        "tools.custom_auth.ForceTokenUserJWTAuthentication", # <<< YOUR CUSTOM AUTH CLASS
    ),
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',  # Adjust as needed for unauthenticated requests
        'user': '20000/day' # Adjust as needed for authenticated requests
    }
}

SIMPLE_JWT = {

    "SIGNING_KEY": JWT_SECRET_KEY,  # <<< USE DJANGO'S SECRET_KEY LOADED FROM ENV
    "VERIFYING_KEY": JWT_SECRET_KEY,
    "ISSUER": os.getenv('JWT_ISSUER', "https://ms1.auth-service.com"), # MUST match MS1's issuer
    "AUTH_HEADER_TYPES": ("Bearer",),
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60), # e.g., 1 hour
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),    # e.g., 1 day
    "LEEWAY": timedelta(seconds=10),
    "ALGORITHM": "HS256",
    
    # --- Settings related to interpreting the token payload ---
    """
"USER_ID_CLAIM": "user_id": (Your Specific Question)
 This is a critical instruction. It tells simple-jwt:
   "When you parse the token's payload (the data inside),
     the claim that contains the user's primary identifier is named 'user_id'."
       Your MS1's CustomTokenObtainPairSerializer probably adds a claim with this name.
    """

    "USER_ID_CLAIM": "user_id",

    "USER_ID_FIELD": "id",
    "TOKEN_USER_CLASS": "rest_framework_simplejwt.models.TokenUser", # Explicitly use TokenUse

    # --- Settings for features MS2 likely DOES NOT use ---
    "UPDATE_LAST_LOGIN": False,
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False, 

}


RABBITMQ_URL = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')

NODE_SERVICE_URL= os.getenv('NODE_SERVICE_URL', 'http://localhost:8003')
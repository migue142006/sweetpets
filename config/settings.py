import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent.parent
# ENV_FILE permite separar .env, .env.test y .env.production; no sobrescribe variables del SO.
load_dotenv(BASE_DIR / os.getenv('ENV_FILE', '.env'))
def boolean(name, default=False):
    return os.getenv(name, str(default)).lower() in ('true','1','yes')
def required(name):
    value = os.getenv(name)
    if not value or value.startswith('REEMPLAZAR'):
        raise ImproperlyConfigured(f'Configura {name} en tu archivo de entorno')
    return value
SECRET_KEY = required('DJANGO_SECRET_KEY')
DEBUG = boolean('DJANGO_DEBUG')
APP_ENV = os.getenv('APP_ENV','development')
if APP_ENV == 'production' and DEBUG:
    raise ImproperlyConfigured('DEBUG debe ser False en producción')
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS','127.0.0.1,localhost').split(',')
CSRF_TRUSTED_ORIGINS = list(filter(None, os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS','').split(',')))
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','clinic']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':required('DB_NAME'),'USER':required('DB_USER'),'PASSWORD':required('DB_PASSWORD'),'HOST':os.getenv('DB_HOST','127.0.0.1'),'PORT':os.getenv('DB_PORT','5432'),'CONN_MAX_AGE':0,'TEST':{'NAME':os.getenv('DB_TEST_NAME','test_sweetpets_dev')}}}
AUTH_USER_MODEL = 'clinic.User'
AUTHENTICATION_BACKENDS = ['clinic.auth.LockoutBackend']
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':10}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = LOGIN_URL
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 3600
X_FRAME_OPTIONS = 'DENY'
if APP_ENV == 'production':
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND','django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST','')
EMAIL_PORT = int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS = boolean('EMAIL_USE_TLS',True)
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL','no-reply@example.com')
EMAIL_TIMEOUT = 10

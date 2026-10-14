"""ZIDICARHIRE settings. Values come from the .env file next to manage.py (see .env.example)."""
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from .env import env_bool, env_int, env_list, env_str, env_time

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

DEBUG = env_bool('DEBUG', False)
SECRET_KEY = env_str('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Set SECRET_KEY in .env (see .env.example for how to generate one).')
    SECRET_KEY = 'dev-only-insecure-key-change-me'
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')
SITE_URL = env_str('SITE_URL', 'http://localhost:8000').rstrip('/')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'fleet',
    'bookings',
    'payments',
    'chat',
    'dashboard',
    'pages',
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

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'fleet.context_processors.business',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------- Uploads ----------
MAX_UPLOAD_MB = env_int('MAX_UPLOAD_MB', 5, minimum=1)
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = (MAX_UPLOAD_MB + 1) * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'dashboard:login'
LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'dashboard:login'

CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# ---------- Email ----------
EMAIL_HOST = env_str('EMAIL_HOST')
EMAIL_PORT = env_int('EMAIL_PORT', 587)
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', False)
EMAIL_HOST_USER = env_str('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env_str('EMAIL_HOST_PASSWORD')
# Emails print in the terminal until the mail server login is filled in.
if EMAIL_HOST and EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = env_str('DEFAULT_FROM_EMAIL', 'ZIDICARHIRE <noreply@zidicarhire.com>')
EMAIL_TIMEOUT = 10
ADMIN_NOTIFY_EMAILS = env_list('ADMIN_NOTIFY_EMAILS')

# ---------- PayHero M-Pesa ----------
PAYHERO_AUTH_TOKEN = env_str('PAYHERO_AUTH_TOKEN')
PAYHERO_API_USERNAME = env_str('PAYHERO_API_USERNAME')
PAYHERO_API_PASSWORD = env_str('PAYHERO_API_PASSWORD')
PAYHERO_CHANNEL_ID = env_str('PAYHERO_CHANNEL_ID')
MPESA_TILL_NUMBER = env_str('MPESA_TILL_NUMBER')
MPESA_ACCOUNT_NAME = env_str('MPESA_ACCOUNT_NAME', 'ZIDICARHIRE')
FAKE_PAYMENTS = env_bool('FAKE_PAYMENTS', False)

# ---------- Booking rules ----------
# Unpaid bookings hold the car for this long, then release it.
BOOKING_HOLD_MINUTES = env_int('BOOKING_HOLD_MINUTES', 10, minimum=1)
MIN_RENTAL_DAYS = env_int('MIN_RENTAL_DAYS', 1, minimum=1)
MAX_RENTAL_DAYS = max(env_int('MAX_RENTAL_DAYS', 60, minimum=1), MIN_RENTAL_DAYS)
BUSINESS_OPEN_TIME = env_time('BUSINESS_OPEN_TIME', '07:00')
BUSINESS_CLOSE_TIME = env_time('BUSINESS_CLOSE_TIME', '20:00')

BUSINESS = {
    'name': env_str('BUSINESS_NAME', 'ZIDICARHIRE'),
    'phone': env_str('BUSINESS_PHONE', '+254700000000'),
    'whatsapp': env_str('BUSINESS_WHATSAPP'),
    'email': env_str('BUSINESS_EMAIL', 'bookings@zidicarhire.com'),
    'address': env_str('BUSINESS_ADDRESS'),
    'location': env_str('BUSINESS_LOCATION', 'Nairobi, Kenya'),
    'kra_pin': env_str('KRA_PIN'),
    'till_number': MPESA_TILL_NUMBER,
    'till_name': MPESA_ACCOUNT_NAME,
}

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}

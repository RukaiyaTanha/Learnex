from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()
from urllib.parse import urlparse, parse_qs

BASE_DIR = Path(__file__).resolve().parent.parent

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-#a%2062@#6dv0mre7sbrce5&)-9fs-cmf0xopt*#1qw%ma9a=i')

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('1', 'true', 'yes')

# Allow hosts configurable via `ALLOWED_HOSTS` env var (comma-separated).
# Default includes Render's `onrender.com` subdomains so the app works there
# even if the environment variable is not set yet.
ALLOWED_HOSTS = [h for h in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost,testserver,.onrender.com').split(',') if h]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
]

AUTH_USER_MODEL = 'accounts.CustomUser'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],  # 🔥 Added global templates folder
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

# WSGI application
WSGI_APPLICATION = 'core.wsgi.application'

# Original MySQL config (kept as commented reference):
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.mysql',
#         'NAME': 'SmartClassDB',
#         'USER': 'root',
#         'PASSWORD': 'tanha2003',
#         'HOST': '127.0.0.1',
#         'PORT': '3306',
#     }
# }

# Database configuration selectable via environment variable `DB_ENGINE`.
# Set `DB_ENGINE=postgresql` to use PostgreSQL, otherwise defaults to MySQL.
DB_ENGINE = os.getenv('DB_ENGINE', 'mysql').lower()

if DB_ENGINE in ('postgres', 'postgresql', 'psql'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB', os.getenv('DB_NAME', 'SmartClassDB')),
            'USER': os.getenv('POSTGRES_USER', os.getenv('DB_USER', 'postgres')),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', os.getenv('DB_PASSWORD', '')),
            'HOST': os.getenv('POSTGRES_HOST', os.getenv('DB_HOST', '127.0.0.1')),
            'PORT': os.getenv('POSTGRES_PORT', os.getenv('DB_PORT', '5432')),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('MYSQL_DATABASE', os.getenv('DB_NAME', 'SmartClassDB')),
            'USER': os.getenv('MYSQL_USER', os.getenv('DB_USER', 'root')),
            'PASSWORD': os.getenv('MYSQL_PASSWORD', os.getenv('DB_PASSWORD', 'tanha2003')),
            'HOST': os.getenv('MYSQL_HOST', os.getenv('DB_HOST', '127.0.0.1')),
            'PORT': os.getenv('MYSQL_PORT', os.getenv('DB_PORT', '3306')),
        }
    }

# If a single DATABASE_URL is provided (e.g. Render's provided DATABASE_URL), parse it
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    scheme = parsed.scheme
    if scheme.startswith('postgres'):
        engine = 'django.db.backends.postgresql'
    elif scheme.startswith('mysql'):
        engine = 'django.db.backends.mysql'
    elif scheme.startswith('sqlite'):
        engine = 'django.db.backends.sqlite3'
    else:
        engine = 'django.db.backends.postgresql'

    db_name = parsed.path[1:] if parsed.path and parsed.path.startswith('/') else parsed.path
    db_user = parsed.username or ''
    db_password = parsed.password or ''
    db_host = parsed.hostname or ''
    db_port = parsed.port or ''

    # parse any query params (e.g., ?sslmode=require)
    query_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    DATABASES = {
        'default': {
            'ENGINE': engine,
            'NAME': db_name,
            'USER': db_user,
            'PASSWORD': db_password,
            'HOST': db_host,
            'PORT': str(db_port),
            'OPTIONS': {},
        }
    }

    # apply sslmode if provided
    if 'sslmode' in query_params and query_params['sslmode'] in ('require', 'verify-full'):
        DATABASES['default']['OPTIONS']['sslmode'] = query_params['sslmode']

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Use WhiteNoise storage for static files in production
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# default primary key field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email backend configuration
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "tanharukiya@gmail.com"       # replace with your Gmail
EMAIL_HOST_PASSWORD = "mwjd cmzx izea wgrk"      # NOT your real password, use app password
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


# optional: check
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
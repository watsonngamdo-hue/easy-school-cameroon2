"""
Configuration Django d'Easy School Cameroon.

Tous les secrets et paramètres dépendant de l'environnement sont lus depuis les
variables d'environnement (ou un fichier .env, jamais versionné).
Voir .env.example pour la liste complète.
"""
from pathlib import Path
import os

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

# ---------------------------------------------------------------------------
# Sécurité de base
# ---------------------------------------------------------------------------
DEBUG = config("DEBUG", default=False, cast=bool)

SECRET_KEY = config("SECRET_KEY", default="")
if not SECRET_KEY:
    if DEBUG:
        # Clé jetable uniquement pour le développement local.
        SECRET_KEY = "dev-only-insecure-key-change-me"
    else:
        raise RuntimeError("La variable d'environnement SECRET_KEY est obligatoire en production.")

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,easyschoolcameroon.com,www.easyschoolcameroon.com",
    cast=Csv(),
)
# Render fournit automatiquement le nom d'hôte public du service.
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="https://easyschoolcameroon.com,https://www.easyschoolcameroon.com",
    cast=Csv(),
)
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# URL de l'administration Django (à garder discrète).
ADMIN_URL = config("ADMIN_URL", default="dangereasy-learn/").strip("/") + "/"

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "django.contrib.sites",
    # Tiers
    "embed_video",
    "bootstrap4",
    "crispy_bootstrap4",
    "ckeditor",
    "phonenumber_field",
    "crispy_forms",
    "multiselectfield",
    "storages",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "anymail",
    # Applications du projet
    "chatapp",
    "quizapp",
    "authapp",
    "aiapp",
    "programme",
    "depot",
    "profs",
]
if DEBUG:
    INSTALLED_APPS.append("django_extensions")

CRISPY_ALLOWED_TEMPLATE_PACKS = ["bootstrap4"]
CRISPY_TEMPLATE_PACK = "bootstrap4"
AUTH_USER_MODEL = "authapp.UserRegistration"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "Elearning.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "Elearning.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [TEMPLATES_DIR],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "chatapp.context_processors.unread_messages_count",
                "programme.context_processors.social_links",
            ],
        },
    },
]

WSGI_APPLICATION = "Elearning.wsgi.application"

# ---------------------------------------------------------------------------
# Base de données
#   1. DATABASE_URL (Render, Heroku, Neon…)
#   2. sinon POSTGRES_* (docker-compose)
#   3. sinon SQLite (développement)
# ---------------------------------------------------------------------------
if config("DATABASE_URL", default=""):
    DATABASES = {
        "default": dj_database_url.parse(
            config("DATABASE_URL"), conn_max_age=600, conn_health_checks=True
        )
    }
elif config("POSTGRES_DB", default=""):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("POSTGRES_DB"),
            "USER": config("POSTGRES_USER"),
            "PASSWORD": config("POSTGRES_PASSWORD"),
            "HOST": config("POSTGRES_HOST", default="db"),
            "PORT": config("POSTGRES_PORT", default=5432, cast=int),
            "CONN_MAX_AGE": 600,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": config("SQLITE_PATH", default=str(BASE_DIR / "db.sqlite3")),
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Cache / Celery
# ---------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    # Sans Redis, les tâches sont exécutées immédiatement dans le processus web.
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = False
    CELERY_BROKER_URL = "memory://"

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

# ---------------------------------------------------------------------------
# Authentification (django-allauth)
# ---------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/level"

ACCOUNT_ADAPTER = "allauth.account.adapter.DefaultAccountAdapter"
ACCOUNT_AUTHENTICATED_LOGIN_REDIRECTS = True
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_USER_MODEL_EMAIL_FIELD = "email"
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = config("ACCOUNT_EMAIL_VERIFICATION", default="mandatory")
# La confirmation se fait par un bouton (POST) : un antivirus ou un aperçu de lien
# ne peut plus confirmer un e-mail à la place de l'utilisateur.
ACCOUNT_CONFIRM_EMAIL_ON_GET = False
ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL = LOGIN_URL
ACCOUNT_EMAIL_CONFIRMATION_AUTHENTICATED_REDIRECT_URL = None
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 3
ACCOUNT_EMAIL_SUBJECT_PREFIX = "Easy School – "
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"
ACCOUNT_EMAIL_MAX_LENGTH = 254
ACCOUNT_MAX_EMAIL_ADDRESSES = 2
# Limitation du nombre de tentatives (anti force brute).
ACCOUNT_RATE_LIMITS = {
    "login": "30/m/ip",
    "login_failed": "5/5m/ip,5/5m/key",
    "signup": "10/h/ip",
    "reset_password": "5/h/ip,3/h/key",
    "reset_password_from_key": "20/h/key",
    "confirm_email": "3/h/key",
    "change_password": "5/m/user",
}
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False
# La déconnexion exige un POST protégé par CSRF.
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
ACCOUNT_LOGIN_ON_PASSWORD_RESET = False
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_SESSION_REMEMBER = None
ACCOUNT_SIGNUP_REDIRECT_URL = LOGIN_REDIRECT_URL
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_TEMPLATE_EXTENSION = "html"
ACCOUNT_USERNAME_BLACKLIST = ["admin", "administrateur", "administrator"]

ACCOUNT_FORMS = {
    "login": "authapp.forms.MyCustomLoginForm",
    "signup": "authapp.forms.MyCustomSignupForm",
}

CKEDITOR_CONFIGS = {
    "default": {
        "toolbar": [
            ["Bold", "Italic", "Underline"],
            ["Link", "Unlink"],
            ["NumberedList", "BulletedList"],
            ["RemoveFormat"],
        ],
        "height": 120,
        "width": "100%",
    },
}

# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------
BREVO_API_KEY = config("BREVO_API_KEY", default="")
DEFAULT_FROM_EMAIL = config("EMAIL_HOST_USER", default="no-reply@easyschoolcameroon.com")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
if BREVO_API_KEY:
    EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
    ANYMAIL = {"BREVO_API_KEY": BREVO_API_KEY}
else:
    # Sans clé Brevo, les e-mails sont affichés dans la console (développement / démo).
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fr"
TIME_ZONE = "Africa/Douala"
USE_I18N = True
USE_TZ = True
SITE_ID = 1
BASE_URL = config("BASE_URL", default="https://easyschoolcameroon.com/")

# ---------------------------------------------------------------------------
# Fichiers statiques et médias
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Les épreuves envoyées par les élèves ne sont JAMAIS servies publiquement.
PRIVATE_MEDIA_ROOT = Path(config("PRIVATE_MEDIA_ROOT", default=str(BASE_DIR / "private_media")))

AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME", default="")
USE_S3 = bool(AWS_STORAGE_BUCKET_NAME)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "private": {
        "BACKEND": "Elearning.storage.StockagePrive",
        "OPTIONS": {"location": str(PRIVATE_MEDIA_ROOT)},
    },
}
if USE_S3:
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN", default="") or None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False
    # Clé CloudFront : lue depuis l'environnement, jamais écrite dans le code.
    AWS_CLOUDFRONT_KEY_ID = config("AWS_CLOUDFRONT_KEY_ID", default="") or None
    _cf_key = config("AWS_CLOUDFRONT_KEY", default="").replace("\\n", "\n").strip()
    AWS_CLOUDFRONT_KEY = _cf_key.encode("ascii") if _cf_key else None
    STORAGES["default"] = {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}
    STORAGES["private"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "location": "private-epreuves",
            "default_acl": "private",
            "querystring_auth": True,
            "querystring_expire": 300,
            "custom_domain": None,
            "file_overwrite": False,
        },
    }

WHITENOISE_MANIFEST_STRICT = False
SERVE_MEDIA = config("SERVE_MEDIA", default=DEBUG, cast=bool)

# Limites d'upload (les vues appliquent ensuite leurs propres limites).
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000
FILE_UPLOAD_PERMISSIONS = 0o640

# ---------------------------------------------------------------------------
# Clés des services d'IA (jamais de valeur par défaut dans le code)
# ---------------------------------------------------------------------------
DEEPSEEK_API_KEY = config("DEEPSEEK_API_KEY", default="")
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")

# ---------------------------------------------------------------------------
# En-têtes et cookies de sécurité
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=not DEBUG, cast=bool)
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = False

# ---------------------------------------------------------------------------
# Journalisation (console uniquement, pas de contenu utilisateur en DEBUG)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "aiapp": {"handlers": ["console"], "level": config("AI_LOG_LEVEL", default="INFO"), "propagate": False},
    },
}

GRAPH_MODELS = {"all_applications": True, "group_models": True}

# ---------------------------------------------------------------------------
# Module de dépôt d'épreuves
# ---------------------------------------------------------------------------
DEPOT_RECOMPENSE_FCFA = config("DEPOT_RECOMPENSE_FCFA", default=25, cast=int)
DEPOT_TAILLE_MAX_MO = config("DEPOT_TAILLE_MAX_MO", default=10, cast=int)
DEPOT_LIMITE_PAR_JOUR = config("DEPOT_LIMITE_PAR_JOUR", default=20, cast=int)
# Espace professeurs
PROF_COMMISSION_PLATEFORME = config("PROF_COMMISSION_PLATEFORME", default=30, cast=int)  # % gardé par EasySchool
PROF_DELAI_DISPONIBILITE_JOURS = config("PROF_DELAI_DISPONIBILITE_JOURS", default=7, cast=int)
PROF_RETRAIT_MINIMUM = config("PROF_RETRAIT_MINIMUM", default=5000, cast=int)
PROF_VIDEO_TAILLE_MAX_MO = config("PROF_VIDEO_TAILLE_MAX_MO", default=300, cast=int)
PROF_PDF_TAILLE_MAX_MO = config("PROF_PDF_TAILLE_MAX_MO", default=30, cast=int)

# Protection des contenus payants
MAX_APPAREILS_PAR_COMPTE = config("MAX_APPAREILS_PAR_COMPTE", default=2, cast=int)
PROTECTION_LIMITE_PAR_HEURE = config("PROTECTION_LIMITE_PAR_HEURE", default=120, cast=int)
# True : l'épreuve est visible dans la banque de la classe dès son envoi.
# False : elle attend que l'administrateur la publie (action « Publier »).
DEPOT_PUBLICATION_AUTO = config("DEPOT_PUBLICATION_AUTO", default=True, cast=bool)

# ---------------------------------------------------------------------------
# Jazzmin (thème d'administration, optionnel)
# ---------------------------------------------------------------------------
JAZZMIN_SETTINGS = {
    "site_title": "EasySchool Admin",
    "site_header": "EasySchool",
    "site_brand": "EasySchool Cameroun",
    "welcome_sign": "Portail de gestion EasySchool",
    "show_ui_builder": False,
}

# CKEditor 4 n'est plus maintenu : tout HTML saisi est nettoyé côté serveur
# (Elearning/sanitize.py), ce qui neutralise ses failles XSS connues.
# Migration conseillée à terme : django-ckeditor-5.
SILENCED_SYSTEM_CHECKS = ["ckeditor.W001"]

import sys as _sys  # noqa: E402
if "test" in _sys.argv:
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

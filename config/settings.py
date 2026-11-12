"""
Configuración de Django para el proyecto Comunidades.

Los valores sensibles o que cambian entre entornos (clave secreta, base de datos)
se leen de variables de entorno. Ver `.env.example`.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(nombre: str, por_defecto: str) -> str:
    return os.environ.get(nombre, por_defecto)


# --- Seguridad ---------------------------------------------------------------
# La clave por defecto SOLO vale para desarrollo local. En producción se define
# DJANGO_SECRET_KEY y DJANGO_DEBUG=0.
SECRET_KEY = env("DJANGO_SECRET_KEY", "solo-desarrollo-no-usar-en-produccion")
DEBUG = env("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]


# --- Aplicaciones ------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Propias
    "core",
    "fincas",
    "contabilidad",
    "cobros",
    "bancos",
    "juntas",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "portal.contexto.portal",  # T5.1: es_vecino para el menú
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Base de datos -----------------------------------------------------------
# PostgreSQL en Docker (ver docker-compose.yml). Los valores por defecto
# coinciden con los del docker-compose para que funcione sin configurar nada.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "comunidades"),
        "USER": env("POSTGRES_USER", "comunidades"),
        "PASSWORD": env("POSTGRES_PASSWORD", "comunidades"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        # Falla rápido si la base de datos no está arrancada (en vez de colgarse).
        "OPTIONS": {"connect_timeout": 3},
    }
}

# Modelo de usuario propio. Debe definirse ANTES de la primera migración:
# cambiarlo después obliga a rehacer la base de datos.
AUTH_USER_MODEL = "core.Usuario"

# Login propio de la aplicación (el del admin es aparte, en /admin/login/).
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"  # T5.1: decide entre comunidades (despacho) y portal (vecino)
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Idioma y zona horaria ---------------------------------------------------
LANGUAGE_CODE = "es-es"
TIME_ZONE = "Europe/Madrid"

# --- Email (T4.1: convocatorias de junta) -------------------------------------------------
# En desarrollo, los emails se escriben en la consola del servidor en vez de enviarse. Para
# enviarlos de verdad: DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend y
# las variables EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD. En los tests,
# Django usa siempre un buzón en memoria (django.core.mail.outbox).
EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "25"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "0") == "1"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "comunidades@example.com")
USE_I18N = True
USE_TZ = True


# --- Ficheros estáticos ------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

"""Tests de humo de la Fase 0: el proyecto arranca y está bien configurado.

Todos menos los marcados con `django_db` pasan aunque Docker no esté arrancado.
"""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import resolve


def test_usa_modelo_de_usuario_propio():
    assert settings.AUTH_USER_MODEL == "core.Usuario"
    assert get_user_model()._meta.label == "core.Usuario"


def test_usa_postgresql():
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


def test_idioma_y_zona_horaria_de_espana():
    assert settings.LANGUAGE_CODE == "es-es"
    assert settings.TIME_ZONE == "Europe/Madrid"


def test_admin_esta_enrutado():
    assert resolve("/admin/").app_name == "admin"


@pytest.mark.django_db
def test_postgresql_guarda_y_lee_usuarios():
    Usuario = get_user_model()
    Usuario.objects.create_user(username="prueba", password="clave-de-prueba-123")
    assert Usuario.objects.get(username="prueba").check_password("clave-de-prueba-123")


def test_admin_redirige_al_login_sin_sesion(client, db):
    respuesta = client.get("/admin/")
    assert respuesta.status_code == 302
    assert respuesta.url.startswith("/admin/login/")

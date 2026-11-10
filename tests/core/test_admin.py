"""T1.1 — El admin de Django muestra despachos y la relación Usuario → Despacho."""

import pytest
from django.contrib.auth import get_user_model

from core.models import Despacho


@pytest.fixture
def cliente_admin(client):
    jefe = get_user_model().objects.create_superuser(username="jefe", password="clave-123-xyz")
    client.force_login(jefe)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url", ["/admin/core/despacho/", "/admin/core/despacho/add/", "/admin/core/usuario/add/"]
)
def test_paginas_del_admin_cargan(cliente_admin, url):
    assert cliente_admin.get(url).status_code == 200


@pytest.mark.django_db
def test_ficha_de_usuario_permite_elegir_despacho(cliente_admin):
    despacho = Despacho.objects.create(nombre="Fincas Alfa")
    usuario = get_user_model().objects.create_user(username="ana", despacho=despacho)
    respuesta = cliente_admin.get(f"/admin/core/usuario/{usuario.pk}/change/")
    assert respuesta.status_code == 200
    assert 'name="despacho"' in respuesta.content.decode()

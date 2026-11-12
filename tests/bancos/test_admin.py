"""T3.1 — Admin de extractos: solo lectura (se importan desde la web y son inmutables)."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from bancos.importacion import importar_norma43

from .conftest import fichero

pytestmark = pytest.mark.django_db


@pytest.fixture
def superusuario(db):
    return get_user_model().objects.create_superuser(username="root", password="x")


def test_lista_y_ficha_se_ven_sin_poder_cambiar(client, superusuario, comunidad):
    [guardado] = importar_norma43(comunidad, fichero(), nombre_fichero="abril.n43")
    client.force_login(superusuario)
    assert client.get(reverse("admin:bancos_extracto_changelist")).status_code == 200
    ficha = client.get(reverse("admin:bancos_extracto_change", args=[guardado.pk]))
    assert ficha.status_code == 200
    assert "REC-1-7" in ficha.content.decode()  # movimientos en línea
    assert client.get(reverse("admin:bancos_extracto_add")).status_code == 403
    borrar = reverse("admin:bancos_extracto_delete", args=[guardado.pk])
    assert client.post(borrar, {"post": "yes"}).status_code == 403

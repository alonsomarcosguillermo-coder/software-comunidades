"""T1.2 — Aislamiento: cada modelo de fincas sabe cómo llegar a su despacho
(`CAMPO_DESPACHO`) y se filtra con `filtrar_por_despacho`. Un usuario del despacho A
no ve nada del despacho B."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model

from core.aislamiento import filtrar_por_despacho
from fincas.models import CAMPO_DESPACHO, Comunidad, Inmueble, Propietario, Titularidad


@pytest.fixture
def usuaria_a(despacho_a):
    return get_user_model().objects.create_user(username="ana", despacho=despacho_a)


@pytest.fixture
def datos(comunidad_a, comunidad_b, piso_a, piso_b, propietaria_a, propietario_b, titularidad_a):
    titularidad_b = Titularidad.objects.create(
        inmueble=piso_b, propietario=propietario_b, fecha_inicio=date(2020, 1, 1)
    )
    return {
        Comunidad: (comunidad_a, comunidad_b),
        Inmueble: (piso_a, piso_b),
        Propietario: (propietaria_a, propietario_b),
        Titularidad: (titularidad_a, titularidad_b),
    }


@pytest.mark.django_db
@pytest.mark.parametrize("modelo", [Comunidad, Inmueble, Propietario, Titularidad])
def test_usuario_de_a_no_ve_datos_de_b(modelo, datos, usuaria_a):
    de_a, de_b = datos[modelo]
    visibles = filtrar_por_despacho(modelo.objects.all(), usuaria_a, CAMPO_DESPACHO[modelo])
    assert list(visibles) == [de_a]
    assert de_b not in visibles

"""T1.4 — Aislamiento: un usuario del despacho A no ve la contabilidad del despacho B."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from contabilidad.models import CAMPO_DESPACHO, Apunte, Asiento, Cuenta
from contabilidad.registro import registrar_asiento
from contabilidad.servicios import Linea
from core.aislamiento import filtrar_por_despacho


def _contabilidad(comunidad):
    banco = Cuenta.objects.create(comunidad=comunidad, codigo="572", nombre="Banco")
    caja = Cuenta.objects.create(comunidad=comunidad, codigo="570", nombre="Caja")
    asiento = registrar_asiento(
        comunidad,
        date(2026, 1, 1),
        "Traspaso",
        [Linea(banco, debe=Decimal("1.00")), Linea(caja, haber=Decimal("1.00"))],
    )
    return {Cuenta: {banco, caja}, Asiento: {asiento}, Apunte: set(asiento.apuntes.all())}


@pytest.mark.django_db
@pytest.mark.parametrize("modelo", [Cuenta, Asiento, Apunte])
def test_usuario_de_a_no_ve_contabilidad_de_b(modelo, comunidad, otra_comunidad):
    de_a = _contabilidad(comunidad)[modelo]
    de_b = _contabilidad(otra_comunidad)[modelo]
    usuaria = get_user_model().objects.create_user(username="ana", despacho=comunidad.despacho)
    visibles = set(filtrar_por_despacho(modelo.objects.all(), usuaria, CAMPO_DESPACHO[modelo]))
    assert visibles == de_a
    assert not visibles & de_b

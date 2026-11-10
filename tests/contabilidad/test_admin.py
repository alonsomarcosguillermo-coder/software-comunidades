"""T1.4 — Admin de contabilidad: las cuentas se gestionan; los asientos solo se consultan."""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from contabilidad.registro import registrar_asiento
from contabilidad.servicios import Linea


@pytest.fixture
def cliente_admin(client, db):
    jefe = get_user_model().objects.create_superuser(username="jefe", password="clave-123-xyz")
    client.force_login(jefe)
    return client


@pytest.fixture
def asiento(comunidad, banco, propietarios):
    return registrar_asiento(
        comunidad,
        date(2026, 1, 10),
        "Cobro",
        [Linea(banco, debe=Decimal("100.00")), Linea(propietarios, haber=Decimal("100.00"))],
    )


@pytest.mark.django_db
def test_paginas_cargan(cliente_admin, asiento, banco):
    for url in (
        "/admin/contabilidad/cuenta/",
        "/admin/contabilidad/cuenta/add/",
        f"/admin/contabilidad/cuenta/{banco.pk}/change/",
        "/admin/contabilidad/asiento/",
        f"/admin/contabilidad/asiento/{asiento.pk}/change/",
    ):
        assert cliente_admin.get(url).status_code == 200, url


@pytest.mark.django_db
def test_lista_de_cuentas_muestra_el_saldo_calculado(cliente_admin, asiento):
    html = cliente_admin.get("/admin/contabilidad/cuenta/").content.decode()
    assert "100,00" in html
    assert "-100,00" in html


@pytest.mark.django_db
def test_asientos_no_se_crean_ni_borran_desde_el_admin(cliente_admin, asiento):
    assert cliente_admin.get("/admin/contabilidad/asiento/add/").status_code == 403
    respuesta = cliente_admin.get(f"/admin/contabilidad/asiento/{asiento.pk}/delete/")
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_asientos_no_se_modifican_desde_el_admin(cliente_admin, asiento):
    url = f"/admin/contabilidad/asiento/{asiento.pk}/change/"
    cliente_admin.post(url, {"concepto": "Cambiado"})
    asiento.refresh_from_db()
    assert asiento.concepto == "Cobro"

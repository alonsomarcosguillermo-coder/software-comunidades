"""T2.1 — Página de presupuestos de una comunidad (con el estado del fondo de reserva).

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver los datos.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from contabilidad.registro import registrar_asiento
from contabilidad.servicios import Linea

from .conftest import D

pytestmark = pytest.mark.django_db


def _url(comunidad):
    return reverse("cobros:presupuestos_comunidad", args=[comunidad.pk])


@pytest.fixture
def ana(despacho_a):
    return get_user_model().objects.create_user(username="ana", despacho=despacho_a)


@pytest.fixture
def berta(despacho_b):
    return get_user_model().objects.create_user(username="berta", despacho=despacho_b)


@pytest.fixture
def sin_despacho(db):
    return get_user_model().objects.create_user(username="suelto")


def _dotar(comunidad, banco, fondo, importe):
    registrar_asiento(
        comunidad,
        date(2026, 1, 31),
        "Dotación al fondo de reserva",
        [Linea(banco, debe=D(importe)), Linea(fondo, haber=D(importe))],
    )


# --- Acceso y aislamiento -----------------------------------------------------------


def test_sin_sesion_redirige_al_login(client, presupuesto_a):
    respuesta = client.get(_url(presupuesto_a.comunidad))
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse("login"))


def test_aislamiento_usuario_de_a_no_ve_presupuestos_de_b(client, ana, presupuesto_b):
    client.force_login(ana)
    assert client.get(_url(presupuesto_b.comunidad)).status_code == 404


def test_aislamiento_usuario_de_b_no_ve_presupuestos_de_a(client, berta, presupuesto_a):
    client.force_login(berta)
    assert client.get(_url(presupuesto_a.comunidad)).status_code == 404


def test_aislamiento_usuario_sin_despacho_no_ve_nada(client, sin_despacho, presupuesto_a):
    client.force_login(sin_despacho)
    assert client.get(_url(presupuesto_a.comunidad)).status_code == 404


def test_aislamiento_solo_aparecen_presupuestos_de_la_comunidad(
    client, ana, presupuesto_a, presupuesto_b
):
    client.force_login(ana)
    respuesta = client.get(_url(presupuesto_a.comunidad))
    assert [f.presupuesto for f in respuesta.context["filas"]] == [presupuesto_a]
    assert "Ascensor" not in respuesta.content.decode()  # partida de la comunidad de B


# --- Contenido ----------------------------------------------------------------------


def test_muestra_partidas_y_totales(client, ana, presupuesto_a):
    client.force_login(ana)
    html = client.get(_url(presupuesto_a.comunidad)).content.decode()
    assert "Ejercicio 2026" in html
    assert "Borrador" in html
    assert "Limpieza" in html and "2500,00 €" in html
    assert "4000,00 €" in html  # gastos
    assert "4500,00 €" in html  # total a cobrar


def test_presupuesto_aprobado_muestra_la_fecha(client, ana, aprobado_a):
    client.force_login(ana)
    assert "Aprobado el 15/1/2026" in client.get(_url(aprobado_a.comunidad)).content.decode()


def test_comunidad_sin_presupuestos(client, ana, comunidad_a):
    client.force_login(ana)
    assert "todavía no tiene presupuestos" in client.get(_url(comunidad_a)).content.decode()


def test_r_res_01_avisa_si_no_hay_cuenta_de_fondo(client, ana, aprobado_a):
    client.force_login(ana)
    html = client.get(_url(aprobado_a.comunidad)).content.decode()
    assert "ninguna cuenta contable marcada como fondo de" in html


def test_r_res_01_avisa_si_no_hay_presupuesto_aprobado(client, ana, presupuesto_a, fondo_a):
    client.force_login(ana)
    html = client.get(_url(presupuesto_a.comunidad)).content.decode()
    assert "no hay ningún presupuesto" in html


def test_r_res_01_muestra_lo_que_falta(client, ana, aprobado_a, banco_a, fondo_a):
    _dotar(aprobado_a.comunidad, banco_a, fondo_a, "350.00")
    client.force_login(ana)
    html = client.get(_url(aprobado_a.comunidad)).content.decode()
    assert "Faltan 50,00 € para el mínimo legal" in html


def test_r_res_01_muestra_que_cumple(client, ana, aprobado_a, banco_a, fondo_a):
    _dotar(aprobado_a.comunidad, banco_a, fondo_a, "400.00")
    client.force_login(ana)
    assert "Cumple R-RES-01" in client.get(_url(aprobado_a.comunidad)).content.decode()


def test_r_res_01_prevision_con_la_aportacion_del_presupuesto(
    client, ana, presupuesto_a, banco_a, fondo_a
):
    # Saldo 0 + aportación 500 € frente a un mínimo de 400 €: llegará.
    client.force_login(ana)
    fila = client.get(_url(presupuesto_a.comunidad)).context["filas"][0]
    assert fila.prevision.saldo == D("500.00")
    assert fila.prevision.cumple


def test_la_lista_de_comunidades_enlaza_con_sus_presupuestos(client, ana, comunidad_a):
    client.force_login(ana)
    html = client.get(reverse("fincas:lista_comunidades")).content.decode()
    assert _url(comunidad_a) in html

"""T2.2 — Emitir cuotas desde la página de presupuestos.

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver ni modificar los datos.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from cobros.emision import emitir_cuotas
from cobros.models import Emision
from fincas.models import Inmueble

from .conftest import D

pytestmark = pytest.mark.django_db


def _url_emitir(presupuesto):
    return reverse("cobros:emitir_cuotas", args=[presupuesto.comunidad_id, presupuesto.pk])


def _url_pagina(presupuesto):
    return reverse("cobros:presupuestos_comunidad", args=[presupuesto.comunidad_id])


def _usuario(username, despacho, con_permiso=True):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    if con_permiso:
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="cobros", codename="add_emision")
        )
    return usuario


@pytest.fixture
def listo(aprobado_a, fondo_a):
    for referencia, coeficiente in [("1A", "60"), ("L1", "40")]:
        Inmueble.objects.create(
            comunidad=aprobado_a.comunidad,
            tipo=Inmueble.Tipo.PISO,
            referencia=referencia,
            coeficiente=D(coeficiente),
        )
    return aprobado_a


@pytest.fixture
def ana(despacho_a):
    return _usuario("ana", despacho_a)


@pytest.fixture
def berta(despacho_b):
    return _usuario("berta", despacho_b)


DATOS = {"periodo": "1", "fecha": "2026-01-05"}


# --- Emitir -------------------------------------------------------------------------


def test_emite_y_redirige_con_mensaje(client, ana, listo):
    client.force_login(ana)
    respuesta = client.post(_url_emitir(listo), DATOS, follow=True)
    assert respuesta.redirect_chain == [(_url_pagina(listo), 302)]
    emision = Emision.objects.get(presupuesto=listo, periodo=1)
    assert emision.fecha == date(2026, 1, 5)
    assert "Emitidas las cuotas del periodo 1/4 de 2026" in respuesta.content.decode()


def test_error_de_negocio_se_muestra_como_mensaje(client, ana, listo):
    emitir_cuotas(listo, 1, date(2026, 1, 5))
    client.force_login(ana)
    respuesta = client.post(_url_emitir(listo), DATOS, follow=True)
    assert "ya está emitido" in respuesta.content.decode()
    assert Emision.objects.count() == 1


def test_r_pre_01_no_emite_un_borrador(client, ana, presupuesto_a, fondo_a):
    client.force_login(ana)
    respuesta = client.post(_url_emitir(presupuesto_a), DATOS, follow=True)
    assert "R-PRE-01" in respuesta.content.decode()
    assert not Emision.objects.exists()


def test_datos_invalidos(client, ana, listo):
    client.force_login(ana)
    respuesta = client.post(_url_emitir(listo), {"periodo": "x"}, follow=True)
    assert "periodo y una fecha válidos" in respuesta.content.decode()
    assert not Emision.objects.exists()


def test_solo_acepta_post(client, ana, listo):
    client.force_login(ana)
    assert client.get(_url_emitir(listo)).status_code == 405


def test_sin_sesion_no_emite(client, listo):
    respuesta = client.post(_url_emitir(listo), DATOS)
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse("login"))
    assert not Emision.objects.exists()


def test_sin_permiso_no_emite(client, despacho_a, listo):
    client.force_login(_usuario("emilio", despacho_a, con_permiso=False))
    assert client.post(_url_emitir(listo), DATOS).status_code == 403
    assert not Emision.objects.exists()


def test_aislamiento_usuario_de_otro_despacho_no_puede_emitir(client, berta, listo):
    client.force_login(berta)
    assert client.post(_url_emitir(listo), DATOS).status_code == 404
    assert not Emision.objects.exists()


def test_aislamiento_no_vale_mezclar_comunidad_propia_con_presupuesto_ajeno(
    client, berta, listo, comunidad_b
):
    # La URL lleva la comunidad de Berta pero el presupuesto de Ana: 404.
    client.force_login(berta)
    url = reverse("cobros:emitir_cuotas", args=[comunidad_b.pk, listo.pk])
    assert client.post(url, DATOS).status_code == 404
    assert not Emision.objects.exists()


# --- Página de presupuestos -------------------------------------------------------------


def test_la_pagina_muestra_los_periodos_emitidos_y_pendientes(client, ana, listo):
    emision = emitir_cuotas(listo, 1, date(2026, 1, 5))
    client.force_login(ana)
    respuesta = client.get(_url_pagina(listo))
    html = respuesta.content.decode()
    assert "Cuotas (trimestral)" in html
    assert "Emitido el 5/1/2026" in html
    assert f"asiento {emision.asiento.numero}" in html
    assert "1125,00 €" in html
    assert html.count('name="periodo"') == 3  # quedan 3 periodos por emitir


def test_sin_permiso_no_aparecen_los_botones(client, despacho_a, listo):
    client.force_login(_usuario("emilio", despacho_a, con_permiso=False))
    html = client.get(_url_pagina(listo)).content.decode()
    assert 'name="periodo"' not in html
    assert "Pendiente" in html


def test_un_borrador_no_muestra_cuotas(client, ana, presupuesto_a):
    client.force_login(ana)
    assert "Cuotas (" not in client.get(_url_pagina(presupuesto_a)).content.decode()

"""T2.3 — Página de derramas de una comunidad y admin de derramas y grupos de reparto.

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver los datos.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from cobros.derramas import emitir_derrama
from cobros.models import Derrama
from fincas.models import GrupoReparto

from .conftest import D

pytestmark = pytest.mark.django_db


def _url(comunidad):
    return reverse("cobros:derramas_comunidad", args=[comunidad.pk])


@pytest.fixture
def ana(despacho_a):
    return get_user_model().objects.create_user(username="ana", despacho=despacho_a)


@pytest.fixture
def cliente_admin(client):
    jefe = get_user_model().objects.create_superuser(username="jefe", password="clave-123-xyz")
    client.force_login(jefe)
    return client


# --- Página: acceso y aislamiento -----------------------------------------------------


def test_sin_sesion_redirige_al_login(client, derrama_a):
    respuesta = client.get(_url(derrama_a.comunidad))
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse("login"))


def test_aislamiento_usuario_de_a_no_ve_derramas_de_b(client, ana, derrama_b):
    client.force_login(ana)
    assert client.get(_url(derrama_b.comunidad)).status_code == 404


def test_usuario_sin_despacho_no_ve_nada(client, derrama_a):
    client.force_login(get_user_model().objects.create_user(username="suelto"))
    assert client.get(_url(derrama_a.comunidad)).status_code == 404


# --- Página: contenido ----------------------------------------------------------------


def test_muestra_el_reparto_previsto_por_inmueble_y_plazo(client, ana, derrama_a, derrama_b):
    client.force_login(ana)
    respuesta = client.get(_url(derrama_a.comunidad))
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "Fachada" in html
    assert "Reparto previsto" in html
    assert "Tejado" not in html  # derrama de otro despacho
    (ficha,) = respuesta.context["fichas"]
    assert [f.inmueble.referencia for f in ficha.filas] == ["1A", "1B", "L1"]
    assert [f.cuotas for f in ficha.filas] == [
        [D("300.00")] * 3,
        [D("300.00")] * 3,
        [D("400.00")] * 3,
    ]
    assert "1/4/2026" in html  # vencimiento del plazo 2


def test_muestra_el_reparto_emitido(client, ana, derrama_a, grupo_ascensor_a):
    derrama_a.grupo = grupo_ascensor_a
    derrama_a.save()
    emitir_derrama(derrama_a, date(2026, 1, 25))
    # Cambiar el grupo después no cambia lo que se muestra: es lo emitido.
    grupo_ascensor_a.miembros.filter(inmueble__referencia="1B").delete()
    client.force_login(ana)
    respuesta = client.get(_url(derrama_a.comunidad))
    html = respuesta.content.decode()
    assert "Emitida" in html
    assert "Reparto previsto" not in html
    (ficha,) = respuesta.context["fichas"]
    assert [(f.inmueble.referencia, f.total) for f in ficha.filas] == [
        ("1A", D("1500.00")),
        ("1B", D("1500.00")),
    ]


def test_explica_por_que_no_se_puede_repartir(client, ana, derrama_a, inmuebles_a):
    inmuebles_a["L1"].delete()
    client.force_login(ana)
    html = client.get(_url(derrama_a.comunidad)).content.decode()
    assert "No se puede repartir" in html
    assert "R-COEF-01" in html


def test_comunidad_sin_derramas(client, ana, comunidad_a):
    client.force_login(ana)
    assert "no tiene derramas" in client.get(_url(comunidad_a)).content.decode()


def test_la_pagina_de_presupuestos_enlaza_las_derramas(client, ana, comunidad_a):
    client.force_login(ana)
    url = reverse("cobros:presupuestos_comunidad", args=[comunidad_a.pk])
    assert _url(comunidad_a) in client.get(url).content.decode()


# --- Admin ----------------------------------------------------------------------------

URL_DERRAMAS = "/admin/cobros/derrama/"
URL_GRUPOS = "/admin/fincas/gruporeparto/"


def test_paginas_del_admin_cargan(cliente_admin, derrama_a, derrama_b, grupo_ascensor_a):
    emitir_derrama(derrama_b, date(2026, 2, 15))
    for url in (
        URL_DERRAMAS,
        f"{URL_DERRAMAS}add/",
        f"{URL_DERRAMAS}{derrama_a.pk}/change/",
        f"{URL_DERRAMAS}{derrama_b.pk}/change/",  # emitida
        URL_GRUPOS,
        f"{URL_GRUPOS}add/",
        f"{URL_GRUPOS}{grupo_ascensor_a.pk}/change/",
    ):
        assert cliente_admin.get(url).status_code == 200, url


def test_admin_accion_emitir(cliente_admin, derrama_a):
    respuesta = cliente_admin.post(
        URL_DERRAMAS, {"action": "emitir", "_selected_action": [derrama_a.pk]}, follow=True
    )
    assert respuesta.status_code == 200
    assert Derrama.objects.get(pk=derrama_a.pk).esta_emitida
    assert derrama_a.cuotas.count() == 9


def test_admin_accion_emitir_explica_el_error(cliente_admin, derrama_a):
    derrama_a.fecha_acuerdo = None
    derrama_a.save()
    respuesta = cliente_admin.post(
        URL_DERRAMAS, {"action": "emitir", "_selected_action": [derrama_a.pk]}, follow=True
    )
    assert "sin acordar" in respuesta.content.decode()
    assert not Derrama.objects.get(pk=derrama_a.pk).esta_emitida


def test_admin_derrama_emitida_es_de_solo_lectura(cliente_admin, derrama_a):
    emitir_derrama(derrama_a, date(2026, 1, 25))
    html = cliente_admin.get(f"{URL_DERRAMAS}{derrama_a.pk}/change/").content.decode()
    assert 'name="importe"' not in html
    assert f"{URL_DERRAMAS}{derrama_a.pk}/delete/" not in html


def _datos_grupo(comunidad, miembros):
    datos = {
        "comunidad": comunidad.pk,
        "nombre": "Ascensor",
        "miembros-TOTAL_FORMS": str(len(miembros)),
        "miembros-INITIAL_FORMS": "0",
        "miembros-MIN_NUM_FORMS": "0",
        "miembros-MAX_NUM_FORMS": "1000",
    }
    for i, (inmueble, coeficiente) in enumerate(miembros):
        datos |= {f"miembros-{i}-inmueble": inmueble.pk, f"miembros-{i}-coeficiente": coeficiente}
    return datos


def test_admin_crear_grupo_con_inmuebles(cliente_admin, inmuebles_a):
    comunidad = inmuebles_a["1A"].comunidad
    datos = _datos_grupo(comunidad, [(inmuebles_a["1A"], ""), (inmuebles_a["1B"], "")])
    respuesta = cliente_admin.post(f"{URL_GRUPOS}add/", datos)
    assert respuesta.status_code == 302
    grupo = GrupoReparto.objects.get()
    assert set(grupo.coeficientes()) == {inmuebles_a["1A"].pk, inmuebles_a["1B"].pk}


def test_r_rep_01_admin_rechaza_grupo_con_coeficientes_mezclados(cliente_admin, inmuebles_a):
    comunidad = inmuebles_a["1A"].comunidad
    datos = _datos_grupo(comunidad, [(inmuebles_a["1A"], "60"), (inmuebles_a["1B"], "")])
    respuesta = cliente_admin.post(f"{URL_GRUPOS}add/", datos)
    assert respuesta.status_code == 200
    assert "todos o ninguno" in respuesta.content.decode()
    assert not GrupoReparto.objects.exists()


def test_admin_rechaza_inmueble_de_otra_comunidad(cliente_admin, inmuebles_a, derrama_b):
    comunidad = inmuebles_a["1A"].comunidad
    inmueble_b = derrama_b.comunidad.inmuebles.get()
    datos = _datos_grupo(comunidad, [(inmuebles_a["1A"], ""), (inmueble_b, "")])
    respuesta = cliente_admin.post(f"{URL_GRUPOS}add/", datos)
    assert respuesta.status_code == 200
    assert "otra comunidad" in respuesta.content.decode()
    assert not GrupoReparto.objects.exists()

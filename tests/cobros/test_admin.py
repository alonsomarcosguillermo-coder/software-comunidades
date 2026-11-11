"""T2.1 — Admin de presupuestos: partidas en línea; un presupuesto aprobado es de solo lectura."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model

from cobros.models import Presupuesto

from .conftest import D

pytestmark = pytest.mark.django_db

URL_LISTA = "/admin/cobros/presupuesto/"


@pytest.fixture
def cliente_admin(client):
    jefe = get_user_model().objects.create_superuser(username="jefe", password="clave-123-xyz")
    client.force_login(jefe)
    return client


def _datos(comunidad, partidas, fecha_aprobacion=""):
    datos = {
        "comunidad": comunidad.pk,
        "ejercicio": "2027",
        "fecha_aprobacion": fecha_aprobacion,
        "aportacion_fondo_reserva": "100.00",
        "periodos": "4",
        "partidas-TOTAL_FORMS": str(len(partidas)),
        "partidas-INITIAL_FORMS": "0",
        "partidas-MIN_NUM_FORMS": "0",
        "partidas-MAX_NUM_FORMS": "1000",
    }
    for i, (concepto, importe) in enumerate(partidas):
        datos |= {f"partidas-{i}-concepto": concepto, f"partidas-{i}-importe": importe}
    return datos


def test_paginas_del_admin_cargan(cliente_admin, presupuesto_a, presupuesto_b):
    for url in (
        URL_LISTA,
        f"{URL_LISTA}add/",
        f"{URL_LISTA}{presupuesto_a.pk}/change/",
        f"{URL_LISTA}{presupuesto_b.pk}/change/",  # aprobado
    ):
        assert cliente_admin.get(url).status_code == 200, url


def test_crear_presupuesto_con_partidas(cliente_admin, comunidad_a):
    datos = _datos(comunidad_a, [("Limpieza", "1200.00"), ("Luz", "800.50")])
    respuesta = cliente_admin.post(f"{URL_LISTA}add/", datos)
    assert respuesta.status_code == 302, respuesta.content.decode()
    presupuesto = Presupuesto.objects.get(comunidad=comunidad_a, ejercicio=2027)
    assert presupuesto.total_gastos() == D("2000.50")
    assert not presupuesto.esta_aprobado


def test_crear_y_aprobar_en_el_mismo_formulario_guarda_las_partidas(cliente_admin, comunidad_a):
    datos = _datos(comunidad_a, [("Seguro", "650.00")], fecha_aprobacion="2026-12-15")
    respuesta = cliente_admin.post(f"{URL_LISTA}add/", datos)
    assert respuesta.status_code == 302, respuesta.content.decode()
    presupuesto = Presupuesto.objects.get(comunidad=comunidad_a, ejercicio=2027)
    assert presupuesto.fecha_aprobacion == date(2026, 12, 15)
    assert presupuesto.total_gastos() == D("650.00")


def test_aprobado_no_deja_editar_importes(cliente_admin, presupuesto_b):
    respuesta = cliente_admin.get(f"{URL_LISTA}{presupuesto_b.pk}/change/")
    html = respuesta.content.decode()
    assert 'name="aportacion_fondo_reserva"' not in html
    assert 'name="partidas-0-importe"' not in html
    assert "Ascensor" in html  # se ven, pero no se editan


def test_borrador_deja_editar_partidas(cliente_admin, presupuesto_a):
    html = cliente_admin.get(f"{URL_LISTA}{presupuesto_a.pk}/change/").content.decode()
    assert 'name="partidas-0-importe"' in html


def test_aprobado_no_se_puede_borrar_desde_el_admin(cliente_admin, presupuesto_b):
    respuesta = cliente_admin.post(f"{URL_LISTA}{presupuesto_b.pk}/delete/", {"post": "yes"})
    assert respuesta.status_code == 403
    assert Presupuesto.objects.filter(pk=presupuesto_b.pk).exists()


def test_la_lista_muestra_los_totales(cliente_admin, presupuesto_a):
    html = cliente_admin.get(URL_LISTA).content.decode()
    assert "4000.00" in html or "4000,00" in html
    assert "4500.00" in html or "4500,00" in html


def test_admin_de_emisiones_solo_lectura(cliente_admin, presupuesto_b):
    from cobros.emision import emitir_cuotas
    from fincas.models import Inmueble

    Inmueble.objects.create(
        comunidad=presupuesto_b.comunidad, tipo="piso", referencia="1", coeficiente=D("100")
    )
    emision = emitir_cuotas(presupuesto_b, 1, date(2026, 2, 5))
    assert cliente_admin.get("/admin/cobros/emision/").status_code == 200
    html = cliente_admin.get(f"/admin/cobros/emision/{emision.pk}/change/").content.decode()
    assert 'name="cuotas-0-importe"' not in html
    assert cliente_admin.get("/admin/cobros/emision/add/").status_code == 403

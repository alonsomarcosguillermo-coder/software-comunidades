"""T3.3 — Devoluciones desde la web: conciliación manual de un cargo, deshacer y estado.

Regla de CLAUDE.md: un usuario de otro despacho NO puede ver ni modificar los datos.
"""

from datetime import date, datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from bancos.conciliacion import conciliar_automaticamente, conciliar_devolucion
from bancos.models import Devolucion
from cobros.models import Recibo
from cobros.remesas import crear_remesa

from .conftest import abono, cargo, importar, recibo_de

pytestmark = pytest.mark.django_db


def _usuario(username, despacho):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    for codename in ("add_conciliacion", "delete_conciliacion"):
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="bancos", codename=codename)
        )
    return usuario


@pytest.fixture
def ana(despacho_a):
    return _usuario("ana", despacho_a)


@pytest.fixture
def berta(despacho_b):
    return _usuario("berta", despacho_b)


@pytest.fixture
def cargo_devolucion(con_recibos):
    """Remesa de 1A y 1B cobrada en enero; en febrero, un cargo con el importe de 1A."""
    ahora = timezone.make_aware(datetime(2026, 1, 10, 12, 0))
    remesa = crear_remesa(con_recibos, date(2026, 1, 15), ahora=ahora)
    importar(con_recibos, abono(str(remesa.total), remesa.mensaje_id, dia=15))
    conciliar_automaticamente(con_recibos)
    a1 = recibo_de(con_recibos, "1A")
    [movimiento] = importar(
        con_recibos,
        cargo(str(a1.importe), "DEVOLUCION RECIBO", dia=5, mes=2),
        desde=date(2026, 2, 1),
        hasta=date(2026, 2, 28),
    )
    return movimiento


def _manual(movimiento):
    return reverse(
        "bancos:conciliar_movimiento", args=[movimiento.extracto.comunidad_id, movimiento.pk]
    )


def _deshacer(movimiento):
    return reverse(
        "bancos:deshacer_conciliacion", args=[movimiento.extracto.comunidad_id, movimiento.pk]
    )


def _detalle(movimiento):
    return reverse(
        "bancos:detalle_extracto", args=[movimiento.extracto.comunidad_id, movimiento.extracto_id]
    )


def test_la_pagina_de_un_cargo_ofrece_los_recibos_cobrados(
    client, ana, con_recibos, cargo_devolucion
):
    client.force_login(ana)
    respuesta = client.get(_manual(cargo_devolucion))
    html = respuesta.content.decode()
    assert "Recibos devueltos" in html
    assert 'value="devolucion"' in html
    cobrados = {r.referencia for r in respuesta.context["recibos"]}
    assert cobrados == {
        recibo_de(con_recibos, "1A").referencia,
        recibo_de(con_recibos, "1B").referencia,
    }


def test_registra_la_devolucion_a_mano(client, ana, con_recibos, cargo_devolucion):
    a1 = recibo_de(con_recibos, "1A")
    client.force_login(ana)
    respuesta = client.post(
        _manual(cargo_devolucion), {"accion": "devolucion", "recibos": [a1.pk]}, follow=True
    )
    assert respuesta.redirect_chain == [(_detalle(cargo_devolucion), 302)]
    assert Recibo.objects.get(pk=a1.pk).estado == "devuelto"
    assert f"Devolución de {a1.referencia}" in respuesta.content.decode()


def test_no_acepta_como_devuelto_un_recibo_sin_cobrar(client, ana, con_recibos, cargo_devolucion):
    l1 = recibo_de(con_recibos, "L1")  # no estaba en la remesa: no es una opción válida
    client.force_login(ana)
    html = client.post(
        _manual(cargo_devolucion), {"accion": "devolucion", "recibos": [l1.pk]}, follow=True
    ).content.decode()
    assert "Elige al menos un recibo cobrado" in html
    assert not Devolucion.objects.exists()


def test_deshacer_un_cobro_con_devoluciones_muestra_el_motivo(
    client, ana, con_recibos, cargo_devolucion
):
    conciliar_devolucion(cargo_devolucion, [recibo_de(con_recibos, "1A")])
    abono_remesa = Devolucion.objects.get().cobro.movimiento
    client.force_login(ana)
    html = client.post(_deshacer(abono_remesa), follow=True).content.decode()
    assert "deshaz antes la devolución" in html


def test_deshacer_la_devolucion_desde_la_web(client, ana, con_recibos, cargo_devolucion):
    a1 = recibo_de(con_recibos, "1A")
    conciliar_devolucion(cargo_devolucion, [a1])
    client.force_login(ana)
    html = client.post(_deshacer(cargo_devolucion), follow=True).content.decode()
    assert "Conciliación deshecha" in html
    assert Recibo.objects.get(pk=a1.pk).estado == "cobrado"


def test_la_pagina_de_recibos_muestra_los_devueltos(client, ana, con_recibos, cargo_devolucion):
    conciliar_devolucion(cargo_devolucion, [recibo_de(con_recibos, "1A")])
    client.force_login(ana)
    url = reverse("cobros:recibos_comunidad", args=[con_recibos.pk])
    html = client.get(url).content.decode()
    assert "Devuelto" in html and "Cobrado" in html


def test_aislamiento_otro_despacho_no_registra_devoluciones(
    client, berta, con_recibos, cargo_devolucion
):
    a1 = recibo_de(con_recibos, "1A")
    client.force_login(berta)
    assert client.get(_manual(cargo_devolucion)).status_code == 404
    respuesta = client.post(_manual(cargo_devolucion), {"accion": "devolucion", "recibos": [a1.pk]})
    assert respuesta.status_code == 404
    assert not Devolucion.objects.exists()


def test_aislamiento_otro_despacho_no_deshace_devoluciones(
    client, berta, con_recibos, cargo_devolucion
):
    conciliar_devolucion(cargo_devolucion, [recibo_de(con_recibos, "1A")])
    client.force_login(berta)
    assert client.post(_deshacer(cargo_devolucion)).status_code == 404
    assert Devolucion.objects.exists()

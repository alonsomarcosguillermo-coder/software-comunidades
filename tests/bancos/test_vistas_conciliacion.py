"""T3.2 — Páginas de conciliación: automática, manual (recibos o cuenta) y deshacer.

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver ni modificar los datos.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from bancos.conciliacion import conciliar_con_recibos
from bancos.models import Conciliacion
from cobros.models import Recibo
from contabilidad.models import Asiento, Cuenta

from .conftest import abono, cargo, importar, recibo_de

pytestmark = pytest.mark.django_db


def _usuario(username, despacho, *permisos):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    for codename in permisos:
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="bancos", codename=codename)
        )
    return usuario


PERMISOS = ("add_conciliacion", "delete_conciliacion")


@pytest.fixture
def ana(despacho_a):
    return _usuario("ana", despacho_a, *PERMISOS)


@pytest.fixture
def berta(despacho_b):
    return _usuario("berta", despacho_b, *PERMISOS)


@pytest.fixture
def movimientos(con_recibos):
    """[abono con la referencia del recibo de L1, abono sin referencia, cargo de luz]."""
    l1 = recibo_de(con_recibos, "L1")
    return importar(
        con_recibos,
        abono(str(l1.importe), "TRANSFERENCIA", referencia=l1.referencia),
        abono(str(recibo_de(con_recibos, "1A").importe), "TRANSFERENCIA VECINO 1"),
        cargo("86.40", "RECIBO ELECTRICA FICTICIA SA"),
    )


def _automatica(comunidad):
    return reverse("bancos:conciliar_automaticamente", args=[comunidad.pk])


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


def _lista(comunidad):
    return reverse("bancos:extractos_comunidad", args=[comunidad.pk])


# --- Automática ----------------------------------------------------------------------------


def test_automatica_concilia_y_lo_avisa(client, ana, con_recibos, movimientos):
    client.force_login(ana)
    respuesta = client.post(_automatica(con_recibos), follow=True)
    assert respuesta.redirect_chain == [(_lista(con_recibos), 302)]
    assert "Conciliados automáticamente 1 movimientos. Quedan 2 pendientes" in (
        respuesta.content.decode()
    )
    assert Conciliacion.objects.get().movimiento == movimientos[0]


def test_automatica_sin_nada_que_conciliar(client, ana, con_recibos, movimientos):
    client.force_login(ana)
    client.post(_automatica(con_recibos))
    html = client.post(_automatica(con_recibos), follow=True).content.decode()
    assert "Ningún movimiento encaja" in html


def test_la_lista_muestra_pendientes_y_el_boton(client, ana, con_recibos, movimientos):
    client.force_login(ana)
    html = client.get(_lista(con_recibos)).content.decode()
    assert "3 pendientes" in html
    assert "Conciliar automáticamente" in html


def test_automatica_sin_permiso(client, despacho_a, con_recibos, movimientos):
    client.force_login(_usuario("emilio", despacho_a))
    assert client.post(_automatica(con_recibos)).status_code == 403
    assert "Conciliar automáticamente" not in client.get(_lista(con_recibos)).content.decode()
    assert not Conciliacion.objects.exists()


def test_aislamiento_otro_despacho_no_concilia_automaticamente(
    client, berta, con_recibos, movimientos
):
    client.force_login(berta)
    assert client.post(_automatica(con_recibos)).status_code == 404
    assert not Conciliacion.objects.exists()


# --- Detalle -------------------------------------------------------------------------------


def test_detalle_muestra_estado_y_acciones(client, ana, con_recibos, movimientos):
    l1 = recibo_de(con_recibos, "L1")
    conciliacion = conciliar_con_recibos(movimientos[0], [l1])
    client.force_login(ana)
    html = client.get(_detalle(movimientos[0])).content.decode()
    assert f"Asiento {conciliacion.asiento.numero}" in html
    assert _deshacer(movimientos[0]) in html
    assert _manual(movimientos[1]) in html  # pendiente: enlace para conciliar
    assert html.count("Pendiente") == 2


# --- Manual --------------------------------------------------------------------------------


def test_pagina_manual_de_un_abono(client, ana, con_recibos, movimientos):
    client.force_login(ana)
    respuesta = client.get(_manual(movimientos[1]))
    assert respuesta.status_code == 200
    referencias = [r.referencia for r in respuesta.context["recibos"]]
    # Los del importe exacto (1A y 1B, 300 € cada uno) van primero.
    a1, b1 = recibo_de(con_recibos, "1A"), recibo_de(con_recibos, "1B")
    assert set(referencias[:2]) == {a1.referencia, b1.referencia}
    assert "Suministros" in respuesta.content.decode()  # cuenta 628 para lo que no es recibo


def test_pagina_manual_de_un_cargo_no_ofrece_recibos(client, ana, movimientos):
    client.force_login(ana)
    respuesta = client.get(_manual(movimientos[2]))
    assert respuesta.context["recibos"] == []
    assert "Recibos que paga" not in respuesta.content.decode()


def test_concilia_a_mano_con_un_recibo(client, ana, con_recibos, movimientos):
    a1 = recibo_de(con_recibos, "1A")
    client.force_login(ana)
    respuesta = client.post(
        _manual(movimientos[1]), {"accion": "recibos", "recibos": [a1.pk]}, follow=True
    )
    assert respuesta.redirect_chain == [(_detalle(movimientos[1]), 302)]
    conciliacion = Conciliacion.objects.get()
    assert conciliacion.creada_por == ana
    assert not conciliacion.automatica
    assert Recibo.objects.get(pk=a1.pk).estado == "cobrado"
    assert f"asiento {conciliacion.asiento.numero}" in respuesta.content.decode()


def test_concilia_a_mano_con_una_cuenta(client, ana, movimientos):
    gasto = Cuenta.objects.get(codigo="628")
    client.force_login(ana)
    client.post(_manual(movimientos[2]), {"accion": "cuenta", "cuenta": gasto.pk})
    assert Conciliacion.objects.get().cuenta == gasto


def test_importe_que_no_cuadra_como_mensaje(client, ana, con_recibos, movimientos):
    l1 = recibo_de(con_recibos, "L1")  # 400 €, el movimiento es de 300 €
    client.force_login(ana)
    respuesta = client.post(
        _manual(movimientos[1]), {"accion": "recibos", "recibos": [l1.pk]}, follow=True
    )
    assert respuesta.redirect_chain == [(_manual(movimientos[1]), 302)]
    assert "coincidir al céntimo" in respuesta.content.decode()
    assert not Conciliacion.objects.exists()


def test_sin_elegir_nada(client, ana, movimientos):
    client.force_login(ana)
    html = client.post(_manual(movimientos[1]), {"accion": "recibos"}, follow=True)
    assert "Elige al menos un recibo" in html.content.decode()
    html = client.post(_manual(movimientos[1]), {"accion": "cuenta"}, follow=True)
    assert "Elige una cuenta" in html.content.decode()


def test_no_acepta_recibos_de_otra_comunidad(client, ana, con_recibos, movimientos, despacho_b):
    # Un id de recibo ajeno no es una opción válida del formulario.
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(despacho=despacho_b, nombre="Otra")
    ajena = Cuenta.objects.create(comunidad=otra, codigo="628", nombre="Ajena")
    client.force_login(ana)
    client.post(_manual(movimientos[2]), {"accion": "cuenta", "cuenta": ajena.pk})
    assert not Conciliacion.objects.exists()


def test_movimiento_ya_conciliado_vuelve_al_extracto(client, ana, con_recibos, movimientos):
    conciliar_con_recibos(movimientos[0], [recibo_de(con_recibos, "L1")])
    client.force_login(ana)
    respuesta = client.get(_manual(movimientos[0]))
    assert respuesta.status_code == 302


def test_manual_sin_permiso(client, despacho_a, movimientos):
    client.force_login(_usuario("emilio", despacho_a))
    assert client.get(_manual(movimientos[1])).status_code == 403


def test_aislamiento_otro_despacho_no_ve_ni_concilia(client, berta, con_recibos, movimientos):
    client.force_login(berta)
    assert client.get(_manual(movimientos[1])).status_code == 404
    a1 = recibo_de(con_recibos, "1A")
    respuesta = client.post(_manual(movimientos[1]), {"accion": "recibos", "recibos": [a1.pk]})
    assert respuesta.status_code == 404
    assert not Conciliacion.objects.exists()


def test_movimiento_con_otra_comunidad_en_la_url(client, ana, despacho_a, movimientos):
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(despacho=despacho_a, nombre="CP Plaza Imaginaria 7")
    client.force_login(ana)
    url = reverse("bancos:conciliar_movimiento", args=[otra.pk, movimientos[1].pk])
    assert client.get(url).status_code == 404


# --- Deshacer ------------------------------------------------------------------------------


def test_deshacer(client, ana, con_recibos, movimientos):
    conciliacion = conciliar_con_recibos(movimientos[0], [recibo_de(con_recibos, "L1")])
    client.force_login(ana)
    respuesta = client.post(_deshacer(movimientos[0]), follow=True)
    assert respuesta.redirect_chain == [(_detalle(movimientos[0]), 302)]
    assert "Conciliación deshecha" in respuesta.content.decode()
    assert not Conciliacion.objects.exists()
    assert Asiento.objects.get(pk=conciliacion.asiento.pk).esta_anulado()


def test_deshacer_sin_permiso(client, despacho_a, con_recibos, movimientos):
    conciliar_con_recibos(movimientos[0], [recibo_de(con_recibos, "L1")])
    client.force_login(_usuario("emilio", despacho_a, "add_conciliacion"))
    assert client.post(_deshacer(movimientos[0])).status_code == 403
    assert Conciliacion.objects.exists()
    assert _deshacer(movimientos[0]) not in client.get(_detalle(movimientos[0])).content.decode()


def test_aislamiento_otro_despacho_no_puede_deshacer(client, berta, con_recibos, movimientos):
    conciliar_con_recibos(movimientos[0], [recibo_de(con_recibos, "L1")])
    client.force_login(berta)
    assert client.post(_deshacer(movimientos[0])).status_code == 404
    assert Conciliacion.objects.exists()


def test_deshacer_solo_por_post(client, ana, movimientos):
    client.force_login(ana)
    assert client.get(_deshacer(movimientos[0])).status_code == 405


# --- Recibos -------------------------------------------------------------------------------


def test_la_pagina_de_recibos_muestra_los_cobrados(client, ana, con_recibos, movimientos):
    conciliar_con_recibos(movimientos[0], [recibo_de(con_recibos, "L1")])
    client.force_login(ana)
    html = client.get(reverse("cobros:recibos_comunidad", args=[con_recibos.pk])).content.decode()
    assert "Cobrado" in html

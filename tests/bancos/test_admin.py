"""T3.1 — Admin de extractos: solo lectura (se importan desde la web y son inmutables)."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from bancos.conciliacion import conciliar_con_recibos, conciliar_devolucion
from bancos.importacion import importar_norma43

from .conftest import abono, cargo, fichero, importar, recibo_de

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


def test_conciliaciones_en_solo_lectura(client, superusuario, con_recibos):
    # T3.2: borrarla desde el admin dejaría el asiento sin contra-asiento.
    l1 = recibo_de(con_recibos, "L1")
    [movimiento] = importar(con_recibos, abono(str(l1.importe)))
    conciliacion = conciliar_con_recibos(movimiento, [l1])
    client.force_login(superusuario)
    assert client.get(reverse("admin:bancos_conciliacion_changelist")).status_code == 200
    ficha = client.get(reverse("admin:bancos_conciliacion_change", args=[conciliacion.pk]))
    assert ficha.status_code == 200
    borrar = reverse("admin:bancos_conciliacion_delete", args=[conciliacion.pk])
    assert client.post(borrar, {"post": "yes"}).status_code == 403


def test_ficha_de_una_devolucion(client, superusuario, con_recibos):
    # T3.3: la conciliación del cargo muestra en línea los recibos devueltos.
    l1 = recibo_de(con_recibos, "L1")
    cobro, devolucion = importar(
        con_recibos, abono(str(l1.importe), dia=10), cargo(str(l1.importe), dia=20)
    )
    conciliar_con_recibos(cobro, [l1])
    conciliacion = conciliar_devolucion(devolucion, [l1])
    client.force_login(superusuario)
    ficha = client.get(reverse("admin:bancos_conciliacion_change", args=[conciliacion.pk]))
    assert ficha.status_code == 200
    assert l1.referencia in ficha.content.decode()

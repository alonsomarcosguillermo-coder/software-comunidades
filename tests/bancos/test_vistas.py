"""T3.1 — Páginas de extractos: lista con subida del fichero y detalle con los movimientos.

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver ni modificar los datos.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from bancos.importacion import importar_norma43
from bancos.models import Extracto

from .conftest import extracto, fichero

pytestmark = pytest.mark.django_db


def _usuario(username, despacho, *permisos):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    for codename in permisos:
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="bancos", codename=codename)
        )
    return usuario


@pytest.fixture
def ana(despacho_a):
    return _usuario("ana", despacho_a, "add_extracto")


@pytest.fixture
def berta(despacho_b):
    return _usuario("berta", despacho_b, "add_extracto")


@pytest.fixture
def importado(comunidad):
    [guardado] = importar_norma43(comunidad, fichero(), nombre_fichero="abril.n43")
    return guardado


def _lista(comunidad):
    return reverse("bancos:extractos_comunidad", args=[comunidad.pk])


def _importar(comunidad):
    return reverse("bancos:importar_extracto", args=[comunidad.pk])


def _detalle(guardado):
    return reverse("bancos:detalle_extracto", args=[guardado.comunidad_id, guardado.pk])


def _subida(contenido=None, nombre="abril.n43"):
    return {"fichero": SimpleUploadedFile(nombre, contenido or fichero())}


# --- Lista ---------------------------------------------------------------------------------


def test_lista_los_extractos(client, ana, importado):
    client.force_login(ana)
    html = client.get(_lista(importado.comunidad)).content.decode()
    assert "1/4/2026" in html and "30/4/2026" in html
    assert "1525,50 €" in html  # saldo final (coma decimal: es-es)
    assert "9999 0000 ****0001" in html  # cuenta, oculta
    assert _detalle(importado) in html


def test_lista_vacia_con_formulario(client, ana, comunidad):
    client.force_login(ana)
    html = client.get(_lista(comunidad)).content.decode()
    assert "Todavía no hay extractos" in html
    assert 'type="file"' in html


def test_sin_permiso_no_ve_el_formulario(client, despacho_a, comunidad):
    client.force_login(_usuario("emilio", despacho_a))
    respuesta = client.get(_lista(comunidad))
    assert respuesta.status_code == 200
    assert 'type="file"' not in respuesta.content.decode()


def test_aislamiento_otro_despacho_no_ve_la_lista(client, berta, importado):
    client.force_login(berta)
    assert client.get(_lista(importado.comunidad)).status_code == 404


def test_lista_exige_sesion(client, comunidad):
    assert client.get(_lista(comunidad)).status_code == 302


# --- Importar ------------------------------------------------------------------------------


def test_importa_el_fichero_y_lo_avisa(client, ana, comunidad):
    client.force_login(ana)
    respuesta = client.post(_importar(comunidad), _subida(), follow=True)
    assert respuesta.redirect_chain == [(_lista(comunidad), 302)]
    guardado = Extracto.objects.get()
    assert guardado.importado_por == ana
    assert guardado.nombre_fichero == "abril.n43"
    assert "Importado 1 extracto con 2 movimientos" in respuesta.content.decode()


def test_error_del_fichero_como_mensaje(client, ana, comunidad):
    client.force_login(ana)
    html = client.post(
        _importar(comunidad), _subida(b"esto no es un Norma 43"), follow=True
    ).content.decode()
    assert "no es un Norma 43 válido" in html
    assert not Extracto.objects.exists()


def test_periodo_repetido_como_mensaje(client, ana, importado):
    client.force_login(ana)
    html = client.post(_importar(importado.comunidad), _subida(), follow=True).content.decode()
    assert "Ya hay un extracto" in html
    assert Extracto.objects.count() == 1


def test_sin_fichero(client, ana, comunidad):
    client.force_login(ana)
    html = client.post(_importar(comunidad), {}, follow=True).content.decode()
    assert "Elige un fichero" in html


def test_fichero_demasiado_grande(client, ana, comunidad, monkeypatch):
    from bancos import views

    contenido = fichero()
    monkeypatch.setattr(views, "TAMANO_MAXIMO", len(contenido) - 1)
    client.force_login(ana)
    html = client.post(_importar(comunidad), _subida(contenido), follow=True).content.decode()
    assert "demasiado grande" in html
    assert not Extracto.objects.exists()


def test_sin_permiso_no_importa(client, despacho_a, comunidad):
    client.force_login(_usuario("emilio", despacho_a))
    assert client.post(_importar(comunidad), _subida()).status_code == 403
    assert not Extracto.objects.exists()


def test_aislamiento_otro_despacho_no_puede_importar(client, berta, comunidad):
    client.force_login(berta)
    assert client.post(_importar(comunidad), _subida()).status_code == 404
    assert not Extracto.objects.exists()


def test_importar_solo_por_post(client, ana, comunidad):
    client.force_login(ana)
    assert client.get(_importar(comunidad)).status_code == 405


# --- Detalle -------------------------------------------------------------------------------


def test_detalle_con_los_movimientos(client, ana, importado):
    client.force_login(ana)
    html = client.get(_detalle(importado)).content.decode()
    assert "REC-1-7" in html
    assert "TRANSFERENCIA DE MARTA INVENTADA" in html
    assert "45,50" in html and "-20,00" in html
    assert "Giros, transferencias" in html  # nombre del concepto común 04
    assert "1500,00 €" in html and "1525,50 €" in html


def test_aislamiento_otro_despacho_no_ve_el_detalle(client, berta, importado):
    client.force_login(berta)
    assert client.get(_detalle(importado)).status_code == 404


def test_detalle_con_la_comunidad_equivocada_da_404(client, ana, importado, despacho_a):
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(despacho=despacho_a, nombre="CP Plaza Imaginaria 7")
    client.force_login(ana)
    url = reverse("bancos:detalle_extracto", args=[otra.pk, importado.pk])
    assert client.get(url).status_code == 404


def test_enlace_desde_la_pagina_de_la_comunidad(client, ana, comunidad):
    client.force_login(ana)
    url = reverse("cobros:presupuestos_comunidad", args=[comunidad.pk])
    assert _lista(comunidad) in client.get(url).content.decode()


def test_varios_extractos_ordenados_del_mas_reciente(client, ana, comunidad):
    mayo = extracto(desde=date(2026, 5, 1), hasta=date(2026, 5, 31), saldo="1525.50")
    importar_norma43(comunidad, fichero(extracto(), mayo), nombre_fichero="x.n43")
    client.force_login(ana)
    html = client.get(_lista(comunidad)).content.decode()
    assert html.index("1/5/2026") < html.index("1/4/2026")


def test_extracto_sin_cargos_muestra_cero(client, ana, comunidad):
    importar_norma43(comunidad, fichero(extracto(movimientos=())), nombre_fichero="x.n43")
    client.force_login(ana)
    html = client.get(_lista(comunidad)).content.decode()
    assert "0,00 €" in html
    assert "None" not in html

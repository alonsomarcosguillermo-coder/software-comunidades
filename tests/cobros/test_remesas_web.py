"""T2.5 — Crear y descargar remesas desde la página de recibos.

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver ni modificar los datos. El fichero lleva IBAN completos: exige permiso.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from cobros.models import Remesa
from cobros.remesas import crear_remesa
from cobros.sepa.pain008 import validar_pain008

from .test_recibos import vecinos_a  # noqa: F401  (fixture)
from .test_remesas import comunidad  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db

COBRO = timezone.localdate() + timedelta(days=7)


def _usuario(username, despacho, *permisos):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    for codename in permisos:
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="cobros", codename=codename)
        )
    return usuario


@pytest.fixture
def ana(despacho_a):
    return _usuario("ana", despacho_a, "add_remesa", "view_remesa")


@pytest.fixture
def berta(despacho_b):
    return _usuario("berta", despacho_b, "add_remesa", "view_remesa")


def _crear(comunidad):  # noqa: F811
    return reverse("cobros:crear_remesa", args=[comunidad.pk])


def _descargar(comunidad, remesa):  # noqa: F811
    return reverse("cobros:descargar_remesa", args=[comunidad.pk, remesa.pk])


def _pagina(comunidad):  # noqa: F811
    return reverse("cobros:recibos_comunidad", args=[comunidad.pk])


# --- Crear ----------------------------------------------------------------------------------


def test_crea_la_remesa_y_lo_avisa(client, ana, comunidad):  # noqa: F811
    client.force_login(ana)
    respuesta = client.post(_crear(comunidad), {"fecha_cobro": COBRO.isoformat()}, follow=True)
    assert respuesta.redirect_chain == [(_pagina(comunidad), 302)]
    remesa = Remesa.objects.get(comunidad=comunidad)
    html = respuesta.content.decode()
    assert f"Creada la remesa 1: {remesa.num_recibos} recibos" in html
    assert remesa.nombre_fichero in html  # enlace de descarga
    assert "Remesa 1 (FRST)" in html  # estado de los recibos


def test_error_de_negocio_como_mensaje(client, ana, comunidad):  # noqa: F811
    client.force_login(ana)
    hoy = timezone.localdate().isoformat()
    html = client.post(_crear(comunidad), {"fecha_cobro": hoy}, follow=True).content.decode()
    assert "posterior a hoy" in html
    assert not Remesa.objects.exists()


def test_fecha_no_valida(client, ana, comunidad):  # noqa: F811
    client.force_login(ana)
    html = client.post(_crear(comunidad), {"fecha_cobro": "ayer"}, follow=True).content.decode()
    assert "fecha de cobro válida" in html


def test_sin_permiso_no_crea_ni_ve_el_formulario(client, despacho_a, comunidad):  # noqa: F811
    client.force_login(_usuario("emilio", despacho_a))
    assert client.post(_crear(comunidad), {"fecha_cobro": COBRO.isoformat()}).status_code == 403
    assert not Remesa.objects.exists()
    assert "Crear remesa" not in client.get(_pagina(comunidad)).content.decode()


def test_aislamiento_otro_despacho_no_puede_crear(client, berta, comunidad):  # noqa: F811
    client.force_login(berta)
    assert client.post(_crear(comunidad), {"fecha_cobro": COBRO.isoformat()}).status_code == 404
    assert not Remesa.objects.exists()


def test_crear_solo_por_post(client, ana, comunidad):  # noqa: F811
    client.force_login(ana)
    assert client.get(_crear(comunidad)).status_code == 405


# --- Descargar -----------------------------------------------------------------------------


def test_descarga_el_fichero_guardado(client, ana, comunidad):  # noqa: F811
    remesa = crear_remesa(comunidad, COBRO)
    client.force_login(ana)
    respuesta = client.get(_descargar(comunidad, remesa))
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "application/xml"
    assert respuesta["Content-Disposition"] == f'attachment; filename="{remesa.nombre_fichero}"'
    assert respuesta.content == remesa.xml.encode()
    validar_pain008(respuesta.content)


def test_sin_permiso_no_descarga_ni_ve_el_enlace(client, despacho_a, comunidad):  # noqa: F811
    remesa = crear_remesa(comunidad, COBRO)
    client.force_login(_usuario("emilio", despacho_a))
    assert client.get(_descargar(comunidad, remesa)).status_code == 403
    assert remesa.nombre_fichero not in client.get(_pagina(comunidad)).content.decode()


def test_aislamiento_otro_despacho_no_descarga(client, berta, comunidad):  # noqa: F811
    remesa = crear_remesa(comunidad, COBRO)
    client.force_login(berta)
    assert client.get(_descargar(comunidad, remesa)).status_code == 404


def test_aislamiento_no_vale_mezclar_comunidad_propia_con_remesa_ajena(
    client,
    berta,
    comunidad,  # noqa: F811
    comunidad_b,
):
    remesa = crear_remesa(comunidad, COBRO)
    client.force_login(berta)
    url = reverse("cobros:descargar_remesa", args=[comunidad_b.pk, remesa.pk])
    assert client.get(url).status_code == 404


def test_sin_sesion_no_descarga(client, comunidad):  # noqa: F811
    remesa = crear_remesa(comunidad, COBRO)
    respuesta = client.get(_descargar(comunidad, remesa))
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse("login"))

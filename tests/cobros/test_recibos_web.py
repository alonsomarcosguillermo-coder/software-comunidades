"""T2.4 — Página de recibos y mandatos, y botón "Generar recibos".

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver ni modificar los datos. Además, el IBAN completo no debe aparecer nunca.
"""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from cobros.emision import emitir_cuotas
from cobros.models import Recibo
from cobros.recibos import generar_recibos
from fincas.models import Titularidad

from .test_recibos import _mandato, vecinos_a  # noqa: F401  (fixture)
from .test_sepa_identificadores import iban_ficticio

pytestmark = pytest.mark.django_db


def _usuario(username, despacho, con_permiso=True):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    if con_permiso:
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="cobros", codename="add_recibo")
        )
    return usuario


@pytest.fixture
def ana(despacho_a):
    return _usuario("ana", despacho_a)


@pytest.fixture
def berta(despacho_b):
    return _usuario("berta", despacho_b)


@pytest.fixture
def con_cuotas(aprobado_a, fondo_a, vecinos_a):  # noqa: F811
    emitir_cuotas(aprobado_a, 1, date(2026, 1, 5))
    return aprobado_a.comunidad


def _pagina(comunidad):
    return reverse("cobros:recibos_comunidad", args=[comunidad.pk])


def _generar(comunidad):
    return reverse("cobros:generar_recibos", args=[comunidad.pk])


# --- Página ------------------------------------------------------------------------------


def test_sin_sesion_redirige_al_login(client, comunidad_a):
    respuesta = client.get(_pagina(comunidad_a))
    assert respuesta.status_code == 302
    assert respuesta.url.startswith(reverse("login"))


def test_aislamiento_usuario_de_otro_despacho_no_ve_los_recibos(client, berta, con_cuotas):
    generar_recibos(con_cuotas)
    client.force_login(berta)
    assert client.get(_pagina(con_cuotas)).status_code == 404


def test_muestra_recibos_con_su_domiciliacion(client, ana, con_cuotas, vecinos_a):  # noqa: F811
    mandato = _mandato(con_cuotas, vecinos_a["1A"], 4321)
    generar_recibos(con_cuotas)
    client.force_login(ana)
    html = client.get(_pagina(con_cuotas)).content.decode()
    assert "Cuota ordinaria 2026, periodo 1/4 · 1A" in html
    assert "Vecino 1A" in html
    assert mandato.iban_oculto in html  # domiciliado
    assert html.count("Sin mandato") == 2  # 1B y L1
    assert mandato.referencia in html


def test_el_iban_completo_no_aparece_nunca(client, ana, con_cuotas, vecinos_a):  # noqa: F811
    mandato = _mandato(con_cuotas, vecinos_a["1A"], 4321)
    con_cuotas.iban_cobros = iban_ficticio(8888)
    con_cuotas.save()
    generar_recibos(con_cuotas)
    client.force_login(ana)
    html = client.get(_pagina(con_cuotas)).content.decode()
    assert mandato.iban not in html and mandato.iban[4:12] not in html
    assert con_cuotas.iban_cobros not in html
    assert "8888" in html  # sí, los últimos dígitos


def test_datos_de_acreedor(client, ana, comunidad_a):
    client.force_login(ana)
    html = client.get(_pagina(comunidad_a)).content.decode()
    assert "falta el NIF de la comunidad" in html
    assert "falta el IBAN de cobro" in html
    comunidad_a.nif = "H00000000"
    comunidad_a.save()
    html = client.get(_pagina(comunidad_a)).content.decode()
    assert comunidad_a.identificador_acreedor() in html


def test_mandato_dado_de_baja(client, ana, comunidad_a, vecinos_a):  # noqa: F811
    _mandato(comunidad_a, vecinos_a["1A"], fecha_baja=date(2026, 1, 1))
    client.force_login(ana)
    assert "Baja el 1/1/2026" in client.get(_pagina(comunidad_a)).content.decode()


# --- Generar -------------------------------------------------------------------------------


def test_generar_crea_los_recibos_y_avisa(client, ana, con_cuotas):
    client.force_login(ana)
    respuesta = client.post(_generar(con_cuotas), follow=True)
    assert respuesta.redirect_chain == [(_pagina(con_cuotas), 302)]
    assert "Generados 3 recibos." in respuesta.content.decode()
    assert Recibo.objects.filter(comunidad=con_cuotas).count() == 3


def test_generar_sin_cuotas_pendientes(client, ana, con_cuotas):
    generar_recibos(con_cuotas)
    client.force_login(ana)
    assert (
        "No había cuotas sin recibo."
        in client.post(_generar(con_cuotas), follow=True).content.decode()
    )


def test_generar_avisa_de_inmuebles_sin_titular(client, ana, con_cuotas, inmuebles_a):
    Titularidad.objects.filter(inmueble=inmuebles_a["L1"]).delete()
    client.force_login(ana)
    html = client.post(_generar(con_cuotas), follow=True).content.decode()
    assert "no tenía titular en el vencimiento: L1 (05/01/2026)" in html


def test_sin_permiso_no_genera_ni_ve_el_boton(client, despacho_a, con_cuotas):
    client.force_login(_usuario("emilio", despacho_a, con_permiso=False))
    assert client.post(_generar(con_cuotas)).status_code == 403
    assert not Recibo.objects.exists()
    assert "Generar recibos" not in client.get(_pagina(con_cuotas)).content.decode()


def test_aislamiento_usuario_de_otro_despacho_no_puede_generar(client, berta, con_cuotas):
    client.force_login(berta)
    assert client.post(_generar(con_cuotas)).status_code == 404
    assert not Recibo.objects.exists()


def test_generar_solo_por_post(client, ana, con_cuotas):
    client.force_login(ana)
    assert client.get(_generar(con_cuotas)).status_code == 405

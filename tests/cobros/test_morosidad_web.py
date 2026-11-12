"""T3.4 — Informe de morosos y certificado de deuda R-DEU-01 con la base de datos: consultas,
PDF y vistas.

Regla de CLAUDE.md: cada vista lleva un test que comprueba que un usuario de otro despacho
NO puede ver ni modificar los datos. Todos los datos son ficticios.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone

from bancos.conciliacion import conciliar_con_recibos
from cobros.deudas import certificado_deuda_de, informe_morosos_de
from cobros.pdf import formato_euros, pdf_certificado_deuda, pdf_informe_morosos
from fincas.models import Inmueble, Propietario, Titularidad

# Comunidad con el 1er trimestre de 2026 emitido: recibos de 1A (300 €), 1B (300 €) y
# L1 (400 €) que vencen el 5/1/2026. Ver tests/bancos/conftest.py.
from tests.bancos.conftest import abono, comunidad, con_recibos, importar, recibo_de  # noqa: F401

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def con_un_cobro(con_recibos):  # noqa: F811
    """El recibo de 1A se cobra por transferencia el 20/1/2026."""
    [movimiento] = importar(con_recibos, abono("300.00", referencia="REC-1A", dia=20))
    conciliar_con_recibos(movimiento, [recibo_de(con_recibos, "1A")])
    return con_recibos


# --- Consultas ---------------------------------------------------------------------------


def test_informe_morosos_usa_la_fecha_del_cobro_conciliado(con_un_cobro):
    """Antes del cobro (15/1) deben los tres; después (1/2), solo 1B y L1."""
    antes = informe_morosos_de(con_un_cobro, date(2026, 1, 15))
    assert antes.total == D("1000.00")
    despues = informe_morosos_de(con_un_cobro, date(2026, 2, 1))
    assert [(m.propietario, m.total) for m in despues.morosos] == [
        ("Vecino 3", D("400.00")),
        ("Vecino 2", D("300.00")),
    ]


def test_informe_morosos_el_dia_del_vencimiento_aun_no_hay_morosos(con_recibos):  # noqa: F811
    assert informe_morosos_de(con_recibos, date(2026, 1, 5)).morosos == ()


def test_certificado_r_deu_01_inmueble_al_corriente(con_un_cobro):
    datos = certificado_deuda_de(recibo_de(con_un_cobro, "1A").inmueble, date(2026, 2, 1))
    assert datos.estado.al_corriente
    assert [p.nombre for p in datos.titulares] == ["Vecino 1"]


def test_certificado_r_deu_01_con_deuda_y_recibos_por_vencer(con_recibos):  # noqa: F811
    l1 = Inmueble.objects.get(comunidad=con_recibos, referencia="L1")
    assert certificado_deuda_de(l1, date(2026, 1, 3)).estado.total_por_vencer == D("400.00")
    estado = certificado_deuda_de(l1, date(2026, 2, 1)).estado
    assert estado.total_vencido == D("400.00")
    assert estado.por_vencer == ()


def test_certificado_r_deu_01_incluye_la_deuda_de_un_titular_anterior(con_recibos):  # noqa: F811
    """La deuda se certifica por inmueble: tras una venta sigue apareciendo, con su pagador."""
    l1 = Inmueble.objects.get(comunidad=con_recibos, referencia="L1")
    Titularidad.objects.filter(inmueble=l1).update(fecha_fin=date(2026, 3, 31))
    comprador = Propietario.objects.create(despacho=con_recibos.despacho, nombre="Comprador")
    Titularidad.objects.create(inmueble=l1, propietario=comprador, fecha_inicio=date(2026, 4, 1))
    datos = certificado_deuda_de(l1, date(2026, 5, 1))
    assert [p.nombre for p in datos.titulares] == ["Comprador"]
    assert [(r.propietario, r.importe) for r in datos.estado.vencidos] == [
        ("Vecino 3", D("400.00"))
    ]


# --- PDF ---------------------------------------------------------------------------------


def test_formato_euros_espanol():
    assert formato_euros(D("1234.5")) == "1.234,50 €"
    assert formato_euros(D("0.005")) == "0,01 €"  # ROUND_HALF_UP
    assert formato_euros(D("-20")) == "-20,00 €"


def test_pdf_informe_morosos_contiene_deudores_y_total(con_un_cobro):
    informe = informe_morosos_de(con_un_cobro, date(2026, 2, 1))
    pdf = pdf_informe_morosos(con_un_cobro, informe, comprimir=False)
    assert pdf.startswith(b"%PDF")
    for texto in [b"Informe de morosos", b"Vecino 3", b"Vecino 2", b"700,00", b"01/02/2026"]:
        assert texto in pdf
    assert b"Vecino 1" not in pdf  # ya pagó


def test_pdf_informe_sin_morosos(con_recibos):  # noqa: F811
    pdf = pdf_informe_morosos(
        con_recibos, informe_morosos_de(con_recibos, date(2026, 1, 2)), comprimir=False
    )
    assert b"no hay recibos vencidos pendientes de pago" in pdf


def test_pdf_certificado_r_deu_01_con_deuda(con_recibos):  # noqa: F811
    l1 = Inmueble.objects.get(comunidad=con_recibos, referencia="L1")
    pdf = pdf_certificado_deuda(certificado_deuda_de(l1, date(2026, 2, 1)), comprimir=False)
    for texto in [b"Certificado de deuda", b"400,00", b"Vecino 3", b"9.1.e", b"R-DEU-01"]:
        assert texto in pdf


def test_pdf_certificado_r_deu_01_al_corriente(con_un_cobro):
    inmueble = recibo_de(con_un_cobro, "1A").inmueble
    pdf = pdf_certificado_deuda(certificado_deuda_de(inmueble, date(2026, 2, 1)), comprimir=False)
    assert b"al corriente de pago" in pdf


def test_pdf_admite_nombres_con_caracteres_especiales(con_recibos):  # noqa: F811
    Propietario.objects.filter(nombre="Vecino 3").update(nombre="Pérez & Hijos <SL>")
    informe = informe_morosos_de(con_recibos, date(2026, 2, 1))
    assert pdf_informe_morosos(con_recibos, informe).startswith(b"%PDF")


# --- Vistas ------------------------------------------------------------------------------


def _usuario(username, despacho, con_permiso=True):
    usuario = get_user_model().objects.create_user(username=username, despacho=despacho)
    if con_permiso:
        usuario.user_permissions.add(
            Permission.objects.get(content_type__app_label="cobros", codename="view_recibo")
        )
    return usuario


@pytest.fixture
def ana(con_recibos):  # noqa: F811
    return _usuario("ana", con_recibos.despacho)


@pytest.fixture
def berta(db):
    from core.models import Despacho

    return _usuario("berta", Despacho.objects.create(nombre="Fincas Beta"))


def _urls(comunidad):  # noqa: F811
    inmueble = comunidad.inmuebles.get(referencia="L1")
    return [
        reverse("cobros:morosos_comunidad", args=[comunidad.pk]),
        reverse("cobros:informe_morosos_pdf", args=[comunidad.pk]),
        reverse("cobros:certificado_deuda_pdf", args=[comunidad.pk, inmueble.pk]),
    ]


def test_sin_sesion_redirige_al_login(client, con_recibos):  # noqa: F811
    for url in _urls(con_recibos):
        respuesta = client.get(url)
        assert respuesta.status_code == 302
        assert respuesta.url.startswith(reverse("login"))


def test_aislamiento_usuario_de_otro_despacho_no_ve_la_deuda(client, berta, con_recibos):  # noqa: F811
    client.force_login(berta)
    for url in _urls(con_recibos):
        assert client.get(url).status_code == 404, url


def test_sin_permiso_de_ver_recibos_da_403(client, con_recibos):  # noqa: F811
    client.force_login(_usuario("carlos", con_recibos.despacho, con_permiso=False))
    for url in _urls(con_recibos):
        assert client.get(url).status_code == 403, url


def test_certificado_de_inmueble_de_otra_comunidad_da_404(client, ana, con_recibos):  # noqa: F811
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(despacho=con_recibos.despacho, nombre="CP Otra")
    ajeno = Inmueble.objects.create(comunidad=otra, tipo="piso", referencia="2A", coeficiente=100)
    client.force_login(ana)
    url = reverse("cobros:certificado_deuda_pdf", args=[con_recibos.pk, ajeno.pk])
    assert client.get(url).status_code == 404


def test_pagina_de_morosos_a_una_fecha(client, ana, con_un_cobro):
    client.force_login(ana)
    url = reverse("cobros:morosos_comunidad", args=[con_un_cobro.pk])
    html = client.get(url, {"fecha": "2026-02-01"}).content.decode()
    assert "Vecino 3" in html and "Vecino 2" in html
    assert "Vecino 1" not in html.split("Certificado de deuda")[0]
    assert "700,00 €" in html
    # Enlaces al PDF y a los certificados con la misma fecha.
    assert "informe.pdf?fecha=2026-02-01" in html
    assert "certificado-deuda.pdf?fecha=2026-02-01" in html


def test_pagina_sin_morosos(client, ana, con_recibos):  # noqa: F811
    client.force_login(ana)
    url = reverse("cobros:morosos_comunidad", args=[con_recibos.pk])
    assert "Sin morosos" in client.get(url, {"fecha": "2026-01-02"}).content.decode()


def test_pagina_con_fecha_futura_avisa_y_muestra_hoy(client, ana, con_recibos):  # noqa: F811
    client.force_login(ana)
    manana = timezone.localdate() + timedelta(days=1)
    url = reverse("cobros:morosos_comunidad", args=[con_recibos.pk])
    respuesta = client.get(url, {"fecha": manana.isoformat()})
    assert respuesta.status_code == 200
    assert "no puede ser posterior a hoy" in respuesta.content.decode()
    assert respuesta.context["fecha"] == timezone.localdate()


def test_pdfs_se_descargan(client, ana, con_recibos):  # noqa: F811
    client.force_login(ana)
    _, informe, certificado = _urls(con_recibos)
    respuesta = client.get(informe, {"fecha": "2026-02-01"})
    assert respuesta["Content-Type"] == "application/pdf"
    assert f"morosos-{con_recibos.pk}-20260201.pdf" in respuesta["Content-Disposition"]
    assert respuesta.content.startswith(b"%PDF")
    respuesta = client.get(certificado)  # sin fecha: hoy
    assert respuesta["Content-Type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")


def test_pdfs_con_fecha_no_valida_dan_400(client, ana, con_recibos):  # noqa: F811
    client.force_login(ana)
    manana = (timezone.localdate() + timedelta(days=1)).isoformat()
    for url in _urls(con_recibos)[1:]:
        assert client.get(url, {"fecha": "no-es-fecha"}).status_code == 400
        assert client.get(url, {"fecha": manana}).status_code == 400

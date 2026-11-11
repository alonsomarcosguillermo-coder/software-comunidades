"""T2.5 — Crear remesas SEPA (R-SEPA-02) con los recibos domiciliables (R-SEPA-01)."""

from datetime import date, datetime

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from lxml import etree

from cobros.derramas import emitir_derrama
from cobros.emision import emitir_cuotas
from cobros.models import Recibo, Remesa
from cobros.recibos import generar_recibos
from cobros.remesas import RemesaInvalida, crear_remesa
from cobros.sepa.identificadores import construir_iban
from cobros.sepa.pain008 import NS, validar_pain008
from contabilidad.models import ContabilidadInmutable

from .conftest import D
from .test_recibos import _mandato, vecinos_a  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db

AHORA = timezone.make_aware(datetime(2026, 1, 10, 12, 0, 0))
COBRO = date(2026, 1, 15)


@pytest.fixture
def comunidad(aprobado_a, fondo_a, vecinos_a, derrama_a):  # noqa: F811
    """Recibos del 1er trimestre (vencen el 5/1) y de una derrama (1/3, 1/4, 1/5).

    1A y 1B tienen mandato; L1 no.
    """
    comunidad = aprobado_a.comunidad
    comunidad.nif = "H00000000"
    comunidad.iban_cobros = construir_iban("ES", "99990000100000000001")
    comunidad.save()
    emitir_cuotas(aprobado_a, 1, date(2026, 1, 5))
    emitir_derrama(derrama_a, date(2026, 2, 1))
    _mandato(comunidad, vecinos_a["1A"], 1)
    _mandato(comunidad, vecinos_a["1B"], 2)
    generar_recibos(comunidad)
    return comunidad


def _xpath(remesa, ruta):
    return etree.fromstring(remesa.xml.encode()).xpath(ruta, namespaces={"p": NS})


# --- Crear -------------------------------------------------------------------------------


def test_r_sepa_02_incluye_solo_recibos_domiciliables_que_vencen_hasta_el_cobro(comunidad):
    remesa = crear_remesa(comunidad, COBRO, ahora=AHORA)
    incluidos = remesa.recibos.order_by("numero")
    # Solo cuotas ordinarias (vencen el 5/1) de 1A y 1B: L1 no tiene mandato y la derrama
    # aún no vence.
    assert [r.inmueble.referencia for r in incluidos] == ["1A", "1B"]
    assert remesa.num_recibos == 2
    assert remesa.total == sum(r.importe for r in incluidos)
    assert remesa.numero == 1
    assert remesa.fecha_cobro == COBRO


def test_r_sepa_02_el_fichero_guardado_valida_y_cuadra(comunidad):
    remesa = crear_remesa(comunidad, COBRO, ahora=AHORA)
    validar_pain008(remesa.xml.encode())
    assert _xpath(remesa, "string(//p:GrpHdr/p:MsgId)") == remesa.mensaje_id
    assert D(_xpath(remesa, "string(//p:GrpHdr/p:CtrlSum)")) == remesa.total
    referencias = _xpath(remesa, "//p:EndToEndId/text()")
    assert sorted(referencias) == sorted(r.referencia for r in remesa.recibos.all())
    assert _xpath(remesa, "string(//p:ReqdColltnDt)") == "2026-01-15"


def test_r_sepa_01_cada_adeudo_usa_el_mandato_del_pagador(comunidad, vecinos_a):  # noqa: F811
    remesa = crear_remesa(comunidad, COBRO, ahora=AHORA)
    recibo = remesa.recibos.get(inmueble__referencia="1A")
    assert recibo.mandato.propietario == vecinos_a["1A"]
    mandatos = _xpath(remesa, "//p:MndtId/text()")
    assert recibo.mandato.referencia in mandatos
    assert recibo.mandato.iban in _xpath(remesa, "//p:DbtrAcct/p:Id/p:IBAN/text()")


def test_los_recibos_quedan_remesados_y_los_demas_pendientes(comunidad):
    remesa = crear_remesa(comunidad, COBRO, ahora=AHORA)
    assert all(r.estado == "remesado" for r in remesa.recibos.all())
    pendientes = Recibo.objects.filter(comunidad=comunidad, remesa__isnull=True)
    assert pendientes.count() == 10  # L1 (cuota) + 9 de la derrama
    assert all(r.estado == "pendiente" and r.secuencia == "" for r in pendientes)


def test_r_sepa_02_primer_cobro_frst_y_siguientes_rcur(comunidad):
    primera = crear_remesa(comunidad, COBRO, ahora=AHORA)
    assert set(primera.recibos.values_list("secuencia", flat=True)) == {"FRST"}
    segunda = crear_remesa(comunidad, date(2026, 3, 2), ahora=AHORA)
    assert set(segunda.recibos.values_list("secuencia", flat=True)) == {"RCUR"}
    assert _xpath(segunda, "//p:SeqTp/text()") == ["RCUR"]


def test_un_recibo_no_entra_en_dos_remesas(comunidad):
    primera = crear_remesa(comunidad, COBRO, ahora=AHORA)
    segunda = crear_remesa(comunidad, date(2026, 3, 2), ahora=AHORA)
    assert not set(primera.recibos.all()) & set(segunda.recibos.all())
    assert segunda.numero == 2
    assert segunda.mensaje_id != primera.mensaje_id
    with pytest.raises(RemesaInvalida, match="No hay recibos domiciliables"):
        crear_remesa(comunidad, date(2026, 3, 2), ahora=AHORA)


def test_r_sepa_01_mandato_firmado_despues_del_cobro_no_vale(comunidad, vecinos_a):  # noqa: F811
    _mandato(comunidad, vecinos_a["L1"], 3, fecha_firma=date(2026, 2, 1))
    remesa = crear_remesa(comunidad, COBRO, ahora=AHORA)
    assert "L1" not in {r.inmueble.referencia for r in remesa.recibos.all()}
    remesa = crear_remesa(comunidad, date(2026, 3, 2), ahora=AHORA)
    assert "L1" in {r.inmueble.referencia for r in remesa.recibos.all()}


def test_r_sepa_01_mandato_dado_de_baja_no_vale(comunidad, vecinos_a):  # noqa: F811
    mandato = comunidad.mandatos.get(propietario=vecinos_a["1B"])
    mandato.fecha_baja = date(2026, 1, 1)
    mandato.save()
    remesa = crear_remesa(comunidad, COBRO, ahora=AHORA)
    assert [r.inmueble.referencia for r in remesa.recibos.all()] == ["1A"]


# --- Rechazos -----------------------------------------------------------------------------


def _nada_guardado(comunidad):
    assert not Remesa.objects.exists()
    assert not Recibo.objects.filter(comunidad=comunidad, remesa__isnull=False).exists()


@pytest.mark.parametrize("cobro", [date(2026, 1, 10), date(2026, 1, 9)])
def test_la_fecha_de_cobro_debe_ser_futura(comunidad, cobro):
    with pytest.raises(RemesaInvalida, match="posterior a hoy"):
        crear_remesa(comunidad, cobro, ahora=AHORA)
    _nada_guardado(comunidad)


def test_sin_nif_no_hay_identificador_de_acreedor(comunidad):
    comunidad.nif = ""
    comunidad.save()
    with pytest.raises(RemesaInvalida, match="NIF"):
        crear_remesa(comunidad, COBRO, ahora=AHORA)
    _nada_guardado(comunidad)


def test_sin_iban_de_cobro(comunidad):
    comunidad.iban_cobros = ""
    comunidad.save()
    with pytest.raises(RemesaInvalida, match="IBAN"):
        crear_remesa(comunidad, COBRO, ahora=AHORA)


def test_sin_recibos_domiciliables(comunidad):
    with pytest.raises(RemesaInvalida, match="No hay recibos domiciliables"):
        crear_remesa(comunidad, date(2026, 1, 4), ahora=timezone.make_aware(datetime(2026, 1, 1)))
    _nada_guardado(comunidad)


def test_r_sepa_02_si_el_xml_no_valida_no_se_guarda_nada(comunidad, vecinos_a):  # noqa: F811
    # Un titular de cuenta sin ningún carácter admitido deja el nombre vacío: el XSD lo rechaza.
    mandato = comunidad.mandatos.get(propietario=vecinos_a["1A"])
    mandato.fecha_baja = date(2025, 12, 31)
    mandato.save()
    _mandato(comunidad, vecinos_a["1A"], 9, titular_cuenta="&&&", referencia="MANDATO-9")
    with pytest.raises(RemesaInvalida, match="esquema"):
        crear_remesa(comunidad, COBRO, ahora=AHORA)
    _nada_guardado(comunidad)


# --- Inmutabilidad y restricciones -----------------------------------------------------


def test_una_remesa_no_se_modifica_ni_se_borra(comunidad):
    remesa = crear_remesa(comunidad, COBRO, ahora=AHORA)
    remesa.xml = "<otro/>"
    with pytest.raises(ContabilidadInmutable):
        remesa.save()
    with pytest.raises(ContabilidadInmutable):
        remesa.delete()


def test_la_base_de_datos_exige_remesa_mandato_y_secuencia_a_la_vez(comunidad):
    remesa = crear_remesa(comunidad, COBRO, ahora=AHORA)
    pendiente = Recibo.objects.filter(comunidad=comunidad, remesa__isnull=True).first()
    with pytest.raises(IntegrityError), transaction.atomic():
        Recibo.objects.filter(pk=pendiente.pk).update(remesa=remesa)  # sin mandato ni secuencia

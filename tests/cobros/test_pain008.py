"""T2.5 — Fichero de remesa ISO 20022 pain.008.001.02 (R-SEPA-02), como funciones puras.

Cada XML generado se valida contra el esquema XSD oficial (`cobros/sepa/pain.008.001.02.xsd`).
Todos los datos son ficticios (IBAN de la entidad inexistente 9999).
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from lxml import etree

from cobros.sepa.identificadores import construir_iban, identificador_acreedor
from cobros.sepa.pain008 import (
    NS,
    Acreedor,
    Adeudo,
    DatosRemesa,
    XmlInvalido,
    generar_pain008,
    validar_pain008,
)


def D(valor: str) -> Decimal:
    return Decimal(valor)


ACREEDOR = Acreedor(
    nombre="Comunidad de Propietarios Calle Ficticia 1",
    iban=construir_iban("ES", "99990000100000000001"),
    identificador=identificador_acreedor("H00000000"),
)


def _adeudo(n: int, importe="10.00", secuencia="RCUR", **campos) -> Adeudo:
    datos = {
        "referencia": f"REC-1-{n}",
        "importe": D(importe),
        "mandato": f"MANDATO-{n}",
        "fecha_firma": date(2025, 6, 1),
        "secuencia": secuencia,
        "deudor": f"Vecino {n}",
        "iban_deudor": construir_iban("ES", f"99990000{n:012d}"),
        "concepto": f"Cuota ordinaria 2026, periodo 1/4 · {n}",
    } | campos
    return Adeudo(**datos)


def _remesa(*adeudos: Adeudo) -> DatosRemesa:
    return DatosRemesa(
        mensaje_id="REM1-1-20260110120000",
        creada=datetime(2026, 1, 10, 12, 0, 0),
        fecha_cobro=date(2026, 1, 15),
        acreedor=ACREEDOR,
        adeudos=adeudos,
    )


def _xpath(xml: bytes, ruta: str):
    return etree.fromstring(xml).xpath(ruta, namespaces={"p": NS})


# --- Estructura -----------------------------------------------------------------------------


def test_r_sepa_02_el_xml_generado_valida_contra_el_xsd():
    xml = generar_pain008(_remesa(_adeudo(1), _adeudo(2, "25.50")))
    validar_pain008(xml)  # no lanza
    assert xml.startswith(b"<?xml")


def test_r_sepa_02_cabecera_con_numero_de_adeudos_y_suma_de_control():
    xml = generar_pain008(_remesa(_adeudo(1, "10.00"), _adeudo(2, "25.50"), _adeudo(3, "0.01")))
    assert _xpath(xml, "string(//p:GrpHdr/p:MsgId)") == "REM1-1-20260110120000"
    assert _xpath(xml, "string(//p:GrpHdr/p:NbOfTxs)") == "3"
    assert _xpath(xml, "string(//p:GrpHdr/p:CtrlSum)") == "35.51"
    assert _xpath(xml, "string(//p:GrpHdr/p:CreDtTm)") == "2026-01-10T12:00:00"


def test_r_sepa_02_esquema_core_y_datos_del_acreedor():
    xml = generar_pain008(_remesa(_adeudo(1)))
    assert _xpath(xml, "string(//p:PmtInf/p:PmtTpInf/p:SvcLvl/p:Cd)") == "SEPA"
    assert _xpath(xml, "string(//p:PmtInf/p:PmtTpInf/p:LclInstrm/p:Cd)") == "CORE"
    assert _xpath(xml, "string(//p:PmtInf/p:ReqdColltnDt)") == "2026-01-15"
    assert _xpath(xml, "string(//p:PmtInf/p:CdtrAcct/p:Id/p:IBAN)") == ACREEDOR.iban
    assert _xpath(xml, "string(//p:CdtrSchmeId//p:Othr/p:Id)") == ACREEDOR.identificador
    assert _xpath(xml, "string(//p:CdtrSchmeId//p:Othr/p:SchmeNm/p:Prtry)") == "SEPA"
    assert _xpath(xml, "string(//p:PmtInf/p:ChrgBr)") == "SLEV"


def test_r_sepa_02_cada_adeudo_lleva_su_mandato_r_sepa_01():
    adeudo = _adeudo(7, "42.00")
    xml = generar_pain008(_remesa(adeudo))
    tx = "//p:DrctDbtTxInf"
    assert _xpath(xml, f"string({tx}/p:PmtId/p:EndToEndId)") == "REC-1-7"
    assert _xpath(xml, f"string({tx}/p:InstdAmt)") == "42.00"
    assert _xpath(xml, f"string({tx}/p:InstdAmt/@Ccy)") == "EUR"
    assert _xpath(xml, f"string({tx}//p:MndtRltdInf/p:MndtId)") == "MANDATO-7"
    assert _xpath(xml, f"string({tx}//p:MndtRltdInf/p:DtOfSgntr)") == "2025-06-01"
    assert _xpath(xml, f"string({tx}/p:DbtrAcct/p:Id/p:IBAN)") == adeudo.iban_deudor
    assert _xpath(xml, f"string({tx}/p:Dbtr/p:Nm)") == "Vecino 7"


def test_r_sepa_02_sin_bic_se_indica_notprovided():
    xml = generar_pain008(_remesa(_adeudo(1)))
    assert _xpath(xml, "string(//p:CdtrAgt/p:FinInstnId/p:Othr/p:Id)") == "NOTPROVIDED"
    assert _xpath(xml, "string(//p:DbtrAgt/p:FinInstnId/p:Othr/p:Id)") == "NOTPROVIDED"


def test_r_sepa_02_un_bloque_por_tipo_de_secuencia():
    xml = generar_pain008(
        _remesa(_adeudo(1, secuencia="FRST"), _adeudo(2, "5.00"), _adeudo(3, "7.00"))
    )
    bloques = _xpath(xml, "//p:PmtInf")
    assert [b.xpath("string(p:PmtTpInf/p:SeqTp)", namespaces={"p": NS}) for b in bloques] == [
        "FRST",
        "RCUR",
    ]
    assert [b.xpath("string(p:NbOfTxs)", namespaces={"p": NS}) for b in bloques] == ["1", "2"]
    assert [b.xpath("string(p:CtrlSum)", namespaces={"p": NS}) for b in bloques] == [
        "10.00",
        "12.00",
    ]
    ids = [b.xpath("string(p:PmtInfId)", namespaces={"p": NS}) for b in bloques]
    assert len(set(ids)) == 2


def test_r_sepa_02_textos_con_el_juego_de_caracteres_sepa():
    xml = generar_pain008(_remesa(_adeudo(1, deudor="Begoña Muñoz & Cía")))
    assert _xpath(xml, "string(//p:Dbtr/p:Nm)") == "Begona Munoz Cia"
    assert _xpath(xml, "string(//p:RmtInf/p:Ustrd)") == "Cuota ordinaria 2026, periodo 1/4 1"


# --- Rechazos ----------------------------------------------------------------------------


def test_sin_adeudos_no_hay_remesa():
    with pytest.raises(ValueError):
        generar_pain008(_remesa())


@pytest.mark.parametrize("importe", ["0.00", "-1.00", "1.001"])
def test_importes_invalidos(importe):
    with pytest.raises(ValueError):
        generar_pain008(_remesa(_adeudo(1, importe)))


def test_secuencia_invalida():
    with pytest.raises(ValueError):
        generar_pain008(_remesa(_adeudo(1, secuencia="OOFF")))


def test_validar_rechaza_un_xml_que_no_cumple_el_esquema():
    xml = generar_pain008(_remesa(_adeudo(1)))
    roto = xml.replace(b"<NbOfTxs>1</NbOfTxs>", b"<NbOfTxs>uno</NbOfTxs>", 1)
    with pytest.raises(XmlInvalido, match="NbOfTxs"):
        validar_pain008(roto)


def test_validar_rechaza_un_nombre_que_queda_vacio():
    # Un nombre solo con caracteres no admitidos se queda vacío: el XSD lo rechaza.
    xml = generar_pain008(_remesa(_adeudo(1, deudor="&&&")))
    with pytest.raises(XmlInvalido):
        validar_pain008(xml)


def test_validar_rechaza_algo_que_no_es_xml():
    with pytest.raises(XmlInvalido):
        validar_pain008(b"esto no es XML")


# --- Propiedad ------------------------------------------------------------------------------

importes = st.integers(min_value=1, max_value=99_999_999).map(lambda c: Decimal(c) / 100)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(importes, st.sampled_from(["FRST", "RCUR"])), min_size=1, max_size=30))
def test_r_sepa_02_propiedad_siempre_valida_y_la_suma_cuadra(lineas):
    adeudos = [_adeudo(n, str(i), s) for n, (i, s) in enumerate(lineas, start=1)]
    xml = generar_pain008(_remesa(*adeudos))
    validar_pain008(xml)
    assert Decimal(_xpath(xml, "string(//p:GrpHdr/p:CtrlSum)")) == sum(i for i, _ in lineas)
    assert int(_xpath(xml, "string(//p:GrpHdr/p:NbOfTxs)")) == len(lineas)
    sumas = [Decimal(t) for t in _xpath(xml, "//p:PmtInf/p:CtrlSum/text()")]
    assert sum(sumas) == sum(i for i, _ in lineas)

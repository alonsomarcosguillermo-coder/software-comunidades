"""Fichero de remesa de adeudos directos SEPA CORE: ISO 20022 pain.008.001.02 (R-SEPA-02).

Funciones puras: reciben dataclasses y devuelven bytes, sin base de datos. Es la versión en
la que se basa el "Cuaderno 19.14 XML" de la banca española (ver ADR 008).

    Document / CstmrDrctDbtInitn
      GrpHdr            cabecera: id del mensaje, fecha, nº de adeudos, suma de control
      PmtInf (1 o 2)    un bloque por tipo de secuencia (FRST primer cobro, RCUR siguientes)
        DrctDbtTxInf    un adeudo por recibo: importe, mandato, deudor, IBAN, concepto

El XML se valida contra el XSD oficial (`pain.008.001.02.xsd`, junto a este módulo) con
`validar_pain008`. El orden de los elementos importa: es el que fija el esquema.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import cache
from pathlib import Path

from lxml import etree

from .identificadores import texto_sepa

NS = "urn:iso:std:iso:20022:tech:xsd:pain.008.001.02"
XSD = Path(__file__).with_name("pain.008.001.02.xsd")
SECUENCIAS = ("FRST", "RCUR")  # primer cobro de un mandato / cobros siguientes
CENTIMO = Decimal("0.01")


class XmlInvalido(ValueError):
    """El XML no cumple el esquema pain.008.001.02."""


@dataclass(frozen=True)
class Acreedor:
    """La comunidad que cobra."""

    nombre: str
    iban: str
    identificador: str  # identificador de acreedor SEPA (AT-02)
    bic: str = ""


@dataclass(frozen=True)
class Adeudo:
    """Un recibo domiciliado."""

    referencia: str  # EndToEndId: identifica el recibo de punta a punta (máx. 35)
    importe: Decimal
    mandato: str  # referencia del mandato (R-SEPA-01)
    fecha_firma: date  # del mandato (R-SEPA-01)
    secuencia: str  # "FRST" o "RCUR"
    deudor: str  # titular de la cuenta
    iban_deudor: str
    concepto: str


@dataclass(frozen=True)
class DatosRemesa:
    mensaje_id: str  # único por acreedor (máx. 35; se le añade "-FRST"/"-RCUR" por bloque)
    creada: datetime
    fecha_cobro: date
    acreedor: Acreedor
    adeudos: Sequence[Adeudo]


def _importe(valor: Decimal) -> str:
    return f"{valor:.2f}"


def _comprobar(datos: DatosRemesa) -> None:
    if not datos.adeudos:
        raise ValueError("Una remesa necesita al menos un adeudo.")
    if len(datos.mensaje_id) > 30:
        raise ValueError("El identificador del mensaje no puede pasar de 30 caracteres.")
    for adeudo in datos.adeudos:
        if not isinstance(adeudo.importe, Decimal):
            raise TypeError("Los importes deben ser Decimal.")
        if adeudo.importe <= 0 or adeudo.importe != adeudo.importe.quantize(CENTIMO):
            raise ValueError(f"Importe no válido en {adeudo.referencia}: {adeudo.importe}.")
        if adeudo.secuencia not in SECUENCIAS:
            raise ValueError(f"Tipo de secuencia no admitido: {adeudo.secuencia}.")


def _sub(padre, etiqueta: str, texto: str | None = None, **atributos):
    """Añade `<etiqueta>` (en el espacio de nombres de pain.008) dentro de `padre`."""
    elemento = etree.SubElement(padre, f"{{{NS}}}{etiqueta}", **atributos)
    if texto is not None:
        elemento.text = texto
    return elemento


def _entidad(padre, etiqueta: str, bic: str) -> None:
    """Banco (agente): por BIC o, sin él, "NOTPROVIDED" (se identifica por el IBAN)."""
    institucion = _sub(_sub(padre, etiqueta), "FinInstnId")
    if bic:
        _sub(institucion, "BIC", bic)
    else:
        _sub(_sub(institucion, "Othr"), "Id", "NOTPROVIDED")


def _cuenta(padre, etiqueta: str, iban: str) -> None:
    _sub(_sub(_sub(padre, etiqueta), "Id"), "IBAN", iban)


def generar_pain008(datos: DatosRemesa) -> bytes:
    """XML pain.008.001.02 de la remesa (UTF-8, con declaración). No lo valida: ver
    `validar_pain008`."""
    _comprobar(datos)
    acreedor = datos.acreedor
    total = sum((a.importe for a in datos.adeudos), Decimal("0"))

    documento = etree.Element(f"{{{NS}}}Document", nsmap={None: NS})
    raiz = _sub(documento, "CstmrDrctDbtInitn")

    cabecera = _sub(raiz, "GrpHdr")
    _sub(cabecera, "MsgId", datos.mensaje_id)
    _sub(cabecera, "CreDtTm", datos.creada.replace(microsecond=0).isoformat())
    _sub(cabecera, "NbOfTxs", str(len(datos.adeudos)))
    _sub(cabecera, "CtrlSum", _importe(total))
    presentador = _sub(cabecera, "InitgPty")
    _sub(presentador, "Nm", texto_sepa(acreedor.nombre, 70))
    _sub(_sub(_sub(_sub(presentador, "Id"), "OrgId"), "Othr"), "Id", acreedor.identificador)

    for secuencia in SECUENCIAS:
        adeudos = [a for a in datos.adeudos if a.secuencia == secuencia]
        if not adeudos:
            continue
        bloque = _sub(raiz, "PmtInf")
        _sub(bloque, "PmtInfId", f"{datos.mensaje_id}-{secuencia}")
        _sub(bloque, "PmtMtd", "DD")
        _sub(bloque, "NbOfTxs", str(len(adeudos)))
        _sub(bloque, "CtrlSum", _importe(sum((a.importe for a in adeudos), Decimal("0"))))
        tipo = _sub(bloque, "PmtTpInf")
        _sub(_sub(tipo, "SvcLvl"), "Cd", "SEPA")
        _sub(_sub(tipo, "LclInstrm"), "Cd", "CORE")
        _sub(tipo, "SeqTp", secuencia)
        _sub(bloque, "ReqdColltnDt", datos.fecha_cobro.isoformat())
        _sub(_sub(bloque, "Cdtr"), "Nm", texto_sepa(acreedor.nombre, 70))
        _cuenta(bloque, "CdtrAcct", acreedor.iban)
        _entidad(bloque, "CdtrAgt", acreedor.bic)
        _sub(bloque, "ChrgBr", "SLEV")  # comisiones: cada uno las de su banco (norma SEPA)
        esquema = _sub(_sub(_sub(bloque, "CdtrSchmeId"), "Id"), "PrvtId")
        otro = _sub(esquema, "Othr")
        _sub(otro, "Id", acreedor.identificador)
        _sub(_sub(otro, "SchmeNm"), "Prtry", "SEPA")

        for adeudo in adeudos:
            transaccion = _sub(bloque, "DrctDbtTxInf")
            _sub(_sub(transaccion, "PmtId"), "EndToEndId", adeudo.referencia)
            _sub(transaccion, "InstdAmt", _importe(adeudo.importe), Ccy="EUR")
            mandato = _sub(_sub(transaccion, "DrctDbtTx"), "MndtRltdInf")
            _sub(mandato, "MndtId", adeudo.mandato)
            _sub(mandato, "DtOfSgntr", adeudo.fecha_firma.isoformat())
            _entidad(transaccion, "DbtrAgt", "")
            _sub(_sub(transaccion, "Dbtr"), "Nm", texto_sepa(adeudo.deudor, 70))
            _cuenta(transaccion, "DbtrAcct", adeudo.iban_deudor)
            _sub(_sub(transaccion, "RmtInf"), "Ustrd", texto_sepa(adeudo.concepto, 140))

    return etree.tostring(documento, xml_declaration=True, encoding="UTF-8", pretty_print=True)


@cache
def _esquema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(XSD)))


def validar_pain008(xml: bytes) -> None:
    """Lanza `XmlInvalido` si `xml` no cumple el esquema oficial pain.008.001.02."""
    try:
        documento = etree.fromstring(xml)
    except etree.XMLSyntaxError as error:
        raise XmlInvalido(f"No es un XML válido: {error}") from error
    esquema = _esquema()
    if not esquema.validate(documento):
        errores = "; ".join(f"línea {e.line}: {e.message}" for e in esquema.error_log)
        raise XmlInvalido(f"El fichero no cumple el esquema pain.008.001.02: {errores}")

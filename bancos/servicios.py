"""Conciliación automática (T3.2): qué movimientos del banco pagan qué recibos. Funciones
puras, sin base de datos.

Criterio "importe + referencia" (ADR 010):
- Un abono paga uno o varios recibos si sus textos (referencias y conceptos) mencionan
  sus referencias (REC-<comunidad>-<nº>) y el importe es exactamente la suma de esos recibos.
- Un abono paga una remesa SEPA si menciona su identificador de mensaje (MsgId) y el importe
  es exactamente el total de la remesa.
- Ante cualquier duda (importe distinto, dos movimientos que reclaman el mismo recibo, un
  movimiento que encaja de dos formas) no se propone nada: lo decide una persona
  (conciliación manual). Conciliar mal es peor que no conciliar.
"""

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

CERO = Decimal("0.00")


@dataclass(frozen=True)
class MovimientoPendiente:
    id: int
    importe: Decimal  # + abono, − cargo
    textos: tuple[str, ...]  # referencias y conceptos del movimiento


@dataclass(frozen=True)
class ReciboPendiente:
    id: int
    referencia: str
    importe: Decimal


@dataclass(frozen=True)
class RemesaPendiente:
    id: int
    mensaje_id: str
    recibos: tuple[int, ...]  # todos sus recibos, ninguno cobrado todavía
    total: Decimal


@dataclass(frozen=True)
class Propuesta:
    movimiento: int
    recibos: tuple[int, ...]
    remesa: int | None = None


def contiene_referencia(texto: str, referencia: str) -> bool:
    """¿Aparece `referencia` en `texto` como palabra completa? "REC-1-1" no está en
    "REC-1-12": a los lados no puede haber letras, cifras ni guiones."""
    patron = rf"(?<![A-Z0-9-]){re.escape(referencia.upper())}(?![A-Z0-9-])"
    return re.search(patron, texto.upper()) is not None


def _candidatas(
    movimiento: MovimientoPendiente,
    recibos: list[ReciboPendiente],
    remesas: list[RemesaPendiente],
) -> list[Propuesta]:
    texto = "\n".join(movimiento.textos)
    candidatas = [
        Propuesta(movimiento=movimiento.id, recibos=remesa.recibos, remesa=remesa.id)
        for remesa in remesas
        if remesa.total == movimiento.importe and contiene_referencia(texto, remesa.mensaje_id)
    ]
    mencionados = [r for r in recibos if contiene_referencia(texto, r.referencia)]
    ya_en_remesa = {frozenset(c.recibos) for c in candidatas}
    if (
        mencionados
        and sum((r.importe for r in mencionados), CERO) == movimiento.importe
        # Si son justo los recibos de la remesa mencionada, es el mismo cobro, no otro.
        and frozenset(r.id for r in mencionados) not in ya_en_remesa
    ):
        candidatas.append(
            Propuesta(movimiento=movimiento.id, recibos=tuple(r.id for r in mencionados))
        )
    return candidatas


def proponer_conciliaciones(
    movimientos: list[MovimientoPendiente],
    recibos: list[ReciboPendiente],
    remesas: list[RemesaPendiente],
) -> list[Propuesta]:
    """Propuestas seguras: cada una cuadra al céntimo y no comparte recibos con otra.

    `recibos` y `remesas` deben ser solo los pendientes de cobro.
    """
    propuestas = []
    for movimiento in movimientos:
        if movimiento.importe <= 0:
            continue  # los cargos no pagan recibos
        candidatas = _candidatas(movimiento, recibos, remesas)
        if len(candidatas) == 1:  # con dos formas de encajar, es ambiguo
            propuestas.append(candidatas[0])
    return _sin_recibos_repetidos(propuestas)


def _sin_recibos_repetidos(propuestas: list[Propuesta]) -> list[Propuesta]:
    # Un recibo reclamado por dos movimientos: ninguno de los dos se concilia solo.
    usos = Counter(r for p in propuestas for r in p.recibos)
    return [p for p in propuestas if all(usos[r] == 1 for r in p.recibos)]


def proponer_devoluciones(
    movimientos: list[MovimientoPendiente], cobrados: list[ReciboPendiente]
) -> list[Propuesta]:
    """T3.3 — Cargos que devuelven recibos ya cobrados (ADR 011).

    Mismo criterio que los cobros, con el signo al revés: el cargo menciona las referencias
    de recibos cobrados y su importe (en positivo) es exactamente su suma. Sin dudas o nada.
    `cobrados` deben ser solo los recibos que ahora mismo están cobrados.
    """
    propuestas = []
    for movimiento in movimientos:
        if movimiento.importe >= 0:
            continue  # una devolución saca dinero de la cuenta: es un cargo
        texto = "\n".join(movimiento.textos)
        mencionados = [r for r in cobrados if contiene_referencia(texto, r.referencia)]
        if mencionados and sum((r.importe for r in mencionados), CERO) == -movimiento.importe:
            propuestas.append(
                Propuesta(movimiento=movimiento.id, recibos=tuple(r.id for r in mencionados))
            )
    return _sin_recibos_repetidos(propuestas)

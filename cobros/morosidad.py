"""T3.4 — Morosidad: qué se debe a la comunidad en una fecha. Cálculo puro (sin Django).

Interpretación aplicada (ver `docs/DOMINIO.md`, pendiente de validar):
- Un recibo está **impagado** en una fecha si no se había cobrado en ella. Cobrado = un
  movimiento del banco conciliado lo paga (T3.2), y cuenta la fecha de ese movimiento.
  Si el banco devuelve el cobro (T3.3), el recibo vuelve a estar impagado desde la fecha
  del cargo de la devolución (entre el cobro y la devolución estuvo pagado).
- Está **vencido** si su vencimiento es anterior a la fecha: el mismo día del vencimiento
  todavía se puede pagar.
- **Deuda** = recibos impagados y vencidos. **Moroso** = propietario con deuda (SPEC.md).
  Cada recibo es deuda de su pagador (el titular en el vencimiento, ver T2.4).
- **Al corriente** = sin deuda. Un recibo emitido que aún no ha vencido no es deuda, pero el
  certificado R-DEU-01 lo menciona aparte, porque el comprador querrá saberlo.

Las consultas que leen los recibos de la base de datos están en `cobros.deudas`.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

CERO = Decimal("0.00")


@dataclass(frozen=True)
class ReciboDeuda:
    """Lo que hace falta de un recibo para saber si es deuda (y para listarlo)."""

    id: int
    referencia: str
    concepto: str
    inmueble_id: int
    inmueble: str  # referencia del inmueble ("1ºA")
    propietario_id: int  # el pagador del recibo
    propietario: str
    importe: Decimal
    vencimiento: date
    fecha_cobro: date | None = None  # fecha del movimiento que lo pagó; None = sin cobrar
    remesado: bool = False  # enviado al banco en una remesa (puede estar pendiente de cobro)
    # T3.3 — Cobros que el banco devolvió: (fecha del cobro, fecha de la devolución). Entre
    # una y otra el recibo estuvo pagado; desde la devolución vuelve a ser deuda.
    devoluciones: tuple[tuple[date, date], ...] = ()

    def impagado_en(self, fecha: date) -> bool:
        if self.fecha_cobro is not None and self.fecha_cobro <= fecha:
            return False
        return not any(cobro <= fecha < devuelto for cobro, devuelto in self.devoluciones)

    def devuelto_en(self, fecha: date) -> bool:
        """Impagado en `fecha` después de que el banco devolviera algún cobro suyo."""
        return self.impagado_en(fecha) and any(d <= fecha for _, d in self.devoluciones)

    def vencido_en(self, fecha: date) -> bool:
        return self.vencimiento < fecha


def _orden(recibo: ReciboDeuda) -> tuple:
    return (recibo.vencimiento, recibo.id)


def _suma(recibos: Iterable[ReciboDeuda]) -> Decimal:
    return sum((r.importe for r in recibos), CERO)


def recibos_impagados(recibos: Iterable[ReciboDeuda], fecha: date) -> list[ReciboDeuda]:
    """Los recibos sin cobrar en `fecha` (vencidos o no), del más antiguo al más nuevo."""
    return sorted((r for r in recibos if r.impagado_en(fecha)), key=_orden)


@dataclass(frozen=True)
class Moroso:
    propietario_id: int
    propietario: str
    recibos: tuple[ReciboDeuda, ...]  # sus recibos vencidos e impagados, del más antiguo

    @property
    def total(self) -> Decimal:
        return _suma(self.recibos)

    @property
    def mas_antiguo(self) -> date:
        return self.recibos[0].vencimiento

    @property
    def inmuebles(self) -> tuple[str, ...]:
        return tuple(sorted({r.inmueble for r in self.recibos}))


@dataclass(frozen=True)
class InformeMorosos:
    fecha: date
    morosos: tuple[Moroso, ...]  # de mayor a menor deuda

    @property
    def total(self) -> Decimal:
        return sum((m.total for m in self.morosos), CERO)

    @property
    def num_recibos(self) -> int:
        return sum(len(m.recibos) for m in self.morosos)


def informe_morosos(recibos: Iterable[ReciboDeuda], fecha: date) -> InformeMorosos:
    """Propietarios con recibos vencidos e impagados en `fecha`, de mayor a menor deuda
    (empates: por nombre y luego por identificador, para que el orden sea siempre el mismo)."""
    por_propietario: dict[int, list[ReciboDeuda]] = {}
    for recibo in recibos_impagados(recibos, fecha):
        if recibo.vencido_en(fecha):
            por_propietario.setdefault(recibo.propietario_id, []).append(recibo)
    morosos = [
        Moroso(propietario_id=pid, propietario=lista[0].propietario, recibos=tuple(lista))
        for pid, lista in por_propietario.items()
    ]
    morosos.sort(key=lambda m: (-m.total, m.propietario, m.propietario_id))
    return InformeMorosos(fecha=fecha, morosos=tuple(morosos))


@dataclass(frozen=True)
class EstadoDeuda:
    """R-DEU-01 — Estado de deudas de un inmueble en una fecha (lo que dice el certificado)."""

    fecha: date
    vencidos: tuple[ReciboDeuda, ...]  # la deuda
    por_vencer: tuple[ReciboDeuda, ...]  # emitidos y sin cobrar, pero aún no vencidos

    @property
    def total_vencido(self) -> Decimal:
        return _suma(self.vencidos)

    @property
    def total_por_vencer(self) -> Decimal:
        return _suma(self.por_vencer)

    @property
    def al_corriente(self) -> bool:
        return not self.vencidos


def estado_deuda(recibos: Iterable[ReciboDeuda], fecha: date) -> EstadoDeuda:
    """R-DEU-01 — Estado de deudas en `fecha` a partir de los recibos de un inmueble."""
    impagados = recibos_impagados(recibos, fecha)
    return EstadoDeuda(
        fecha=fecha,
        vencidos=tuple(r for r in impagados if r.vencido_en(fecha)),
        por_vencer=tuple(r for r in impagados if not r.vencido_en(fecha)),
    )

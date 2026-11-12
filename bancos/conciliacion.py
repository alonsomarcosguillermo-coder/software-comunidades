"""Conciliación bancaria (T3.2). Es la ÚNICA forma prevista de crear o deshacer
conciliaciones.

Conciliar un movimiento = explicarlo en la contabilidad:
- Abono que paga recibos: asiento 572 Banco (Debe) / 430 Propietarios (Haber, un apunte
  por recibo). Los recibos pasan a cobrados.
- Cualquier otro movimiento (un gasto, una comisión, un ingreso que no es un recibo):
  asiento entre 572 y la cuenta que elija la persona.

La decisión de qué recibos paga un movimiento (automática) es pura y está en
`bancos.servicios`; aquí se valida, se registra el asiento y se guarda, en una transacción.
"""

from collections.abc import Iterable
from datetime import date

from django.db import transaction
from django.db.models import Count, Q, Sum

from cobros.emision import CUENTA_PROPIETARIOS, cuenta_por_codigo
from cobros.models import Recibo, Remesa
from contabilidad.models import Cuenta
from contabilidad.registro import anular_asiento, registrar_asiento
from contabilidad.servicios import Linea
from fincas.models import Comunidad

from .models import CobroRecibo, Conciliacion, Movimiento
from .servicios import (
    CERO,
    MovimientoPendiente,
    ReciboPendiente,
    RemesaPendiente,
    proponer_conciliaciones,
)

CUENTA_BANCO = ("572", "Banco")
# No se puede conciliar "a mano" contra estas cuentas: el banco es la contrapartida de
# todo, y los propietarios (430) se mueven solo cobrando recibos concretos.
CODIGOS_RESERVADOS = {CUENTA_BANCO[0], CUENTA_PROPIETARIOS[0]}


class ConciliacionInvalida(ValueError):
    """No se puede conciliar (o deshacer) el movimiento."""


def _bloquear(movimiento: Movimiento) -> Comunidad:
    """Bloquea la comunidad (dos conciliaciones a la vez esperan su turno) y comprueba que
    el movimiento sigue pendiente."""
    comunidad = Comunidad.objects.select_for_update().get(pk=movimiento.extracto.comunidad_id)
    if Conciliacion.objects.filter(movimiento=movimiento).exists():
        raise ConciliacionInvalida("El movimiento ya está conciliado.")
    return comunidad


def _texto_movimiento(movimiento: Movimiento) -> str:
    return f"movimiento del {movimiento.fecha_operacion:%d/%m/%Y} ({movimiento.importe} €)"


@transaction.atomic
def conciliar_con_recibos(
    movimiento: Movimiento,
    recibos: Iterable[Recibo],
    *,
    usuario=None,
    automatica: bool = False,
    remesa: Remesa | None = None,
) -> Conciliacion:
    """El abono `movimiento` paga exactamente `recibos` (su suma = el importe)."""
    comunidad = _bloquear(movimiento)
    recibos = sorted(set(recibos), key=lambda r: r.numero)
    if movimiento.importe <= 0:
        raise ConciliacionInvalida("Un cargo no puede pagar recibos: solo los abonos.")
    if not recibos:
        raise ConciliacionInvalida("Elige al menos un recibo.")
    if any(r.comunidad_id != comunidad.pk for r in recibos):
        raise ConciliacionInvalida("Algún recibo es de otra comunidad.")
    cobrados = CobroRecibo.objects.filter(recibo__in=recibos).select_related("recibo")
    if cobrados:
        lista = ", ".join(c.recibo.referencia for c in cobrados)
        raise ConciliacionInvalida(f"Estos recibos ya están cobrados: {lista}.")
    total = sum((r.importe for r in recibos), CERO)
    if total != movimiento.importe:
        raise ConciliacionInvalida(
            f"Los recibos suman {total} € y el movimiento es de {movimiento.importe} €: tienen "
            "que coincidir al céntimo."
        )

    propietarios = cuenta_por_codigo(comunidad, *CUENTA_PROPIETARIOS)
    lineas = [Linea(cuenta_por_codigo(comunidad, *CUENTA_BANCO), debe=total)]
    lineas += [
        Linea(propietarios, haber=r.importe, concepto=f"{r.referencia} · {r.concepto}"[:200])
        for r in recibos
    ]
    if remesa is not None:
        concepto = f"Cobro de la remesa {remesa.numero}"
    else:
        concepto = "Cobro de " + ", ".join(r.referencia for r in recibos)
    asiento = registrar_asiento(comunidad, movimiento.fecha_operacion, concepto[:200], lineas)
    conciliacion = Conciliacion.objects.create(
        movimiento=movimiento,
        asiento=asiento,
        remesa=remesa,
        automatica=automatica,
        creada_por=usuario,
    )
    CobroRecibo.objects.bulk_create(
        CobroRecibo(conciliacion=conciliacion, recibo=r) for r in recibos
    )
    return conciliacion


@transaction.atomic
def conciliar_con_cuenta(movimiento: Movimiento, cuenta: Cuenta, *, usuario=None) -> Conciliacion:
    """Lleva el movimiento a otra cuenta contable: un cargo al Debe de `cuenta` (p. ej. un
    gasto), un abono a su Haber (p. ej. un ingreso que no es un recibo)."""
    comunidad = _bloquear(movimiento)
    if cuenta.comunidad_id != comunidad.pk:
        raise ConciliacionInvalida("La cuenta es de otra comunidad.")
    if cuenta.codigo in CODIGOS_RESERVADOS:
        raise ConciliacionInvalida(
            f"No se puede conciliar contra la cuenta {cuenta.codigo}: los cobros de "
            "propietarios se concilian eligiendo sus recibos."
        )
    importe = abs(movimiento.importe)
    banco = cuenta_por_codigo(comunidad, *CUENTA_BANCO)
    concepto = (movimiento.conceptos.splitlines() or [movimiento.nombre_concepto])[0]
    if movimiento.importe > 0:
        lineas = [Linea(banco, debe=importe), Linea(cuenta, haber=importe)]
    else:
        lineas = [Linea(cuenta, debe=importe), Linea(banco, haber=importe)]
    asiento = registrar_asiento(comunidad, movimiento.fecha_operacion, concepto[:200], lineas)
    return Conciliacion.objects.create(
        movimiento=movimiento, asiento=asiento, cuenta=cuenta, creada_por=usuario
    )


@transaction.atomic
def deshacer_conciliacion(conciliacion: Conciliacion, fecha: date) -> None:
    """Anula el asiento con un contra-asiento (la contabilidad conserva los dos) y borra la
    conciliación: el movimiento vuelve a pendiente y sus recibos, a pendientes de cobro."""
    Comunidad.objects.select_for_update().get(pk=conciliacion.asiento.comunidad_id)
    movimiento = conciliacion.movimiento
    anular_asiento(
        conciliacion.asiento,
        fecha,
        f"Deshecha la conciliación del {_texto_movimiento(movimiento)}"[:200],
    )
    conciliacion.delete()  # CASCADE: también sus CobroRecibo


def movimientos_pendientes(comunidad: Comunidad):
    return Movimiento.objects.filter(
        extracto__comunidad=comunidad, conciliacion__isnull=True
    ).order_by("fecha_operacion", "pk")


def recibos_pendientes(comunidad: Comunidad):
    """Recibos aún sin cobrar (estén o no en una remesa)."""
    return comunidad.recibos.filter(cobro__isnull=True).order_by("vencimiento", "numero")


@transaction.atomic
def conciliar_automaticamente(comunidad: Comunidad, *, usuario=None) -> list[Conciliacion]:
    """Concilia los abonos pendientes que encajan sin dudas por importe + referencia."""
    comunidad = Comunidad.objects.select_for_update().get(pk=comunidad.pk)
    movimientos = {m.pk: m for m in movimientos_pendientes(comunidad)}
    recibos = {r.pk: r for r in recibos_pendientes(comunidad)}
    # Remesas con todos sus recibos pendientes de cobro.
    remesas = {
        r.pk: r
        for r in comunidad.remesas.annotate(
            cobrados=Count("recibos", filter=Q(recibos__cobro__isnull=False)),
            pendiente=Sum("recibos__importe"),
        ).filter(cobrados=0)
    }
    recibos_de_remesa: dict[int, list[int]] = {}
    for recibo in recibos.values():
        if recibo.remesa_id in remesas:
            recibos_de_remesa.setdefault(recibo.remesa_id, []).append(recibo.pk)

    propuestas = proponer_conciliaciones(
        [
            MovimientoPendiente(
                id=m.pk,
                importe=m.importe,
                textos=(m.referencia_1, m.referencia_2, *m.conceptos.splitlines()),
            )
            for m in movimientos.values()
        ],
        [
            ReciboPendiente(id=r.pk, referencia=r.referencia, importe=r.importe)
            for r in recibos.values()
        ],
        [
            RemesaPendiente(
                id=r.pk,
                mensaje_id=r.mensaje_id,
                recibos=tuple(sorted(recibos_de_remesa.get(r.pk, ()))),
                total=r.pendiente or CERO,
            )
            for r in remesas.values()
        ],
    )
    return [
        conciliar_con_recibos(
            movimientos[p.movimiento],
            [recibos[r] for r in p.recibos],
            usuario=usuario,
            automatica=True,
            remesa=remesas.get(p.remesa) if p.remesa else None,
        )
        for p in propuestas
    ]

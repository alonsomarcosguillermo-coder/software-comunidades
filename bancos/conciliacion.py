"""Conciliación bancaria (T3.2). Es la ÚNICA forma prevista de crear o deshacer
conciliaciones.

Conciliar un movimiento = explicarlo en la contabilidad:
- Abono que paga recibos: asiento 572 Banco (Debe) / 430 Propietarios (Haber, un apunte
  por recibo). Los recibos pasan a cobrados.
- Cargo que devuelve recibos cobrados (T3.3): asiento 430 (Debe) / 572 (Haber). Los
  recibos dejan de estar cobrados: vuelven a ser deuda del propietario.
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

from .models import CobroRecibo, Conciliacion, Devolucion, Movimiento
from .servicios import (
    CERO,
    MovimientoPendiente,
    ReciboPendiente,
    RemesaPendiente,
    proponer_conciliaciones,
    proponer_devoluciones,
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
    conciliación: el movimiento vuelve a pendiente y sus recibos, a pendientes de cobro.

    T3.3: un cobro con recibos devueltos no se deshace (antes, la devolución). Deshacer una
    devolución vuelve a dar por cobrados sus recibos con el cobro original, salvo que ya se
    hayan vuelto a cobrar con otro movimiento.
    """
    Comunidad.objects.select_for_update().get(pk=conciliacion.asiento.comunidad_id)
    devueltos = Devolucion.objects.filter(cobro=conciliacion).select_related("recibo")
    if devueltos:
        lista = ", ".join(d.recibo.referencia for d in devueltos)
        raise ConciliacionInvalida(
            f"Este cobro tiene recibos devueltos ({lista}): deshaz antes la devolución."
        )
    devoluciones = list(conciliacion.devoluciones.select_related("recibo"))
    recobrados = CobroRecibo.objects.filter(
        recibo__in=[d.recibo for d in devoluciones]
    ).select_related("recibo")
    if recobrados:
        lista = ", ".join(c.recibo.referencia for c in recobrados)
        raise ConciliacionInvalida(
            f"Estos recibos se han vuelto a cobrar después de la devolución ({lista}): deshaz "
            "antes ese cobro."
        )
    movimiento = conciliacion.movimiento
    anular_asiento(
        conciliacion.asiento,
        fecha,
        f"Deshecha la conciliación del {_texto_movimiento(movimiento)}"[:200],
    )
    conciliacion.delete()  # CASCADE: también sus CobroRecibo y sus Devolucion
    # Los recibos devueltos vuelven a estar cobrados por su cobro original.
    CobroRecibo.objects.bulk_create(
        CobroRecibo(conciliacion_id=d.cobro_id, recibo=d.recibo) for d in devoluciones
    )


# --- Devoluciones (T3.3) -------------------------------------------------------------------


@transaction.atomic
def conciliar_devolucion(
    movimiento: Movimiento, recibos: Iterable[Recibo], *, usuario=None, automatica: bool = False
) -> Conciliacion:
    """El cargo `movimiento` devuelve exactamente `recibos`, que estaban cobrados.

    Asiento 430 Propietarios (Debe, un apunte por recibo) / 572 Banco (Haber): el dinero sale
    del banco y el propietario vuelve a deberlo. Cada recibo deja de estar cobrado.
    """
    comunidad = _bloquear(movimiento)
    recibos = sorted(set(recibos), key=lambda r: r.numero)
    if movimiento.importe >= 0:
        raise ConciliacionInvalida("Una devolución es un cargo; este movimiento es un abono.")
    if not recibos:
        raise ConciliacionInvalida("Elige al menos un recibo devuelto.")
    if any(r.comunidad_id != comunidad.pk for r in recibos):
        raise ConciliacionInvalida("Algún recibo es de otra comunidad.")
    cobros = {c.recibo_id: c for c in CobroRecibo.objects.filter(recibo__in=recibos)}
    sin_cobrar = [r.referencia for r in recibos if r.pk not in cobros]
    if sin_cobrar:
        raise ConciliacionInvalida(
            f"Solo se puede devolver un recibo cobrado, y estos no lo están: "
            f"{', '.join(sin_cobrar)}."
        )
    total = sum((r.importe for r in recibos), CERO)
    if total != -movimiento.importe:
        raise ConciliacionInvalida(
            f"Los recibos suman {total} € y el cargo es de {-movimiento.importe} €: tienen que "
            "coincidir al céntimo. Si el banco cobra una comisión en el mismo cargo, "
            "concilíalo contra una cuenta y registra la devolución aparte."
        )

    propietarios = cuenta_por_codigo(comunidad, *CUENTA_PROPIETARIOS)
    lineas = [
        Linea(propietarios, debe=r.importe, concepto=f"{r.referencia} devuelto"[:200])
        for r in recibos
    ]
    lineas.append(Linea(cuenta_por_codigo(comunidad, *CUENTA_BANCO), haber=total))
    concepto = "Devolución de " + ", ".join(r.referencia for r in recibos)
    asiento = registrar_asiento(comunidad, movimiento.fecha_operacion, concepto[:200], lineas)
    conciliacion = Conciliacion.objects.create(
        movimiento=movimiento, asiento=asiento, automatica=automatica, creada_por=usuario
    )
    Devolucion.objects.bulk_create(
        Devolucion(conciliacion=conciliacion, recibo=r, cobro_id=cobros[r.pk].conciliacion_id)
        for r in recibos
    )
    # El recibo deja de estar cobrado: vuelve a ser deuda y se puede volver a cobrar.
    CobroRecibo.objects.filter(pk__in=[c.pk for c in cobros.values()]).delete()
    return conciliacion


def recibos_cobrados(comunidad: Comunidad):
    return comunidad.recibos.filter(cobro__isnull=False).order_by("vencimiento", "numero")


def movimientos_pendientes(comunidad: Comunidad):
    return Movimiento.objects.filter(
        extracto__comunidad=comunidad, conciliacion__isnull=True
    ).order_by("fecha_operacion", "pk")


def recibos_pendientes(comunidad: Comunidad):
    """Recibos aún sin cobrar (estén o no en una remesa)."""
    return comunidad.recibos.filter(cobro__isnull=True).order_by("vencimiento", "numero")


@transaction.atomic
def conciliar_automaticamente(comunidad: Comunidad, *, usuario=None) -> list[Conciliacion]:
    """Concilia lo que encaja sin dudas por importe + referencia: primero los abonos que
    cobran recibos o remesas y después (T3.3) los cargos que devuelven recibos cobrados."""
    comunidad = Comunidad.objects.select_for_update().get(pk=comunidad.pk)
    hechas = _cobrar_automaticamente(comunidad, usuario)
    return hechas + _devolver_automaticamente(comunidad, usuario)


def _datos_movimiento(m: Movimiento) -> MovimientoPendiente:
    return MovimientoPendiente(
        id=m.pk,
        importe=m.importe,
        textos=(m.referencia_1, m.referencia_2, *m.conceptos.splitlines()),
    )


def _devolver_automaticamente(comunidad: Comunidad, usuario) -> list[Conciliacion]:
    movimientos = {m.pk: m for m in movimientos_pendientes(comunidad).filter(importe__lt=0)}
    cobrados = {r.pk: r for r in recibos_cobrados(comunidad)}
    propuestas = proponer_devoluciones(
        [_datos_movimiento(m) for m in movimientos.values()],
        [
            ReciboPendiente(id=r.pk, referencia=r.referencia, importe=r.importe)
            for r in cobrados.values()
        ],
    )
    return [
        conciliar_devolucion(
            movimientos[p.movimiento],
            [cobrados[r] for r in p.recibos],
            usuario=usuario,
            automatica=True,
        )
        for p in propuestas
    ]


def _cobrar_automaticamente(comunidad: Comunidad, usuario) -> list[Conciliacion]:
    movimientos = {m.pk: m for m in movimientos_pendientes(comunidad)}
    recibos = {r.pk: r for r in recibos_pendientes(comunidad)}
    # Remesas aún sin cobrar, con todos sus recibos pendientes de cobro.
    remesas = {
        r.pk: r
        for r in comunidad.remesas.filter(conciliaciones__isnull=True)
        .annotate(
            cobrados=Count("recibos", filter=Q(recibos__cobro__isnull=False)),
            pendiente=Sum("recibos__importe"),
        )
        .filter(cobrados=0)
    }
    recibos_de_remesa: dict[int, list[int]] = {}
    for recibo in recibos.values():
        if recibo.remesa_id in remesas:
            recibos_de_remesa.setdefault(recibo.remesa_id, []).append(recibo.pk)

    propuestas = proponer_conciliaciones(
        [_datos_movimiento(m) for m in movimientos.values()],
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

"""T3.4 — Deuda de la base de datos: lee los recibos y llama al cálculo puro de
`cobros.morosidad`.

La fecha de cobro de un recibo es la del movimiento del banco que lo paga (conciliación,
T3.2). Se llega a ella por la relación inversa `cobro` (`bancos.CobroRecibo`), sin importar
la app bancos.
"""

from dataclasses import dataclass
from datetime import date

from django.db.models import F, QuerySet

from fincas.models import Comunidad, Inmueble, Propietario

from .models import Recibo
from .morosidad import EstadoDeuda, InformeMorosos, ReciboDeuda, estado_deuda, informe_morosos


def recibos_deuda(recibos: QuerySet[Recibo]) -> list[ReciboDeuda]:
    """Convierte recibos de la base de datos en `ReciboDeuda` (dos consultas).

    T3.3 — Un recibo devuelto ya no tiene `cobro` (se borra al devolverlo), pero cada
    `Devolucion` recuerda qué conciliación lo había cobrado: de ahí salen los periodos
    "cobrado → devuelto", para calcular bien la deuda en fechas pasadas.
    """
    filas = (
        recibos.select_related("inmueble", "propietario")
        .annotate(fecha_cobro=F("cobro__conciliacion__movimiento__fecha_operacion"))
        .prefetch_related(
            "devoluciones__cobro__movimiento", "devoluciones__conciliacion__movimiento"
        )
    )
    return [
        ReciboDeuda(
            id=r.pk,
            referencia=r.referencia,
            concepto=r.concepto,
            inmueble_id=r.inmueble_id,
            inmueble=r.inmueble.referencia,
            propietario_id=r.propietario_id,
            propietario=r.propietario.nombre,
            importe=r.importe,
            vencimiento=r.vencimiento,
            fecha_cobro=r.fecha_cobro,
            remesado=r.remesa_id is not None,
            devoluciones=tuple(
                (d.cobro.movimiento.fecha_operacion, d.conciliacion.movimiento.fecha_operacion)
                for d in r.devoluciones.all()
            ),
        )
        for r in filas
    ]


def informe_morosos_de(comunidad: Comunidad, fecha: date) -> InformeMorosos:
    """Morosos de la comunidad en `fecha` (solo hacen falta los recibos que ya vencían)."""
    return informe_morosos(recibos_deuda(comunidad.recibos.filter(vencimiento__lt=fecha)), fecha)


@dataclass(frozen=True)
class DatosCertificado:
    """R-DEU-01 — Todo lo que lleva el certificado de deuda de un inmueble."""

    comunidad: Comunidad
    inmueble: Inmueble
    titulares: list[Propietario]  # titulares en la fecha del certificado
    estado: EstadoDeuda


def certificado_deuda_de(inmueble: Inmueble, fecha: date) -> DatosCertificado:
    """R-DEU-01 — Estado de deudas del inmueble en `fecha`, con todos sus recibos (sea quien
    sea el pagador: también los de titulares anteriores)."""
    return DatosCertificado(
        comunidad=inmueble.comunidad,
        inmueble=inmueble,
        titulares=list(inmueble.propietarios_en(fecha).order_by("nombre")),
        estado=estado_deuda(recibos_deuda(inmueble.recibos.all()), fecha),
    )

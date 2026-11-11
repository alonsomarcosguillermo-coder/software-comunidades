"""Recibos (T2.4). `generar_recibos` es la ÚNICA forma prevista de crear recibos.

De cada cuota ordinaria (T2.2) y cada cuota de derrama (T2.3) sale un recibo. Los recibos no
llevan asiento: la deuda ya se apuntó en la 430 al emitir las cuotas. El cobro se
contabilizará al conciliar con el banco (T3.2).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction
from django.db.models import Max

from fincas.models import Comunidad, Inmueble, Propietario, Titularidad

from .models import Cuota, CuotaDerrama, Mandato, Recibo


def elegir_pagador(titulares: Sequence[tuple[int, bool]]) -> int | None:
    """Entre los titulares vigentes de un inmueble, quién paga el recibo.

    `titulares`: (id del propietario, ¿tiene mandato SEPA vigente?). Con un solo titular, él.
    Con cotitulares, el primero (menor id) que tenga mandato vigente; si ninguno lo tiene,
    el primero. Sin titulares, None. Interpretación pendiente de validar (ver DOMINIO.md).
    """
    if not titulares:
        return None
    ordenados = sorted(titulares)
    con_mandato = [pk for pk, tiene in ordenados if tiene]
    return con_mandato[0] if con_mandato else ordenados[0][0]


@dataclass
class ResultadoGeneracion:
    creados: list[Recibo] = field(default_factory=list)
    # Cuotas que no se han podido convertir en recibo: (inmueble, vencimiento).
    sin_titular: list[tuple[Inmueble, date]] = field(default_factory=list)


def _pagador(comunidad: Comunidad, inmueble: Inmueble, fecha: date) -> Propietario | None:
    titulares = list(
        Propietario.objects.filter(
            titularidades__in=Titularidad.objects.vigentes(fecha).filter(inmueble=inmueble)
        ).distinct()
    )
    con_mandato = set(
        Mandato.objects.vigentes(fecha)
        .filter(comunidad=comunidad, propietario__in=titulares)
        .values_list("propietario_id", flat=True)
    )
    elegido = elegir_pagador([(p.pk, p.pk in con_mandato) for p in titulares])
    return next((p for p in titulares if p.pk == elegido), None)


@transaction.atomic
def generar_recibos(comunidad: Comunidad) -> ResultadoGeneracion:
    """Crea un recibo por cada cuota de la comunidad que todavía no lo tenga.

    Se puede ejecutar las veces que se quiera: una cuota nunca tiene dos recibos (también lo
    impide la base de datos). Las cuotas de inmuebles sin titular en la fecha de vencimiento
    se quedan sin recibo y se devuelven en `sin_titular`, para que alguien lo corrija.
    """
    # Bloquea la comunidad: dos generaciones simultáneas no repiten número ni recibo.
    Comunidad.objects.select_for_update().get(pk=comunidad.pk)
    siguiente = (comunidad.recibos.aggregate(n=Max("numero"))["n"] or 0) + 1

    pendientes = []  # (vencimiento, orden, inmueble, concepto, importe, campos de origen)
    cuotas = Cuota.objects.filter(
        emision__presupuesto__comunidad=comunidad, recibo__isnull=True
    ).select_related("emision__presupuesto", "inmueble")
    for cuota in cuotas:
        emision = cuota.emision
        presupuesto = emision.presupuesto
        pendientes.append(
            (
                emision.fecha,
                (0, cuota.pk),
                cuota.inmueble,
                f"Cuota ordinaria {presupuesto.ejercicio}, periodo {emision.periodo}/"
                f"{presupuesto.periodos} · {cuota.inmueble.referencia}",
                cuota.importe,
                {"cuota": cuota},
            )
        )
    cuotas_derrama = CuotaDerrama.objects.filter(
        derrama__comunidad=comunidad, recibo__isnull=True
    ).select_related("derrama", "inmueble")
    for cuota in cuotas_derrama:
        derrama = cuota.derrama
        pendientes.append(
            (
                cuota.vencimiento,
                (1, cuota.pk),
                cuota.inmueble,
                f"Derrama {derrama.concepto}, plazo {cuota.plazo}/{derrama.plazos} · "
                f"{cuota.inmueble.referencia}",
                cuota.importe,
                {"cuota_derrama": cuota},
            )
        )

    resultado = ResultadoGeneracion()
    # Numeración por fecha de vencimiento: los recibos que antes vencen, antes se numeran.
    for vencimiento, _, inmueble, concepto, importe, origen in sorted(
        pendientes, key=lambda p: (p[0], p[2].referencia, p[1])
    ):
        pagador = _pagador(comunidad, inmueble, vencimiento)
        if pagador is None:
            resultado.sin_titular.append((inmueble, vencimiento))
            continue
        resultado.creados.append(
            Recibo.objects.create(
                comunidad=comunidad,
                numero=siguiente,
                inmueble=inmueble,
                propietario=pagador,
                concepto=concepto[:140],
                importe=importe,
                vencimiento=vencimiento,
                **origen,
            )
        )
        siguiente += 1
    return resultado

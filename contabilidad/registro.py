"""Registro de asientos en la base de datos. Es la ÚNICA forma prevista de crear asientos.

La lógica pura (¿cuadra?, ¿cómo se invierte?) está en `servicios.py`; aquí solo se
orquesta: validar, numerar y guardar, todo en una transacción.
"""

from collections.abc import Sequence
from datetime import date

from django.db import transaction
from django.db.models import Max

from fincas.models import Comunidad

from .models import Apunte, Asiento
from .servicios import AsientoInvalido, Linea, comprobar_cuadre, invertir


@transaction.atomic
def registrar_asiento(
    comunidad: Comunidad,
    fecha: date,
    concepto: str,
    lineas: Sequence[Linea],
    *,
    anula: Asiento | None = None,
) -> Asiento:
    """Crea un asiento con sus apuntes. Falla (sin guardar nada) si no cuadra."""
    comprobar_cuadre(lineas)
    for linea in lineas:
        if linea.cuenta.comunidad_id != comunidad.pk:
            raise AsientoInvalido(f"La cuenta {linea.cuenta} es de otra comunidad.")

    # Bloquea la fila de la comunidad hasta el final de la transacción: si dos personas
    # registran a la vez, la segunda espera y no se repite el número de asiento.
    Comunidad.objects.select_for_update().get(pk=comunidad.pk)
    ultimo = comunidad.asientos.aggregate(n=Max("numero"))["n"] or 0

    asiento = Asiento.objects.create(
        comunidad=comunidad, numero=ultimo + 1, fecha=fecha, concepto=concepto, anula=anula
    )
    Apunte.objects.bulk_create(
        Apunte(
            asiento=asiento,
            cuenta=linea.cuenta,
            debe=linea.debe,
            haber=linea.haber,
            concepto=linea.concepto,
        )
        for linea in lineas
    )
    return asiento


def anular_asiento(asiento: Asiento, fecha: date, concepto: str = "") -> Asiento:
    """Corrige un asiento con un contra-asiento: los mismos apuntes con Debe y Haber
    intercambiados. El asiento original no se toca."""
    if asiento.anula_id is not None:
        raise AsientoInvalido(
            f"El asiento {asiento.numero} es un contra-asiento; registra uno nuevo correcto."
        )
    if asiento.esta_anulado():
        raise AsientoInvalido(f"El asiento {asiento.numero} ya está anulado.")
    lineas = [
        Linea(cuenta=a.cuenta, debe=a.debe, haber=a.haber, concepto=a.concepto)
        for a in asiento.apuntes.select_related("cuenta")
    ]
    return registrar_asiento(
        asiento.comunidad,
        fecha,
        concepto or f"Anulación del asiento {asiento.numero}: {asiento.concepto}",
        invertir(lineas),
        anula=asiento,
    )

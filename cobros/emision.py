"""Emisión de cuotas ordinarias (T2.2). Es la ÚNICA forma prevista de crear emisiones y cuotas.

Los cálculos son funciones puras de `servicios.py`; aquí solo se orquesta: validar, bloquear,
calcular, registrar el asiento y guardar, todo en una transacción.

Asiento de una emisión (ver ADR 005):
    Debe  430 Propietarios          una línea por inmueble (lo que debe cada uno)
    Haber 705 Cuotas ordinarias     la parte que cubre los gastos del presupuesto
    Haber <fondo de reserva>        la parte que es aportación al fondo (R-RES-01)
"""

from datetime import date

from django.db import transaction

from contabilidad.models import Cuenta
from contabilidad.registro import registrar_asiento
from contabilidad.servicios import Linea
from fincas.models import Comunidad

from .models import Cuota, Emision, Presupuesto
from .servicios import CERO, desglose_del_periodo, plan_de_cuotas

# Cuentas que usa la emisión. Si la comunidad no las tiene, se crean con estos datos.
CUENTA_PROPIETARIOS = ("430", "Propietarios")
CUENTA_CUOTAS = ("705", "Cuotas ordinarias")


class EmisionInvalida(ValueError):
    """No se pueden emitir las cuotas pedidas."""


def _cuenta(comunidad: Comunidad, codigo: str, nombre: str) -> Cuenta:
    return Cuenta.objects.get_or_create(
        comunidad=comunidad, codigo=codigo, defaults={"nombre": nombre}
    )[0]


@transaction.atomic
def emitir_cuotas(presupuesto: Presupuesto, periodo: int, fecha: date) -> Emision:
    """Emite las cuotas del `periodo` (1..presupuesto.periodos) y registra su asiento.

    Falla con `EmisionInvalida` (sin guardar nada) si el presupuesto no está aprobado
    (R-PRE-01), si los coeficientes de la comunidad no suman 100 % (R-COEF-01), si el
    periodo no existe o ya está emitido, o si falta la cuenta del fondo de reserva.
    """
    # Bloquea el presupuesto hasta el final de la transacción: si dos personas emiten el
    # mismo periodo a la vez, la segunda espera y luego ve que ya está emitido.
    presupuesto = Presupuesto.objects.select_for_update().get(pk=presupuesto.pk)
    comunidad = presupuesto.comunidad

    if not presupuesto.esta_aprobado:
        raise EmisionInvalida(
            "R-PRE-01: el presupuesto no está aprobado; no se pueden emitir sus cuotas."
        )
    if not 1 <= periodo <= presupuesto.periodos:
        raise EmisionInvalida(f"El periodo {periodo} no está entre 1 y {presupuesto.periodos}.")
    if presupuesto.emisiones.filter(periodo=periodo).exists():
        raise EmisionInvalida(f"El periodo {periodo} ya está emitido.")
    if not comunidad.coeficientes_cuadran():
        raise EmisionInvalida(
            "R-COEF-01: los coeficientes de la comunidad no suman 100 %; corrígelos antes "
            "de emitir cuotas."
        )
    gastos = presupuesto.total_gastos()
    aportacion = presupuesto.aportacion_fondo_reserva
    if gastos + aportacion <= 0:
        raise EmisionInvalida("El presupuesto no tiene importes que cobrar.")
    fondo = Cuenta.objects.filter(comunidad=comunidad, es_fondo_reserva=True).first()
    if aportacion > 0 and fondo is None:
        raise EmisionInvalida(
            "R-RES-01: el presupuesto tiene aportación al fondo de reserva, pero la "
            "comunidad no tiene ninguna cuenta marcada como fondo de reserva."
        )

    inmuebles = {inmueble.pk: inmueble for inmueble in comunidad.inmuebles.all()}
    coeficientes = {pk: inmueble.coeficiente for pk, inmueble in inmuebles.items()}
    plan = plan_de_cuotas(gastos + aportacion, coeficientes, presupuesto.periodos)
    # Un coeficiente muy pequeño puede dar una cuota de 0 €: no se emite (ni se apunta).
    cuotas = {pk: importe for pk, importe in plan[periodo].items() if importe > 0}
    totales = {p: sum(c.values(), CERO) for p, c in plan.items()}
    ingreso, a_fondo = desglose_del_periodo(totales, periodo, gastos=gastos, aportacion=aportacion)

    propietarios = _cuenta(comunidad, *CUENTA_PROPIETARIOS)
    lineas = [
        Linea(propietarios, debe=importe, concepto=inmuebles[pk].referencia)
        for pk, importe in sorted(cuotas.items(), key=lambda c: inmuebles[c[0]].referencia)
    ]
    if ingreso > 0:
        lineas.append(Linea(_cuenta(comunidad, *CUENTA_CUOTAS), haber=ingreso))
    if a_fondo > 0:
        lineas.append(Linea(fondo, haber=a_fondo))

    asiento = registrar_asiento(
        comunidad,
        fecha,
        f"Cuotas ordinarias {presupuesto.ejercicio}, periodo {periodo}/{presupuesto.periodos}",
        lineas,
    )
    emision = Emision.objects.create(
        presupuesto=presupuesto, periodo=periodo, fecha=fecha, asiento=asiento
    )
    Cuota.objects.bulk_create(
        Cuota(emision=emision, inmueble_id=pk, importe=importe) for pk, importe in cuotas.items()
    )
    return emision

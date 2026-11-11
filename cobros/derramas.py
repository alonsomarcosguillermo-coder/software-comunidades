"""Derramas (T2.3): reparto y emisión. `emitir_derrama` es la ÚNICA forma prevista de crear
cuotas de derrama.

Los cálculos son funciones puras de `servicios.py`; aquí solo se orquesta: validar, bloquear,
calcular, registrar el asiento y guardar, todo en una transacción.

Asiento de una derrama (ver ADR 006). Se registra entera al emitirla, porque la deuda nace
del acuerdo; los plazos solo dicen cuándo vence cada parte:
    Debe  430 Propietarios     una línea por inmueble (su parte de la derrama)
    Haber 706 Derramas         el importe total
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction

from contabilidad.models import Cuenta
from contabilidad.registro import registrar_asiento
from contabilidad.servicios import Linea
from fincas.models import Comunidad, Inmueble
from fincas.servicios import GrupoInvalido

from .models import CuotaDerrama, Derrama
from .servicios import CERO, plan_de_derrama

# Cuentas que usa la emisión. Si la comunidad no las tiene, se crean con estos datos.
# Mismo criterio que la emisión de cuotas ordinarias (T2.2).
CUENTA_PROPIETARIOS = ("430", "Propietarios")
CUENTA_DERRAMAS = ("706", "Derramas")


class DerramaInvalida(ValueError):
    """No se puede repartir o emitir la derrama."""


@dataclass(frozen=True)
class FilaReparto:
    """Lo que paga un inmueble en cada plazo de una derrama."""

    inmueble: Inmueble
    cuotas: list[Decimal]  # una por plazo, en orden (0 si ese plazo no le toca nada)
    total: Decimal


def coeficientes_para(derrama: Derrama) -> dict[int, Decimal]:
    """{id del inmueble: coeficiente} con el que se reparte la derrama.

    - R-COEF-01: los coeficientes de la comunidad deben sumar 100 %, haya grupo o no (si no,
      los datos de la comunidad están mal y cualquier reparto lo arrastraría).
    - R-REP-01: con grupo de reparto, solo sus inmuebles, con sus coeficientes.
    """
    comunidad = derrama.comunidad
    if not comunidad.coeficientes_cuadran():
        raise DerramaInvalida(
            "R-COEF-01: los coeficientes de la comunidad no suman 100 %; corrígelos antes de "
            "repartir la derrama."
        )
    if derrama.grupo_id is None:
        return dict(comunidad.inmuebles.values_list("pk", "coeficiente"))
    if derrama.grupo.comunidad_id != comunidad.pk:
        raise DerramaInvalida("El grupo de reparto es de otra comunidad.")
    try:
        return derrama.grupo.coeficientes()
    except GrupoInvalido as error:
        raise DerramaInvalida(str(error)) from error


def reparto_previsto(derrama: Derrama) -> dict[int, dict[int, Decimal]]:
    """Plan {plazo: {id del inmueble: importe}} que saldría si se emitiera ahora."""
    return plan_de_derrama(derrama.importe, coeficientes_para(derrama), derrama.plazos)


def reparto_emitido(derrama: Derrama) -> dict[int, dict[int, Decimal]]:
    """Plan {plazo: {id del inmueble: importe}} guardado al emitir la derrama."""
    plan: dict[int, dict[int, Decimal]] = {p: {} for p in range(1, derrama.plazos + 1)}
    for plazo, inmueble_id, importe in derrama.cuotas.values_list(
        "plazo", "inmueble_id", "importe"
    ):
        plan[plazo][inmueble_id] = importe
    return plan


def filas_de_reparto(plan: dict[int, dict[int, Decimal]]) -> list[FilaReparto]:
    """El plan, por inmueble (ordenado por referencia), para mostrarlo en una tabla."""
    ids = {inmueble_id for cuotas in plan.values() for inmueble_id in cuotas}
    filas = []
    for inmueble in Inmueble.objects.filter(pk__in=ids).order_by("referencia"):
        cuotas = [plan[p].get(inmueble.pk, CERO) for p in sorted(plan)]
        filas.append(FilaReparto(inmueble=inmueble, cuotas=cuotas, total=sum(cuotas, CERO)))
    return filas


def _cuenta(comunidad: Comunidad, codigo: str, nombre: str) -> Cuenta:
    return Cuenta.objects.get_or_create(
        comunidad=comunidad, codigo=codigo, defaults={"nombre": nombre}
    )[0]


@transaction.atomic
def emitir_derrama(derrama: Derrama, fecha: date) -> Derrama:
    """Emite la derrama: fija su reparto en cuotas (inmueble × plazo) y registra su asiento.

    Falla con `DerramaInvalida` (sin guardar nada) si no está acordada, si ya está emitida,
    si los coeficientes no suman 100 % (R-COEF-01) o si el grupo no sirve (R-REP-01).
    """
    # Bloquea la derrama hasta el final de la transacción: si dos personas la emiten a la
    # vez, la segunda espera y luego ve que ya está emitida.
    derrama = Derrama.objects.select_for_update().get(pk=derrama.pk)
    if derrama.esta_emitida:
        raise DerramaInvalida("La derrama ya está emitida.")
    if not derrama.esta_acordada:
        raise DerramaInvalida(
            "La derrama no tiene fecha de acuerdo: no se puede emitir una derrama sin acordar."
        )
    comunidad = derrama.comunidad
    plan = reparto_previsto(derrama)
    fechas = derrama.vencimientos()
    # Un coeficiente muy pequeño puede dar una cuota de 0 €: no se emite (ni se apunta).
    cuotas = [
        CuotaDerrama(
            derrama=derrama,
            inmueble_id=inmueble_id,
            plazo=plazo,
            vencimiento=fechas[plazo - 1],
            importe=importe,
        )
        for plazo, importes in plan.items()
        for inmueble_id, importe in importes.items()
        if importe > 0
    ]

    por_inmueble: dict[int, Decimal] = {}
    for cuota in cuotas:
        por_inmueble[cuota.inmueble_id] = por_inmueble.get(cuota.inmueble_id, CERO) + cuota.importe
    referencias = dict(Inmueble.objects.filter(pk__in=por_inmueble).values_list("pk", "referencia"))
    propietarios = _cuenta(comunidad, *CUENTA_PROPIETARIOS)
    lineas = [
        Linea(propietarios, debe=importe, concepto=referencias[pk])
        for pk, importe in sorted(por_inmueble.items(), key=lambda par: referencias[par[0]])
    ]
    lineas.append(Linea(_cuenta(comunidad, *CUENTA_DERRAMAS), haber=derrama.importe))

    asiento = registrar_asiento(comunidad, fecha, f"Derrama: {derrama.concepto}", lineas)
    CuotaDerrama.objects.bulk_create(cuotas)
    derrama.asiento = asiento
    derrama.save(update_fields=["asiento"])
    return derrama

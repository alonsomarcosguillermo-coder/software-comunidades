"""Lógica de negocio de cobros, como funciones puras (sin base de datos ni web)."""

from calendar import monthrange
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_UP, Decimal

from fincas.servicios import repartir

CERO = Decimal("0.00")
CENTIMO = Decimal("0.01")

# R-RES-01: el fondo de reserva no puede ser inferior al 10 % del último presupuesto ordinario.
PORCENTAJE_MINIMO_FONDO_RESERVA = Decimal("10")


def _exigir_decimal(*importes) -> None:
    for importe in importes:
        if not isinstance(importe, Decimal):
            raise TypeError(f"Los importes deben ser Decimal, no {type(importe).__name__}")


def total_partidas(importes: Iterable[Decimal]) -> Decimal:
    """Suma exacta de los importes de las partidas de un presupuesto."""
    importes = list(importes)
    _exigir_decimal(*importes)
    return sum(importes, CERO)


def minimo_fondo_reserva(presupuesto: Decimal) -> Decimal:
    """R-RES-01: importe mínimo del fondo de reserva para un presupuesto ordinario.

    Se redondea HACIA ARRIBA al céntimo (no con ROUND_HALF_UP, como el resto del dinero):
    es un mínimo legal ("no inferior al 10 %") y redondear hacia abajo lo incumpliría.
    Ej.: 10 % de 1.234,51 € = 123,451 € → 123,46 €.
    """
    _exigir_decimal(presupuesto)
    if presupuesto < 0:
        raise ValueError(f"Un presupuesto no puede ser negativo ({presupuesto}).")
    exacto = presupuesto * PORCENTAJE_MINIMO_FONDO_RESERVA / 100
    return exacto.quantize(CENTIMO, rounding=ROUND_UP)


@dataclass(frozen=True)
class EstadoFondoReserva:
    """Resultado de comprobar R-RES-01."""

    saldo: Decimal  # lo que hay en el fondo
    minimo: Decimal  # lo que debería haber como mínimo
    faltante: Decimal  # lo que falta para llegar al mínimo (0 si se cumple)

    @property
    def cumple(self) -> bool:
        return self.faltante == 0


def estado_fondo_reserva(saldo: Decimal, presupuesto: Decimal) -> EstadoFondoReserva:
    """R-RES-01: ¿un fondo de reserva con `saldo` cumple con el `presupuesto` ordinario dado?

    `saldo` puede ser negativo (un fondo descubierto); entonces falta todo el mínimo y más.
    """
    _exigir_decimal(saldo, presupuesto)
    minimo = minimo_fondo_reserva(presupuesto)
    return EstadoFondoReserva(saldo=saldo, minimo=minimo, faltante=max(minimo - saldo, CERO))


# --- Cuotas ordinarias (T2.2) ---------------------------------------------------------


def plan_de_cuotas[K: Hashable](
    total: Decimal, coeficientes: Mapping[K, Decimal], periodos: int
) -> dict[int, dict[K, Decimal]]:
    """Cuotas de todo el año: {periodo (1..N): {inmueble: importe}}.

    Dos repartos con R-REP-02 (`repartir`):
      1. `total` (anual) entre los inmuebles, por coeficiente.
      2. La parte anual de cada inmueble, a partes iguales entre los `periodos`. Los
         céntimos sobrantes van a los primeros periodos.
    Así cada inmueble paga en el año exactamente su parte, y la suma de todo es `total`.
    """
    if periodos < 1:
        raise ValueError(f"El número de periodos debe ser al menos 1, no {periodos}.")
    anual = repartir(total, coeficientes)
    iguales = {periodo: Decimal(1) for periodo in range(1, periodos + 1)}
    plan: dict[int, dict[K, Decimal]] = {periodo: {} for periodo in iguales}
    for inmueble, importe in anual.items():
        for periodo, parte in repartir(importe, iguales).items():
            plan[periodo][inmueble] = parte
    return plan


def cuotas_del_periodo[K: Hashable](
    total: Decimal, coeficientes: Mapping[K, Decimal], periodos: int, periodo: int
) -> dict[K, Decimal]:
    """Cuotas de un periodo (1..`periodos`) del plan anual. Ver `plan_de_cuotas`."""
    if not 1 <= periodo <= periodos:
        raise ValueError(f"El periodo {periodo} no está entre 1 y {periodos}.")
    return plan_de_cuotas(total, coeficientes, periodos)[periodo]


def desglose_contable(
    emitido: Decimal, *, gastos: Decimal, aportacion: Decimal
) -> tuple[Decimal, Decimal]:
    """Parte de lo `emitido` que es ingreso por cuotas y parte que va al fondo de reserva.

    En la misma proporción que en el presupuesto (`gastos` : `aportacion`), con R-REP-02
    para que las dos partes sumen exactamente `emitido`. Devuelve (ingreso, fondo).
    """
    _exigir_decimal(emitido, gastos, aportacion)
    pesos = {"1-ingreso": gastos, "2-fondo": aportacion}
    pesos = {clave: peso for clave, peso in pesos.items() if peso > 0}
    if not pesos:
        raise ValueError("El presupuesto no tiene importes que repartir.")
    partes = repartir(emitido, pesos)
    return partes.get("1-ingreso", CERO), partes.get("2-fondo", CERO)


def desglose_del_periodo(
    totales: Mapping[int, Decimal], periodo: int, *, gastos: Decimal, aportacion: Decimal
) -> tuple[Decimal, Decimal]:
    """(ingreso, fondo) del `periodo`, dados los `totales` emitidos en cada periodo del plan.

    Se desglosa lo acumulado hasta este periodo y se resta lo acumulado hasta el anterior:
    así, al emitir todos los periodos, el fondo recibe EXACTAMENTE `aportacion` y los
    ingresos EXACTAMENTE `gastos`, sin que se acumulen céntimos de redondeo.
    """
    if periodo not in totales:
        raise ValueError(f"El periodo {periodo} no está en el plan.")
    hasta = sum((t for p, t in totales.items() if p <= periodo), CERO)
    antes = sum((t for p, t in totales.items() if p < periodo), CERO)
    ingreso, fondo = desglose_contable(hasta, gastos=gastos, aportacion=aportacion)
    ingreso_antes, fondo_antes = desglose_contable(antes, gastos=gastos, aportacion=aportacion)
    return ingreso - ingreso_antes, fondo - fondo_antes


# --- Derramas (T2.3) ------------------------------------------------------------------


def plan_de_derrama[K: Hashable](
    importe: Decimal, coeficientes: Mapping[K, Decimal], plazos: int
) -> dict[int, dict[K, Decimal]]:
    """Cuotas de una derrama: {plazo (1..N): {inmueble: importe}}.

    Dos repartos con R-REP-02 (`repartir`):
      1. `importe` entre los inmuebles por coeficiente (los generales o los de un grupo de
         reparto, R-REP-01).
      2. La parte de cada inmueble, a partes iguales entre los `plazos`. Los céntimos
         sobrantes van a los primeros plazos.
    Así cada inmueble paga en total exactamente su parte, y todo suma `importe`.
    """
    _exigir_decimal(importe)
    if importe <= 0:
        raise ValueError(f"El importe de una derrama debe ser mayor que 0, no {importe}.")
    if plazos < 1:
        raise ValueError(f"El número de plazos debe ser al menos 1, no {plazos}.")
    # Es el mismo algoritmo que el de las cuotas ordinarias, con plazos en vez de periodos.
    return plan_de_cuotas(importe, coeficientes, plazos)


def sumar_meses(fecha: date, meses: int) -> date:
    """`fecha` + `meses` meses. Si ese día no existe (31 de abril), el último del mes."""
    indice = fecha.year * 12 + fecha.month - 1 + meses
    anio, mes = divmod(indice, 12)
    mes += 1
    return date(anio, mes, min(fecha.day, monthrange(anio, mes)[1]))


def vencimientos(primero: date, plazos: int, meses_entre_plazos: int) -> list[date]:
    """Fechas de vencimiento de los plazos de una derrama, cada `meses_entre_plazos` meses.

    Cada fecha se calcula desde `primero` (no desde la anterior), para que un 31 de enero
    dé 28 de febrero y luego 31 de marzo, no 28 de marzo.
    """
    if plazos < 1:
        raise ValueError(f"El número de plazos debe ser al menos 1, no {plazos}.")
    if meses_entre_plazos < 1:
        raise ValueError(f"Entre plazos debe haber al menos 1 mes, no {meses_entre_plazos}.")
    return [sumar_meses(primero, n * meses_entre_plazos) for n in range(plazos)]

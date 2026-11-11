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
    partes = repartir(importe, coeficientes)
    iguales = {plazo: Decimal(1) for plazo in range(1, plazos + 1)}
    plan: dict[int, dict[K, Decimal]] = {plazo: {} for plazo in iguales}
    for inmueble, parte in partes.items():
        for plazo, cuota in repartir(parte, iguales).items():
            plan[plazo][inmueble] = cuota
    return plan


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

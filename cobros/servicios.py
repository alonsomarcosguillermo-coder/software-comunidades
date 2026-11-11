"""Lógica de negocio de cobros, como funciones puras (sin base de datos ni web)."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_UP, Decimal

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

"""Lógica de contabilidad de partida doble, como funciones puras (sin base de datos ni web)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

CERO = Decimal("0")
CENTIMO = Decimal("0.01")


class AsientoInvalido(ValueError):
    """El asiento no cumple las reglas de la partida doble."""


@dataclass(frozen=True)
class Linea:
    """Una línea de un asiento antes de guardarlo: una cuenta y un importe al Debe o al Haber.

    `cuenta` puede ser cualquier cosa (en la base de datos, una `Cuenta`; en los tests
    puros, un código como "572").
    """

    cuenta: Any
    debe: Decimal = CERO
    haber: Decimal = CERO
    concepto: str = ""


def comprobar_cuadre(lineas: Sequence[Linea]) -> None:
    """Comprueba que `lineas` forman un asiento válido de partida doble.

    - Importes `Decimal`, no negativos y en céntimos.
    - Cada línea va al Debe O al Haber (una sola de las dos, y distinta de 0).
    - Al menos dos líneas, y suma del Debe = suma del Haber.

    Lanza `AsientoInvalido` con el motivo.
    """
    for linea in lineas:
        for importe in (linea.debe, linea.haber):
            if not isinstance(importe, Decimal):
                raise TypeError(f"Los importes deben ser Decimal, no {type(importe).__name__}")
            if importe < 0:
                raise AsientoInvalido(
                    f"Importe negativo ({importe}) en {linea.cuenta}: ponlo en el lado contrario."
                )
            if importe != importe.quantize(CENTIMO):
                raise AsientoInvalido(f"El importe {importe} tiene fracciones de céntimo.")
        if (linea.debe > 0) == (linea.haber > 0):
            raise AsientoInvalido(
                f"Cada línea va en el Debe o en el Haber (solo uno, y mayor que 0): {linea.cuenta}."
            )
    if len(lineas) < 2:
        raise AsientoInvalido("Un asiento necesita al menos dos líneas.")
    debe = sum((linea.debe for linea in lineas), CERO)
    haber = sum((linea.haber for linea in lineas), CERO)
    if debe != haber:
        raise AsientoInvalido(f"Asiento descuadrado: Debe {debe} ≠ Haber {haber}.")


def invertir(lineas: Sequence[Linea]) -> list[Linea]:
    """Líneas del contra-asiento: lo que iba al Debe pasa al Haber y viceversa."""
    return [replace(linea, debe=linea.haber, haber=linea.debe) for linea in lineas]

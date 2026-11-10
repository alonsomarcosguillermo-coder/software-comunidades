"""Lógica de negocio de fincas, como funciones puras (sin base de datos ni web)."""

from collections.abc import Iterable
from decimal import Decimal

# R-COEF-01: los coeficientes de una comunidad suman exactamente 100 %.
SUMA_COEFICIENTES = Decimal("100")


class CoeficientesInvalidos(ValueError):
    """Los coeficientes de una comunidad no cumplen R-COEF-01."""


def comprobar_coeficientes(coeficientes: Iterable[Decimal]) -> None:
    """Comprueba R-COEF-01 sobre los coeficientes (en %) de TODOS los inmuebles de una comunidad.

    Lanza `CoeficientesInvalidos` con el motivo si no se cumple. La comparación es exacta
    porque son `Decimal`: 99,9999 no es 100.
    """
    coeficientes = list(coeficientes)
    for coeficiente in coeficientes:
        if not isinstance(coeficiente, Decimal):
            raise TypeError(f"Los coeficientes deben ser Decimal, no {type(coeficiente).__name__}")
    if not coeficientes:
        raise CoeficientesInvalidos("R-COEF-01: la comunidad no tiene ningún inmueble.")
    if any(coeficiente <= 0 for coeficiente in coeficientes):
        raise CoeficientesInvalidos("R-COEF-01: cada coeficiente debe ser mayor que 0.")
    suma = sum(coeficientes, Decimal("0"))
    if suma != SUMA_COEFICIENTES:
        raise CoeficientesInvalidos(
            f"R-COEF-01: los coeficientes suman {suma} % y deben sumar exactamente "
            f"{SUMA_COEFICIENTES} % (diferencia: {SUMA_COEFICIENTES - suma} %)."
        )

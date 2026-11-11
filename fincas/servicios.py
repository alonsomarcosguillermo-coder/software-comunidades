"""Lógica de negocio de fincas, como funciones puras (sin base de datos ni web)."""

from collections.abc import Hashable, Iterable, Mapping
from decimal import Decimal
from fractions import Fraction

CENTIMO = Decimal("0.01")

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


def repartir[K: Hashable](importe: Decimal, coeficientes: Mapping[K, Decimal]) -> dict[K, Decimal]:
    """Reparte `importe` (en euros, con céntimos) en proporción a `coeficientes`.

    Aplica R-REP-02 (método del resto mayor):
      1. Cada parte exacta se trunca a céntimos.
      2. Los céntimos que sobran se dan, de uno en uno, a quienes más parte decimal
         perdieron al truncar.
      3. Empates: por orden de identificador (las claves de `coeficientes`, p. ej. el id del
         inmueble), para que el resultado sea siempre el mismo.
    Así la suma de las partes es SIEMPRE exactamente `importe`.

    Los coeficientes no tienen por qué sumar 100: un grupo de reparto (R-REP-01) usa solo
    algunos inmuebles, y se reparte en proporción a lo que sumen. Un importe negativo (un
    abono) se reparte igual que uno positivo, con el signo cambiado.

    Las cuentas se hacen con `Fraction` (fracciones exactas): ni el `Decimal` redondea por
    el camino, ni hay errores de `float`.
    """
    if not isinstance(importe, Decimal):
        raise TypeError(f"El importe debe ser Decimal, no {type(importe).__name__}")
    for coeficiente in coeficientes.values():
        if not isinstance(coeficiente, Decimal):
            raise TypeError(f"Los coeficientes deben ser Decimal, no {type(coeficiente).__name__}")
    if importe != importe.quantize(CENTIMO):
        raise ValueError(f"El importe {importe} tiene fracciones de céntimo.")
    if not coeficientes:
        raise ValueError("No hay ningún coeficiente entre el que repartir.")
    if any(coeficiente <= 0 for coeficiente in coeficientes.values()):
        raise ValueError("Cada coeficiente debe ser mayor que 0.")

    signo = -1 if importe < 0 else 1
    centimos = int(abs(importe) / CENTIMO)
    total = sum(Fraction(c) for c in coeficientes.values())

    partes: dict[K, int] = {}
    restos: dict[K, Fraction] = {}
    for clave, coeficiente in coeficientes.items():
        exacta = centimos * Fraction(coeficiente) / total
        partes[clave] = exacta.numerator // exacta.denominator  # truncar (exacta >= 0)
        restos[clave] = exacta - partes[clave]

    sobrantes = centimos - sum(partes.values())  # siempre 0 <= sobrantes < nº de partes
    for clave in sorted(coeficientes, key=lambda k: (-restos[k], k))[:sobrantes]:
        partes[clave] += 1

    return {clave: (Decimal(signo * cent) * CENTIMO) for clave, cent in partes.items()}


# --- Grupos de reparto (R-REP-01, T2.3) ------------------------------------------------


class GrupoInvalido(ValueError):
    """Un grupo de reparto no se puede usar para repartir (R-REP-01)."""


def coeficientes_de_grupo[K: Hashable](
    miembros: Iterable[tuple[K, Decimal, Decimal | None]],
) -> dict[K, Decimal]:
    """R-REP-01: coeficientes con los que reparte un grupo de reparto.

    `miembros` son tuplas (clave del inmueble, coeficiente general, coeficiente propio en el
    grupo o None). Hay dos formas de definir un grupo, y no se pueden mezclar:
      - Sin coeficientes propios: se usan los generales de sus inmuebles. Es el caso típico
        de excluir inmuebles de un gasto (p. ej. los locales del ascensor); `repartir` ya
        reparte en proporción a lo que sumen, aunque no lleguen a 100.
      - Con coeficientes propios en TODOS: los que fijen los estatutos o el acuerdo.
    """
    miembros = list(miembros)
    for _, general, propio in miembros:
        for valor in (general, propio):
            if valor is not None and not isinstance(valor, Decimal):
                raise TypeError(f"Los coeficientes deben ser Decimal, no {type(valor).__name__}")
    if not miembros:
        raise GrupoInvalido("R-REP-01: el grupo de reparto no tiene ningún inmueble.")
    con_propio = [propio is not None for _, _, propio in miembros]
    if any(con_propio) and not all(con_propio):
        raise GrupoInvalido(
            "R-REP-01: los coeficientes propios del grupo deben ponerse en todos o ninguno "
            "de sus inmuebles."
        )
    coeficientes = {
        clave: (propio if propio is not None else general) for clave, general, propio in miembros
    }
    if any(coeficiente <= 0 for coeficiente in coeficientes.values()):
        raise GrupoInvalido("R-REP-01: cada coeficiente del grupo debe ser mayor que 0.")
    return coeficientes

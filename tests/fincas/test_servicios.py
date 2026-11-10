"""T1.2 — Validación de coeficientes (R-COEF-01), como función pura sin base de datos."""

from decimal import Decimal

import pytest

from fincas.servicios import CoeficientesInvalidos, comprobar_coeficientes


def D(valor: str) -> Decimal:
    return Decimal(valor)


def test_r_coef_01_coeficientes_que_suman_100_son_validos():
    comprobar_coeficientes([D("33.3333"), D("33.3333"), D("33.3334")])


def test_r_coef_01_un_solo_inmueble_con_100():
    comprobar_coeficientes([D("100")])


@pytest.mark.parametrize(
    "coeficientes",
    [
        [D("50"), D("49.9999")],  # falta una diezmilésima
        [D("50"), D("50.0001")],  # sobra una diezmilésima
        [D("33.3333"), D("33.3333"), D("33.3333")],  # el clásico tercio mal redondeado
    ],
)
def test_r_coef_01_la_suma_debe_ser_exactamente_100(coeficientes):
    with pytest.raises(CoeficientesInvalidos, match="100"):
        comprobar_coeficientes(coeficientes)


def test_r_coef_01_sin_inmuebles_no_es_valido():
    with pytest.raises(CoeficientesInvalidos, match="ningún inmueble"):
        comprobar_coeficientes([])


@pytest.mark.parametrize("malo", [D("0"), D("-10")])
def test_r_coef_01_cada_coeficiente_debe_ser_positivo(malo):
    with pytest.raises(CoeficientesInvalidos, match="mayor que 0"):
        comprobar_coeficientes([D("100") - malo, malo])


def test_r_coef_01_no_acepta_float():
    # Los coeficientes van siempre en Decimal: en float, 0.1 + 0.2 != 0.3.
    with pytest.raises(TypeError):
        comprobar_coeficientes([50.0, 50.0])

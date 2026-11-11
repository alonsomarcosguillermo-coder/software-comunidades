"""T2.3 — Cálculo de una derrama en plazos, como funciones puras.

Reparto en dos pasos, los dos con R-REP-02 (`fincas.servicios.repartir`):
  1. El importe total se reparte entre los inmuebles por coeficiente (o los del grupo, R-REP-01).
  2. La parte de cada inmueble se divide a partes iguales entre los plazos.
"""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cobros.servicios import plan_de_derrama, sumar_meses, vencimientos
from fincas.servicios import repartir


def D(valor: str) -> Decimal:
    return Decimal(valor)


# --- Plan de plazos -------------------------------------------------------------------


def test_r_rep_02_derrama_exacta_en_plazos():
    plan = plan_de_derrama(D("3000.00"), {1: D("60"), 2: D("40")}, plazos=3)
    assert plan == {
        1: {1: D("600.00"), 2: D("400.00")},
        2: {1: D("600.00"), 2: D("400.00")},
        3: {1: D("600.00"), 2: D("400.00")},
    }


def test_r_rep_02_los_centimos_sobrantes_van_a_los_primeros_plazos():
    plan = plan_de_derrama(D("100.00"), {1: D("100")}, plazos=3)
    assert [plan[p][1] for p in (1, 2, 3)] == [D("33.34"), D("33.33"), D("33.33")]


def test_r_rep_01_grupo_con_coeficientes_que_no_suman_100():
    # Solo los pisos (30 % + 20 %): pagan 60 % y 40 % de la derrama.
    plan = plan_de_derrama(D("1000.00"), {1: D("30"), 2: D("20")}, plazos=1)
    assert plan == {1: {1: D("600.00"), 2: D("400.00")}}


@pytest.mark.parametrize("plazos", [0, -2])
def test_numero_de_plazos_invalido(plazos):
    with pytest.raises(ValueError):
        plan_de_derrama(D("100.00"), {1: D("100")}, plazos=plazos)


def test_importe_de_derrama_positivo():
    with pytest.raises(ValueError):
        plan_de_derrama(D("0.00"), {1: D("100")}, plazos=1)
    with pytest.raises(ValueError):
        plan_de_derrama(D("-10.00"), {1: D("100")}, plazos=1)


importes = st.decimals(min_value=D("0.01"), max_value=D("999999.99"), places=2)
coeficientes = st.dictionaries(
    st.integers(min_value=1, max_value=500),
    st.decimals(min_value=D("0.0001"), max_value=D("100"), places=4),
    min_size=1,
    max_size=25,
)


@given(importe=importes, coefs=coeficientes, plazos=st.integers(min_value=1, max_value=60))
def test_r_rep_02_la_derrama_cuadra_al_centimo(importe, coefs, plazos):
    plan = plan_de_derrama(importe, coefs, plazos)
    assert set(plan) == set(range(1, plazos + 1))
    # Todo suma exactamente el importe de la derrama...
    assert sum((sum(c.values(), D("0")) for c in plan.values()), D("0")) == importe
    # ...y cada inmueble paga en total exactamente su parte del reparto por coeficiente.
    parte = repartir(importe, coefs)
    for inmueble in coefs:
        assert sum((plan[p][inmueble] for p in plan), D("0")) == parte[inmueble]
    # Los plazos de un mismo inmueble difieren como mucho en un céntimo.
    for inmueble in coefs:
        cuotas = [plan[p][inmueble] for p in plan]
        assert max(cuotas) - min(cuotas) <= D("0.01")


# --- Vencimientos ---------------------------------------------------------------------


def test_vencimientos_mensuales():
    assert vencimientos(date(2026, 3, 5), plazos=3, meses_entre_plazos=1) == [
        date(2026, 3, 5),
        date(2026, 4, 5),
        date(2026, 5, 5),
    ]


def test_vencimientos_trimestrales_cruzando_el_anio():
    assert vencimientos(date(2026, 11, 1), plazos=3, meses_entre_plazos=3) == [
        date(2026, 11, 1),
        date(2027, 2, 1),
        date(2027, 5, 1),
    ]


def test_vencimientos_a_fin_de_mes_no_se_desplazan():
    # Del 31 de enero: 28 de febrero, pero luego vuelve al 31 (no se queda en el 28).
    assert vencimientos(date(2027, 1, 31), plazos=4, meses_entre_plazos=1) == [
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
        date(2027, 4, 30),
    ]


def test_sumar_meses_en_bisiesto():
    assert sumar_meses(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert sumar_meses(date(2026, 12, 15), 0) == date(2026, 12, 15)


@pytest.mark.parametrize(("plazos", "meses"), [(0, 1), (2, 0), (1, -1)])
def test_vencimientos_parametros_invalidos(plazos, meses):
    with pytest.raises(ValueError):
        vencimientos(date(2026, 1, 1), plazos=plazos, meses_entre_plazos=meses)

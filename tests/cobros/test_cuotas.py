"""T2.2 — Cálculo de las cuotas ordinarias, como funciones puras.

Reparto en dos pasos, los dos con R-REP-02 (`fincas.servicios.repartir`):
  1. El total anual del presupuesto se reparte entre los inmuebles por coeficiente.
  2. La parte anual de cada inmueble se divide en partes iguales entre los periodos.
Así cada inmueble paga en el año EXACTAMENTE su parte, y todo cuadra al céntimo.
"""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cobros.servicios import (
    cuotas_del_periodo,
    desglose_contable,
    desglose_del_periodo,
    plan_de_cuotas,
)
from fincas.servicios import repartir


def D(valor: str) -> Decimal:
    return Decimal(valor)


COEFS = {1: D("60"), 2: D("40")}


# --- Casos concretos ------------------------------------------------------------------


def test_r_rep_02_plan_mensual_exacto():
    plan = plan_de_cuotas(D("1200.00"), COEFS, periodos=12)
    assert set(plan) == set(range(1, 13))
    assert all(plan[p] == {1: D("60.00"), 2: D("40.00")} for p in plan)


def test_r_rep_02_los_centimos_sobrantes_van_a_los_primeros_periodos():
    # Inmueble 1: 100,00 € al año en 3 periodos → 33,34 + 33,33 + 33,33.
    plan = plan_de_cuotas(D("100.00"), {1: D("100")}, periodos=3)
    assert [plan[p][1] for p in (1, 2, 3)] == [D("33.34"), D("33.33"), D("33.33")]


def test_cuotas_del_periodo_coincide_con_el_plan():
    plan = plan_de_cuotas(D("1000.00"), {1: D("33.3333"), 2: D("66.6667")}, periodos=4)
    for periodo in range(1, 5):
        cuotas = cuotas_del_periodo(D("1000.00"), {1: D("33.3333"), 2: D("66.6667")}, 4, periodo)
        assert cuotas == plan[periodo]


@pytest.mark.parametrize("periodo", [0, 5, -1])
def test_periodo_fuera_de_rango(periodo):
    with pytest.raises(ValueError):
        cuotas_del_periodo(D("100.00"), COEFS, 4, periodo)


@pytest.mark.parametrize("periodos", [0, -1])
def test_numero_de_periodos_invalido(periodos):
    with pytest.raises(ValueError):
        plan_de_cuotas(D("100.00"), COEFS, periodos)


def test_rechaza_float():
    with pytest.raises(TypeError):
        plan_de_cuotas(100.0, COEFS, 12)


# --- Propiedades -------------------------------------------------------------------------

importes = st.integers(min_value=0, max_value=100_000_000).map(lambda c: Decimal(c) / 100)
coeficientes = st.dictionaries(
    keys=st.integers(min_value=1, max_value=500),
    values=st.integers(min_value=1, max_value=1_000_000).map(lambda n: Decimal(n) / 10_000),
    min_size=1,
    max_size=25,
)
num_periodos = st.sampled_from([1, 2, 3, 4, 6, 12])


@given(total=importes, coefs=coeficientes, periodos=num_periodos)
def test_r_rep_02_propiedad_todo_el_plan_suma_el_total(total, coefs, periodos):
    plan = plan_de_cuotas(total, coefs, periodos)
    assert sum(sum(c.values()) for c in plan.values()) == total


@given(total=importes, coefs=coeficientes, periodos=num_periodos)
def test_r_rep_02_propiedad_cada_inmueble_paga_al_anio_su_parte_exacta(total, coefs, periodos):
    plan = plan_de_cuotas(total, coefs, periodos)
    anual = repartir(total, coefs)
    for inmueble in coefs:
        assert sum(plan[p][inmueble] for p in plan) == anual[inmueble]


@given(total=importes, coefs=coeficientes, periodos=num_periodos)
def test_r_rep_02_propiedad_las_cuotas_de_un_inmueble_difieren_como_mucho_un_centimo(
    total, coefs, periodos
):
    plan = plan_de_cuotas(total, coefs, periodos)
    for inmueble in coefs:
        cuotas = [plan[p][inmueble] for p in plan]
        assert max(cuotas) - min(cuotas) <= D("0.01")


# --- Desglose contable de lo emitido -------------------------------------------------


def test_desglose_separa_gastos_y_fondo_de_reserva():
    # Presupuesto 4.000 € de gastos + 500 € de fondo; se emiten 1.125 € (un trimestre).
    assert desglose_contable(D("1125.00"), gastos=D("4000.00"), aportacion=D("500.00")) == (
        D("1000.00"),
        D("125.00"),
    )


def test_desglose_sin_aportacion_todo_es_ingreso():
    assert desglose_contable(D("100.00"), gastos=D("400.00"), aportacion=D("0.00")) == (
        D("100.00"),
        D("0.00"),
    )


def test_desglose_solo_aportacion():
    assert desglose_contable(D("100.00"), gastos=D("0.00"), aportacion=D("400.00")) == (
        D("0.00"),
        D("100.00"),
    )


@given(emitido=importes, gastos=importes, aportacion=importes)
def test_r_rep_02_propiedad_el_desglose_cuadra(emitido, gastos, aportacion):
    if gastos + aportacion == 0:
        return
    ingreso, fondo = desglose_contable(emitido, gastos=gastos, aportacion=aportacion)
    assert ingreso + fondo == emitido
    assert ingreso >= 0 and fondo >= 0


@given(gastos=importes, aportacion=importes, coefs=coeficientes, periodos=num_periodos)
def test_r_res_01_propiedad_al_final_del_anio_el_fondo_recibe_la_aportacion_exacta(
    gastos, aportacion, coefs, periodos
):
    if gastos + aportacion == 0:
        return
    plan = plan_de_cuotas(gastos + aportacion, coefs, periodos)
    totales = {p: sum(c.values()) for p, c in plan.items()}
    desgloses = [
        desglose_del_periodo(totales, p, gastos=gastos, aportacion=aportacion) for p in plan
    ]
    assert sum(i for i, _ in desgloses) == gastos
    assert sum(f for _, f in desgloses) == aportacion
    assert all(i >= 0 and f >= 0 for i, f in desgloses)
    assert all(i + f == totales[p] for (i, f), p in zip(desgloses, plan, strict=True))

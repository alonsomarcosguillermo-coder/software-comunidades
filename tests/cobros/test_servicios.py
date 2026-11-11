"""T2.1 — Fondo de reserva (R-RES-01) y totales del presupuesto, como funciones puras.

R-RES-01: la comunidad debe tener un fondo de reserva no inferior al 10 % de su último
presupuesto ordinario (art. 9.1.f LPH).
"""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cobros.servicios import estado_fondo_reserva, minimo_fondo_reserva, total_partidas


def D(valor: str) -> Decimal:
    return Decimal(valor)


# Importes en euros con céntimos, de 0 a 10 millones.
importes = st.integers(min_value=0, max_value=1_000_000_000).map(lambda c: Decimal(c) / 100)


# --- Mínimo del fondo de reserva --------------------------------------------------------


def test_r_res_01_minimo_es_el_10_por_ciento():
    assert minimo_fondo_reserva(D("12000.00")) == D("1200.00")


def test_r_res_01_minimo_redondea_hacia_arriba_al_centimo():
    # 10 % de 1234,51 = 123,451 → 123,46: redondear a 123,45 dejaría el fondo por DEBAJO
    # del mínimo legal ("no inferior al 10 %").
    assert minimo_fondo_reserva(D("1234.51")) == D("123.46")


def test_r_res_01_minimo_de_presupuesto_cero_es_cero():
    assert minimo_fondo_reserva(D("0.00")) == D("0.00")


def test_r_res_01_minimo_rechaza_float():
    with pytest.raises(TypeError):
        minimo_fondo_reserva(1200.0)


def test_r_res_01_minimo_rechaza_presupuesto_negativo():
    with pytest.raises(ValueError):
        minimo_fondo_reserva(D("-1.00"))


@given(importes)
def test_r_res_01_propiedad_minimo_nunca_inferior_al_10_por_ciento_exacto(presupuesto):
    minimo = minimo_fondo_reserva(presupuesto)
    assert minimo >= presupuesto / 10
    assert minimo - presupuesto / 10 < D("0.01")  # y como mucho un céntimo por encima
    assert minimo == minimo.quantize(D("0.01"))


# --- Estado del fondo -----------------------------------------------------------------


def test_r_res_01_fondo_suficiente_cumple():
    estado = estado_fondo_reserva(saldo=D("1500.00"), presupuesto=D("12000.00"))
    assert estado.cumple
    assert estado.minimo == D("1200.00")
    assert estado.faltante == D("0.00")


def test_r_res_01_fondo_exactamente_en_el_minimo_cumple():
    assert estado_fondo_reserva(saldo=D("1200.00"), presupuesto=D("12000.00")).cumple


def test_r_res_01_fondo_insuficiente_indica_cuanto_falta():
    estado = estado_fondo_reserva(saldo=D("1199.99"), presupuesto=D("12000.00"))
    assert not estado.cumple
    assert estado.faltante == D("0.01")


def test_r_res_01_fondo_con_saldo_negativo_falta_todo_y_mas():
    estado = estado_fondo_reserva(saldo=D("-100.00"), presupuesto=D("1000.00"))
    assert estado.faltante == D("200.00")


def test_r_res_01_estado_rechaza_float():
    with pytest.raises(TypeError):
        estado_fondo_reserva(saldo=100.0, presupuesto=D("1000.00"))


@given(saldo=importes, presupuesto=importes)
def test_r_res_01_propiedad_saldo_mas_faltante_alcanza_el_minimo(saldo, presupuesto):
    estado = estado_fondo_reserva(saldo=saldo, presupuesto=presupuesto)
    assert estado.faltante >= 0
    assert estado.cumple == (estado.faltante == 0)
    assert saldo + estado.faltante >= estado.minimo
    if not estado.cumple:
        assert saldo + estado.faltante == estado.minimo  # falta lo justo, ni un céntimo más


# --- Total de partidas ------------------------------------------------------------------


def test_total_partidas_suma_exacta():
    assert total_partidas([D("2160.00"), D("900.50"), D("0.10"), D("0.20")]) == D("3060.80")


def test_total_partidas_sin_partidas_es_cero():
    assert total_partidas([]) == D("0.00")


def test_total_partidas_rechaza_float():
    with pytest.raises(TypeError):
        total_partidas([D("1.00"), 0.1])

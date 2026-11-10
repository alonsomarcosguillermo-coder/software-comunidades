"""T1.3 — Reparto de un importe según coeficientes (R-REP-02).

R-REP-02: se trunca cada parte a céntimos y los céntimos sobrantes se dan uno a uno a los
inmuebles con mayor parte decimal descartada (método del resto mayor). Empates: por orden
de identificador. La suma siempre cuadra.

Además de casos concretos calculados a mano, se usan tests de propiedades (hypothesis):
en vez de escribir ejemplos, se describe qué debe cumplirse SIEMPRE y la librería genera
cientos de entradas aleatorias buscando una que lo incumpla.
"""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fincas.servicios import repartir


def D(valor: str) -> Decimal:
    return Decimal(valor)


# --- Casos concretos -----------------------------------------------------------


def test_r_rep_02_reparto_exacto_sin_sobrantes():
    assert repartir(D("100.00"), {1: D("60"), 2: D("40")}) == {1: D("60.00"), 2: D("40.00")}


def test_r_rep_02_tercios_el_centimo_sobrante_va_al_primer_identificador():
    # 100 / 3 = 33,333... → 33,33 cada uno (suman 99,99). Sobra 1 céntimo; los tres restos
    # empatan, así que va al de menor identificador.
    assert repartir(D("100.00"), {3: D("1"), 1: D("1"), 2: D("1")}) == {
        1: D("33.34"),
        2: D("33.33"),
        3: D("33.33"),
    }


def test_r_rep_02_el_sobrante_va_al_mayor_resto_no_al_mayor_coeficiente():
    # 10,00 € entre coeficientes 50 / 30 / 20 de un total de 100... da exacto. Usamos 10,01 €:
    #   1: 5,005 → 5,00 (resto 0,5 cént.)
    #   2: 3,003 → 3,00 (resto 0,3 cént.)
    #   3: 2,002 → 2,00 (resto 0,2 cént.)
    # Sobra 1 céntimo → al 1 (mayor resto).
    assert repartir(D("10.01"), {1: D("50"), 2: D("30"), 3: D("20")}) == {
        1: D("5.01"),
        2: D("3.00"),
        3: D("2.00"),
    }
    # Con 10,02 € los restos son 1,0 / 0,6 / 0,4 céntimos: 1 → 5,01 exacto (sin resto),
    # 2 → 3,006 (resto 0,6), 3 → 2,004 (resto 0,4). Sobra 1 céntimo → al 2, aunque el 1
    # tiene más coeficiente.
    assert repartir(D("10.02"), {1: D("50"), 2: D("30"), 3: D("20")}) == {
        1: D("5.01"),
        2: D("3.01"),
        3: D("2.00"),
    }


def test_r_rep_02_coeficientes_que_no_suman_100_se_reparten_en_proporcion():
    # Un grupo de reparto (R-REP-01) usa solo algunos inmuebles: el reparto es proporcional
    # a la suma de sus coeficientes, sea cual sea.
    assert repartir(D("90.00"), {1: D("12.5"), 2: D("25")}) == {1: D("30.00"), 2: D("60.00")}


def test_r_rep_02_importe_cero():
    assert repartir(D("0.00"), {1: D("50"), 2: D("50")}) == {1: D("0.00"), 2: D("0.00")}


def test_r_rep_02_importe_negativo_es_simetrico():
    # Un abono se reparte igual que un cargo, con el signo cambiado.
    assert repartir(D("-100.00"), {1: D("1"), 2: D("1"), 3: D("1")}) == {
        1: D("-33.34"),
        2: D("-33.33"),
        3: D("-33.33"),
    }


def test_r_rep_02_un_solo_inmueble_se_lleva_todo():
    assert repartir(D("123.45"), {7: D("3.1416")}) == {7: D("123.45")}


def test_r_rep_02_importe_menor_que_numero_de_inmuebles():
    # 2 céntimos entre 3: dos reciben 1 céntimo y uno nada.
    assert repartir(D("0.02"), {1: D("1"), 2: D("1"), 3: D("1")}) == {
        1: D("0.01"),
        2: D("0.01"),
        3: D("0.00"),
    }


def test_r_rep_02_las_partes_tienen_dos_decimales():
    for parte in repartir(D("100"), {1: D("1"), 2: D("2")}).values():
        assert parte.as_tuple().exponent == -2


# --- Entradas inválidas ----------------------------------------------------------


def test_r_rep_02_importe_con_fracciones_de_centimo_no_valido():
    with pytest.raises(ValueError, match="céntimo"):
        repartir(D("10.005"), {1: D("1")})


def test_r_rep_02_sin_coeficientes_no_valido():
    with pytest.raises(ValueError, match="ningún"):
        repartir(D("10.00"), {})


@pytest.mark.parametrize("malo", [D("0"), D("-1")])
def test_r_rep_02_coeficiente_no_positivo_no_valido(malo):
    with pytest.raises(ValueError, match="mayor que 0"):
        repartir(D("10.00"), {1: D("1"), 2: malo})


@pytest.mark.parametrize(
    ("importe", "coeficientes"),
    [(10.0, {1: D("1")}), (D("10"), {1: 1.0}), (10, {1: D("1")})],
)
def test_r_rep_02_solo_acepta_decimal(importe, coeficientes):
    with pytest.raises(TypeError):
        repartir(importe, coeficientes)


# --- Propiedades (hypothesis) ----------------------------------------------------

importes = st.decimals(
    min_value=D("-1000000.00"), max_value=D("1000000.00"), places=2, allow_nan=False
)
coeficientes = st.dictionaries(
    keys=st.integers(min_value=1, max_value=10_000),
    values=st.decimals(min_value=D("0.0001"), max_value=D("100"), places=4),
    min_size=1,
    max_size=60,
)


@given(importes, coeficientes)
def test_r_rep_02_la_suma_siempre_cuadra_al_centimo(importe, coefs):
    partes = repartir(importe, coefs)
    assert sum(partes.values()) == importe
    assert partes.keys() == coefs.keys()


@given(importes, coeficientes)
def test_r_rep_02_cada_parte_dista_menos_de_un_centimo_de_la_exacta(importe, coefs):
    total = sum(coefs.values())
    for clave, parte in repartir(importe, coefs).items():
        exacta = importe * coefs[clave] / total
        assert abs(parte - exacta) < D("0.01")


@given(importes, coeficientes)
def test_r_rep_02_a_mas_coeficiente_nunca_menos_cuota(importe, coefs):
    partes = repartir(abs(importe), coefs)
    for a in coefs:
        for b in coefs:
            if coefs[a] > coefs[b]:
                assert partes[a] >= partes[b]


@given(importes, coeficientes)
def test_r_rep_02_es_determinista_y_no_depende_del_orden(importe, coefs):
    al_reves = dict(reversed(list(coefs.items())))
    assert repartir(importe, coefs) == repartir(importe, al_reves)


@given(importes, coeficientes)
def test_r_rep_02_signo_simetrico(importe, coefs):
    negativas = {k: -v for k, v in repartir(importe, coefs).items()}
    assert repartir(-importe, coefs) == negativas

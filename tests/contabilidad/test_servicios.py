"""T1.4 — Partida doble: comprobación de cuadre como función pura (sin base de datos).

Regla de CLAUDE.md: en cada asiento, la suma del Debe es igual a la del Haber.
"""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from contabilidad.servicios import AsientoInvalido, Linea, comprobar_cuadre, invertir


def D(valor: str) -> Decimal:
    return Decimal(valor)


def test_asiento_cuadrado_es_valido():
    comprobar_cuadre([Linea("572", debe=D("100.00")), Linea("430", haber=D("100.00"))])


def test_asiento_con_varias_lineas_por_lado():
    comprobar_cuadre(
        [
            Linea("622", debe=D("70.00")),
            Linea("628", debe=D("30.00")),
            Linea("572", haber=D("100.00")),
        ]
    )


def test_asiento_descuadrado_no_es_valido():
    with pytest.raises(AsientoInvalido, match="descuadrado"):
        comprobar_cuadre([Linea("572", debe=D("100.00")), Linea("430", haber=D("99.99"))])


def test_asiento_necesita_al_menos_dos_lineas():
    with pytest.raises(AsientoInvalido, match="dos"):
        comprobar_cuadre([Linea("572", debe=D("0.01"))])


@pytest.mark.parametrize(
    "linea",
    [
        Linea("572"),  # ni debe ni haber
        Linea("572", debe=D("1.00"), haber=D("1.00")),  # los dos a la vez
    ],
)
def test_cada_linea_va_al_debe_o_al_haber(linea):
    with pytest.raises(AsientoInvalido, match="Debe o en el Haber"):
        comprobar_cuadre([linea, Linea("430", haber=D("1.00"))])


def test_importes_negativos_no_validos():
    # Un importe "negativo" se expresa poniéndolo en el lado contrario.
    with pytest.raises(AsientoInvalido, match="negativ"):
        comprobar_cuadre([Linea("572", debe=D("-1.00")), Linea("430", debe=D("1.00"))])


def test_fracciones_de_centimo_no_validas():
    with pytest.raises(AsientoInvalido, match="céntimo"):
        comprobar_cuadre([Linea("572", debe=D("1.005")), Linea("430", haber=D("1.005"))])


def test_solo_decimal():
    with pytest.raises(TypeError):
        comprobar_cuadre([Linea("572", debe=1.0), Linea("430", haber=1.0)])


def test_invertir_cambia_debe_por_haber():
    lineas = [Linea("572", debe=D("100.00"), concepto="x"), Linea("430", haber=D("100.00"))]
    assert invertir(lineas) == [
        Linea("572", haber=D("100.00"), concepto="x"),
        Linea("430", debe=D("100.00")),
    ]


importes = st.decimals(min_value=D("0.01"), max_value=D("1000000.00"), places=2)


@given(st.lists(importes, min_size=1, max_size=20))
def test_un_asiento_cuadrado_invertido_sigue_cuadrado(cargos):
    lineas = [Linea(f"6{i}", debe=c) for i, c in enumerate(cargos)]
    lineas.append(Linea("572", haber=sum(cargos)))
    comprobar_cuadre(lineas)
    comprobar_cuadre(invertir(lineas))

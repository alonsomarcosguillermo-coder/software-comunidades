"""T2.3 — R-REP-01: coeficientes de un grupo de reparto, como función pura."""

from decimal import Decimal

import pytest

from fincas.servicios import GrupoInvalido, coeficientes_de_grupo


def D(valor: str) -> Decimal:
    return Decimal(valor)


def test_r_rep_01_sin_coeficientes_propios_usa_los_generales():
    # Grupo "ascensor" sin los locales: los pisos pagan en proporción a su coeficiente general.
    miembros = [(1, D("30"), None), (2, D("20"), None)]
    assert coeficientes_de_grupo(miembros) == {1: D("30"), 2: D("20")}


def test_r_rep_01_con_coeficientes_propios_usa_los_del_grupo():
    miembros = [(1, D("30"), D("50")), (2, D("20"), D("50"))]
    assert coeficientes_de_grupo(miembros) == {1: D("50"), 2: D("50")}


def test_r_rep_01_no_se_mezclan_coeficientes_propios_y_generales():
    # Mezclarlos daría proporciones sin sentido (unos en % del edificio, otros del grupo).
    with pytest.raises(GrupoInvalido, match="todos o ninguno"):
        coeficientes_de_grupo([(1, D("30"), D("50")), (2, D("20"), None)])


def test_r_rep_01_un_grupo_vacio_no_sirve_para_repartir():
    with pytest.raises(GrupoInvalido, match="ningún inmueble"):
        coeficientes_de_grupo([])


@pytest.mark.parametrize("propio", [D("0"), D("-1")])
def test_r_rep_01_coeficiente_propio_positivo(propio):
    with pytest.raises(GrupoInvalido, match="mayor que 0"):
        coeficientes_de_grupo([(1, D("30"), propio), (2, D("20"), D("10"))])


def test_coeficientes_deben_ser_decimal():
    with pytest.raises(TypeError):
        coeficientes_de_grupo([(1, 30.0, None)])
    with pytest.raises(TypeError):
        coeficientes_de_grupo([(1, D("30"), 50.0)])

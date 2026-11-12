"""T4.3 — Piezas puras de la celebración: votantes, convocatoria aplicable y plazo R-MAY-05."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from juntas.servicios import (
    ConvocatoriaInvalida,
    InmuebleConTitulares,
    convocatoria_aplicable,
    plazo_ausentes_vencido,
    votantes,
)


def D(valor) -> Decimal:
    return Decimal(str(valor))


# --- Votantes ------------------------------------------------------------------------------


def test_cada_propietario_vota_con_la_suma_de_sus_inmuebles():
    # Pablo tiene un piso y una plaza de garaje: cuenta una vez, con 22,5 + 2.
    inmuebles = [
        InmuebleConTitulares(1, D("22.5"), ("Pablo",)),
        InmuebleConTitulares(2, D("2"), ("Pablo",)),
        InmuebleConTitulares(3, D("75.5"), ("Carmen",)),
    ]
    assert votantes(inmuebles) == {"Pablo": D("24.5"), "Carmen": D("75.5")}


def test_cotitulares_votan_con_un_representante():
    # Art. 15.1 LPH: el inmueble en proindiviso vota por medio de un representante. Por
    # defecto, el primero de la lista (la lista viene ordenada por nombre).
    inmuebles = [
        InmuebleConTitulares(1, D(50), ("Benito", "Berta")),
        InmuebleConTitulares(2, D(50), ("Ana",)),
    ]
    assert votantes(inmuebles) == {"Benito": D(50), "Ana": D(50)}


def test_el_representante_de_un_inmueble_se_puede_elegir():
    inmuebles = [
        InmuebleConTitulares(1, D(50), ("Benito", "Berta")),
        InmuebleConTitulares(2, D(50), ("Ana",)),
    ]
    assert votantes(inmuebles, representantes={1: "Berta"}) == {"Berta": D(50), "Ana": D(50)}


def test_el_representante_tiene_que_ser_titular():
    inmuebles = [InmuebleConTitulares(1, D(100), ("Benito", "Berta"))]
    with pytest.raises(ValueError):
        votantes(inmuebles, representantes={1: "Ana"})


def test_inmuebles_sin_titular_no_votan():
    inmuebles = [InmuebleConTitulares(1, D(60), ("Ana",)), InmuebleConTitulares(2, D(40), ())]
    assert votantes(inmuebles) == {"Ana": D(60)}


@given(
    st.lists(
        st.tuples(
            st.decimals(min_value=D("0.0001"), max_value=D(50), places=4),
            st.lists(st.sampled_from("ABCDE"), min_size=1, max_size=3, unique=True),
        ),
        max_size=10,
    )
)
def test_propiedad_las_cuotas_se_conservan(filas):
    inmuebles = [
        InmuebleConTitulares(n, cuota, tuple(sorted(titulares)))
        for n, (cuota, titulares) in enumerate(filas)
    ]
    assert sum(votantes(inmuebles).values(), D(0)) == sum((c for c, _ in filas), D(0))


# --- Convocatoria aplicable (R-JUN-03) -----------------------------------------------------

PRIMERA = datetime(2026, 3, 10, 19, 0)
SEGUNDA = PRIMERA + timedelta(minutes=30)


def test_con_quorum_es_primera_convocatoria():
    assert convocatoria_aplicable(PRIMERA, PRIMERA, SEGUNDA, hay_quorum=True) == 1


def test_sin_quorum_se_espera_a_la_segunda():
    with pytest.raises(ConvocatoriaInvalida, match="segunda convocatoria"):
        convocatoria_aplicable(PRIMERA + timedelta(minutes=10), PRIMERA, SEGUNDA, hay_quorum=False)


def test_sin_quorum_a_la_hora_de_la_segunda():
    assert convocatoria_aplicable(SEGUNDA, PRIMERA, SEGUNDA, hay_quorum=False) == 2


def test_sin_quorum_ni_segunda_convocatoria_no_se_celebra():
    with pytest.raises(ConvocatoriaInvalida, match="no tenía segunda"):
        convocatoria_aplicable(SEGUNDA, PRIMERA, None, hay_quorum=False)


def test_no_se_empieza_antes_de_la_hora():
    with pytest.raises(ConvocatoriaInvalida, match="antes de la hora"):
        convocatoria_aplicable(PRIMERA - timedelta(minutes=1), PRIMERA, SEGUNDA, hay_quorum=True)


# --- R-MAY-05: plazo de 30 días naturales ---------------------------------------------------


def test_r_may_05_dentro_del_plazo_no_se_computan_los_ausentes():
    # Notificados el 1/4: pueden discrepar hasta el 1/5 (30 días naturales).
    assert not plazo_ausentes_vencido(date(2026, 4, 1), date(2026, 5, 1))


def test_r_may_05_pasado_el_plazo_si():
    assert plazo_ausentes_vencido(date(2026, 4, 1), date(2026, 5, 2))


def test_r_may_05_sin_notificar_no_corre_el_plazo():
    assert not plazo_ausentes_vencido(None, date(2027, 1, 1))

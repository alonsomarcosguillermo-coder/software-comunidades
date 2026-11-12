"""T4.1 — Plazos de la convocatoria: R-JUN-02 (antelación) y R-JUN-03 (segunda convocatoria).
Funciones puras."""

from datetime import date, datetime, timedelta

import pytest

from juntas.servicios import (
    ANTELACION_ORDINARIA,
    ConvocatoriaInvalida,
    comprobar_antelacion,
    comprobar_segunda_convocatoria,
    fecha_minima_ordinaria,
)

CITACION = date(2026, 3, 1)


# --- R-JUN-02: antelación ------------------------------------------------------------------


def test_r_jun_02_ordinaria_con_seis_dias_completos_de_antelacion():
    # Citada el 1/3: los días 2, 3, 4, 5, 6 y 7 son los seis días completos; junta el 8.
    comprobar_antelacion(ordinaria=True, citacion=CITACION, junta=date(2026, 3, 8))


def test_r_jun_02_ordinaria_con_menos_antelacion_se_rechaza():
    with pytest.raises(ConvocatoriaInvalida, match="R-JUN-02"):
        comprobar_antelacion(ordinaria=True, citacion=CITACION, junta=date(2026, 3, 7))


def test_r_jun_02_fecha_minima_de_la_ordinaria():
    assert ANTELACION_ORDINARIA == 6
    assert fecha_minima_ordinaria(CITACION) == date(2026, 3, 8)


def test_r_jun_02_extraordinaria_basta_que_sea_despues_de_la_citacion():
    # La ley pide la antelación "posible" para que llegue a todos: no fija días.
    comprobar_antelacion(ordinaria=False, citacion=CITACION, junta=date(2026, 3, 2))


def test_r_jun_02_extraordinaria_el_mismo_dia_se_rechaza():
    with pytest.raises(ConvocatoriaInvalida, match="posterior"):
        comprobar_antelacion(ordinaria=False, citacion=CITACION, junta=CITACION)


@pytest.mark.parametrize("dias", range(0, 20))
def test_r_jun_02_la_fecha_minima_es_el_limite_exacto(dias):
    junta = CITACION + timedelta(days=dias)
    if junta >= fecha_minima_ordinaria(CITACION):
        comprobar_antelacion(ordinaria=True, citacion=CITACION, junta=junta)
    else:
        with pytest.raises(ConvocatoriaInvalida):
            comprobar_antelacion(ordinaria=True, citacion=CITACION, junta=junta)


# --- R-JUN-03: segunda convocatoria -------------------------------------------------------

PRIMERA = datetime(2026, 3, 10, 19, 0)


def test_r_jun_03_sin_segunda_convocatoria():
    comprobar_segunda_convocatoria(PRIMERA, None)


def test_r_jun_03_media_hora_despues_el_mismo_dia():
    comprobar_segunda_convocatoria(PRIMERA, PRIMERA + timedelta(minutes=30))


def test_r_jun_03_menos_de_media_hora_se_rechaza():
    with pytest.raises(ConvocatoriaInvalida, match="R-JUN-03"):
        comprobar_segunda_convocatoria(PRIMERA, PRIMERA + timedelta(minutes=29))


def test_r_jun_03_antes_que_la_primera_se_rechaza():
    with pytest.raises(ConvocatoriaInvalida):
        comprobar_segunda_convocatoria(PRIMERA, PRIMERA - timedelta(hours=1))

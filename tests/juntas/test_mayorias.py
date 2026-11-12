"""T4.2 — Cálculo de mayorías: R-MAY-01..05, R-VOT-01 y quórum (R-JUN-03). Funciones puras.

Casos con números pequeños y redondos para que se puedan comprobar a mano, y propiedades con
hypothesis para lo que debe cumplirse siempre.
"""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from juntas.mayorias import (
    Mayoria,
    Sentido,
    Voto,
    calcular,
    hay_quorum_primera,
)

F, C, A, X = Sentido.FAVOR, Sentido.CONTRA, Sentido.ABSTENCION, Sentido.AUSENTE


def D(valor) -> Decimal:
    return Decimal(str(valor))


def votos(*filas) -> list[Voto]:
    """filas: (cuota, sentido) o (cuota, sentido, {opciones})."""
    resultado = []
    for n, fila in enumerate(filas, start=1):
        cuota, sentido, *opciones = fila
        resultado.append(Voto(votante=n, cuota=D(cuota), sentido=sentido, **(opciones or [{}])[0]))
    return resultado


def aprobado(lista, mayoria, *, segunda=False, ausentes=False) -> bool:
    return calcular(
        lista, mayoria, segunda_convocatoria=segunda, computar_ausentes=ausentes
    ).aprobado


# --- R-MAY-01: doble mayoría ---------------------------------------------------------------


def test_r_may_01_mayoria_de_propietarios_sin_mayoria_de_cuotas_no_basta():
    # 3 de 4 propietarios a favor, pero solo el 30 % de las cuotas.
    lista = votos((10, F), (10, F), (10, F), (70, C))
    assert not aprobado(lista, Mayoria.SIMPLE)


def test_r_may_01_mayoria_de_cuotas_sin_mayoria_de_propietarios_no_basta():
    # El 70 % de las cuotas, pero 1 de 4 propietarios.
    lista = votos((70, F), (10, C), (10, C), (10, C))
    assert not aprobado(lista, Mayoria.SIMPLE)


def test_r_may_01_las_dos_mayorias():
    lista = votos((30, F), (30, F), (40, C))
    resultado = calcular(lista, Mayoria.SIMPLE, segunda_convocatoria=False, computar_ausentes=False)
    assert resultado.aprobado
    assert (resultado.favor.propietarios, resultado.favor.cuotas) == (2, D(60))
    assert (resultado.base.propietarios, resultado.base.cuotas) == (3, D(100))


# --- R-MAY-02: mayoría simple ---------------------------------------------------------------


def test_r_may_02_primera_convocatoria_cuenta_sobre_el_total():
    # 2 a favor (40 %), 1 en contra (10 %), 2 ausentes (50 %): no es mayoría del total.
    lista = votos((20, F), (20, F), (10, C), (25, X), (25, X))
    assert not aprobado(lista, Mayoria.SIMPLE)


def test_r_may_02_segunda_convocatoria_cuenta_sobre_los_presentes():
    # Mismos votos en segunda: 2 de 3 presentes y 40 de 50 puntos de cuota presentes.
    lista = votos((20, F), (20, F), (10, C), (25, X), (25, X))
    assert aprobado(lista, Mayoria.SIMPLE, segunda=True)


def test_r_may_02_la_mitad_justa_no_es_mayoria():
    lista = votos((25, F), (25, C), (25, F), (25, C))
    assert not aprobado(lista, Mayoria.SIMPLE)
    assert not aprobado(lista, Mayoria.SIMPLE, segunda=True)


def test_r_may_02_segunda_las_abstenciones_cuentan_como_presentes():
    # 2 a favor (40 %) de 5 presentes con 3 abstenciones: no es mayoría de asistentes.
    lista = votos((20, F), (20, F), (20, A), (20, A), (20, A))
    assert not aprobado(lista, Mayoria.SIMPLE, segunda=True)


def test_r_may_02_segunda_tambien_exige_mas_de_la_mitad_de_las_cuotas_presentes():
    # 2 de 3 presentes, pero 20 de 60 puntos de cuota presentes.
    lista = votos((10, F), (10, F), (40, C), (40, X))
    assert not aprobado(lista, Mayoria.SIMPLE, segunda=True)


def test_r_may_02_segunda_sin_nadie_presente():
    assert not aprobado(votos((50, X), (50, X)), Mayoria.SIMPLE, segunda=True)


# --- R-MAY-03: tres quintos --------------------------------------------------------------------


def test_r_may_03_tres_quintos_exactos_del_total():
    lista = votos((20, F), (20, F), (20, F), (20, C), (20, X))
    assert aprobado(lista, Mayoria.TRES_QUINTOS)


def test_r_may_03_por_debajo_de_tres_quintos():
    # 3 de 5 propietarios, pero 59 % de las cuotas.
    lista = votos((20, F), (20, F), (19, F), (21, C), (20, C))
    assert not aprobado(lista, Mayoria.TRES_QUINTOS)


def test_r_may_03_en_segunda_tambien_es_sobre_el_total():
    # 3 de 3 presentes, pero solo 3 de 6 propietarios: no llega.
    lista = votos((20, F), (20, F), (20, F), (15, X), (15, X), (10, X))
    assert not aprobado(lista, Mayoria.TRES_QUINTOS, segunda=True)


# --- R-MAY-04: unanimidad ----------------------------------------------------------------------


def test_r_may_04_unanimidad():
    assert aprobado(votos((50, F), (50, F)), Mayoria.UNANIMIDAD)


def test_r_may_04_una_abstencion_rompe_la_unanimidad():
    assert not aprobado(votos((50, F), (40, F), (10, A)), Mayoria.UNANIMIDAD)


def test_r_may_04_un_ausente_rompe_la_unanimidad_si_no_se_computa():
    assert not aprobado(votos((50, F), (40, F), (10, X)), Mayoria.UNANIMIDAD)


# --- R-MAY-05: ausentes que no discrepan --------------------------------------------------------


def test_r_may_05_ausentes_que_no_discrepan_cuentan_a_favor():
    lista = votos((50, F), (40, F), (10, X))
    resultado = calcular(
        lista, Mayoria.UNANIMIDAD, segunda_convocatoria=False, computar_ausentes=True
    )
    assert resultado.aprobado
    assert resultado.ausentes_a_favor.propietarios == 1


def test_r_may_05_un_ausente_que_discrepa_cuenta_en_contra():
    lista = votos((50, F), (40, F), (10, X, {"discrepa": True}))
    assert not aprobado(lista, Mayoria.UNANIMIDAD, ausentes=True)


def test_r_may_05_tres_quintos_con_ausentes():
    lista = votos((20, F), (20, F), (20, C), (20, X), (20, X))
    assert not aprobado(lista, Mayoria.TRES_QUINTOS)
    assert aprobado(lista, Mayoria.TRES_QUINTOS, ausentes=True)


def test_r_may_05_no_cambia_la_segunda_convocatoria_simple():
    # En segunda, la simple se cuenta sobre los presentes: los ausentes no intervienen.
    lista = votos((20, F), (20, C), (20, C), (40, X))
    assert not aprobado(lista, Mayoria.SIMPLE, segunda=True)
    assert not aprobado(lista, Mayoria.SIMPLE, segunda=True, ausentes=True)


# --- R-VOT-01: privados de voto -----------------------------------------------------------------


def test_r_vot_01_el_privado_de_voto_no_cuenta_ni_en_la_base():
    # Sin el privado (50 %), quedan 3 propietarios con 50 puntos: 2 a favor con 45 → mayoría.
    # Contándolo, no lo sería (45 de 100).
    lista = votos((30, F), (15, F), (5, C), (50, C, {"privado_de_voto": True}))
    resultado = calcular(lista, Mayoria.SIMPLE, segunda_convocatoria=False, computar_ausentes=False)
    assert resultado.aprobado
    assert (resultado.base.propietarios, resultado.base.cuotas) == (3, D(50))
    assert (resultado.privados.propietarios, resultado.privados.cuotas) == (1, D(50))


def test_r_vot_01_su_voto_no_se_cuenta_aunque_lo_emita():
    lista = votos((30, C), (20, F), (50, F, {"privado_de_voto": True}))
    assert not aprobado(lista, Mayoria.SIMPLE)


def test_r_vot_01_todos_privados_de_voto():
    lista = votos((50, F, {"privado_de_voto": True}), (50, F, {"privado_de_voto": True}))
    assert not aprobado(lista, Mayoria.SIMPLE)


# --- Explicación y recuentos -----------------------------------------------------------------


def test_explica_por_que_no_se_aprueba():
    lista = votos((10, F), (10, F), (10, F), (70, C))
    resultado = calcular(lista, Mayoria.SIMPLE, segunda_convocatoria=False, computar_ausentes=False)
    assert "cuotas" in resultado.explicacion
    assert "R-MAY-02" in resultado.explicacion


def test_recuento_por_sentido():
    lista = votos((10, F), (20, C), (30, A), (40, X))
    r = calcular(lista, Mayoria.SIMPLE, segunda_convocatoria=False, computar_ausentes=False)
    assert (r.favor.cuotas, r.contra.cuotas, r.abstencion.cuotas, r.ausentes.cuotas) == (
        D(10),
        D(20),
        D(30),
        D(40),
    )


def test_cuota_negativa_es_un_error():
    with pytest.raises(ValueError):
        Voto(votante=1, cuota=D(-1), sentido=F)


# --- Quórum de primera convocatoria (R-JUN-03) -------------------------------------------------


def test_r_jun_03_quorum_con_mayoria_de_propietarios_y_cuotas():
    assert hay_quorum_primera(votos((30, F), (30, A), (40, X)))


def test_r_jun_03_sin_mayoria_de_cuotas_no_hay_quorum():
    assert not hay_quorum_primera(votos((10, F), (10, C), (80, X)))


def test_r_jun_03_los_privados_de_voto_cuentan_para_el_quorum():
    # Pueden asistir y deliberar (art. 15.2): asisten.
    assert hay_quorum_primera(votos((30, F), (30, C, {"privado_de_voto": True}), (40, X)))


# --- Propiedades ------------------------------------------------------------------------------

_votos = st.lists(
    st.builds(
        lambda cuota, sentido, privado, discrepa: (cuota, sentido, privado, discrepa),
        st.decimals(min_value=D("0.0001"), max_value=D(50), places=4),
        st.sampled_from(list(Sentido)),
        st.booleans(),
        st.booleans(),
    ),
    min_size=1,
    max_size=12,
)


def _construir(filas) -> list[Voto]:
    return [
        Voto(votante=n, cuota=c, sentido=s, privado_de_voto=p, discrepa=d and s == X)
        for n, (c, s, p, d) in enumerate(filas)
    ]


@given(_votos, st.booleans(), st.booleans())
def test_propiedad_mayorias_ordenadas(filas, segunda, ausentes):
    """Lo que aprueba la unanimidad lo aprueban los 3/5, y lo que aprueban los 3/5 lo
    aprueba la simple en primera (y, por tanto, en segunda)."""
    lista = _construir(filas)
    unanime = aprobado(lista, Mayoria.UNANIMIDAD, segunda=segunda, ausentes=ausentes)
    tres_quintos = aprobado(lista, Mayoria.TRES_QUINTOS, segunda=segunda, ausentes=ausentes)
    simple = aprobado(lista, Mayoria.SIMPLE, ausentes=ausentes)
    assert not unanime or tres_quintos
    assert not tres_quintos or simple


@given(_votos, st.sampled_from(list(Mayoria)), st.booleans(), st.booleans(), st.data())
def test_propiedad_monotonia(filas, mayoria, segunda, ausentes, data):
    """Si un voto en contra pasa a favor, un acuerdo aprobado sigue aprobado."""
    lista = _construir(filas)
    contrarios = [i for i, v in enumerate(lista) if v.sentido == C]
    antes = aprobado(lista, mayoria, segunda=segunda, ausentes=ausentes)
    if contrarios and antes:
        i = data.draw(st.sampled_from(contrarios))
        lista[i] = Voto(
            votante=lista[i].votante,
            cuota=lista[i].cuota,
            sentido=F,
            privado_de_voto=lista[i].privado_de_voto,
        )
        assert aprobado(lista, mayoria, segunda=segunda, ausentes=ausentes)


@given(_votos, st.sampled_from(list(Mayoria)), st.booleans(), st.booleans(), st.data())
def test_propiedad_r_vot_01_el_voto_del_privado_no_influye(filas, mayoria, segunda, ausentes, data):
    lista = _construir(filas)
    privados = [i for i, v in enumerate(lista) if v.privado_de_voto]
    if privados:
        i = data.draw(st.sampled_from(privados))
        otro = data.draw(st.sampled_from(list(Sentido)))
        cambiada = list(lista)
        cambiada[i] = Voto(
            votante=lista[i].votante, cuota=lista[i].cuota, sentido=otro, privado_de_voto=True
        )
        assert aprobado(lista, mayoria, segunda=segunda, ausentes=ausentes) == aprobado(
            cambiada, mayoria, segunda=segunda, ausentes=ausentes
        )


@given(_votos)
def test_propiedad_simple_en_primera_implica_en_segunda(filas):
    lista = _construir(filas)
    if aprobado(lista, Mayoria.SIMPLE):
        assert aprobado(lista, Mayoria.SIMPLE, segunda=True)


@given(_votos, st.sampled_from(list(Mayoria)), st.booleans(), st.booleans())
def test_propiedad_los_recuentos_suman_la_base(filas, mayoria, segunda, ausentes):
    r = calcular(
        _construir(filas), mayoria, segunda_convocatoria=segunda, computar_ausentes=ausentes
    )
    total = r.favor.cuotas + r.contra.cuotas + r.abstencion.cuotas + r.ausentes.cuotas
    assert total + r.privados.cuotas == sum(c for c, *_ in filas)


def test_las_mayorias_coinciden_con_las_del_orden_del_dia():
    from juntas.models import PuntoOrden

    con_votacion = set(PuntoOrden.Mayoria.values) - {PuntoOrden.Mayoria.SIN_VOTACION}
    assert con_votacion == {m.value for m in Mayoria}

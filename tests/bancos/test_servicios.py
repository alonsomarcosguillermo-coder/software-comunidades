"""T3.2 — Propuesta de conciliación automática (importe + referencia). Funciones puras."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from bancos.servicios import (
    MovimientoPendiente,
    Propuesta,
    ReciboPendiente,
    RemesaPendiente,
    contiene_referencia,
    proponer_conciliaciones,
)


def D(valor: str) -> Decimal:
    return Decimal(valor)


def mov(id, importe, *textos):
    return MovimientoPendiente(id=id, importe=D(importe), textos=textos)


def rec(id, numero, importe):
    return ReciboPendiente(id=id, referencia=f"REC-1-{numero}", importe=D(importe))


# --- Buscar una referencia en un texto ---------------------------------------------------------


def test_encuentra_la_referencia_entre_otras_palabras():
    assert contiene_referencia("TRANSF. PAGO REC-1-7 MARTA", "REC-1-7")


def test_no_confunde_una_referencia_con_otra_mas_larga():
    # REC-1-1 no es REC-1-12 ni REC-1-1-B ni XREC-1-1.
    assert not contiene_referencia("REC-1-12", "REC-1-1")
    assert not contiene_referencia("REC-1-1-B", "REC-1-1")
    assert not contiene_referencia("XREC-1-1", "REC-1-1")


def test_sin_distinguir_mayusculas():
    assert contiene_referencia("pago rec-1-7", "REC-1-7")


def test_referencia_al_final_o_con_signos_alrededor():
    assert contiene_referencia("PAGO:REC-1-7.", "REC-1-7")
    assert contiene_referencia("REC-1-7", "REC-1-7")


# --- Recibos -------------------------------------------------------------------------------


def test_un_recibo_con_su_referencia_y_su_importe():
    propuestas = proponer_conciliaciones(
        [mov(10, "45.50", "REC-1-7")], [rec(1, 7, "45.50"), rec(2, 8, "45.50")], []
    )
    assert propuestas == [Propuesta(movimiento=10, recibos=(1,))]


def test_la_referencia_puede_ir_en_los_conceptos():
    propuestas = proponer_conciliaciones(
        [mov(10, "45.50", "", "", "TRANSFERENCIA DE MARTA", "PAGO REC-1-7")],
        [rec(1, 7, "45.50")],
        [],
    )
    assert propuestas == [Propuesta(movimiento=10, recibos=(1,))]


def test_importe_distinto_no_se_concilia():
    # Pago parcial o con otro importe: lo decide una persona (conciliación manual).
    assert proponer_conciliaciones([mov(10, "45.00", "REC-1-7")], [rec(1, 7, "45.50")], []) == []


def test_sin_referencia_no_se_concilia_aunque_coincida_el_importe():
    assert (
        proponer_conciliaciones([mov(10, "45.50", "TRANSFERENCIA")], [rec(1, 7, "45.50")], []) == []
    )


def test_varios_recibos_en_una_transferencia_si_la_suma_cuadra():
    propuestas = proponer_conciliaciones(
        [mov(10, "100.00", "REC-1-7 REC-1-8")], [rec(1, 7, "45.50"), rec(2, 8, "54.50")], []
    )
    assert propuestas == [Propuesta(movimiento=10, recibos=(1, 2))]


def test_varios_recibos_que_no_suman_el_importe():
    propuestas = proponer_conciliaciones(
        [mov(10, "45.50", "REC-1-7 REC-1-8")], [rec(1, 7, "45.50"), rec(2, 8, "54.50")], []
    )
    assert propuestas == []


def test_los_cargos_no_se_concilian_con_recibos():
    assert proponer_conciliaciones([mov(10, "-45.50", "REC-1-7")], [rec(1, 7, "45.50")], []) == []


def test_recibo_reclamado_por_dos_movimientos_no_se_concilia():
    # Ambiguo (¿pagó dos veces?): mejor que lo mire una persona.
    propuestas = proponer_conciliaciones(
        [mov(10, "45.50", "REC-1-7"), mov(11, "45.50", "REC-1-7")], [rec(1, 7, "45.50")], []
    )
    assert propuestas == []


def test_referencia_de_un_recibo_ya_cobrado_no_cuenta():
    # Solo se pasan los recibos pendientes: el cobrado no está en la lista.
    assert proponer_conciliaciones([mov(10, "45.50", "REC-1-7")], [rec(2, 8, "45.50")], []) == []


# --- Remesas -------------------------------------------------------------------------------


def _remesa(total="100.00"):
    return RemesaPendiente(id=5, mensaje_id="REM1-1-20260401120000", recibos=(1, 2), total=D(total))


def test_abono_de_una_remesa_con_su_identificador_y_su_total():
    propuestas = proponer_conciliaciones(
        [mov(10, "100.00", "", "", "ABONO REMESA REM1-1-20260401120000")],
        [rec(1, 7, "45.50"), rec(2, 8, "54.50")],
        [_remesa()],
    )
    assert propuestas == [Propuesta(movimiento=10, recibos=(1, 2), remesa=5)]


def test_remesa_con_otro_importe_no_se_concilia():
    # Si el banco descuenta recibos rechazados, el abono no es el total: decide una persona.
    propuestas = proponer_conciliaciones(
        [mov(10, "54.50", "REM1-1-20260401120000")],
        [rec(1, 7, "45.50"), rec(2, 8, "54.50")],
        [_remesa()],
    )
    assert propuestas == []


def test_remesa_mencionada_junto_a_las_referencias_de_sus_recibos():
    propuestas = proponer_conciliaciones(
        [mov(10, "100.00", "REM1-1-20260401120000 REC-1-7 REC-1-8")],
        [rec(1, 7, "45.50"), rec(2, 8, "54.50")],
        [_remesa()],
    )
    assert propuestas == [Propuesta(movimiento=10, recibos=(1, 2), remesa=5)]


def test_remesa_y_recibo_en_conflicto_no_se_concilian():
    propuestas = proponer_conciliaciones(
        [mov(10, "100.00", "REM1-1-20260401120000"), mov(11, "45.50", "REC-1-7")],
        [rec(1, 7, "45.50"), rec(2, 8, "54.50")],
        [_remesa()],
    )
    assert propuestas == []


# --- Propiedades ---------------------------------------------------------------------------


@given(
    importes=st.lists(
        st.decimals(min_value=D("0.01"), max_value=D("999.99"), places=2), min_size=1, max_size=8
    ),
    pagos=st.lists(st.tuples(st.integers(0, 7), st.integers(0, 7)), max_size=8),
)
def test_propiedades(importes, pagos):
    """Cada propuesta cuadra al céntimo, ningún recibo ni movimiento se usa dos veces."""
    recibos = [rec(i, i, importe) for i, importe in enumerate(importes)]
    movimientos = []
    for n, (a, b) in enumerate(pagos):
        elegidos = {a % len(recibos), b % len(recibos)}
        total = sum(recibos[i].importe for i in elegidos)
        textos = " ".join(recibos[i].referencia for i in elegidos)
        movimientos.append(mov(100 + n, str(total), textos))
    propuestas = proponer_conciliaciones(movimientos, recibos, [])
    usados = [r for p in propuestas for r in p.recibos]
    assert len(usados) == len(set(usados))
    assert len({p.movimiento for p in propuestas}) == len(propuestas)
    por_id = {m.id: m for m in movimientos}
    for p in propuestas:
        assert sum(recibos[r].importe for r in p.recibos) == por_id[p.movimiento].importe

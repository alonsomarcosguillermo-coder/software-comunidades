"""T3.3 — Propuesta automática de devoluciones de recibos (importe + referencia). Puras."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from bancos.servicios import MovimientoPendiente, Propuesta, ReciboPendiente, proponer_devoluciones


def D(valor: str) -> Decimal:
    return Decimal(valor)


def mov(id, importe, *textos):
    return MovimientoPendiente(id=id, importe=D(importe), textos=textos)


def rec(id, numero, importe):
    return ReciboPendiente(id=id, referencia=f"REC-1-{numero}", importe=D(importe))


def test_un_cargo_con_la_referencia_y_el_importe_de_un_recibo_cobrado():
    propuestas = proponer_devoluciones(
        [mov(10, "-300.00", "DEVOLUCION RECIBO", "REC-1-7 AM04")], [rec(1, 7, "300.00")]
    )
    assert propuestas == [Propuesta(movimiento=10, recibos=(1,))]


def test_un_abono_no_es_una_devolucion():
    assert proponer_devoluciones([mov(10, "300.00", "REC-1-7")], [rec(1, 7, "300.00")]) == []


def test_importe_distinto_no_se_propone():
    # p. ej. el banco cobra la comisión en el mismo cargo: lo decide una persona.
    assert proponer_devoluciones([mov(10, "-303.50", "REC-1-7")], [rec(1, 7, "300.00")]) == []


def test_sin_referencia_no_se_propone():
    assert proponer_devoluciones([mov(10, "-300.00", "DEVOLUCION")], [rec(1, 7, "300.00")]) == []


def test_varios_recibos_devueltos_en_un_cargo():
    propuestas = proponer_devoluciones(
        [mov(10, "-700.00", "REC-1-7 REC-1-8")], [rec(1, 7, "300.00"), rec(2, 8, "400.00")]
    )
    assert propuestas == [Propuesta(movimiento=10, recibos=(1, 2))]


def test_recibo_reclamado_por_dos_cargos_no_se_propone():
    propuestas = proponer_devoluciones(
        [mov(10, "-300.00", "REC-1-7"), mov(11, "-300.00", "REC-1-7")], [rec(1, 7, "300.00")]
    )
    assert propuestas == []


def test_recibo_no_cobrado_no_se_devuelve():
    # Solo se pasan los cobrados; uno pendiente no puede devolverse.
    assert proponer_devoluciones([mov(10, "-300.00", "REC-1-7")], [rec(2, 8, "300.00")]) == []


@given(
    importes=st.lists(
        st.decimals(min_value=D("0.01"), max_value=D("999.99"), places=2), min_size=1, max_size=8
    ),
    cargos=st.lists(st.tuples(st.integers(0, 7), st.integers(0, 7)), max_size=8),
)
def test_propiedades(importes, cargos):
    """Cada propuesta cuadra al céntimo y ningún recibo se devuelve dos veces."""
    recibos = [rec(i, i, importe) for i, importe in enumerate(importes)]
    movimientos = []
    for n, (a, b) in enumerate(cargos):
        elegidos = {a % len(recibos), b % len(recibos)}
        total = sum(recibos[i].importe for i in elegidos)
        textos = " ".join(recibos[i].referencia for i in elegidos)
        movimientos.append(mov(100 + n, str(-total), textos))
    propuestas = proponer_devoluciones(movimientos, recibos)
    usados = [r for p in propuestas for r in p.recibos]
    assert len(usados) == len(set(usados))
    por_id = {m.id: m for m in movimientos}
    for p in propuestas:
        assert sum(recibos[r].importe for r in p.recibos) == -por_id[p.movimiento].importe

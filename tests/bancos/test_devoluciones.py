"""T3.3 — Devoluciones de recibos: el banco devuelve un cobro y el recibo vuelve a ser deuda."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from bancos.conciliacion import (
    ConciliacionInvalida,
    conciliar_automaticamente,
    conciliar_con_recibos,
    conciliar_devolucion,
    deshacer_conciliacion,
    recibos_pendientes,
)
from bancos.models import CobroRecibo, Devolucion
from cobros.models import Recibo
from cobros.remesas import crear_remesa
from contabilidad.models import Cuenta

from .conftest import abono, cargo, importar, recibo_de

pytestmark = pytest.mark.django_db

FEBRERO = {"desde": date(2026, 2, 1), "hasta": date(2026, 2, 28)}


def _saldo(comunidad, codigo):
    return Cuenta.objects.get(comunidad=comunidad, codigo=codigo).saldo()


def _estado(recibo):
    return Recibo.objects.get(pk=recibo.pk).estado


@pytest.fixture
def remesa_cobrada(con_recibos):
    """Remesa de 1A y 1B (con mandato) cobrada en enero por su abono, conciliado."""
    ahora = timezone.make_aware(datetime(2026, 1, 10, 12, 0))
    remesa = crear_remesa(con_recibos, date(2026, 1, 15), ahora=ahora)
    importar(con_recibos, abono(str(remesa.total), "ABONO REMESA", remesa.mensaje_id, dia=15))
    [cobro] = conciliar_automaticamente(con_recibos)
    assert cobro.remesa == remesa
    return cobro


def _devolucion_de(recibo, *textos, dia=5, mes=2):
    """Cargo de la devolución de `recibo` (por defecto, el 5 de febrero)."""
    return cargo(str(recibo.importe), "DEVOLUCION RECIBO", *textos, dia=dia, mes=mes)


# --- Manual ----------------------------------------------------------------------------------


def test_devolucion_vuelve_a_dejar_el_recibo_como_deuda(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    debe_antes = _saldo(con_recibos, "430")
    banco_antes = _saldo(con_recibos, "572")
    [movimiento] = importar(con_recibos, _devolucion_de(a1, dia=5), **FEBRERO)

    conciliacion = conciliar_devolucion(movimiento, [a1])

    assert _estado(a1) == "devuelto"
    assert a1 in recibos_pendientes(con_recibos)  # vuelve a ser deuda
    assert _estado(recibo_de(con_recibos, "1B")) == "cobrado"  # el otro sigue cobrado
    devolucion = Devolucion.objects.get()
    assert (devolucion.recibo, devolucion.cobro, devolucion.conciliacion) == (
        a1,
        remesa_cobrada,
        conciliacion,
    )
    asiento = conciliacion.asiento
    assert asiento.concepto == f"Devolución de {a1.referencia}"
    assert asiento.fecha == date(2026, 2, 5)
    # El propietario vuelve a deber el recibo y el dinero sale del banco.
    assert _saldo(con_recibos, "430") == debe_antes + a1.importe
    assert _saldo(con_recibos, "572") == banco_antes - a1.importe


def test_el_recibo_devuelto_se_puede_volver_a_cobrar(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    devolucion, transferencia = importar(
        con_recibos,
        _devolucion_de(a1, dia=5),
        abono(str(a1.importe), "TRANSFERENCIA", dia=20, mes=2),
        **FEBRERO,
    )
    conciliar_devolucion(devolucion, [a1])
    conciliar_con_recibos(transferencia, [a1])
    assert _estado(a1) == "cobrado"
    assert CobroRecibo.objects.get(recibo=a1).conciliacion.movimiento == transferencia


def test_solo_se_devuelven_recibos_cobrados(con_recibos, remesa_cobrada):
    l1 = recibo_de(con_recibos, "L1")  # sin mandato, no estaba en la remesa: sin cobrar
    [movimiento] = importar(con_recibos, _devolucion_de(l1), **FEBRERO)
    with pytest.raises(ConciliacionInvalida, match="no lo están"):
        conciliar_devolucion(movimiento, [l1])
    assert not Devolucion.objects.exists()


def test_un_abono_no_es_una_devolucion(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    [movimiento] = importar(con_recibos, abono(str(a1.importe), mes=2), **FEBRERO)
    with pytest.raises(ConciliacionInvalida, match="es un cargo"):
        conciliar_devolucion(movimiento, [a1])


def test_el_importe_tiene_que_cuadrar(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    con_comision = cargo(str(a1.importe + Decimal("3.50")), "DEVOLUCION + COMISION", mes=2)
    [movimiento] = importar(con_recibos, con_comision, **FEBRERO)
    with pytest.raises(ConciliacionInvalida, match="coincidir al céntimo"):
        conciliar_devolucion(movimiento, [a1])
    assert _estado(a1) == "cobrado"


def test_la_bd_impide_devolver_dos_veces_el_mismo_cobro(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    [movimiento] = importar(con_recibos, _devolucion_de(a1), **FEBRERO)
    conciliacion = conciliar_devolucion(movimiento, [a1])
    with pytest.raises(IntegrityError), transaction.atomic():
        Devolucion.objects.create(conciliacion=conciliacion, recibo=a1, cobro=remesa_cobrada)


# --- Automática ------------------------------------------------------------------------------


def test_automatica_concilia_la_devolucion_con_su_referencia(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    importar(
        con_recibos,
        _devolucion_de(a1, a1.referencia, "AM04 FONDOS INSUFICIENTES", dia=5),
        cargo("3.50", "COMISION DEVOLUCION", dia=5, mes=2),  # sin referencia: queda pendiente
        **FEBRERO,
    )
    [hecha] = conciliar_automaticamente(con_recibos)
    assert hecha.automatica
    assert [d.recibo for d in hecha.devoluciones.all()] == [a1]
    assert _estado(a1) == "devuelto"


def test_automatica_cobra_y_devuelve_en_el_mismo_extracto(con_recibos):
    """El abono de la remesa y su devolución llegan en el mismo fichero: primero se cobra y
    después se devuelve."""
    ahora = timezone.make_aware(datetime(2026, 1, 10, 12, 0))
    remesa = crear_remesa(con_recibos, date(2026, 1, 15), ahora=ahora)
    b1 = recibo_de(con_recibos, "1B")
    importar(
        con_recibos,
        abono(str(remesa.total), "ABONO REMESA", remesa.mensaje_id, dia=15),
        _devolucion_de(b1, b1.referencia, dia=22, mes=1),
    )
    cobro, devolucion = conciliar_automaticamente(con_recibos)
    assert cobro.remesa == remesa
    assert devolucion.devoluciones.get().recibo == b1
    assert _estado(b1) == "devuelto"
    assert _estado(recibo_de(con_recibos, "1A")) == "cobrado"


def test_automatica_no_devuelve_recibos_sin_cobrar(con_recibos):
    l1 = recibo_de(con_recibos, "L1")
    importar(con_recibos, _devolucion_de(l1, l1.referencia, mes=1))
    assert conciliar_automaticamente(con_recibos) == []


# --- Deshacer --------------------------------------------------------------------------------


def test_no_se_deshace_un_cobro_con_recibos_devueltos(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    [movimiento] = importar(con_recibos, _devolucion_de(a1), **FEBRERO)
    conciliar_devolucion(movimiento, [a1])
    with pytest.raises(ConciliacionInvalida, match="deshaz antes la devolución"):
        deshacer_conciliacion(remesa_cobrada, date(2026, 3, 1))


def test_deshacer_la_devolucion_restaura_el_cobro(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    debe_antes = _saldo(con_recibos, "430")
    [movimiento] = importar(con_recibos, _devolucion_de(a1), **FEBRERO)
    devolucion = conciliar_devolucion(movimiento, [a1])

    deshacer_conciliacion(devolucion, date(2026, 3, 1))

    assert _estado(a1) == "cobrado"
    assert CobroRecibo.objects.get(recibo=a1).conciliacion == remesa_cobrada
    assert not Devolucion.objects.exists()
    assert devolucion.asiento.esta_anulado()
    assert _saldo(con_recibos, "430") == debe_antes
    # Y ahora sí se puede deshacer el cobro de la remesa.
    deshacer_conciliacion(remesa_cobrada, date(2026, 3, 1))


def test_no_se_deshace_la_devolucion_si_el_recibo_se_volvio_a_cobrar(con_recibos, remesa_cobrada):
    a1 = recibo_de(con_recibos, "1A")
    cargo_dev, transferencia = importar(
        con_recibos, _devolucion_de(a1, dia=5), abono(str(a1.importe), dia=20, mes=2), **FEBRERO
    )
    devolucion = conciliar_devolucion(cargo_dev, [a1])
    conciliar_con_recibos(transferencia, [a1])
    with pytest.raises(ConciliacionInvalida, match="vuelto a cobrar"):
        deshacer_conciliacion(devolucion, date(2026, 3, 1))
    assert Devolucion.objects.exists()

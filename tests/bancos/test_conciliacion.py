"""T3.2 — Conciliación automática y manual con la base de datos (`bancos.conciliacion`)."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from bancos.conciliacion import (
    ConciliacionInvalida,
    conciliar_automaticamente,
    conciliar_con_cuenta,
    conciliar_con_recibos,
    deshacer_conciliacion,
)
from bancos.models import CobroRecibo, Conciliacion
from cobros.remesas import crear_remesa
from contabilidad.models import Asiento, Cuenta

from .conftest import abono, cargo, importar, recibo_de

pytestmark = pytest.mark.django_db


def _saldo(comunidad, codigo):
    return Cuenta.objects.get(comunidad=comunidad, codigo=codigo).saldo()


# --- Conciliar con recibos (manual) ----------------------------------------------------------


def test_cobra_un_recibo_con_su_asiento(con_recibos):
    recibo = recibo_de(con_recibos, "L1")
    [movimiento] = importar(con_recibos, abono(str(recibo.importe), "TRANSFERENCIA L1"))
    pendiente_430 = _saldo(con_recibos, "430")

    conciliacion = conciliar_con_recibos(movimiento, [recibo])

    assert recibo.__class__.objects.get(pk=recibo.pk).estado == "cobrado"
    assert not conciliacion.automatica
    asiento = conciliacion.asiento
    assert asiento.fecha == movimiento.fecha_operacion
    assert asiento.total_debe() == asiento.total_haber() == recibo.importe
    assert asiento.concepto == f"Cobro de {recibo.referencia}"
    # 572 sube lo cobrado y lo que deben los propietarios (430) baja lo mismo.
    assert _saldo(con_recibos, "572") == recibo.importe
    assert _saldo(con_recibos, "430") == pendiente_430 - recibo.importe


def test_varios_recibos_en_un_movimiento(con_recibos):
    recibos = [recibo_de(con_recibos, "1A"), recibo_de(con_recibos, "L1")]
    total = sum(r.importe for r in recibos)
    [movimiento] = importar(con_recibos, abono(str(total)))
    conciliacion = conciliar_con_recibos(movimiento, recibos)
    assert conciliacion.cobros.count() == 2
    assert conciliacion.asiento.apuntes.filter(cuenta__codigo="430").count() == 2


def test_la_suma_tiene_que_cuadrar_al_centimo(con_recibos):
    recibo = recibo_de(con_recibos, "L1")
    [movimiento] = importar(con_recibos, abono(str(recibo.importe - Decimal("0.01"))))
    with pytest.raises(ConciliacionInvalida, match="coincidir al céntimo"):
        conciliar_con_recibos(movimiento, [recibo])
    assert not Conciliacion.objects.exists()
    assert not Asiento.objects.filter(concepto__startswith="Cobro").exists()


def test_un_cargo_no_paga_recibos(con_recibos):
    recibo = recibo_de(con_recibos, "L1")
    [movimiento] = importar(con_recibos, cargo(str(recibo.importe)))
    with pytest.raises(ConciliacionInvalida, match="abonos"):
        conciliar_con_recibos(movimiento, [recibo])


def test_un_recibo_no_se_cobra_dos_veces(con_recibos):
    recibo = recibo_de(con_recibos, "L1")
    uno, otro = importar(con_recibos, abono(str(recibo.importe)), abono(str(recibo.importe)))
    conciliar_con_recibos(uno, [recibo])
    with pytest.raises(ConciliacionInvalida, match="ya están cobrados"):
        conciliar_con_recibos(otro, [recibo])


def test_la_base_de_datos_impide_cobrar_dos_veces_un_recibo(con_recibos):
    recibo = recibo_de(con_recibos, "L1")
    [movimiento] = importar(con_recibos, abono(str(recibo.importe)))
    conciliacion = conciliar_con_recibos(movimiento, [recibo])
    with pytest.raises(IntegrityError), transaction.atomic():
        CobroRecibo.objects.create(conciliacion=conciliacion, recibo=recibo)


def test_un_movimiento_no_se_concilia_dos_veces(con_recibos):
    recibo = recibo_de(con_recibos, "L1")
    [movimiento] = importar(con_recibos, abono(str(recibo.importe)))
    conciliar_con_recibos(movimiento, [recibo])
    with pytest.raises(ConciliacionInvalida, match="ya está conciliado"):
        conciliar_con_cuenta(movimiento, Cuenta.objects.get(codigo="628"))


def test_recibos_de_otra_comunidad(con_recibos, despacho_a):
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(despacho=despacho_a, nombre="Otra", iban_cobros="")
    recibo = recibo_de(con_recibos, "L1")
    recibo.comunidad_id = otra.pk  # simulado en memoria: no se guarda
    [movimiento] = importar(con_recibos, abono(str(recibo.importe)))
    with pytest.raises(ConciliacionInvalida, match="otra comunidad"):
        conciliar_con_recibos(movimiento, [recibo])


# --- Conciliar con otra cuenta ---------------------------------------------------------------


def test_un_cargo_a_una_cuenta_de_gasto(con_recibos):
    [movimiento] = importar(con_recibos, cargo("86.40", "RECIBO ELECTRICA FICTICIA SA"))
    gasto = Cuenta.objects.get(codigo="628")
    conciliacion = conciliar_con_cuenta(movimiento, gasto)
    assert conciliacion.cuenta == gasto
    assert conciliacion.asiento.concepto == "RECIBO ELECTRICA FICTICIA SA"
    assert gasto.saldo() == Decimal("86.40")  # deudor
    assert _saldo(con_recibos, "572") == Decimal("-86.40")


def test_un_abono_a_otra_cuenta(con_recibos):
    ingresos = Cuenta.objects.create(comunidad=con_recibos, codigo="769", nombre="Intereses")
    [movimiento] = importar(con_recibos, abono("1.25", "INTERESES"))
    conciliar_con_cuenta(movimiento, ingresos)
    assert ingresos.saldo() == Decimal("-1.25")  # acreedor
    assert _saldo(con_recibos, "572") == Decimal("1.25")


@pytest.mark.parametrize("codigo", ["572", "430"])
def test_no_contra_el_banco_ni_contra_propietarios(con_recibos, codigo):
    [movimiento] = importar(con_recibos, abono("10.00"))
    from cobros.emision import cuenta_por_codigo

    cuenta = cuenta_por_codigo(con_recibos, codigo, "x")
    with pytest.raises(ConciliacionInvalida, match=codigo):
        conciliar_con_cuenta(movimiento, cuenta)


def test_cuenta_de_otra_comunidad(con_recibos, despacho_b):
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(despacho=despacho_b, nombre="Otra")
    ajena = Cuenta.objects.create(comunidad=otra, codigo="628", nombre="Suministros")
    [movimiento] = importar(con_recibos, cargo("10.00"))
    with pytest.raises(ConciliacionInvalida, match="otra comunidad"):
        conciliar_con_cuenta(movimiento, ajena)


# --- Deshacer --------------------------------------------------------------------------------


def test_deshacer_anula_el_asiento_y_libera_el_recibo(con_recibos):
    recibo = recibo_de(con_recibos, "L1")
    [movimiento] = importar(con_recibos, abono(str(recibo.importe)))
    conciliacion = conciliar_con_recibos(movimiento, [recibo])
    asiento = conciliacion.asiento

    deshacer_conciliacion(conciliacion, date(2026, 2, 1))

    assert asiento.esta_anulado()  # la contabilidad conserva el asiento y su contra-asiento
    assert not Conciliacion.objects.exists()
    assert not CobroRecibo.objects.exists()
    assert recibo.__class__.objects.get(pk=recibo.pk).estado == "pendiente"
    assert _saldo(con_recibos, "572") == 0
    # Y se puede volver a conciliar.
    conciliar_con_recibos(movimiento, [recibo])


# --- Automática ------------------------------------------------------------------------------


def test_automatica_por_referencia_e_importe(con_recibos):
    l1, a1 = recibo_de(con_recibos, "L1"), recibo_de(con_recibos, "1A")
    movimientos = importar(
        con_recibos,
        abono(str(l1.importe), "TRANSFERENCIA", referencia=l1.referencia),  # encaja
        abono(str(a1.importe), "TRANSFERENCIA SIN REFERENCIA"),  # no: sin referencia
        cargo("20.00", "COMISION"),  # no: es un cargo
    )
    hechas = conciliar_automaticamente(con_recibos)
    assert [c.movimiento for c in hechas] == [movimientos[0]]
    assert hechas[0].automatica
    assert [c.recibo for c in hechas[0].cobros.all()] == [l1]


def test_automatica_de_una_remesa(con_recibos):
    ahora = timezone.make_aware(datetime(2026, 1, 10, 12, 0))
    remesa = crear_remesa(con_recibos, date(2026, 1, 15), ahora=ahora)
    importar(con_recibos, abono(str(remesa.total), "ABONO REMESA", remesa.mensaje_id))
    [hecha] = conciliar_automaticamente(con_recibos)
    assert hecha.remesa == remesa
    assert {c.recibo for c in hecha.cobros.all()} == set(remesa.recibos.all())
    assert hecha.asiento.concepto == f"Cobro de la remesa {remesa.numero}"
    assert all(r.estado == "cobrado" for r in remesa.recibos.all())


def test_automatica_es_repetible(con_recibos):
    l1 = recibo_de(con_recibos, "L1")
    importar(con_recibos, abono(str(l1.importe), referencia=l1.referencia))
    assert len(conciliar_automaticamente(con_recibos)) == 1
    assert conciliar_automaticamente(con_recibos) == []
    assert Conciliacion.objects.count() == 1


def test_automatica_no_toca_otras_comunidades(con_recibos, despacho_b):
    from fincas.models import Comunidad

    otra = Comunidad.objects.create(despacho=despacho_b, nombre="Otra", iban_cobros="")
    l1 = recibo_de(con_recibos, "L1")
    importar(con_recibos, abono(str(l1.importe), referencia=l1.referencia))
    assert conciliar_automaticamente(otra) == []
    assert not Conciliacion.objects.exists()

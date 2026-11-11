"""T2.2 — Emisión de cuotas ordinarias por periodo, con su asiento contable."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from cobros.emision import EmisionInvalida, emitir_cuotas
from cobros.models import Cuota, Emision, PresupuestoAprobado
from contabilidad.models import ContabilidadInmutable, Cuenta
from fincas.models import Inmueble

from .conftest import D

pytestmark = pytest.mark.django_db

FECHA = date(2026, 1, 5)


@pytest.fixture
def inmuebles_a(comunidad_a):
    piso = Inmueble.objects.create(
        comunidad=comunidad_a, tipo=Inmueble.Tipo.PISO, referencia="1A", coeficiente=D("60")
    )
    local = Inmueble.objects.create(
        comunidad=comunidad_a, tipo=Inmueble.Tipo.LOCAL, referencia="L1", coeficiente=D("40")
    )
    return piso, local


@pytest.fixture
def listo(aprobado_a, inmuebles_a, fondo_a):
    """Presupuesto 2026 aprobado, trimestral: 4.000 € de gastos + 500 € al fondo."""
    assert aprobado_a.periodos == 4
    return aprobado_a


def _saldo(comunidad, codigo) -> Decimal:
    return Cuenta.objects.get(comunidad=comunidad, codigo=codigo).saldo()


# --- Emisión correcta -------------------------------------------------------------------


def test_emite_una_cuota_por_inmueble_segun_coeficiente(listo, inmuebles_a):
    piso, local = inmuebles_a
    emision = emitir_cuotas(listo, 1, FECHA)
    # 4.500 € / 4 trimestres = 1.125 €; 60 % y 40 %.
    assert {c.inmueble: c.importe for c in emision.cuotas.all()} == {
        piso: D("675.00"),
        local: D("450.00"),
    }
    assert emision.total() == D("1125.00")


def test_registra_un_asiento_que_cuadra_y_separa_el_fondo(listo, inmuebles_a):
    emision = emitir_cuotas(listo, 1, FECHA)
    asiento = emision.asiento
    assert asiento.fecha == FECHA
    assert asiento.concepto == "Cuotas ordinarias 2026, periodo 1/4"
    assert asiento.total_debe() == asiento.total_haber() == D("1125.00")
    comunidad = listo.comunidad
    assert _saldo(comunidad, "430") == D("1125.00")  # lo deben los propietarios
    assert _saldo(comunidad, "705") == D("-1000.00")  # ingreso (saldo acreedor)
    assert _saldo(comunidad, "113") == D("-125.00")  # fondo de reserva (acreedor)


def test_el_asiento_tiene_una_linea_por_inmueble(listo):
    apuntes = emitir_cuotas(listo, 1, FECHA).asiento.apuntes.filter(cuenta__codigo="430")
    assert {(a.concepto, a.debe) for a in apuntes} == {("1A", D("675.00")), ("L1", D("450.00"))}


def test_crea_las_cuentas_430_y_705_si_no_existen(listo):
    assert not Cuenta.objects.filter(codigo__in=["430", "705"]).exists()
    emitir_cuotas(listo, 1, FECHA)
    assert Cuenta.objects.filter(comunidad=listo.comunidad, codigo__in=["430", "705"]).count() == 2


def test_reutiliza_las_cuentas_existentes(listo):
    propias = Cuenta.objects.create(comunidad=listo.comunidad, codigo="430", nombre="Vecinos")
    emitir_cuotas(listo, 1, FECHA)
    assert propias.apuntes.count() == 2


def test_r_rep_02_emitir_todo_el_anio_cuadra_al_centimo(comunidad_a, aprobado_a, fondo_a):
    # Coeficientes y total "incómodos": nada se divide exacto.
    for referencia, coeficiente in [("A", "33.3333"), ("B", "33.3333"), ("C", "33.3334")]:
        Inmueble.objects.create(
            comunidad=comunidad_a,
            tipo=Inmueble.Tipo.PISO,
            referencia=referencia,
            coeficiente=D(coeficiente),
        )
    for periodo in range(1, 5):
        emitir_cuotas(aprobado_a, periodo, date(2026, 3 * periodo - 2, 1))
    assert sum(e.total() for e in aprobado_a.emisiones.all()) == D("4500.00")
    assert _saldo(comunidad_a, "705") == D("-4000.00")  # exactamente los gastos
    assert _saldo(comunidad_a, "113") == D("-500.00")  # exactamente la aportación
    # Cada inmueble paga en el año exactamente su parte anual.
    anual = {
        i.referencia: sum(c.importe for c in Cuota.objects.filter(inmueble=i))
        for i in comunidad_a.inmuebles.all()
    }
    assert anual == {"A": D("1500.00"), "B": D("1500.00"), "C": D("1500.00")}


def test_presupuesto_sin_aportacion_no_necesita_cuenta_de_fondo(listo, fondo_a):
    # Otro presupuesto, sin aportación y sin usar la cuenta del fondo.
    listo.fecha_aprobacion = None
    listo.save()
    listo.aportacion_fondo_reserva = D("0.00")
    listo.fecha_aprobacion = date(2026, 1, 15)
    listo.save()
    Cuenta.objects.filter(pk=fondo_a.pk).update(es_fondo_reserva=False)
    emision = emitir_cuotas(listo, 1, FECHA)
    assert emision.total() == D("1000.00")
    assert not emision.asiento.apuntes.filter(cuenta=fondo_a).exists()


def test_inmueble_con_cuota_cero_no_genera_cuota(comunidad_a, fondo_a):
    from cobros.models import Partida, Presupuesto

    presupuesto = Presupuesto.objects.create(
        comunidad=comunidad_a, ejercicio=2026, periodos=Presupuesto.Periodicidad.MENSUAL
    )
    Partida.objects.create(presupuesto=presupuesto, concepto="Luz", importe=D("12.00"))
    presupuesto.fecha_aprobacion = date(2026, 1, 1)
    presupuesto.save()
    Inmueble.objects.create(
        comunidad=comunidad_a, tipo="piso", referencia="Grande", coeficiente=D("99.9")
    )
    Inmueble.objects.create(
        comunidad=comunidad_a, tipo="trastero", referencia="Mini", coeficiente=D("0.1")
    )
    # 12 € al año: el trastero paga 0,01 € al año → 0 € casi todos los meses.
    emision = emitir_cuotas(presupuesto, 12, FECHA)
    assert [c.inmueble.referencia for c in emision.cuotas.all()] == ["Grande"]
    assert emision.asiento.total_debe() == emision.total()


# --- Negativas ------------------------------------------------------------------------------


def _sin_cambios(presupuesto):
    assert not Emision.objects.exists()
    assert not Cuota.objects.exists()
    assert not presupuesto.comunidad.asientos.exists()


def test_r_pre_01_no_emite_si_el_presupuesto_no_esta_aprobado(presupuesto_a, inmuebles_a, fondo_a):
    with pytest.raises(EmisionInvalida, match="R-PRE-01"):
        emitir_cuotas(presupuesto_a, 1, FECHA)
    _sin_cambios(presupuesto_a)


def test_r_coef_01_no_emite_si_los_coeficientes_no_suman_100(listo, inmuebles_a):
    Inmueble.objects.filter(pk=inmuebles_a[1].pk).update(coeficiente=D("39.9999"))
    with pytest.raises(EmisionInvalida, match="R-COEF-01"):
        emitir_cuotas(listo, 1, FECHA)
    _sin_cambios(listo)


def test_r_coef_01_no_emite_si_la_comunidad_no_tiene_inmuebles(aprobado_a, fondo_a):
    with pytest.raises(EmisionInvalida, match="R-COEF-01"):
        emitir_cuotas(aprobado_a, 1, FECHA)


@pytest.mark.parametrize("periodo", [0, 5])
def test_no_emite_periodos_fuera_de_rango(listo, periodo):
    with pytest.raises(EmisionInvalida):
        emitir_cuotas(listo, periodo, FECHA)
    _sin_cambios(listo)


def test_no_emite_dos_veces_el_mismo_periodo(listo):
    emitir_cuotas(listo, 1, FECHA)
    with pytest.raises(EmisionInvalida, match="ya está emitido"):
        emitir_cuotas(listo, 1, FECHA)
    assert listo.emisiones.count() == 1
    assert listo.comunidad.asientos.count() == 1


def test_la_base_de_datos_impide_emitir_dos_veces_el_mismo_periodo(listo):
    emision = emitir_cuotas(listo, 1, FECHA)
    with pytest.raises(IntegrityError), transaction.atomic():
        Emision.objects.create(presupuesto=listo, periodo=1, fecha=FECHA, asiento=emision.asiento)


def test_r_res_01_no_emite_aportacion_sin_cuenta_de_fondo(aprobado_a, inmuebles_a):
    with pytest.raises(EmisionInvalida, match="R-RES-01"):
        emitir_cuotas(aprobado_a, 1, FECHA)
    _sin_cambios(aprobado_a)


# --- Inmutabilidad y efectos sobre el presupuesto ---------------------------------------


def test_emision_y_cuotas_son_inmutables(listo):
    emision = emitir_cuotas(listo, 1, FECHA)
    cuota = emision.cuotas.first()
    cuota.importe = D("1.00")
    with pytest.raises(ContabilidadInmutable):
        cuota.save()
    with pytest.raises(ContabilidadInmutable):
        cuota.delete()
    with pytest.raises(ContabilidadInmutable):
        Cuota.objects.update(importe=D("1.00"))
    with pytest.raises(ContabilidadInmutable):
        emision.delete()


def test_con_cuotas_emitidas_no_se_puede_quitar_la_aprobacion(listo):
    emitir_cuotas(listo, 1, FECHA)
    listo.fecha_aprobacion = None
    with pytest.raises(PresupuestoAprobado, match="cuotas emitidas"):
        listo.save()


def test_sin_cuotas_emitidas_si_se_puede_quitar_la_aprobacion(listo):
    listo.fecha_aprobacion = None
    listo.save()
    assert not listo.esta_aprobado


def test_aprobado_no_admite_cambiar_la_periodicidad(listo):
    listo.periodos = 12
    with pytest.raises(PresupuestoAprobado):
        listo.save()

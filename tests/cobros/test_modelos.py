"""T2.1 — Presupuesto ordinario y partidas en la base de datos."""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from cobros.models import Partida, Presupuesto, PresupuestoAprobado
from contabilidad.models import Cuenta

from .conftest import D

pytestmark = pytest.mark.django_db


# --- Totales ----------------------------------------------------------------------------


def test_total_gastos_es_la_suma_de_las_partidas(presupuesto_a):
    assert presupuesto_a.total_gastos() == D("4000.00")


def test_total_incluye_la_aportacion_al_fondo_de_reserva(presupuesto_a):
    assert presupuesto_a.total() == D("4500.00")


def test_presupuesto_sin_partidas_suma_cero(comunidad_a):
    presupuesto = Presupuesto.objects.create(comunidad=comunidad_a, ejercicio=2027)
    assert presupuesto.total_gastos() == D("0.00")
    assert presupuesto.total() == D("0.00")


# --- Restricciones ----------------------------------------------------------------------


def test_un_solo_presupuesto_por_comunidad_y_ejercicio(presupuesto_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        Presupuesto.objects.create(comunidad=presupuesto_a.comunidad, ejercicio=2026)


def test_la_misma_comunidad_puede_tener_presupuestos_de_varios_ejercicios(presupuesto_a):
    Presupuesto.objects.create(comunidad=presupuesto_a.comunidad, ejercicio=2027)
    assert presupuesto_a.comunidad.presupuestos.count() == 2


@pytest.mark.parametrize("importe", ["0.00", "-10.00"])
def test_la_base_de_datos_rechaza_partidas_sin_importe_positivo(presupuesto_a, importe):
    with pytest.raises(IntegrityError), transaction.atomic():
        Partida.objects.create(presupuesto=presupuesto_a, concepto="Error", importe=D(importe))


def test_la_base_de_datos_rechaza_aportacion_negativa(comunidad_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        Presupuesto.objects.create(
            comunidad=comunidad_a, ejercicio=2026, aportacion_fondo_reserva=D("-1.00")
        )


def test_conceptos_de_partida_no_se_repiten_en_un_presupuesto(presupuesto_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        Partida.objects.create(presupuesto=presupuesto_a, concepto="Luz", importe=D("1.00"))


# --- R-PRE-01: presupuesto aprobado ----------------------------------------------------


def test_r_pre_01_sin_fecha_de_aprobacion_es_borrador(presupuesto_a):
    assert not presupuesto_a.esta_aprobado


def test_r_pre_01_con_fecha_de_aprobacion_esta_aprobado(aprobado_a):
    assert aprobado_a.esta_aprobado


def test_borrador_se_puede_editar(presupuesto_a):
    partida = presupuesto_a.partidas.get(concepto="Luz")
    partida.importe = D("1600.00")
    partida.save()
    Partida.objects.create(presupuesto=presupuesto_a, concepto="Seguro", importe=D("300.00"))
    presupuesto_a.partidas.get(concepto="Limpieza").delete()
    assert presupuesto_a.total_gastos() == D("1900.00")


def test_aprobado_no_admite_partidas_nuevas(aprobado_a):
    with pytest.raises(PresupuestoAprobado):
        Partida.objects.create(presupuesto=aprobado_a, concepto="Seguro", importe=D("300.00"))


def test_aprobado_no_admite_cambiar_partidas(aprobado_a):
    partida = aprobado_a.partidas.get(concepto="Luz")
    partida.importe = D("1.00")
    with pytest.raises(PresupuestoAprobado):
        partida.save()


def test_aprobado_no_admite_borrar_partidas(aprobado_a):
    with pytest.raises(PresupuestoAprobado):
        aprobado_a.partidas.get(concepto="Luz").delete()


def test_aprobado_no_admite_cambiar_la_aportacion(aprobado_a):
    aprobado_a.aportacion_fondo_reserva = D("0.00")
    with pytest.raises(PresupuestoAprobado):
        aprobado_a.save()


def test_aprobado_no_se_puede_borrar(aprobado_a):
    with pytest.raises(PresupuestoAprobado):
        aprobado_a.delete()


def test_aprobado_no_se_puede_borrar_en_bloque(aprobado_a):
    with pytest.raises(PresupuestoAprobado):
        Presupuesto.objects.filter(pk=aprobado_a.pk).delete()
    assert Presupuesto.objects.filter(pk=aprobado_a.pk).exists()


def test_aprobado_se_puede_corregir_la_fecha_de_aprobacion(aprobado_a):
    aprobado_a.fecha_aprobacion = date(2026, 1, 20)
    aprobado_a.save()
    aprobado_a.refresh_from_db()
    assert aprobado_a.fecha_aprobacion == date(2026, 1, 20)


def test_quitando_la_aprobacion_vuelve_a_ser_editable(aprobado_a):
    aprobado_a.fecha_aprobacion = None
    aprobado_a.save()
    Partida.objects.create(presupuesto=aprobado_a, concepto="Seguro", importe=D("300.00"))
    assert aprobado_a.total_gastos() == D("4300.00")


def test_borrador_se_puede_borrar_con_sus_partidas(presupuesto_a):
    presupuesto_a.delete()
    assert not Partida.objects.exists()


# --- Último presupuesto ordinario (R-RES-01) ------------------------------------------


def test_r_res_01_ultimo_aprobado_ignora_borradores(aprobado_a):
    Presupuesto.objects.create(comunidad=aprobado_a.comunidad, ejercicio=2027)  # borrador
    assert Presupuesto.objects.ultimo_aprobado(aprobado_a.comunidad) == aprobado_a


def test_r_res_01_ultimo_aprobado_es_el_del_ejercicio_mas_reciente(aprobado_a):
    nuevo = Presupuesto.objects.create(
        comunidad=aprobado_a.comunidad, ejercicio=2027, fecha_aprobacion=date(2026, 12, 15)
    )
    assert Presupuesto.objects.ultimo_aprobado(aprobado_a.comunidad) == nuevo


def test_r_res_01_sin_presupuestos_aprobados_no_hay_ultimo(presupuesto_a):
    assert Presupuesto.objects.ultimo_aprobado(presupuesto_a.comunidad) is None


def test_r_res_01_ultimo_aprobado_no_mira_otras_comunidades(presupuesto_a, presupuesto_b):
    assert Presupuesto.objects.ultimo_aprobado(presupuesto_a.comunidad) is None


# --- Cuenta del fondo de reserva --------------------------------------------------------


def test_r_res_01_una_sola_cuenta_de_fondo_de_reserva_por_comunidad(fondo_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        Cuenta.objects.create(
            comunidad=fondo_a.comunidad, codigo="114", nombre="Otro fondo", es_fondo_reserva=True
        )


def test_r_res_01_cada_comunidad_puede_tener_su_cuenta_de_fondo(fondo_a, comunidad_b):
    Cuenta.objects.create(
        comunidad=comunidad_b, codigo="113", nombre="Fondo de reserva", es_fondo_reserva=True
    )
    assert Cuenta.objects.filter(es_fondo_reserva=True).count() == 2

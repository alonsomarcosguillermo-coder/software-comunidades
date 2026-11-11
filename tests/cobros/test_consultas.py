"""T2.1 — R-RES-01 con los datos de la base de datos: saldo del fondo según la contabilidad."""

from datetime import date

import pytest

from cobros.consultas import fondo_reserva_de, saldo_fondo_reserva
from contabilidad.registro import anular_asiento, registrar_asiento
from contabilidad.servicios import Linea

from .conftest import D

pytestmark = pytest.mark.django_db


def _dotar(comunidad, banco, fondo, importe: str, fecha=date(2026, 1, 31)):
    """Aportación al fondo: entra dinero en el banco (Debe) y crece el fondo (Haber)."""
    return registrar_asiento(
        comunidad,
        fecha,
        "Dotación al fondo de reserva",
        [Linea(banco, debe=D(importe)), Linea(fondo, haber=D(importe))],
    )


def test_r_res_01_sin_cuenta_de_fondo_no_hay_saldo(comunidad_a, banco_a):
    assert saldo_fondo_reserva(comunidad_a) is None


def test_r_res_01_cuenta_de_fondo_sin_apuntes_tiene_saldo_cero(comunidad_a, fondo_a):
    assert saldo_fondo_reserva(comunidad_a) == D("0.00")


def test_r_res_01_saldo_del_fondo_es_su_saldo_acreedor(comunidad_a, banco_a, fondo_a):
    _dotar(comunidad_a, banco_a, fondo_a, "300.00")
    _dotar(comunidad_a, banco_a, fondo_a, "150.50")
    assert saldo_fondo_reserva(comunidad_a) == D("450.50")


def test_r_res_01_saldo_del_fondo_descuenta_contra_asientos(comunidad_a, banco_a, fondo_a):
    _dotar(comunidad_a, banco_a, fondo_a, "300.00")
    anular_asiento(_dotar(comunidad_a, banco_a, fondo_a, "999.00"), date(2026, 2, 1))
    assert saldo_fondo_reserva(comunidad_a) == D("300.00")


def test_r_res_01_saldo_del_fondo_hasta_una_fecha(comunidad_a, banco_a, fondo_a):
    _dotar(comunidad_a, banco_a, fondo_a, "100.00", fecha=date(2026, 1, 31))
    _dotar(comunidad_a, banco_a, fondo_a, "200.00", fecha=date(2026, 6, 30))
    assert saldo_fondo_reserva(comunidad_a, hasta=date(2026, 3, 1)) == D("100.00")


def test_r_res_01_fondo_insuficiente_respecto_al_ultimo_presupuesto(aprobado_a, banco_a, fondo_a):
    # Gastos 4.000 € → mínimo 400 €. Hay 350 €: faltan 50 €.
    _dotar(aprobado_a.comunidad, banco_a, fondo_a, "350.00")
    fondo = fondo_reserva_de(aprobado_a.comunidad)
    assert fondo.presupuesto == aprobado_a
    assert fondo.saldo == D("350.00")
    assert not fondo.estado.cumple
    assert fondo.estado.minimo == D("400.00")
    assert fondo.estado.faltante == D("50.00")


def test_r_res_01_fondo_suficiente(aprobado_a, banco_a, fondo_a):
    _dotar(aprobado_a.comunidad, banco_a, fondo_a, "400.00")
    assert fondo_reserva_de(aprobado_a.comunidad).estado.cumple


def test_r_res_01_la_base_son_los_gastos_sin_la_aportacion(aprobado_a, fondo_a):
    # Total del presupuesto 4.500 € (incluye 500 € de aportación); la base son los 4.000 €.
    assert fondo_reserva_de(aprobado_a.comunidad).estado.minimo == D("400.00")


def test_r_res_01_sin_presupuesto_aprobado_no_se_puede_comprobar(presupuesto_a, fondo_a):
    fondo = fondo_reserva_de(presupuesto_a.comunidad)
    assert fondo.presupuesto is None
    assert fondo.estado is None


def test_r_res_01_sin_cuenta_de_fondo_no_se_puede_comprobar(aprobado_a):
    fondo = fondo_reserva_de(aprobado_a.comunidad)
    assert fondo.saldo is None
    assert fondo.estado is None

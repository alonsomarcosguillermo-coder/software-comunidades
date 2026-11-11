from datetime import date
from decimal import Decimal

import pytest

from cobros.models import Partida, Presupuesto
from contabilidad.models import Cuenta
from core.models import Despacho
from fincas.models import Comunidad

# Todos los datos de los tests son ficticios.


def D(valor: str) -> Decimal:
    return Decimal(valor)


@pytest.fixture
def despacho_a(db):
    return Despacho.objects.create(nombre="Fincas Alfa")


@pytest.fixture
def despacho_b(db):
    return Despacho.objects.create(nombre="Fincas Beta")


@pytest.fixture
def comunidad_a(despacho_a):
    return Comunidad.objects.create(despacho=despacho_a, nombre="CP Calle Ficticia 1")


@pytest.fixture
def comunidad_b(despacho_b):
    return Comunidad.objects.create(despacho=despacho_b, nombre="CP Avenida Inventada 2")


@pytest.fixture
def presupuesto_a(comunidad_a):
    """Borrador 2026: 4.000 € de gastos + 500 € al fondo de reserva."""
    presupuesto = Presupuesto.objects.create(
        comunidad=comunidad_a, ejercicio=2026, aportacion_fondo_reserva=D("500.00")
    )
    Partida.objects.create(presupuesto=presupuesto, concepto="Limpieza", importe=D("2500.00"))
    Partida.objects.create(presupuesto=presupuesto, concepto="Luz", importe=D("1500.00"))
    return presupuesto


@pytest.fixture
def aprobado_a(presupuesto_a):
    presupuesto_a.fecha_aprobacion = date(2026, 1, 15)
    presupuesto_a.save()
    return presupuesto_a


@pytest.fixture
def presupuesto_b(comunidad_b):
    presupuesto = Presupuesto.objects.create(comunidad=comunidad_b, ejercicio=2026)
    Partida.objects.create(presupuesto=presupuesto, concepto="Ascensor", importe=D("900.00"))
    presupuesto.fecha_aprobacion = date(2026, 2, 1)
    presupuesto.save()
    return presupuesto


@pytest.fixture
def banco_a(comunidad_a):
    return Cuenta.objects.create(comunidad=comunidad_a, codigo="572", nombre="Banco")


@pytest.fixture
def fondo_a(comunidad_a):
    return Cuenta.objects.create(
        comunidad=comunidad_a, codigo="113", nombre="Fondo de reserva", es_fondo_reserva=True
    )

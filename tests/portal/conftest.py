from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from cobros.emision import emitir_cuotas
from cobros.models import Partida, Presupuesto
from cobros.recibos import generar_recibos
from contabilidad.models import Cuenta
from core.models import Despacho
from fincas.models import Comunidad, Inmueble, Propietario, Titularidad

# Todos los datos son ficticios (emails de example.com).


@pytest.fixture
def despacho_a(db):
    return Despacho.objects.create(nombre="Fincas Alfa")


@pytest.fixture
def despacho_b(db):
    return Despacho.objects.create(nombre="Fincas Beta")


def _comunidad(despacho, nombre, titulares):
    """Comunidad con un piso por titular (a partes iguales), primer trimestre de 2026
    emitido el 5/1/2026 y sus recibos (vencidos y sin pagar: todos deben algo)."""
    comunidad = Comunidad.objects.create(despacho=despacho, nombre=nombre)
    cuota = Decimal(100) / len(titulares)
    for n, propietario in enumerate(titulares, start=1):
        inmueble = Inmueble.objects.create(
            comunidad=comunidad, tipo="piso", referencia=f"{n}A", coeficiente=cuota
        )
        Titularidad.objects.create(
            inmueble=inmueble, propietario=propietario, fecha_inicio=date(2020, 1, 1)
        )
    Cuenta.objects.create(comunidad=comunidad, codigo="113", nombre="F", es_fondo_reserva=True)
    presupuesto = Presupuesto.objects.create(comunidad=comunidad, ejercicio=2026)
    Partida.objects.create(presupuesto=presupuesto, concepto="Limpieza", importe=Decimal(1200))
    presupuesto.fecha_aprobacion = date(2025, 12, 1)
    presupuesto.save()
    emitir_cuotas(presupuesto, 1, date(2026, 1, 5))
    generar_recibos(comunidad)
    return comunidad


@pytest.fixture
def marta(despacho_a):
    """Vecina con acceso al portal."""
    usuario = get_user_model().objects.create_user(
        username="marta@example.com", email="marta@example.com", password="clave-de-prueba-123"
    )
    return Propietario.objects.create(
        despacho=despacho_a, nombre="Marta Inventada", email="marta@example.com", usuario=usuario
    )


@pytest.fixture
def pablo(despacho_a):
    """Vecino sin acceso al portal (todavía)."""
    return Propietario.objects.create(
        despacho=despacho_a, nombre="Pablo Prueba", email="pablo@example.com"
    )


@pytest.fixture
def comunidad(despacho_a, marta, pablo):
    return _comunidad(despacho_a, "CP Calle Ficticia 1", [marta, pablo])


@pytest.fixture
def otra_comunidad(despacho_b):
    elena = Propietario.objects.create(despacho=despacho_b, nombre="Elena Ficticia")
    return _comunidad(despacho_b, "CP Avenida Inventada 2", [elena])

from datetime import date, datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import Despacho
from fincas.models import Comunidad, Inmueble, Propietario, Titularidad
from juntas.models import Junta, PuntoOrden

# Todos los datos son ficticios (emails de example.com).


def aware(*args) -> datetime:
    return timezone.make_aware(datetime(*args))


@pytest.fixture
def despacho_a(db):
    return Despacho.objects.create(nombre="Fincas Alfa")


@pytest.fixture
def despacho_b(db):
    return Despacho.objects.create(nombre="Fincas Beta")


@pytest.fixture
def comunidad(despacho_a):
    """1A (30 %) de Ana; 1B (30 %) de Benito y Berta (cotitulares); L1 (40 %) de Luis, sin
    email. Carlos vendió el 1A en 2025: ya no es titular."""
    comunidad = Comunidad.objects.create(despacho=despacho_a, nombre="CP Calle Ficticia 1")
    personas = {
        nombre: Propietario.objects.create(
            despacho=despacho_a,
            nombre=nombre,
            email=f"{nombre.lower()}@example.com" if nombre != "Luis" else "",
        )
        for nombre in ["Ana", "Benito", "Berta", "Luis", "Carlos"]
    }
    for referencia, coeficiente, titulares in [
        ("1A", "30", ["Ana"]),
        ("1B", "30", ["Benito", "Berta"]),
        ("L1", "40", ["Luis"]),
    ]:
        inmueble = Inmueble.objects.create(
            comunidad=comunidad,
            tipo="piso",
            referencia=referencia,
            coeficiente=Decimal(coeficiente),
        )
        for nombre in titulares:
            Titularidad.objects.create(
                inmueble=inmueble, propietario=personas[nombre], fecha_inicio=date(2025, 6, 1)
            )
        if referencia == "1A":
            Titularidad.objects.create(
                inmueble=inmueble,
                propietario=personas["Carlos"],
                fecha_inicio=date(2010, 1, 1),
                fecha_fin=date(2025, 5, 31),
            )
    return comunidad


@pytest.fixture
def junta(comunidad):
    """Ordinaria el 10/3/2026 a las 19:00 (segunda a las 19:30), con dos puntos."""
    junta = Junta.objects.create(
        comunidad=comunidad,
        tipo=Junta.Tipo.ORDINARIA,
        primera_convocatoria=aware(2026, 3, 10, 19, 0),
        segunda_convocatoria=aware(2026, 3, 10, 19, 30),
        lugar="el portal del edificio",
        convoca="La presidenta, Ana",
    )
    PuntoOrden.objects.create(junta=junta, orden=1, titulo="Aprobación de las cuentas de 2025")
    PuntoOrden.objects.create(
        junta=junta,
        orden=2,
        titulo="Presupuesto de 2026",
        descripcion="Incluye la aportación al fondo de reserva.",
    )
    return junta

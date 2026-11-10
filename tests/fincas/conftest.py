from datetime import date
from decimal import Decimal

import pytest

from core.models import Despacho
from fincas.models import Comunidad, Inmueble, Propietario, Titularidad

# Todos los datos personales de los tests son ficticios.


@pytest.fixture
def despacho_a():
    return Despacho.objects.create(nombre="Fincas Alfa")


@pytest.fixture
def despacho_b():
    return Despacho.objects.create(nombre="Fincas Beta")


@pytest.fixture
def comunidad_a(despacho_a):
    return Comunidad.objects.create(despacho=despacho_a, nombre="CP Calle Ficticia 1")


@pytest.fixture
def comunidad_b(despacho_b):
    return Comunidad.objects.create(despacho=despacho_b, nombre="CP Avenida Inventada 2")


@pytest.fixture
def piso_a(comunidad_a):
    return Inmueble.objects.create(
        comunidad=comunidad_a, tipo=Inmueble.Tipo.PISO, referencia="1A", coeficiente=Decimal("60")
    )


@pytest.fixture
def local_a(comunidad_a):
    return Inmueble.objects.create(
        comunidad=comunidad_a, tipo=Inmueble.Tipo.LOCAL, referencia="L1", coeficiente=Decimal("40")
    )


@pytest.fixture
def piso_b(comunidad_b):
    return Inmueble.objects.create(
        comunidad=comunidad_b, tipo=Inmueble.Tipo.PISO, referencia="1A", coeficiente=Decimal("100")
    )


@pytest.fixture
def propietaria_a(despacho_a):
    return Propietario.objects.create(despacho=despacho_a, nombre="Lucía Ejemplo", nif="00000000T")


@pytest.fixture
def propietario_b(despacho_b):
    return Propietario.objects.create(despacho=despacho_b, nombre="Mario Prueba", nif="00000001R")


@pytest.fixture
def titularidad_a(piso_a, propietaria_a):
    return Titularidad.objects.create(
        inmueble=piso_a, propietario=propietaria_a, fecha_inicio=date(2020, 1, 1)
    )

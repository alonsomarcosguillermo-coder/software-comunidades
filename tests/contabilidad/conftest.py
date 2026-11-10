from decimal import Decimal

import pytest

from contabilidad.models import Cuenta
from core.models import Despacho
from fincas.models import Comunidad


def D(valor: str) -> Decimal:
    return Decimal(valor)


@pytest.fixture
def comunidad(db):
    despacho = Despacho.objects.create(nombre="Fincas Alfa")
    return Comunidad.objects.create(despacho=despacho, nombre="CP Calle Ficticia 1")


@pytest.fixture
def otra_comunidad(db):
    despacho = Despacho.objects.create(nombre="Fincas Beta")
    return Comunidad.objects.create(despacho=despacho, nombre="CP Avenida Inventada 2")


@pytest.fixture
def banco(comunidad):
    return Cuenta.objects.create(comunidad=comunidad, codigo="572", nombre="Banco")


@pytest.fixture
def propietarios(comunidad):
    return Cuenta.objects.create(comunidad=comunidad, codigo="430", nombre="Propietarios")


@pytest.fixture
def limpieza(comunidad):
    return Cuenta.objects.create(comunidad=comunidad, codigo="622", nombre="Limpieza")

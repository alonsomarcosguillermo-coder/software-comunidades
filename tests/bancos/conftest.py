from datetime import date
from decimal import Decimal

import pytest

from bancos.norma43 import ExtractoCuenta, Movimiento, escribir_norma43
from cobros.sepa.identificadores import construir_iban
from core.models import Despacho
from fincas.models import Comunidad

# Todos los datos son ficticios: la entidad 9999 no existe.
ENTIDAD, OFICINA, CUENTA = "9999", "0000", "0100000001"
IBAN = construir_iban("ES", ENTIDAD + OFICINA + "10" + CUENTA)


@pytest.fixture
def despacho_a(db):
    return Despacho.objects.create(nombre="Fincas Alfa")


@pytest.fixture
def despacho_b(db):
    return Despacho.objects.create(nombre="Fincas Beta")


@pytest.fixture
def comunidad(despacho_a):
    return Comunidad.objects.create(
        despacho=despacho_a, nombre="CP Calle Ficticia 1", iban_cobros=IBAN
    )


def extracto(
    desde=date(2026, 4, 1),
    hasta=date(2026, 4, 30),
    saldo="1500.00",
    movimientos=None,
    cuenta=CUENTA,
    divisa="978",
) -> ExtractoCuenta:
    if movimientos is None:
        movimientos = (
            Movimiento(
                fecha_operacion=date(2026, 4, 5),
                fecha_valor=date(2026, 4, 5),
                concepto_comun="04",
                importe=Decimal("45.50"),
                referencia_1="REC-1-7",
                conceptos=("TRANSFERENCIA DE MARTA INVENTADA", "CUOTA ABRIL"),
            ),
            Movimiento(
                fecha_operacion=date(2026, 4, 10),
                fecha_valor=date(2026, 4, 10),
                concepto_comun="17",
                importe=Decimal("-20.00"),
            ),
        )
    return ExtractoCuenta(
        entidad=ENTIDAD,
        oficina=OFICINA,
        cuenta=cuenta,
        fecha_inicial=desde,
        fecha_final=hasta,
        saldo_inicial=Decimal(saldo),
        movimientos=tuple(movimientos),
        divisa=divisa,
        titular="CP CALLE FICTICIA 1",
    )


def fichero(*extractos: ExtractoCuenta) -> bytes:
    return escribir_norma43(extractos or [extracto()])

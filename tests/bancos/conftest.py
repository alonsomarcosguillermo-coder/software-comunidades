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


# --- T3.2: comunidad con recibos y una remesa ------------------------------------------------


@pytest.fixture
def con_recibos(comunidad):
    """Presupuesto 2026 aprobado (trimestral), 1er trimestre emitido el 5/1/2026 y sus recibos.

    1A y 1B (30 % cada uno) tienen mandato SEPA; L1 (40 %) no. Hay una cuenta de gasto 628.
    """
    from cobros.emision import emitir_cuotas
    from cobros.models import Mandato, Partida, Presupuesto
    from cobros.recibos import generar_recibos
    from contabilidad.models import Cuenta
    from fincas.models import Inmueble, Propietario, Titularidad

    comunidad.nif = "H00000000"
    comunidad.save()
    for n, (referencia, coeficiente) in enumerate([("1A", 30), ("1B", 30), ("L1", 40)], 1):
        inmueble = Inmueble.objects.create(
            comunidad=comunidad, tipo="piso", referencia=referencia, coeficiente=coeficiente
        )
        vecino = Propietario.objects.create(despacho=comunidad.despacho, nombre=f"Vecino {n}")
        Titularidad.objects.create(
            inmueble=inmueble, propietario=vecino, fecha_inicio=date(2020, 1, 1)
        )
        if referencia != "L1":
            Mandato.objects.create(
                comunidad=comunidad,
                propietario=vecino,
                referencia=f"MANDATO-{n}",
                titular_cuenta=vecino.nombre,
                iban=construir_iban("ES", f"99990000{n:012d}"),
                fecha_firma=date(2025, 6, 1),
            )
    Cuenta.objects.create(
        comunidad=comunidad, codigo="113", nombre="Fondo de reserva", es_fondo_reserva=True
    )
    Cuenta.objects.create(comunidad=comunidad, codigo="628", nombre="Suministros")
    presupuesto = Presupuesto.objects.create(
        comunidad=comunidad, ejercicio=2026, aportacion_fondo_reserva=Decimal("400.00")
    )
    Partida.objects.create(presupuesto=presupuesto, concepto="Limpieza", importe=Decimal("3600"))
    presupuesto.fecha_aprobacion = date(2025, 12, 15)
    presupuesto.save()
    emitir_cuotas(presupuesto, 1, date(2026, 1, 5))
    generar_recibos(comunidad)
    return comunidad


def recibo_de(comunidad, referencia_inmueble):
    return comunidad.recibos.get(inmueble__referencia=referencia_inmueble)


def importar(comunidad, *movimientos, desde=date(2026, 1, 1), hasta=date(2026, 1, 31)):
    """Importa un extracto con `movimientos` (bancos.norma43.Movimiento) y devuelve los
    movimientos guardados, en orden."""
    from bancos.importacion import importar_norma43

    [guardado] = importar_norma43(
        comunidad,
        fichero(extracto(desde=desde, hasta=hasta, movimientos=movimientos)),
        nombre_fichero="enero.n43",
    )
    return list(guardado.movimientos.order_by("orden"))


def abono(importe, *textos, referencia="", dia=20):
    return Movimiento(
        fecha_operacion=date(2026, 1, dia),
        fecha_valor=date(2026, 1, dia),
        concepto_comun="04",
        importe=Decimal(importe),
        referencia_1=referencia,
        conceptos=textos,
    )


def cargo(importe, *textos, dia=25):
    return Movimiento(
        fecha_operacion=date(2026, 1, dia),
        fecha_valor=date(2026, 1, dia),
        concepto_comun="03",
        importe=-Decimal(importe),
        conceptos=textos,
    )

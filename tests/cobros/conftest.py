from datetime import date
from decimal import Decimal

import pytest

from cobros.models import Derrama, Partida, Presupuesto
from contabilidad.models import Cuenta
from core.models import Despacho
from fincas.models import Comunidad, GrupoReparto, Inmueble, MiembroGrupo

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


# --- Derramas (T2.3) ------------------------------------------------------------------


def _inmueble(comunidad, referencia, coeficiente, tipo=Inmueble.Tipo.PISO):
    return Inmueble.objects.create(
        comunidad=comunidad, tipo=tipo, referencia=referencia, coeficiente=D(coeficiente)
    )


@pytest.fixture
def inmuebles_a(comunidad_a):
    """Dos pisos (30 % y 30 %) y un local (40 %): suman 100 % (R-COEF-01)."""
    return {
        "1A": _inmueble(comunidad_a, "1A", "30"),
        "1B": _inmueble(comunidad_a, "1B", "30"),
        "L1": _inmueble(comunidad_a, "L1", "40", Inmueble.Tipo.LOCAL),
    }


@pytest.fixture
def grupo_ascensor_a(inmuebles_a):
    """R-REP-01: el ascensor lo pagan solo los pisos, con sus coeficientes generales."""
    grupo = GrupoReparto.objects.create(comunidad=inmuebles_a["1A"].comunidad, nombre="Ascensor")
    for referencia in ("1A", "1B"):
        MiembroGrupo.objects.create(grupo=grupo, inmueble=inmuebles_a[referencia])
    return grupo


@pytest.fixture
def derrama_a(inmuebles_a):
    """Fachada: 3.000 € entre todos, en 3 plazos mensuales desde el 1/3/2026. Acordada."""
    return Derrama.objects.create(
        comunidad=inmuebles_a["1A"].comunidad,
        concepto="Fachada",
        importe=D("3000.00"),
        plazos=3,
        primer_vencimiento=date(2026, 3, 1),
        fecha_acuerdo=date(2026, 1, 20),
    )


@pytest.fixture
def derrama_b(comunidad_b):
    _inmueble(comunidad_b, "1A", "100")
    return Derrama.objects.create(
        comunidad=comunidad_b,
        concepto="Tejado",
        importe=D("1000.00"),
        primer_vencimiento=date(2026, 4, 1),
        fecha_acuerdo=date(2026, 2, 10),
    )

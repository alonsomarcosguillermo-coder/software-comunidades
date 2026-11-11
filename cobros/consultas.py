"""Consultas a la base de datos para R-RES-01. La regla en sí está en `servicios.py`."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from contabilidad.models import Cuenta
from fincas.models import Comunidad

from .models import Presupuesto
from .servicios import EstadoFondoReserva, estado_fondo_reserva


def saldo_fondo_reserva(comunidad: Comunidad, hasta: date | None = None) -> Decimal | None:
    """Importe del fondo de reserva según la contabilidad, o None si la comunidad no tiene
    marcada ninguna cuenta como fondo de reserva.

    Es una cuenta de patrimonio: las aportaciones van al Haber, así que el fondo es su saldo
    acreedor (Haber − Debe), es decir, `-cuenta.saldo()`. Nunca se guarda: se calcula.
    """
    cuenta = Cuenta.objects.filter(comunidad=comunidad, es_fondo_reserva=True).first()
    if cuenta is None:
        return None
    return -cuenta.saldo(hasta=hasta)


@dataclass(frozen=True)
class FondoReservaComunidad:
    """R-RES-01 aplicado a una comunidad. `estado` es None si falta algún dato."""

    presupuesto: Presupuesto | None  # el último presupuesto ordinario aprobado
    saldo: Decimal | None
    estado: EstadoFondoReserva | None


def fondo_reserva_de(comunidad: Comunidad, hasta: date | None = None) -> FondoReservaComunidad:
    """R-RES-01: ¿el fondo de reserva llega al 10 % del último presupuesto ordinario?"""
    presupuesto = Presupuesto.objects.ultimo_aprobado(comunidad)
    saldo = saldo_fondo_reserva(comunidad, hasta=hasta)
    estado = None
    if presupuesto is not None and saldo is not None:
        estado = estado_fondo_reserva(saldo=saldo, presupuesto=presupuesto.total_gastos())
    return FondoReservaComunidad(presupuesto=presupuesto, saldo=saldo, estado=estado)

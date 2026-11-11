from dataclasses import dataclass
from decimal import Decimal

from django.views.generic import DetailView

from core.aislamiento import FiltradoPorDespachoMixin
from fincas.models import CAMPO_DESPACHO, Comunidad

from .consultas import fondo_reserva_de
from .models import Presupuesto
from .servicios import EstadoFondoReserva, estado_fondo_reserva, total_partidas


@dataclass(frozen=True)
class FilaPresupuesto:
    presupuesto: Presupuesto
    gastos: Decimal
    total: Decimal
    # R-RES-01 previsto: ¿con el saldo actual + la aportación de este presupuesto, el fondo
    # llegará al 10 % de sus gastos? None si la comunidad no tiene cuenta de fondo.
    prevision: EstadoFondoReserva | None


class PresupuestosComunidad(FiltradoPorDespachoMixin, DetailView):
    """Presupuestos de una comunidad del despacho, con sus partidas y el estado del fondo de
    reserva (R-RES-01). Una comunidad de otro despacho da 404 (FiltradoPorDespachoMixin)."""

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO[Comunidad]
    context_object_name = "comunidad"
    template_name = "cobros/presupuestos_comunidad.html"

    def get_context_data(self, **kwargs):
        comunidad = self.object
        fondo = fondo_reserva_de(comunidad)
        filas = []
        # prefetch_related: las partidas de todos los presupuestos en una sola consulta.
        for presupuesto in comunidad.presupuestos.prefetch_related("partidas"):
            gastos = total_partidas(p.importe for p in presupuesto.partidas.all())
            prevision = None
            if fondo.saldo is not None:
                prevision = estado_fondo_reserva(
                    saldo=fondo.saldo + presupuesto.aportacion_fondo_reserva, presupuesto=gastos
                )
            filas.append(
                FilaPresupuesto(
                    presupuesto=presupuesto,
                    gastos=gastos,
                    total=gastos + presupuesto.aportacion_fondo_reserva,
                    prevision=prevision,
                )
            )
        return super().get_context_data(fondo=fondo, filas=filas, **kwargs)

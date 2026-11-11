from dataclasses import dataclass
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Prefetch, Sum
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from core.aislamiento import FiltradoPorDespachoMixin, filtrar_por_despacho
from fincas.models import CAMPO_DESPACHO, Comunidad

from .consultas import fondo_reserva_de
from .emision import EmisionInvalida, emitir_cuotas
from .models import CAMPO_DESPACHO as CAMPO_DESPACHO_COBROS
from .models import Emision, Presupuesto
from .servicios import EstadoFondoReserva, estado_fondo_reserva, total_partidas


@dataclass(frozen=True)
class FilaPresupuesto:
    presupuesto: Presupuesto
    gastos: Decimal
    total: Decimal
    # R-RES-01 previsto: ¿con el saldo actual + la aportación de este presupuesto, el fondo
    # llegará al 10 % de sus gastos? None si la comunidad no tiene cuenta de fondo.
    prevision: EstadoFondoReserva | None
    # T2.2: [(nº de periodo, Emision o None si no se ha emitido)]
    periodos: list[tuple[int, Emision | None]]


class PresupuestosComunidad(FiltradoPorDespachoMixin, DetailView):
    """Presupuestos de una comunidad del despacho, con sus partidas, el estado del fondo de
    reserva (R-RES-01) y sus emisiones de cuotas. Una comunidad de otro despacho da 404."""

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO[Comunidad]
    context_object_name = "comunidad"
    template_name = "cobros/presupuestos_comunidad.html"

    def get_context_data(self, **kwargs):
        comunidad = self.object
        fondo = fondo_reserva_de(comunidad)
        emisiones = Emision.objects.select_related("asiento").annotate(
            total_cuotas=Sum("cuotas__importe")
        )
        filas = []
        # prefetch_related: partidas y emisiones de todos los presupuestos en dos consultas.
        for presupuesto in comunidad.presupuestos.prefetch_related(
            "partidas", Prefetch("emisiones", queryset=emisiones)
        ):
            gastos = total_partidas(p.importe for p in presupuesto.partidas.all())
            prevision = None
            if fondo.saldo is not None:
                prevision = estado_fondo_reserva(
                    saldo=fondo.saldo + presupuesto.aportacion_fondo_reserva, presupuesto=gastos
                )
            emitidas = {e.periodo: e for e in presupuesto.emisiones.all()}
            filas.append(
                FilaPresupuesto(
                    presupuesto=presupuesto,
                    gastos=gastos,
                    total=gastos + presupuesto.aportacion_fondo_reserva,
                    prevision=prevision,
                    periodos=[(n, emitidas.get(n)) for n in range(1, presupuesto.periodos + 1)],
                )
            )
        return super().get_context_data(
            fondo=fondo,
            filas=filas,
            hoy=timezone.localdate(),
            puede_emitir=self.request.user.has_perm("cobros.add_emision"),
            **kwargs,
        )


class FormularioEmision(forms.Form):
    periodo = forms.IntegerField(min_value=1)
    fecha = forms.DateField()


class EmitirCuotas(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST: emite las cuotas de un periodo y vuelve a la página de presupuestos.

    Patrón POST/Redirect/GET: tras emitir se redirige, así que recargar la página no
    repite la emisión. Un presupuesto de otro despacho da 404.
    """

    permission_required = "cobros.add_emision"
    http_method_names = ["post"]

    def post(self, request, pk, presupuesto_pk):
        presupuestos = filtrar_por_despacho(
            Presupuesto.objects.filter(comunidad_id=pk),
            request.user,
            CAMPO_DESPACHO_COBROS[Presupuesto],
        )
        presupuesto = get_object_or_404(presupuestos, pk=presupuesto_pk)
        formulario = FormularioEmision(request.POST)
        if not formulario.is_valid():
            messages.error(request, "Indica un periodo y una fecha válidos.")
        else:
            periodo = formulario.cleaned_data["periodo"]
            try:
                emision = emitir_cuotas(presupuesto, periodo, formulario.cleaned_data["fecha"])
            except EmisionInvalida as error:
                messages.error(request, str(error))
            else:
                messages.success(
                    request,
                    f"Emitidas las cuotas del periodo {periodo}/{presupuesto.periodos} de "
                    f"{presupuesto.ejercicio} (asiento {emision.asiento.numero}).",
                )
        return redirect("cobros:presupuestos_comunidad", pk=pk)

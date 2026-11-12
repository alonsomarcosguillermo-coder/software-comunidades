from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView

from core.aislamiento import FiltradoPorDespachoMixin, filtrar_por_despacho
from fincas.models import CAMPO_DESPACHO as CAMPO_DESPACHO_FINCAS
from fincas.models import Comunidad

from .importacion import ImportacionInvalida, importar_norma43
from .models import CAMPO_DESPACHO, Extracto

# Un extracto de un mes de una comunidad ocupa pocos KB; 5 MB es más que de sobra y evita
# que alguien suba por error (o a propósito) un fichero enorme.
TAMANO_MAXIMO = 5 * 1024 * 1024


class ExtractosComunidad(FiltradoPorDespachoMixin, DetailView):
    """Extractos bancarios importados de una comunidad y el formulario para subir otro.
    Una comunidad de otro despacho da 404."""

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO_FINCAS[Comunidad]
    context_object_name = "comunidad"
    template_name = "bancos/extractos_comunidad.html"

    def get_context_data(self, **kwargs):
        # annotate: nº de movimientos y totales en la misma consulta que los extractos.
        # order_by explícito: Django no aplica Meta.ordering a consultas con GROUP BY.
        # Coalesce: sin movimientos de un signo, la suma es NULL; se muestra 0,00.
        cero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
        extractos = self.object.extractos.annotate(
            num_movimientos=Count("movimientos"),
            abonos=Coalesce(
                Sum("movimientos__importe", filter=Q(movimientos__importe__gt=0)), cero
            ),
            cargos=Coalesce(
                Sum("movimientos__importe", filter=Q(movimientos__importe__lt=0)), cero
            ),
        ).order_by("-fecha_inicial")
        return super().get_context_data(
            extractos=extractos,
            puede_importar=self.request.user.has_perm("bancos.add_extracto"),
            **kwargs,
        )


class FormularioImportacion(forms.Form):
    fichero = forms.FileField()


class ImportarExtracto(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST (multipart): importa un fichero Norma 43 y vuelve a la lista (PRG con mensajes)."""

    permission_required = "bancos.add_extracto"
    http_method_names = ["post"]

    def post(self, request, pk):
        comunidades = filtrar_por_despacho(
            Comunidad.objects.all(), request.user, CAMPO_DESPACHO_FINCAS[Comunidad]
        )
        comunidad = get_object_or_404(comunidades, pk=pk)
        formulario = FormularioImportacion(request.POST, request.FILES)
        if not formulario.is_valid():
            messages.error(request, "Elige un fichero Norma 43 para importar.")
            return redirect("bancos:extractos_comunidad", pk=pk)
        fichero = formulario.cleaned_data["fichero"]
        if fichero.size > TAMANO_MAXIMO:
            messages.error(request, "El fichero es demasiado grande para ser un extracto.")
            return redirect("bancos:extractos_comunidad", pk=pk)
        try:
            extractos = importar_norma43(
                comunidad, fichero.read(), nombre_fichero=fichero.name, usuario=request.user
            )
        except ImportacionInvalida as error:
            messages.error(request, str(error))
        else:
            movimientos = sum(e.movimientos.count() for e in extractos)
            plural = "extracto" if len(extractos) == 1 else "extractos"
            messages.success(
                request,
                f"Importado {len(extractos)} {plural} con {movimientos} movimientos.",
            )
        return redirect("bancos:extractos_comunidad", pk=pk)


class DetalleExtracto(FiltradoPorDespachoMixin, DetailView):
    """Movimientos de un extracto. De otro despacho, o con otra comunidad en la URL: 404."""

    model = Extracto
    campo_despacho = CAMPO_DESPACHO[Extracto]
    pk_url_kwarg = "extracto_pk"
    context_object_name = "extracto"
    template_name = "bancos/detalle_extracto.html"

    def get_queryset(self):
        return super().get_queryset().filter(comunidad_id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        return super().get_context_data(movimientos=self.object.movimientos.all(), **kwargs)

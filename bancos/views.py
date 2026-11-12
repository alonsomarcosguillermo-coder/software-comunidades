from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from cobros.models import Recibo
from contabilidad.models import Cuenta
from core.aislamiento import FiltradoPorDespachoMixin, filtrar_por_despacho
from fincas.models import CAMPO_DESPACHO as CAMPO_DESPACHO_FINCAS
from fincas.models import Comunidad

from .conciliacion import (
    CODIGOS_RESERVADOS,
    ConciliacionInvalida,
    conciliar_automaticamente,
    conciliar_con_cuenta,
    conciliar_con_recibos,
    deshacer_conciliacion,
    movimientos_pendientes,
    recibos_pendientes,
)
from .importacion import ImportacionInvalida, importar_norma43
from .models import CAMPO_DESPACHO, Conciliacion, Extracto, Movimiento

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
            # T3.2: movimientos que aún no están explicados en la contabilidad.
            pendientes=Count("movimientos", filter=Q(movimientos__conciliacion__isnull=True)),
        ).order_by("-fecha_inicial")
        return super().get_context_data(
            extractos=extractos,
            hay_pendientes=any(e.pendientes for e in extractos),
            puede_conciliar=self.request.user.has_perm("bancos.add_conciliacion"),
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
        # T3.2: con su conciliación (si la tiene) y lo que paga, sin una consulta por fila.
        movimientos = self.object.movimientos.select_related(
            "conciliacion__asiento", "conciliacion__cuenta", "conciliacion__remesa"
        ).prefetch_related("conciliacion__cobros__recibo")
        usuario = self.request.user
        return super().get_context_data(
            movimientos=movimientos,
            puede_conciliar=usuario.has_perm("bancos.add_conciliacion"),
            puede_deshacer=usuario.has_perm("bancos.delete_conciliacion"),
            **kwargs,
        )


# --- Conciliación (T3.2) -------------------------------------------------------------------


def _comunidad_del_usuario(request, pk) -> Comunidad:
    """La comunidad `pk` si es del despacho del usuario; si no, 404 (ADR 002)."""
    comunidades = filtrar_por_despacho(
        Comunidad.objects.all(), request.user, CAMPO_DESPACHO_FINCAS[Comunidad]
    )
    return get_object_or_404(comunidades, pk=pk)


def _movimiento_del_usuario(request, pk, movimiento_pk) -> Movimiento:
    movimientos = filtrar_por_despacho(
        Movimiento.objects.filter(extracto__comunidad_id=pk).select_related("extracto"),
        request.user,
        CAMPO_DESPACHO[Movimiento],
    )
    return get_object_or_404(movimientos, pk=movimiento_pk)


def _volver_al_extracto(movimiento: Movimiento):
    return redirect(
        "bancos:detalle_extracto",
        pk=movimiento.extracto.comunidad_id,
        extracto_pk=movimiento.extracto_id,
    )


class ConciliarAutomaticamente(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST: concilia por importe + referencia todo lo que encaje sin dudas (PRG)."""

    permission_required = "bancos.add_conciliacion"
    http_method_names = ["post"]

    def post(self, request, pk):
        comunidad = _comunidad_del_usuario(request, pk)
        hechas = conciliar_automaticamente(comunidad, usuario=request.user)
        quedan = movimientos_pendientes(comunidad).count()
        if hechas:
            messages.success(
                request,
                f"Conciliados automáticamente {len(hechas)} movimientos. Quedan {quedan} "
                "pendientes.",
            )
        else:
            messages.info(
                request,
                f"Ningún movimiento encaja por importe y referencia. Quedan {quedan} "
                "pendientes: concílialos a mano.",
            )
        return redirect("bancos:extractos_comunidad", pk=pk)


class FormularioRecibos(forms.Form):
    recibos = forms.ModelMultipleChoiceField(queryset=Recibo.objects.none())

    def __init__(self, *args, comunidad: Comunidad, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo recibos pendientes de esta comunidad: un id ajeno no es una opción válida.
        self.fields["recibos"].queryset = recibos_pendientes(comunidad)


class FormularioCuenta(forms.Form):
    cuenta = forms.ModelChoiceField(queryset=Cuenta.objects.none())

    def __init__(self, *args, comunidad: Comunidad, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cuenta"].queryset = comunidad.cuentas.exclude(codigo__in=CODIGOS_RESERVADOS)


class ConciliarMovimiento(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Conciliación manual de un movimiento: con los recibos que paga (abonos) o con otra
    cuenta contable. GET muestra las opciones; POST concilia y vuelve al extracto."""

    permission_required = "bancos.add_conciliacion"
    template_name = "bancos/conciliar_movimiento.html"

    def get(self, request, pk, movimiento_pk):
        movimiento = _movimiento_del_usuario(request, pk, movimiento_pk)
        if hasattr(movimiento, "conciliacion"):
            messages.info(request, "Ese movimiento ya está conciliado.")
            return _volver_al_extracto(movimiento)
        comunidad = movimiento.extracto.comunidad
        recibos = []
        if movimiento.importe > 0:
            # Primero los del importe exacto: son los candidatos más probables.
            recibos = sorted(
                recibos_pendientes(comunidad).select_related("propietario", "inmueble"),
                key=lambda r: (r.importe != movimiento.importe, r.vencimiento, r.numero),
            )
        return render(
            request,
            self.template_name,
            {
                "comunidad": comunidad,
                "movimiento": movimiento,
                "recibos": recibos,
                "cuentas": FormularioCuenta(comunidad=comunidad).fields["cuenta"].queryset,
            },
        )

    def post(self, request, pk, movimiento_pk):
        movimiento = _movimiento_del_usuario(request, pk, movimiento_pk)
        comunidad = movimiento.extracto.comunidad
        try:
            if request.POST.get("accion") == "cuenta":
                formulario = FormularioCuenta(request.POST, comunidad=comunidad)
                if not formulario.is_valid():
                    raise ConciliacionInvalida("Elige una cuenta contable.")
                conciliacion = conciliar_con_cuenta(
                    movimiento, formulario.cleaned_data["cuenta"], usuario=request.user
                )
            else:
                formulario = FormularioRecibos(request.POST, comunidad=comunidad)
                if not formulario.is_valid():
                    raise ConciliacionInvalida("Elige al menos un recibo pendiente.")
                conciliacion = conciliar_con_recibos(
                    movimiento, formulario.cleaned_data["recibos"], usuario=request.user
                )
        except ConciliacionInvalida as error:
            messages.error(request, str(error))
            return redirect("bancos:conciliar_movimiento", pk=pk, movimiento_pk=movimiento_pk)
        messages.success(request, f"Movimiento conciliado (asiento {conciliacion.asiento.numero}).")
        return _volver_al_extracto(movimiento)


class DeshacerConciliacion(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST: deshace la conciliación con un contra-asiento fechado hoy (PRG)."""

    permission_required = "bancos.delete_conciliacion"
    http_method_names = ["post"]

    def post(self, request, pk, movimiento_pk):
        movimiento = _movimiento_del_usuario(request, pk, movimiento_pk)
        conciliacion = Conciliacion.objects.filter(movimiento=movimiento).first()
        if conciliacion is None:
            messages.info(request, "Ese movimiento no estaba conciliado.")
        else:
            numero = conciliacion.asiento.numero
            deshacer_conciliacion(conciliacion, timezone.localdate())
            messages.success(
                request,
                f"Conciliación deshecha: el asiento {numero} queda anulado con un contra-asiento.",
            )
        return _volver_al_extracto(movimiento)

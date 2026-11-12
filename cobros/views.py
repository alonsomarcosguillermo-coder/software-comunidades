from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Prefetch, Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from core.aislamiento import FiltradoPorDespachoMixin, filtrar_por_despacho
from fincas.models import CAMPO_DESPACHO, Comunidad

from .consultas import fondo_reserva_de
from .derramas import (
    DerramaInvalida,
    FilaReparto,
    filas_de_reparto,
    reparto_emitido,
    reparto_previsto,
)
from .deudas import certificado_deuda_de, informe_morosos_de
from .emision import EmisionInvalida, emitir_cuotas
from .models import CAMPO_DESPACHO as CAMPO_DESPACHO_COBROS
from .models import Derrama, Emision, Presupuesto
from .pdf import pdf_certificado_deuda, pdf_informe_morosos
from .recibos import generar_recibos
from .remesas import RemesaInvalida, crear_remesa
from .sepa.identificadores import iban_oculto
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


@dataclass(frozen=True)
class FichaDerrama:
    derrama: Derrama
    vencimientos: list
    filas: list[FilaReparto]  # vacía si no se puede repartir (ver `error`)
    error: str  # por qué no se puede repartir todavía (R-COEF-01, R-REP-01...)


class DerramasComunidad(FiltradoPorDespachoMixin, DetailView):
    """Derramas de una comunidad del despacho con su reparto por inmueble y plazo: el
    emitido (fijo) o, si aún no se ha emitido, el que saldría ahora. Una comunidad de otro
    despacho da 404 (FiltradoPorDespachoMixin)."""

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO[Comunidad]
    context_object_name = "comunidad"
    template_name = "cobros/derramas_comunidad.html"

    def get_context_data(self, **kwargs):
        fichas = []
        for derrama in self.object.derramas.select_related("grupo", "comunidad", "asiento"):
            filas, error = [], ""
            try:
                plan = (
                    reparto_emitido(derrama) if derrama.esta_emitida else reparto_previsto(derrama)
                )
                filas = filas_de_reparto(plan)
            except DerramaInvalida as motivo:
                error = str(motivo)
            fichas.append(
                FichaDerrama(
                    derrama=derrama, vencimientos=derrama.vencimientos(), filas=filas, error=error
                )
            )
        return super().get_context_data(fichas=fichas, **kwargs)


# --- Recibos y mandatos (T2.4) ---------------------------------------------------------


def _comunidad_del_usuario(request, pk) -> Comunidad:
    """La comunidad `pk` si es del despacho del usuario; si no, 404 (ADR 002)."""
    comunidades = filtrar_por_despacho(
        Comunidad.objects.all(), request.user, CAMPO_DESPACHO[Comunidad]
    )
    return get_object_or_404(comunidades, pk=pk)


class RecibosComunidad(FiltradoPorDespachoMixin, DetailView):
    """Recibos de una comunidad, si se pueden domiciliar, y sus mandatos SEPA (R-SEPA-01).

    Los IBAN se muestran ocultos. Una comunidad de otro despacho da 404.
    """

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO[Comunidad]
    context_object_name = "comunidad"
    template_name = "cobros/recibos_comunidad.html"

    def get_context_data(self, **kwargs):
        comunidad = self.object
        hoy = timezone.localdate()
        mandatos = list(comunidad.mandatos.select_related("propietario"))
        # R-SEPA-01: el mandato vigente hoy de cada propietario (como mucho uno sin baja).
        vigentes = {m.propietario_id: m for m in mandatos if m.vigente_en(hoy)}
        # "cobro" (T3.2) y "devoluciones" (T3.3) vienen de la app bancos; select_related y
        # prefetch_related evitan una consulta por recibo.
        recibos = (
            comunidad.recibos.select_related("inmueble", "propietario", "remesa", "cobro")
            .prefetch_related("devoluciones")
            .order_by("-numero")
        )
        filas = [(recibo, vigentes.get(recibo.propietario_id)) for recibo in recibos]
        return super().get_context_data(
            filas=filas,
            mandatos=mandatos,
            hoy=hoy,
            iban_cobros=iban_oculto(comunidad.iban_cobros) if comunidad.iban_cobros else "",
            puede_generar=self.request.user.has_perm("cobros.add_recibo"),
            # T2.5 — Remesas
            remesas=comunidad.remesas.all(),
            puede_remesar=self.request.user.has_perm("cobros.add_remesa"),
            puede_descargar=self.request.user.has_perm("cobros.view_remesa"),
            cobro_sugerido=hoy + timedelta(days=7),
            **kwargs,
        )


class GenerarRecibos(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST: crea los recibos de las cuotas que aún no lo tienen (PRG con mensajes)."""

    permission_required = "cobros.add_recibo"
    http_method_names = ["post"]

    def post(self, request, pk):
        comunidad = _comunidad_del_usuario(request, pk)
        resultado = generar_recibos(comunidad)
        if resultado.creados:
            messages.success(request, f"Generados {len(resultado.creados)} recibos.")
        else:
            messages.info(request, "No había cuotas sin recibo.")
        if resultado.sin_titular:
            inmuebles = ", ".join(
                f"{inmueble.referencia} ({fecha:%d/%m/%Y})"
                for inmueble, fecha in resultado.sin_titular
            )
            messages.warning(
                request,
                f"Sin recibo porque el inmueble no tenía titular en el vencimiento: {inmuebles}.",
            )
        return redirect("cobros:recibos_comunidad", pk=pk)


# --- Remesas SEPA (T2.5) ---------------------------------------------------------------


class FormularioRemesa(forms.Form):
    fecha_cobro = forms.DateField()


class CrearRemesa(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST: crea la remesa pain.008 de los recibos domiciliables (PRG con mensajes)."""

    permission_required = "cobros.add_remesa"
    http_method_names = ["post"]

    def post(self, request, pk):
        comunidad = _comunidad_del_usuario(request, pk)
        formulario = FormularioRemesa(request.POST)
        if not formulario.is_valid():
            messages.error(request, "Indica una fecha de cobro válida.")
            return redirect("cobros:recibos_comunidad", pk=pk)
        try:
            remesa = crear_remesa(comunidad, formulario.cleaned_data["fecha_cobro"])
        except RemesaInvalida as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request,
                f"Creada la remesa {remesa.numero}: {remesa.num_recibos} recibos, "
                f"{remesa.total} €. Descarga el fichero y súbelo a la banca online.",
            )
        return redirect("cobros:recibos_comunidad", pk=pk)


class DescargarRemesa(LoginRequiredMixin, PermissionRequiredMixin, View):
    """GET: el fichero pain.008 tal cual se generó. Lleva IBAN completos: exige permiso."""

    permission_required = "cobros.view_remesa"

    def get(self, request, pk, remesa_pk):
        comunidad = _comunidad_del_usuario(request, pk)
        remesa = get_object_or_404(comunidad.remesas, pk=remesa_pk)
        respuesta = HttpResponse(remesa.xml.encode("utf-8"), content_type="application/xml")
        respuesta["Content-Disposition"] = f'attachment; filename="{remesa.nombre_fichero}"'
        return respuesta


# --- Morosidad y certificado de deuda (T3.4) ---------------------------------------------


class FormularioFechaDeuda(forms.Form):
    """`?fecha=` de las páginas de deuda. Vacía = hoy. No se admite una fecha futura: la
    deuda de mañana todavía no se conoce (aún se puede pagar)."""

    fecha = forms.DateField(required=False)

    def clean_fecha(self):
        fecha = self.cleaned_data["fecha"]
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError("La fecha no puede ser posterior a hoy.")
        return fecha or timezone.localdate()


def _fecha_deuda(request) -> tuple[date, str]:
    """La fecha pedida en `?fecha=` (o hoy) y, si no era válida, por qué."""
    formulario = FormularioFechaDeuda(request.GET)
    if formulario.is_valid():
        return formulario.cleaned_data["fecha"], ""
    errores = formulario.errors.get("fecha") or ["Fecha no válida."]
    return timezone.localdate(), f"{errores[0]} Se muestra la deuda a hoy."


def _respuesta_pdf(contenido: bytes, nombre: str) -> HttpResponse:
    respuesta = HttpResponse(contenido, content_type="application/pdf")
    # inline: el navegador lo abre en una pestaña (y desde ahí se puede guardar o imprimir).
    respuesta["Content-Disposition"] = f'inline; filename="{nombre}"'
    return respuesta


class MorososComunidad(FiltradoPorDespachoMixin, PermissionRequiredMixin, DetailView):
    """Propietarios con recibos vencidos sin cobrar en una fecha (`?fecha=`, por defecto
    hoy), con enlaces al PDF del informe y al certificado de deuda de cada inmueble.

    Son datos personales de deuda: exige `cobros.view_recibo`. Una comunidad de otro
    despacho da 404.
    """

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO[Comunidad]
    context_object_name = "comunidad"
    template_name = "cobros/morosos_comunidad.html"
    permission_required = "cobros.view_recibo"

    def get_context_data(self, **kwargs):
        fecha, error = _fecha_deuda(self.request)
        return super().get_context_data(
            fecha=fecha,
            error_fecha=error,
            hoy=timezone.localdate(),
            informe=informe_morosos_de(self.object, fecha),
            inmuebles=self.object.inmuebles.all(),
            **kwargs,
        )


class InformeMorososPdf(LoginRequiredMixin, PermissionRequiredMixin, View):
    """GET: el informe de morosos en PDF, a la fecha `?fecha=` (por defecto, hoy)."""

    permission_required = "cobros.view_recibo"

    def get(self, request, pk):
        comunidad = _comunidad_del_usuario(request, pk)
        fecha, error = _fecha_deuda(request)
        if error:
            return HttpResponseBadRequest(error)
        contenido = pdf_informe_morosos(comunidad, informe_morosos_de(comunidad, fecha))
        return _respuesta_pdf(contenido, f"morosos-{comunidad.pk}-{fecha:%Y%m%d}.pdf")


class CertificadoDeudaPdf(LoginRequiredMixin, PermissionRequiredMixin, View):
    """GET: R-DEU-01 — certificado de deuda de un inmueble en PDF, a `?fecha=` (o hoy)."""

    permission_required = "cobros.view_recibo"

    def get(self, request, pk, inmueble_pk):
        comunidad = _comunidad_del_usuario(request, pk)
        inmueble = get_object_or_404(comunidad.inmuebles, pk=inmueble_pk)
        fecha, error = _fecha_deuda(request)
        if error:
            return HttpResponseBadRequest(error)
        contenido = pdf_certificado_deuda(certificado_deuda_de(inmueble, fecha))
        return _respuesta_pdf(
            contenido, f"certificado-deuda-{comunidad.pk}-{inmueble.pk}-{fecha:%Y%m%d}.pdf"
        )

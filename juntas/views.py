from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from core.aislamiento import FiltradoPorDespachoMixin, filtrar_por_despacho
from fincas.models import CAMPO_DESPACHO as CAMPO_DESPACHO_FINCAS
from fincas.models import Comunidad

from .convocatoria import convocar, morosos_al_convocar, texto_convocatoria
from .forms import FormularioConvocar, FormularioJunta, PuntosFormSet
from .models import CAMPO_DESPACHO, Junta, PuntoOrden
from .servicios import ConvocatoriaInvalida, fecha_minima_ordinaria


def _comunidad_del_usuario(request, pk) -> Comunidad:
    """La comunidad `pk` si es del despacho del usuario; si no, 404 (ADR 002)."""
    comunidades = filtrar_por_despacho(
        Comunidad.objects.all(), request.user, CAMPO_DESPACHO_FINCAS[Comunidad]
    )
    return get_object_or_404(comunidades, pk=pk)


def _junta_del_usuario(request, pk, junta_pk) -> Junta:
    juntas = filtrar_por_despacho(
        Junta.objects.filter(comunidad_id=pk).select_related("comunidad"),
        request.user,
        CAMPO_DESPACHO[Junta],
    )
    return get_object_or_404(juntas, pk=junta_pk)


class JuntasComunidad(FiltradoPorDespachoMixin, DetailView):
    """Juntas de una comunidad del despacho. Una comunidad de otro despacho da 404."""

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO_FINCAS[Comunidad]
    context_object_name = "comunidad"
    template_name = "juntas/juntas_comunidad.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            juntas=self.object.juntas.prefetch_related("puntos"),
            puede_crear=self.request.user.has_perm("juntas.add_junta"),
            **kwargs,
        )


class EditarJunta(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Alta (sin `junta_pk`) o edición de una junta en borrador, con su orden del día.

    Los puntos se guardan en el orden en que aparecen en el formulario (1, 2, 3...).
    """

    template_name = "juntas/editar_junta.html"

    def get_permission_required(self):
        return ["juntas.change_junta" if "junta_pk" in self.kwargs else "juntas.add_junta"]

    def _junta(self, request, pk, junta_pk):
        if junta_pk is None:
            return None
        junta = _junta_del_usuario(request, pk, junta_pk)
        if junta.esta_convocada:
            messages.error(request, "La junta ya está convocada: no se puede cambiar.")
        return junta

    def _pintar(self, request, comunidad, junta, formulario, puntos):
        return render(
            request,
            self.template_name,
            {"comunidad": comunidad, "junta": junta, "formulario": formulario, "puntos": puntos},
        )

    def get(self, request, pk, junta_pk=None):
        comunidad = _comunidad_del_usuario(request, pk)
        junta = self._junta(request, pk, junta_pk)
        if junta is not None and junta.esta_convocada:
            return redirect("juntas:detalle_junta", pk=pk, junta_pk=junta.pk)
        iniciales = [
            {
                "titulo": p.titulo,
                "descripcion": p.descripcion,
                "mayoria": p.mayoria,
                "excepcion_ausentes": not p.computa_ausentes,
            }
            for p in (junta.puntos.all() if junta else [])
        ]
        return self._pintar(
            request,
            comunidad,
            junta,
            FormularioJunta(instance=junta),
            PuntosFormSet(initial=iniciales, prefix="puntos"),
        )

    def post(self, request, pk, junta_pk=None):
        comunidad = _comunidad_del_usuario(request, pk)
        junta = self._junta(request, pk, junta_pk)
        if junta is not None and junta.esta_convocada:
            return redirect("juntas:detalle_junta", pk=pk, junta_pk=junta.pk)
        formulario = FormularioJunta(request.POST, instance=junta)
        puntos = PuntosFormSet(request.POST, prefix="puntos")
        if not (formulario.is_valid() and puntos.is_valid()):
            return self._pintar(request, comunidad, junta, formulario, puntos)
        with transaction.atomic():
            junta = formulario.save(commit=False)
            junta.comunidad = comunidad
            junta.save()
            # Borrador: se rehace el orden del día entero con lo que llega del formulario.
            junta.puntos.all().delete()
            filas = [
                f.cleaned_data
                for f in puntos.forms
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            PuntoOrden.objects.bulk_create(
                PuntoOrden(
                    junta=junta,
                    orden=n,
                    titulo=fila["titulo"],
                    descripcion=fila["descripcion"],
                    mayoria=fila["mayoria"],
                    computa_ausentes=not fila["excepcion_ausentes"],
                )
                for n, fila in enumerate(filas, start=1)
            )
        messages.success(request, "Junta guardada (borrador). Revísala y convócala.")
        return redirect("juntas:detalle_junta", pk=pk, junta_pk=junta.pk)


class DetalleJunta(FiltradoPorDespachoMixin, DetailView):
    """Una junta: datos, orden del día y, en borrador, la vista previa de la convocatoria;
    convocada, a quién se citó. De otro despacho, o con otra comunidad en la URL: 404."""

    model = Junta
    campo_despacho = CAMPO_DESPACHO[Junta]
    pk_url_kwarg = "junta_pk"
    context_object_name = "junta"
    template_name = "juntas/detalle_junta.html"

    def get_queryset(self):
        return super().get_queryset().filter(comunidad_id=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        junta = self.object
        usuario = self.request.user
        contexto = {"comunidad": junta.comunidad, "puntos": junta.puntos.all()}
        if junta.esta_convocada:
            citaciones = list(junta.citaciones.select_related("propietario"))
            contexto |= {
                "citaciones": citaciones,
                "sin_email": [c for c in citaciones if not c.email],
                "morosos": [c for c in citaciones if c.moroso],
                "texto": texto_convocatoria(
                    junta, [c.propietario.nombre for c in citaciones if c.moroso]
                ),
            }
        else:
            hoy = timezone.localdate()
            contexto |= {
                "texto": texto_convocatoria(junta, list(morosos_al_convocar(junta, hoy).values())),
                "hoy": hoy,
                "fecha_minima": fecha_minima_ordinaria(hoy) if junta.es_ordinaria else None,
                "puede_editar": usuario.has_perm("juntas.change_junta"),
                "puede_convocar": usuario.has_perm("juntas.add_citacion"),
            }
        return super().get_context_data(**contexto, **kwargs)


class ConvocarJunta(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST: convoca la junta (citaciones + emails) y vuelve al detalle (PRG)."""

    permission_required = "juntas.add_citacion"
    http_method_names = ["post"]

    def post(self, request, pk, junta_pk):
        junta = _junta_del_usuario(request, pk, junta_pk)
        formulario = FormularioConvocar(request.POST)
        if not formulario.is_valid():
            messages.error(request, "Indica la fecha de la citación.")
            return redirect("juntas:detalle_junta", pk=pk, junta_pk=junta_pk)
        try:
            resultado = convocar(junta, formulario.cleaned_data["citacion"])
        except ConvocatoriaInvalida as error:
            messages.error(request, str(error))
        else:
            messages.success(
                request,
                f"Junta convocada: {len(resultado.enviadas)} emails enviados.",
            )
            if resultado.sin_email:
                nombres = ", ".join(c.propietario.nombre for c in resultado.sin_email)
                messages.warning(
                    request,
                    f"Sin email, cítalos por otro medio (domicilio o tablón, art. 9 LPH): "
                    f"{nombres}.",
                )
        return redirect("juntas:detalle_junta", pk=pk, junta_pk=junta_pk)

"""T4.3 — Páginas de la celebración de la junta: iniciar, votar, R-VOT-01, cerrar el acta,
notificar a los ausentes y sus discrepancias (R-MAY-05), y el borrador del acta.

Todas las acciones son POST y vuelven a la página de la celebración (PRG con mensajes). La
junta se busca siempre filtrando por el despacho del usuario: de otro despacho, 404.
"""

from datetime import datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .celebracion import (
    CelebracionInvalida,
    DatosAsistencia,
    cambiar_impugnacion,
    cerrar_acta,
    iniciar_junta,
    notificar_ausentes,
    registrar_discrepancia,
    registrar_votos,
    resultado,
    texto_acta,
    votantes_de,
)
from .forms import FORMATO_FECHA_HORA
from .models import ActaCerrada, Asistente, Celebracion, PuntoOrden, VotoEmitido
from .views import _junta_del_usuario


def _volver(pk, junta_pk):
    return redirect("juntas:celebracion", pk=pk, junta_pk=junta_pk)


def _celebracion(junta) -> Celebracion:
    celebracion = Celebracion.objects.filter(junta=junta).first()
    if celebracion is None:
        raise CelebracionInvalida("La junta todavía no se ha iniciado.")
    return celebracion


class FormularioInicio(forms.Form):
    presidente = forms.CharField(max_length=200)
    secretario = forms.CharField(max_length=200)
    inicio = forms.DateTimeField(input_formats=[FORMATO_FECHA_HORA])


class FormularioFecha(forms.Form):
    fecha = forms.DateField()


class CelebracionJunta(LoginRequiredMixin, View):
    """GET: sin iniciar, el formulario de asistencia; iniciada, asistentes, votos y
    resultados de cada punto."""

    template_name = "juntas/celebracion.html"

    def get(self, request, pk, junta_pk):
        junta = _junta_del_usuario(request, pk, junta_pk)
        usuario = request.user
        celebracion = Celebracion.objects.filter(junta=junta).first()
        hoy = timezone.localdate()
        contexto = {"comunidad": junta.comunidad, "junta": junta, "celebracion": celebracion}
        if celebracion is None:
            if not junta.esta_convocada:
                messages.info(request, "Convoca antes la junta.")
                return redirect("juntas:detalle_junta", pk=pk, junta_pk=junta_pk)
            contexto |= {
                "votantes": votantes_de(junta, hoy),
                "asistencias": Asistente.Asistencia.choices,
                "inicio": timezone.localtime(max(timezone.now(), junta.primera_convocatoria)),
                "puede_iniciar": usuario.has_perm("juntas.add_celebracion"),
            }
        else:
            asistentes = list(celebracion.asistentes.select_related("propietario"))
            votan = [a for a in asistentes if a.asiste and not a.privado_de_voto]
            puntos = []
            for punto in junta.puntos.all():
                votos = dict(punto.votos.values_list("asistente_id", "sentido"))
                filas = [(a, votos.get(a.pk, "")) for a in votan]
                discrepan = punto.discrepancias.select_related("asistente__propietario")
                puntos.append((punto, resultado(punto, hoy), filas, discrepan))
            contexto |= {
                "asistentes": asistentes,
                "ausentes": [a for a in asistentes if not a.asiste],
                "puntos": puntos,
                "sentidos": VotoEmitido.Sentido.choices,
                "hoy": hoy,
                "puede_votar": usuario.has_perm("juntas.add_votoemitido")
                and not celebracion.esta_cerrada,
                "puede_discrepar": usuario.has_perm("juntas.add_votoemitido"),
                "puede_cerrar": usuario.has_perm("juntas.change_celebracion"),
            }
        return render(request, self.template_name, contexto)


class IniciarJunta(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "juntas.add_celebracion"
    http_method_names = ["post"]

    def post(self, request, pk, junta_pk):
        junta = _junta_del_usuario(request, pk, junta_pk)
        formulario = FormularioInicio(request.POST)
        if not formulario.is_valid():
            messages.error(request, "Indica presidente, secretario y hora de inicio.")
            return _volver(pk, junta_pk)
        datos = formulario.cleaned_data
        asistencias = {}
        for propietario, _cuota in votantes_de(junta, timezone.localdate(datos["inicio"])):
            asistencia = request.POST.get(f"asistencia-{propietario.pk}", "ausente")
            if asistencia not in Asistente.Asistencia.values:
                asistencia = Asistente.Asistencia.AUSENTE
            asistencias[propietario.pk] = DatosAsistencia(
                asistencia, request.POST.get(f"representante-{propietario.pk}", "")
            )
        try:
            celebracion = iniciar_junta(
                junta,
                inicio=datos["inicio"],
                presidente=datos["presidente"],
                secretario=datos["secretario"],
                asistencias=asistencias,
            )
        except CelebracionInvalida as error:
            messages.error(request, str(error))
        else:
            privados = sum(1 for a in celebracion.asistentes.all() if a.privado_de_voto)
            texto = (
                f"Junta iniciada en {celebracion.get_convocatoria_display().lower()} convocatoria."
            )
            if privados:
                texto += f" {privados} propietarios sin derecho a voto por deudas (R-VOT-01)."
            messages.success(request, texto)
        return _volver(pk, junta_pk)


class _AccionCelebracion(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Base de los POST sobre una junta iniciada: errores de negocio como mensajes."""

    http_method_names = ["post"]

    def post(self, request, pk, junta_pk, **kwargs):
        junta = _junta_del_usuario(request, pk, junta_pk)
        try:
            celebracion = _celebracion(junta)
            mensaje = self.accion(request, junta, celebracion, **kwargs)
        except (CelebracionInvalida, ActaCerrada) as error:
            messages.error(request, " ".join(getattr(error, "messages", [str(error)])))
        else:
            messages.success(request, mensaje)
        return _volver(pk, junta_pk)


class VotarPunto(_AccionCelebracion):
    permission_required = "juntas.add_votoemitido"

    def accion(self, request, junta, celebracion, punto_pk):
        punto = get_object_or_404(PuntoOrden, junta=junta, pk=punto_pk)
        votos = {}
        for asistente in celebracion.asistentes.all():
            sentido = request.POST.get(f"voto-{asistente.pk}", "")
            if sentido:
                votos[asistente.pk] = sentido
        registrar_votos(punto, votos)
        return f"Votos del punto {punto.orden} guardados."


class CambiarImpugnacion(_AccionCelebracion):
    permission_required = "juntas.add_votoemitido"

    def accion(self, request, junta, celebracion, asistente_pk):
        asistente = get_object_or_404(Asistente, celebracion=celebracion, pk=asistente_pk)
        impugnada = request.POST.get("impugnada") == "1"
        cambiar_impugnacion(asistente, impugnada)
        if impugnada:
            return f"{asistente.propietario}: deuda impugnada o consignada, puede votar."
        return f"{asistente.propietario}: sin derecho a voto (R-VOT-01)."


class CerrarActa(_AccionCelebracion):
    permission_required = "juntas.change_celebracion"

    def accion(self, request, junta, celebracion):
        cerrar_acta(celebracion)
        return "Acta cerrada: los votos ya no se pueden cambiar."


class NotificarAusentes(_AccionCelebracion):
    permission_required = "juntas.change_celebracion"

    def accion(self, request, junta, celebracion):
        formulario = FormularioFecha(request.POST)
        if not formulario.is_valid():
            raise CelebracionInvalida("Indica la fecha de la notificación.")
        notificar_ausentes(celebracion, formulario.cleaned_data["fecha"])
        return "Notificación a los ausentes anotada: tienen 30 días para discrepar (R-MAY-05)."


class RegistrarDiscrepancia(_AccionCelebracion):
    permission_required = "juntas.add_votoemitido"

    def accion(self, request, junta, celebracion, punto_pk):
        punto = get_object_or_404(PuntoOrden, junta=junta, pk=punto_pk)
        formulario = FormularioFecha(request.POST)
        asistente = celebracion.asistentes.filter(pk=request.POST.get("asistente") or 0).first()
        if asistente is None or not formulario.is_valid():
            raise CelebracionInvalida("Elige el ausente e indica la fecha de su discrepancia.")
        registrar_discrepancia(punto, asistente, formulario.cleaned_data["fecha"])
        return f"Discrepancia de {asistente.propietario} registrada (punto {punto.orden})."


class ActaJunta(LoginRequiredMixin, View):
    """GET: el borrador del acta en una página; con ?descargar=1, como fichero de texto."""

    def get(self, request, pk, junta_pk):
        junta = _junta_del_usuario(request, pk, junta_pk)
        celebracion = get_object_or_404(Celebracion, junta=junta)
        texto = texto_acta(celebracion, timezone.localdate())
        if request.GET.get("descargar"):
            respuesta = HttpResponse(texto, content_type="text/plain; charset=utf-8")
            fecha = datetime.strftime(timezone.localtime(celebracion.iniciada_en), "%Y%m%d")
            respuesta["Content-Disposition"] = f'attachment; filename="acta-{junta.pk}-{fecha}.txt"'
            return respuesta
        return render(
            request,
            "juntas/acta.html",
            {
                "comunidad": junta.comunidad,
                "junta": junta,
                "celebracion": celebracion,
                "texto": texto,
            },
        )

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, TemplateView

from core.aislamiento import FiltradoPorDespachoMixin, filtrar_por_despacho
from fincas.models import CAMPO_DESPACHO, Comunidad, Propietario, Titularidad
from juntas.celebracion import CelebracionInvalida, resultado, texto_acta
from juntas.convocatoria import texto_convocatoria

from .consultas import es_vecino, juntas_de, recibos_de, resumen_de
from .discrepancias import discrepar_online, estado_ausente, puntos_discrepables
from .invitacion import InvitacionInvalida, invitar


def inicio(request):
    """Tras entrar: el despacho, a sus comunidades; un vecino, a su portal."""
    if not request.user.is_authenticated:
        return redirect("login")
    if request.user.despacho_id is None and es_vecino(request.user):
        return redirect("portal:inicio")
    return redirect("fincas:lista_comunidades")


class VecinoMixin(LoginRequiredMixin):
    """Exige sesión y que el usuario sea propietario (tenga alguna ficha enlazada). Todo lo
    que se muestra sale de `portal.consultas`, que filtra por el usuario."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not es_vecino(request.user):
            raise Http404("No tienes acceso al portal del vecino.")
        return super().dispatch(request, *args, **kwargs)


class InicioPortal(VecinoMixin, TemplateView):
    template_name = "portal/inicio.html"

    def get_context_data(self, **kwargs):
        hoy = timezone.localdate()
        return super().get_context_data(
            resumen=resumen_de(self.request.user, hoy, timezone.now()), hoy=hoy, **kwargs
        )


class RecibosPortal(VecinoMixin, TemplateView):
    template_name = "portal/recibos.html"

    def get_context_data(self, **kwargs):
        hoy = timezone.localdate()
        return super().get_context_data(recibos=recibos_de(self.request.user), hoy=hoy, **kwargs)


class JuntasPortal(VecinoMixin, TemplateView):
    template_name = "portal/juntas.html"

    def get_context_data(self, **kwargs):
        juntas = juntas_de(self.request.user, timezone.localdate())
        return super().get_context_data(juntas=juntas, **kwargs)


class JuntaPortal(VecinoMixin, DetailView):
    """Convocatoria y, si el acta está cerrada, el acta. Solo de juntas de sus comunidades
    actuales: cualquier otra da 404."""

    template_name = "portal/junta.html"
    context_object_name = "junta"

    def get_queryset(self):
        return juntas_de(self.request.user, timezone.localdate())

    def get_context_data(self, **kwargs):
        junta = self.object
        morosos = [
            c.propietario.nombre
            for c in junta.citaciones.filter(moroso=True).select_related("propietario")
        ]
        celebracion = getattr(junta, "celebracion", None)
        hoy = timezone.localdate()
        acta = None
        if celebracion is not None and celebracion.esta_cerrada:
            acta = texto_acta(celebracion, hoy)
        # T5.2: si no fue a la junta, puede comunicar su discrepancia (R-MAY-05).
        ausente = estado_ausente(self.request.user, junta, hoy) if celebracion else None
        acuerdos = []
        if ausente is not None and ausente.notificados is not None:
            acuerdos = [
                (punto, resultado(punto, hoy), ausente.discrepancias.get(punto.pk))
                for punto in puntos_discrepables(junta)
            ]
        return super().get_context_data(
            convocatoria=texto_convocatoria(junta, morosos),
            acta=acta,
            ausente=ausente,
            acuerdos=acuerdos,
            **kwargs,
        )


class DiscreparPortal(VecinoMixin, View):
    """POST: el vecino ausente comunica su discrepancia con un acuerdo (R-MAY-05)."""

    http_method_names = ["post"]

    def post(self, request, pk, punto_pk):
        junta = get_object_or_404(juntas_de(request.user, timezone.localdate()), pk=pk)
        punto = get_object_or_404(junta.puntos, pk=punto_pk)
        try:
            discrepancia = discrepar_online(request.user, punto)
        except CelebracionInvalida as error:
            messages.error(request, str(error))
        else:
            hora = timezone.localtime(discrepancia.recibida_en)
            messages.success(
                request,
                f"Discrepancia recibida el {hora:%d/%m/%Y a las %H:%M}. Te hemos enviado un "
                "justificante por email.",
            )
        return redirect("portal:junta", pk=pk)


# --- Para el despacho: dar acceso a los vecinos --------------------------------------------


class VecinosComunidad(FiltradoPorDespachoMixin, DetailView):
    """Titulares actuales de la comunidad y si tienen acceso al portal."""

    model = Comunidad
    campo_despacho = CAMPO_DESPACHO[Comunidad]
    context_object_name = "comunidad"
    template_name = "portal/vecinos_comunidad.html"

    def get_context_data(self, **kwargs):
        hoy = timezone.localdate()
        titularidades = (
            Titularidad.objects.vigentes(hoy)
            .filter(inmueble__comunidad=self.object)
            .select_related("propietario__usuario", "inmueble")
            .order_by("propietario__nombre", "inmueble__referencia")
        )
        por_propietario: dict[int, tuple[Propietario, list[str]]] = {}
        for t in titularidades:
            fila = por_propietario.setdefault(t.propietario_id, (t.propietario, []))
            fila[1].append(t.inmueble.referencia)
        return super().get_context_data(
            vecinos=list(por_propietario.values()),
            puede_invitar=self.request.user.has_perm("core.add_usuario"),
            **kwargs,
        )


class InvitarVecino(LoginRequiredMixin, PermissionRequiredMixin, View):
    """POST: invita al portal a un propietario de la comunidad (del despacho del usuario)."""

    permission_required = "core.add_usuario"
    http_method_names = ["post"]

    def post(self, request, pk, propietario_pk):
        comunidades = filtrar_por_despacho(Comunidad.objects.all(), request.user)
        comunidad = get_object_or_404(comunidades, pk=pk)
        hoy = timezone.localdate()
        propietario = get_object_or_404(
            Propietario.objects.filter(
                pk__in=Titularidad.objects.vigentes(hoy)
                .filter(inmueble__comunidad=comunidad)
                .values("propietario_id")
            ),
            pk=propietario_pk,
        )
        try:
            invitar(propietario, request.build_absolute_uri("/"))
        except InvitacionInvalida as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Invitación enviada a {propietario} ({propietario.email}).")
        return redirect(reverse("portal:vecinos_comunidad", args=[pk]))

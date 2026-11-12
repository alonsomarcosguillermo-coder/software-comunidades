"""T4.1 — Convocar una junta. `convocar` es la ÚNICA forma prevista de pasar una junta de
borrador a convocada.

Qué hace, en una transacción:
1. Comprueba los plazos (R-JUN-02, R-JUN-03, puros en `juntas.servicios`) y que haya orden
   del día.
2. Cita a los titulares de los inmuebles de la comunidad el día de la citación.
3. Art. 16.2 LPH: la convocatoria lleva la relación de propietarios que no están al
   corriente de pago, con la advertencia de que no podrán votar (R-VOT-01). Los morosos
   salen de `cobros.deudas.informe_morosos_de` (T3.4).
4. Envía la convocatoria por email a quien tenga email. A los demás hay que citarlos por
   otro medio (art. 9 LPH: domicilio comunicado, el propio piso o el tablón de anuncios).

Los emails nunca se escriben en logs (CLAUDE.md: datos personales).
"""

from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from cobros.deudas import informe_morosos_de
from fincas.models import Propietario, Titularidad

from .models import Citacion, Junta
from .servicios import ConvocatoriaInvalida, comprobar_antelacion, comprobar_segunda_convocatoria


@dataclass(frozen=True)
class ResultadoConvocatoria:
    junta: Junta
    enviadas: list[Citacion]
    sin_email: list[Citacion]  # hay que citarlos por otro medio


def citados(junta: Junta, fecha: date) -> list[Propietario]:
    """Titulares (también cotitulares) de algún inmueble de la comunidad en `fecha`."""
    ids = Titularidad.objects.vigentes(fecha).filter(inmueble__comunidad=junta.comunidad)
    return list(
        Propietario.objects.filter(pk__in=ids.values("propietario_id")).order_by("nombre", "pk")
    )


def morosos_al_convocar(junta: Junta, fecha: date) -> dict[int, str]:
    """Relación de morosos de la convocatoria (art. 16.2 LPH): {id: nombre}, por nombre."""
    morosos = informe_morosos_de(junta.comunidad, fecha).morosos
    return {m.propietario_id: m.propietario for m in sorted(morosos, key=lambda m: m.propietario)}


def texto_convocatoria(junta: Junta, morosos: list[str]) -> str:
    """El texto de la convocatoria (email, y vista previa antes de convocar)."""
    return render_to_string(
        "juntas/convocatoria.txt",
        {"junta": junta, "puntos": junta.puntos.all(), "morosos": morosos},
    )


@transaction.atomic
def convocar(junta: Junta, citacion: date, *, ahora=None) -> ResultadoConvocatoria:
    junta = Junta.objects.select_for_update().select_related("comunidad").get(pk=junta.pk)
    if junta.esta_convocada:
        raise ConvocatoriaInvalida("La junta ya está convocada.")
    if not junta.puntos.exists():
        raise ConvocatoriaInvalida("La junta no tiene orden del día.")
    primera = timezone.localtime(junta.primera_convocatoria)
    comprobar_antelacion(ordinaria=junta.es_ordinaria, citacion=citacion, junta=primera.date())
    comprobar_segunda_convocatoria(
        primera.replace(tzinfo=None),
        timezone.localtime(junta.segunda_convocatoria).replace(tzinfo=None)
        if junta.segunda_convocatoria
        else None,
    )
    propietarios = citados(junta, citacion)
    if not propietarios:
        raise ConvocatoriaInvalida("La comunidad no tiene propietarios a los que citar.")

    morosos = morosos_al_convocar(junta, citacion)
    junta.convocada_el = citacion
    junta.save()
    citaciones = Citacion.objects.bulk_create(
        Citacion(junta=junta, propietario=p, email=p.email, moroso=p.pk in morosos)
        for p in propietarios
    )

    texto = texto_convocatoria(junta, list(morosos.values()))
    asunto = f"Convocatoria de junta {junta.get_tipo_display().lower()} · {junta.comunidad}"
    con_email = [c for c in citaciones if c.email]
    mensajes = [
        EmailMessage(asunto, texto, settings.DEFAULT_FROM_EMAIL, [c.email]) for c in con_email
    ]
    # Un email por propietario (no uno con todos en copia: no se comparten direcciones).
    get_connection().send_messages(mensajes)
    enviada = ahora or timezone.now()
    for c in con_email:
        c.enviada_en = enviada
    Citacion.objects.bulk_update(con_email, ["enviada_en"])
    return ResultadoConvocatoria(
        junta=junta, enviadas=con_email, sin_email=[c for c in citaciones if not c.email]
    )

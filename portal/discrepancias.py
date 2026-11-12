"""T5.2 — Discrepancia online del ausente (R-MAY-05, art. 17.8 LPH; ADR 017).

La LPH no regula el voto a distancia (R-JUN-04), pero sí que los ausentes, una vez
notificados los acuerdos, comuniquen su discrepancia en 30 días naturales "por cualquier medio
que permita tener constancia de la recepción". El portal es ese medio: se guarda la fecha y
hora de recepción y se envía un acuse por email al vecino.

La validación de fondo (es ausente, está notificado, está en plazo, no repetida) es la de
`juntas.celebracion.registrar_discrepancia`; aquí solo se comprueba que el usuario es quien
dice ser y que el punto admite discrepancia.
"""

from dataclasses import dataclass
from datetime import date, datetime

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from juntas.celebracion import CelebracionInvalida, registrar_discrepancia
from juntas.models import Asistente, Celebracion, Discrepancia, Junta, PuntoOrden
from juntas.servicios import PLAZO_DISCREPANCIA

from .consultas import propietarios_de


def asistente_ausente_de(usuario, junta: Junta) -> Asistente | None:
    """El votante ausente que es este usuario en la junta (si lo es)."""
    return (
        Asistente.objects.filter(
            celebracion__junta=junta,
            propietario__in=propietarios_de(usuario),
            asistencia=Asistente.Asistencia.AUSENTE,
        )
        .select_related("celebracion", "propietario")
        .first()
    )


def puntos_discrepables(junta: Junta):
    """Los acuerdos en los que la discrepancia de un ausente cuenta (R-MAY-05)."""
    return junta.puntos.exclude(mayoria=PuntoOrden.Mayoria.SIN_VOTACION).filter(
        computa_ausentes=True
    )


@dataclass(frozen=True)
class EstadoAusente:
    asistente: Asistente
    notificados: date | None
    hasta: date | None  # último día para discrepar
    en_plazo: bool
    discrepancias: dict[int, Discrepancia]  # por punto


def estado_ausente(usuario, junta: Junta, hoy: date) -> EstadoAusente | None:
    """Qué puede hacer este vecino como ausente en la junta. None si no fue ausente."""
    asistente = asistente_ausente_de(usuario, junta)
    if asistente is None:
        return None
    notificados = asistente.celebracion.ausentes_notificados_el
    hasta = notificados + PLAZO_DISCREPANCIA if notificados else None
    return EstadoAusente(
        asistente=asistente,
        notificados=notificados,
        hasta=hasta,
        en_plazo=hasta is not None and notificados <= hoy <= hasta,
        discrepancias={d.punto_id: d for d in asistente.discrepancias.all()},
    )


@transaction.atomic
def discrepar_online(usuario, punto: PuntoOrden, *, ahora: datetime | None = None) -> Discrepancia:
    """El vecino ausente comunica desde el portal que no está de acuerdo con `punto`."""
    ahora = ahora or timezone.now()
    asistente = asistente_ausente_de(usuario, punto.junta)
    if asistente is None:
        raise CelebracionInvalida(
            "Solo puede comunicar su discrepancia quien no asistió a la junta."
        )
    if not puntos_discrepables(punto.junta).filter(pk=punto.pk).exists():
        raise CelebracionInvalida("En este punto la discrepancia de los ausentes no cuenta.")
    # Bloquea la celebración: dos clics seguidos no crean dos discrepancias.
    Celebracion.objects.select_for_update().get(pk=asistente.celebracion_id)
    discrepancia = registrar_discrepancia(
        punto,
        asistente,
        timezone.localdate(ahora),
        canal=Discrepancia.Canal.PORTAL,
        recibida_en=ahora,
    )
    if usuario.email:
        texto = render_to_string(
            "portal/email_acuse_discrepancia.txt",
            {"discrepancia": discrepancia, "punto": punto, "junta": punto.junta},
        )
        send_mail(
            f"Recibida tu discrepancia · {punto.junta.comunidad}",
            texto,
            settings.DEFAULT_FROM_EMAIL,
            [usuario.email],
        )
    return discrepancia

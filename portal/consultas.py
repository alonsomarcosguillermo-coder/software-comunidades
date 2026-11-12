"""T5.1 — Lo que ve un vecino en el portal. Todas las consultas parten del USUARIO.

Regla del portal (ADR 016): un vecino ve solo lo suyo, nunca lo de otros vecinos.
- Sus recibos: los que ha pagado o debe como pagador (de cualquier fecha, también de
  inmuebles que ya vendió: son sus recibos).
- Su deuda: sus recibos vencidos e impagados hoy (cálculo de T3.4).
- Documentos de la comunidad (convocatorias y actas): solo de las comunidades donde es
  titular HOY. Quien vendió deja de verlos.

Un usuario del despacho que además fuera propietario vería aquí solo su parte de vecino.
"""

from dataclasses import dataclass
from datetime import date

from django.db.models import QuerySet

from cobros.deudas import recibos_deuda
from cobros.models import Recibo
from cobros.morosidad import EstadoDeuda, estado_deuda
from fincas.models import Comunidad, Propietario, Titularidad
from juntas.models import Junta


def propietarios_de(usuario) -> QuerySet[Propietario]:
    """Las fichas de propietario de este usuario (una por despacho)."""
    if not usuario.is_authenticated:
        return Propietario.objects.none()
    return Propietario.objects.filter(usuario=usuario)


def es_vecino(usuario) -> bool:
    return propietarios_de(usuario).exists()


def titularidades_de(usuario, hoy: date) -> QuerySet[Titularidad]:
    return (
        Titularidad.objects.vigentes(hoy)
        .filter(propietario__in=propietarios_de(usuario))
        .select_related("inmueble__comunidad")
        .order_by("inmueble__comunidad__nombre", "inmueble__referencia")
    )


def comunidades_de(usuario, hoy: date) -> QuerySet[Comunidad]:
    """Comunidades donde el usuario es titular de algún inmueble hoy."""
    ids = titularidades_de(usuario, hoy).values("inmueble__comunidad_id")
    return Comunidad.objects.filter(pk__in=ids).order_by("nombre")


def recibos_de(usuario) -> QuerySet[Recibo]:
    return (
        Recibo.objects.filter(propietario__in=propietarios_de(usuario))
        .select_related("comunidad", "inmueble", "cobro", "remesa")
        .prefetch_related("devoluciones")
        .order_by("-vencimiento", "-numero")
    )


def deuda_de(usuario, hoy: date) -> EstadoDeuda:
    """Recibos vencidos e impagados hoy (la deuda) y los pendientes que aún no vencen."""
    return estado_deuda(recibos_deuda(recibos_de(usuario)), hoy)


def juntas_de(usuario, hoy: date) -> QuerySet[Junta]:
    """Juntas convocadas de sus comunidades actuales, de la más reciente a la más antigua."""
    return (
        Junta.objects.filter(comunidad__in=comunidades_de(usuario, hoy), convocada_el__isnull=False)
        .select_related("comunidad", "celebracion")
        .order_by("-primera_convocatoria")
    )


@dataclass(frozen=True)
class Resumen:
    titularidades: list[Titularidad]
    deuda: EstadoDeuda
    proximas_juntas: list[Junta]


def resumen_de(usuario, hoy: date, ahora) -> Resumen:
    juntas = juntas_de(usuario, hoy)
    return Resumen(
        titularidades=list(titularidades_de(usuario, hoy)),
        deuda=deuda_de(usuario, hoy),
        proximas_juntas=list(
            juntas.filter(primera_convocatoria__gte=ahora).order_by("primera_convocatoria")
        ),
    )
